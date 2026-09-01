import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from time import perf_counter

from chat_api.generation.answer_generator import AnswerGenerator
from chat_api.generation.errors import GenerationError
from chat_api.generation.handoff_context import FAQHandoffContext
from chat_api.models import ChatRequest, ChatResponse, RouteDecision, Source, TimingMs
from chat_api.routing.flow_router import RESET_TRIGGERS, FlowRouter
from chat_api.routing.slot_state import ConversationState
from chat_api.retrieval.errors import RetrievalError
from chat_api.services.ai_session_store import SQLiteAISessionStore
from chat_api.services.retrieval_service import RetrievalService


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

SseEmitter = Callable[[str, dict | list], str]
JsonableResponse = Callable[[ChatResponse], dict]
ChatErrorLogger = Callable[[ChatResponse, RouteDecision, str | None], None]


@dataclass
class AIChatResult:
    decision: RouteDecision
    response: ChatResponse | None = None
    events: Iterator[str] | None = None
    error_code: str | None = None


class AIChatService:
    def __init__(
        self,
        *,
        router: FlowRouter,
        retrieval_service: RetrievalService,
        answer_generator: AnswerGenerator,
        ai_session_store: SQLiteAISessionStore | None = None,
        history_max_turns: int = 10,
        history_max_chars: int = 12000,
    ) -> None:
        self.router = router
        self.retrieval_service = retrieval_service
        self.answer_generator = answer_generator
        self.ai_session_store = ai_session_store
        self.history_max_turns = history_max_turns
        self.history_max_chars = history_max_chars

    def handle_message(
        self,
        request: ChatRequest,
        state: ConversationState,
        *,
        response_id: str,
        session_id: str,
        started: float,
        sse: SseEmitter,
        jsonable: JsonableResponse,
        log_complete: ChatErrorLogger,
    ) -> AIChatResult:
        message = request.message or ""
        routing_started = perf_counter()
        decision = self.router.route(message, state, request.intake)
        routing_ms = (perf_counter() - routing_started) * 1000

        if decision.route == "non_rag":
            if self._is_reset_message(message):
                self._mark_existing_session_inactive(session_id)
            return AIChatResult(
                decision=decision,
                response=ChatResponse(
                    response_id=response_id,
                    session_id=session_id,
                    status="needs_input" if decision.next_action == "ask_slot" else "ok",
                    answer=decision.answer or "",
                    next_action=decision.next_action,
                    required_slots=decision.required_slots,
                    timing_ms=TimingMs(routing=routing_ms, total=(perf_counter() - started) * 1000),
                ),
            )

        retrieval_started = perf_counter()
        try:
            timeout_response = self._session_timeout_response_if_needed(
                response_id=response_id,
                session_id=session_id,
                state=state,
                started=started,
                routing_ms=routing_ms,
            )
            if timeout_response is not None:
                return AIChatResult(
                    decision=decision,
                    error_code="session_timeout",
                    response=timeout_response,
                )
            sources = self.retrieval_service.retrieve(message, request.intake)
        except RetrievalError as exc:
            retrieval_ms = (perf_counter() - retrieval_started) * 1000
            logger.warning(
                "chat_rag_retrieval_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": exc.code,
                    "retrieval_ms": retrieval_ms,
                },
            )
            return AIChatResult(
                decision=decision,
                error_code=exc.code,
                response=self._retrieval_error_response(
                    response_id=response_id,
                    session_id=session_id,
                    started=started,
                    routing_ms=routing_ms,
                    retrieval_ms=retrieval_ms,
                ),
            )
        except Exception:
            retrieval_ms = (perf_counter() - retrieval_started) * 1000
            logger.exception(
                "chat_rag_retrieval_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": "retrieval_failed",
                    "retrieval_ms": retrieval_ms,
                },
            )
            return AIChatResult(
                decision=decision,
                error_code="retrieval_failed",
                response=self._retrieval_error_response(
                    response_id=response_id,
                    session_id=session_id,
                    started=started,
                    routing_ms=routing_ms,
                    retrieval_ms=retrieval_ms,
                ),
            )

        retrieval_ms = (perf_counter() - retrieval_started) * 1000
        if not sources:
            return AIChatResult(
                decision=decision,
                response=ChatResponse(
                    response_id=response_id,
                    session_id=session_id,
                    status="no_result",
                    answer="目前沒有找到足夠相關的資料，請換個問法或前往 Contact Page 與我們聯絡。",
                    next_action="none",
                    sources=[],
                    retrieval_version="dense-v1",
                    timing_ms=TimingMs(
                        routing=routing_ms,
                        retrieval=retrieval_ms,
                        total=(perf_counter() - started) * 1000,
                    ),
                ),
            )

        active_messages = self._active_messages(session_id)
        handoff_context = self._handoff_context_for_next_prompt(state, active_messages)
        history = self._history_for_prompt(active_messages)

        if request.stream:
            return AIChatResult(
                decision=decision,
                events=self._stream_rag_events(
                    message=message,
                    request=request,
                    response_id=response_id,
                    session_id=session_id,
                    started=started,
                    routing_ms=routing_ms,
                    retrieval_ms=retrieval_ms,
                    sources=sources,
                    handoff_context=handoff_context,
                    history=history,
                    sse=sse,
                    jsonable=jsonable,
                    log_complete=log_complete,
                    decision=decision,
                ),
            )

        inference_started = perf_counter()
        try:
            answer = self.answer_generator.generate(message, sources, request.intake, handoff_context, history)
        except GenerationError as exc:
            inference_ms = (perf_counter() - inference_started) * 1000
            logger.warning(
                "chat_rag_generation_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": exc.code,
                    "inference_ms": inference_ms,
                },
            )
            return AIChatResult(
                decision=decision,
                error_code=exc.code,
                response=self._generation_error_response(
                    response_id=response_id,
                    session_id=session_id,
                    started=started,
                    routing_ms=routing_ms,
                    retrieval_ms=retrieval_ms,
                    inference_ms=inference_ms,
                    sources=sources,
                ),
            )
        except Exception:
            inference_ms = (perf_counter() - inference_started) * 1000
            logger.exception(
                "chat_rag_generation_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": "generation_failed",
                    "inference_ms": inference_ms,
                },
            )
            return AIChatResult(
                decision=decision,
                error_code="generation_failed",
                response=self._generation_error_response(
                    response_id=response_id,
                    session_id=session_id,
                    started=started,
                    routing_ms=routing_ms,
                    retrieval_ms=retrieval_ms,
                    inference_ms=inference_ms,
                    sources=sources,
                ),
            )

        inference_ms = (perf_counter() - inference_started) * 1000
        self._persist_successful_turn(session_id, message, answer, handoff_context, response_id=response_id)
        return AIChatResult(
            decision=decision,
            response=ChatResponse(
                response_id=response_id,
                session_id=session_id,
                status="ok",
                answer=answer,
                next_action="answer",
                sources=sources,
                retrieval_version=f"dense-v1+{self.answer_generator.prompt_version}",
                timing_ms=TimingMs(
                    routing=routing_ms,
                    retrieval=retrieval_ms,
                    inference=inference_ms,
                    total=(perf_counter() - started) * 1000,
                ),
            ),
        )

    def _stream_rag_events(
        self,
        *,
        message: str,
        request: ChatRequest,
        response_id: str,
        session_id: str,
        started: float,
        routing_ms: float,
        retrieval_ms: float,
        sources: list[Source],
        handoff_context: FAQHandoffContext | None,
        history: list[dict[str, str]],
        sse: SseEmitter,
        jsonable: JsonableResponse,
        log_complete: ChatErrorLogger,
        decision: RouteDecision,
        handoff_occurred: bool = False,
        previous_selection: list[dict[str, str]] | None = None,
        flow_version: str | None = None,
    ) -> Iterator[str]:
        base_payload = {
            "response_id": response_id,
            "session_id": session_id,
            "status": "ok",
            "mode": "ai",
            "next_action": "answer",
            "required_slots": [],
            "input_enabled": True,
            "handoff_occurred": handoff_occurred,
            "previous_selection": previous_selection or [],
            "flow_version": flow_version,
            "retrieval_version": f"dense-v1+{self.answer_generator.prompt_version}",
            "timing_ms": {"routing": routing_ms, "retrieval": retrieval_ms},
        }
        yield sse("metadata", base_payload)
        yield sse("sources", [source.model_dump(mode="json") for source in sources])

        inference_started = perf_counter()
        answer_parts: list[str] = []
        try:
            for delta in self.answer_generator.generate_stream(
                message,
                sources,
                request.intake,
                handoff_context,
                history,
            ):
                answer_parts.append(delta)
                yield sse("delta", {"content": delta})
        except GenerationError as exc:
            inference_ms = (perf_counter() - inference_started) * 1000
            logger.warning(
                "chat_rag_generation_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": exc.code,
                    "inference_ms": inference_ms,
                },
            )
            response = self._generation_error_response(
                response_id=response_id,
                session_id=session_id,
                started=started,
                routing_ms=routing_ms,
                retrieval_ms=retrieval_ms,
                inference_ms=inference_ms,
                sources=sources,
            )
            if handoff_occurred:
                response.handoff_occurred = True
                response.previous_selection = previous_selection or []
                response.flow_version = flow_version
            yield sse("error", {"code": exc.code, "message": response.answer})
            yield sse("final", jsonable(response))
            yield sse("done", {})
            log_complete(response, decision, exc.code)
            return
        except Exception:
            inference_ms = (perf_counter() - inference_started) * 1000
            logger.exception(
                "chat_rag_generation_error",
                extra={
                    "response_id": response_id,
                    "session_id": session_id,
                    "error_code": "generation_failed",
                    "inference_ms": inference_ms,
                },
            )
            response = self._generation_error_response(
                response_id=response_id,
                session_id=session_id,
                started=started,
                routing_ms=routing_ms,
                retrieval_ms=retrieval_ms,
                inference_ms=inference_ms,
                sources=sources,
            )
            if handoff_occurred:
                response.handoff_occurred = True
                response.previous_selection = previous_selection or []
                response.flow_version = flow_version
            yield sse("error", {"code": "generation_failed", "message": response.answer})
            yield sse("final", jsonable(response))
            yield sse("done", {})
            log_complete(response, decision, "generation_failed")
            return

        answer = "".join(answer_parts)
        inference_ms = (perf_counter() - inference_started) * 1000
        self._persist_successful_turn(session_id, message, answer, handoff_context, response_id=response_id)
        response = ChatResponse(
            response_id=response_id,
            session_id=session_id,
            status="ok",
            answer=answer,
            mode="ai",
            next_action="answer",
            input_enabled=True,
            handoff_occurred=handoff_occurred,
            previous_selection=previous_selection or [],
            sources=sources,
            flow_version=flow_version,
            retrieval_version=f"dense-v1+{self.answer_generator.prompt_version}",
            timing_ms=TimingMs(
                routing=routing_ms,
                retrieval=retrieval_ms,
                inference=inference_ms,
                total=(perf_counter() - started) * 1000,
            ),
        )
        yield sse("final", jsonable(response))
        yield sse("done", {})
        log_complete(response, decision, None)

    def _persist_successful_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        handoff_context: FAQHandoffContext | None,
        *,
        response_id: str | None = None,
    ) -> None:
        if self.ai_session_store is None:
            return
        try:
            if not self.ai_session_store.list_messages(session_id):
                seed_context = self._format_seed_context(handoff_context)
                self.ai_session_store.append_message(session_id, "seed", seed_context, response_id=response_id)
            self.ai_session_store.append_message(session_id, "user", user_message, response_id=response_id)
            self.ai_session_store.append_message(session_id, "assistant", assistant_message, response_id=response_id)
        except Exception:
            logger.exception(
                "chat_ai_session_store_error",
                extra={"session_id": session_id, "error_code": "ai_session_persist_failed"},
            )

    def _format_seed_context(self, handoff_context: FAQHandoffContext | None) -> str:
        if handoff_context is None:
            return "no FAQ handoff context"
        return handoff_context.format_for_prompt()

    def _active_messages(self, session_id: str) -> list[object] | None:
        if self.ai_session_store is None:
            return []
        try:
            return list(self.ai_session_store.list_messages(session_id))
        except Exception:
            logger.exception(
                "chat_ai_session_store_error",
                extra={"session_id": session_id, "error_code": "ai_session_history_read_failed"},
            )
            return None

    def _handoff_context_for_next_prompt(
        self,
        state: ConversationState,
        active_messages: list[object] | None,
    ) -> FAQHandoffContext | None:
        if state.current_flow != "ai":
            return None
        if active_messages is None:
            return None
        if active_messages:
            return None
        return FAQHandoffContext.from_previous_selection(state.previous_selection)

    def _history_for_prompt(self, active_messages: list[object] | None) -> list[dict[str, str]]:
        if active_messages is None or self.history_max_turns <= 0:
            return []

        parsed: list[dict[str, str]] = []
        for message in active_messages:
            role, text = self._history_role_and_content(message)
            if role is not None and text:
                parsed.append({"role": role, "content": text})

        max_messages = self.history_max_turns * 2
        recent = parsed[-max_messages:] if max_messages else []
        selected_reversed: list[dict[str, str]] = []
        used_chars = 0
        for message in reversed(recent):
            cost = len(message["role"]) + len(message["content"]) + 3
            if selected_reversed and used_chars + cost > self.history_max_chars:
                break
            if not selected_reversed and cost > self.history_max_chars:
                selected_reversed.append(
                    {"role": message["role"], "content": message["content"][: self.history_max_chars].rstrip()}
                )
                break
            selected_reversed.append(message)
            used_chars += cost
        return list(reversed(selected_reversed))

    def _history_role_and_content(self, message: object) -> tuple[str | None, str]:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role in {"user", "assistant"} and isinstance(content, str):
            return role, content.strip()
        return self._parse_history_message(str(getattr(message, "message_content", message)))

    def _parse_history_message(self, content: str) -> tuple[str | None, str]:
        if content.startswith("user: "):
            return "user", content.removeprefix("user: ").strip()
        if content.startswith("assistant: "):
            return "assistant", content.removeprefix("assistant: ").strip()
        return None, ""

    def _is_reset_message(self, message: str) -> bool:
        text = message.strip()
        lowered = text.lower()
        return any(trigger in lowered if trigger.isascii() else trigger in text for trigger in RESET_TRIGGERS)

    def _mark_existing_session_inactive(self, session_id: str) -> None:
        if self.ai_session_store is None:
            return
        try:
            if hasattr(self.ai_session_store, "has_session") and not self.ai_session_store.has_session(session_id):
                return
            self.ai_session_store.mark_session_inactive(session_id)
        except Exception:
            logger.exception(
                "chat_ai_session_store_error",
                extra={"session_id": session_id, "error_code": "ai_session_reset_failed"},
            )

    def _session_timeout_response_if_needed(
        self,
        *,
        response_id: str,
        session_id: str,
        state: ConversationState,
        started: float,
        routing_ms: float,
    ) -> ChatResponse | None:
        if self.ai_session_store is None or state.current_flow != "ai":
            return None
        try:
            has_session = self.ai_session_store.has_session(session_id)
            is_active = self.ai_session_store.is_session_active(session_id)
        except AttributeError:
            return None
        except Exception:
            logger.exception(
                "chat_ai_session_store_error",
                extra={"session_id": session_id, "error_code": "ai_session_status_check_failed"},
            )
            return None
        if not has_session or is_active:
            return None
        return ChatResponse(
            response_id=response_id,
            session_id=session_id,
            status="session_timeout",
            error_code="session_timeout",
            answer="Session timeout. Please start a new session.",
            mode="system",
            next_action="none",
            input_enabled=False,
            timing_ms=TimingMs(routing=routing_ms, total=(perf_counter() - started) * 1000),
        )

    def _retrieval_error_response(
        self,
        *,
        response_id: str,
        session_id: str,
        started: float,
        routing_ms: float,
        retrieval_ms: float,
    ) -> ChatResponse:
        return ChatResponse(
            response_id=response_id,
            session_id=session_id,
            status="service_error",
            answer="知識查詢服務暫時無法回應，請稍後再試或前往 Contact Page 與我們聯絡。",
            next_action="none",
            retrieval_version="dense-v1",
            timing_ms=TimingMs(
                routing=routing_ms,
                retrieval=retrieval_ms,
                total=(perf_counter() - started) * 1000,
            ),
        )

    def _generation_error_response(
        self,
        *,
        response_id: str,
        session_id: str,
        started: float,
        routing_ms: float,
        retrieval_ms: float,
        inference_ms: float,
        sources: list[Source],
    ) -> ChatResponse:
        return ChatResponse(
            response_id=response_id,
            session_id=session_id,
            status="service_error",
            answer="已找到相關資料，但回答生成服務暫時無法回應，請稍後再試或前往 Contact Page 與我們聯絡。",
            next_action="none",
            sources=sources,
            retrieval_version="dense-v1",
            timing_ms=TimingMs(
                routing=routing_ms,
                retrieval=retrieval_ms,
                inference=inference_ms,
                total=(perf_counter() - started) * 1000,
            ),
        )
