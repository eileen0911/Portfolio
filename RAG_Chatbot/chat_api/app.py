import json
import logging
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from chat_api.clients.embedding import EmbeddingClient
from chat_api.clients.inference import InferenceClient
from chat_api.clients.qdrant import QdrantStore
from chat_api.config import get_settings
from chat_api.faq.errors import FAQFlowError
from chat_api.faq.loader import load_faq_config
from chat_api.faq.models import FAQFlowResponse
from chat_api.faq.service import FAQFlowService
from chat_api.generation.answer_generator import AnswerGenerator
from chat_api.generation.prompt_builder import PromptBuilder
from chat_api.models import (
    ChatOption,
    ChatCTA,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    InternalRetrieveRequest,
    InternalRetrieveResponse,
    RouteDecision,
    TimingMs,
)
from chat_api.routing.flow_router import FlowRouter
from chat_api.routing.slot_state import InMemoryConversationStore
from chat_api.retrieval.dense import DenseRetriever
from chat_api.retrieval.errors import RetrievalError
from chat_api.services.ai_chat_service import AIChatService
from chat_api.services.ai_session_store import SQLiteAISessionStore
from chat_api.services.retrieval_service import RetrievalService


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
settings = get_settings()
router = FlowRouter()
faq_service = FAQFlowService(load_faq_config())
conversation_store = InMemoryConversationStore(timeout_seconds=settings.conversation_timeout_seconds)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
retrieval_service = RetrievalService(
    DenseRetriever(
        embedding_client=EmbeddingClient(settings),
        qdrant_store=QdrantStore(settings),
        settings=settings,
    )
)
answer_generator = AnswerGenerator(
    inference_client=InferenceClient(settings),
    prompt_builder=PromptBuilder(),
)
ai_session_store = SQLiteAISessionStore(
    settings.ai_session_db_path,
    idle_timeout_seconds=settings.ai_session_idle_timeout_seconds,
)
ai_chat_service = AIChatService(
    router=router,
    retrieval_service=retrieval_service,
    answer_generator=answer_generator,
    ai_session_store=ai_session_store,
    history_max_turns=settings.ai_history_max_turns,
    history_max_chars=settings.ai_history_max_chars,
)

OFFICIAL_SITE_NAV_CTA_ALLOWLIST = {
    "contact_page": ChatCTA(
        type="official_site_nav",
        label="前往 Contact Me",
        url_key="contact_page",
        nav_key="contact_page",
        path="contact.php",
        target="parent",
    ),
}


def _log_chat_complete(
    response: ChatResponse,
    decision: RouteDecision,
    *,
    error_code: str | None = None,
) -> None:
    logger.info(
        "chat_request_complete",
        extra={
            "response_id": response.response_id,
            "session_id": response.session_id,
            "route": decision.route,
            "route_next_action": decision.next_action,
            "status": response.status,
            "next_action": response.next_action,
            "source_count": len(response.sources),
            "retrieval_version": response.retrieval_version,
            "routing_ms": response.timing_ms.routing,
            "retrieval_ms": response.timing_ms.retrieval,
            "inference_ms": response.timing_ms.inference,
            "total_ms": response.timing_ms.total,
            "error_code": error_code,
        },
    )


def _jsonable(response: ChatResponse) -> dict:
    return response.model_dump(mode="json")


def _sse(event: str, payload: dict | list) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def _stream_headers() -> dict[str, str]:
    return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _mark_ai_session_inactive(session_id: str, *, response_id: str) -> None:
    try:
        if hasattr(ai_session_store, "has_session") and not ai_session_store.has_session(session_id):
            return
        ai_session_store.mark_session_inactive(session_id)
    except Exception:
        logger.exception(
            "chat_ai_session_store_error",
            extra={"response_id": response_id, "session_id": session_id, "error_code": "ai_session_reset_failed"},
        )


def _start_ai_session(session_id: str, *, response_id: str) -> None:
    try:
        if hasattr(ai_session_store, "start_session"):
            ai_session_store.start_session(session_id)
    except Exception:
        logger.exception(
            "chat_ai_session_store_error",
            extra={"response_id": response_id, "session_id": session_id, "error_code": "ai_session_start_failed"},
        )


def _faq_to_chat_response(
    faq_response: FAQFlowResponse,
    *,
    response_id: str,
    session_id: str,
    routing_ms: float,
    total_ms: float,
) -> ChatResponse:
    cta = _faq_cta(faq_response)
    return ChatResponse(
        response_id=response_id,
        session_id=session_id,
        status="ok",
        answer=faq_response.answer,
        mode=faq_response.mode,
        next_action="none" if not faq_response.options else "select_option",
        options=[
            ChatOption(id=option.id, label=option.label)
            for option in faq_response.options
        ],
        flow_version=faq_response.flow_version,
        input_enabled=faq_response.input_enabled,
        handoff_occurred=faq_response.handoff_occurred,
        previous_selection=faq_response.previous_selection,
        cta=cta,
        timing_ms=TimingMs(routing=routing_ms, total=total_ms),
    )


def _faq_cta(faq_response: FAQFlowResponse) -> ChatCTA | None:
    if not settings.chat_cta_enabled or not settings.chat_cta_official_site_nav_enabled:
        return None
    if not faq_response.cta_key:
        return None
    return OFFICIAL_SITE_NAV_CTA_ALLOWLIST.get(faq_response.cta_key)


def _stream_response(response: ChatResponse, decision: RouteDecision, *, error_code: str | None = None) -> StreamingResponse:
    def events() -> Iterator[str]:
        payload = _jsonable(response)
        metadata = {key: value for key, value in payload.items() if key not in {"answer", "sources"}}
        yield _sse("metadata", metadata)
        if response.sources:
            yield _sse("sources", payload["sources"])
        if response.answer:
            yield _sse("delta", {"content": response.answer})
        yield _sse("final", payload)
        yield _sse("done", {})
        _log_chat_complete(response, decision, error_code=error_code)

    return StreamingResponse(events(), media_type="text/event-stream", headers=_stream_headers())


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    if frontend_dir.exists():
        app.mount("/demo/assets", StaticFiles(directory=frontend_dir), name="demo-assets")

        @app.get("/demo", include_in_schema=False)
        def demo() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok", app=settings.app_name, environment=settings.environment)

    @app.post("/v1/chat", response_model=None)
    def chat(request: ChatRequest) -> ChatResponse | StreamingResponse:
        started = perf_counter()
        response_id = str(uuid4())
        session_id = request.session_id or str(uuid4())
        state = conversation_store.get_or_create(session_id)

        routing_started = perf_counter()
        if request.action == "start_faq":
            decision = RouteDecision(route="non_rag", next_action="select_option")
            _mark_ai_session_inactive(session_id, response_id=response_id)
            faq_response = faq_service.start(state)
            conversation_store.save(state)
            routing_ms = (perf_counter() - routing_started) * 1000
            response = _faq_to_chat_response(
                faq_response,
                response_id=response_id,
                session_id=session_id,
                routing_ms=routing_ms,
                total_ms=(perf_counter() - started) * 1000,
            )
            if request.stream:
                return _stream_response(response, decision)
            _log_chat_complete(response, decision)
            return response

        if request.action == "select_option":
            decision = RouteDecision(route="non_rag", next_action="select_option")
            try:
                faq_response = faq_service.select_option(state, request.option_id or "")
            except FAQFlowError:
                logger.warning(
                    "chat_faq_flow_error",
                    extra={
                        "response_id": response_id,
                        "session_id": session_id,
                        "option_id": request.option_id,
                        "current_node": state.current_node,
                    },
                )
                faq_response = faq_service.start(state)
                routing_ms = (perf_counter() - routing_started) * 1000
                response = ChatResponse(
                    response_id=response_id,
                    session_id=session_id,
                    status="needs_input",
                    answer="選項無效，請重新選擇。",
                    mode="faq",
                    next_action="select_option",
                    options=[
                        ChatOption(id=option.id, label=option.label)
                        for option in faq_response.options
                    ],
                    flow_version=faq_response.flow_version,
                    input_enabled=False,
                    previous_selection=faq_response.previous_selection,
                    timing_ms=TimingMs(routing=routing_ms, total=(perf_counter() - started) * 1000),
                )
                conversation_store.save(state)
                if request.stream:
                    return _stream_response(response, decision, error_code="invalid_faq_option")
                _log_chat_complete(response, decision, error_code="invalid_faq_option")
                return response

            conversation_store.save(state)
            routing_ms = (perf_counter() - routing_started) * 1000
            if faq_response.handoff_occurred:
                _start_ai_session(session_id, response_id=response_id)
            response = _faq_to_chat_response(
                faq_response,
                response_id=response_id,
                session_id=session_id,
                routing_ms=routing_ms,
                total_ms=(perf_counter() - started) * 1000,
            )
            if request.stream:
                return _stream_response(response, decision)
            _log_chat_complete(response, decision)
            return response

        ai_chat_service.router = router
        ai_chat_service.retrieval_service = retrieval_service
        ai_chat_service.answer_generator = answer_generator
        ai_chat_service.ai_session_store = ai_session_store
        ai_chat_service.history_max_turns = settings.ai_history_max_turns
        ai_chat_service.history_max_chars = settings.ai_history_max_chars
        result = ai_chat_service.handle_message(
            request,
            state,
            response_id=response_id,
            session_id=session_id,
            started=started,
            sse=_sse,
            jsonable=_jsonable,
            log_complete=lambda response, decision, error_code=None: _log_chat_complete(
                response,
                decision,
                error_code=error_code,
            ),
        )
        conversation_store.save(state)
        if result.events is not None:
            return StreamingResponse(result.events, media_type="text/event-stream", headers=_stream_headers())

        if result.response is None:
            raise RuntimeError("AIChatService returned no response")

        if request.stream:
            return _stream_response(result.response, result.decision, error_code=result.error_code)

        _log_chat_complete(result.response, result.decision, error_code=result.error_code)
        return result.response

    @app.post("/internal/retrieve", response_model=InternalRetrieveResponse)
    def internal_retrieve(request: InternalRetrieveRequest) -> InternalRetrieveResponse:
        try:
            sources = retrieval_service.retrieve(request.question)
        except RetrievalError as exc:
            logger.warning("internal_retrieve_error", extra={"error_code": exc.code})
            return InternalRetrieveResponse(status="service_error", message=exc.code)
        except Exception:
            logger.exception("internal_retrieve_error", extra={"error_code": "retrieval_failed"})
            return InternalRetrieveResponse(status="service_error", message="retrieval_failed")
        return InternalRetrieveResponse(status="ok", sources=sources)

    return app


app = create_app()
