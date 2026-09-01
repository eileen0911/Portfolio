from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ChatStatus = Literal["ok", "needs_input", "no_result", "service_error", "session_timeout"]
NextAction = Literal["answer", "ask_slot", "contact_page", "select_option", "none"]
RouteType = Literal["non_rag", "rag"]
IntakeService = Literal["product", "knowledge", "contact"]
ChatAction = Literal["message", "start_faq", "select_option"]
ChatMode = Literal["faq", "ai", "contact", "system"]
CTAType = Literal["external_url", "official_site_nav"]
CTATarget = Literal["_blank", "parent"]


class ChatIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: IntakeService
    country: str | None = Field(default=None, max_length=64)
    product_type: str | None = Field(default=None, max_length=64)
    intent: str | None = Field(default=None, max_length=64)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ChatAction = "message"
    message: str | None = Field(default=None, max_length=4000)
    option_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default="zh-TW", max_length=16)
    intake: ChatIntake | None = None
    stream: bool = False

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChatRequest":
        if self.action == "message" and not (self.message and self.message.strip()):
            raise ValueError("message is required when action=message")
        if self.action == "select_option" and not (self.option_id and self.option_id.strip()):
            raise ValueError("option_id is required when action=select_option")
        return self


class Source(BaseModel):
    page_id: int | str | None = None
    title: str
    chunk_index: int | None = None
    score: float
    text: str
    source_category: str | None = None
    book_name: str | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)


class TimingMs(BaseModel):
    routing: float | None = None
    retrieval: float | None = None
    inference: float | None = None
    total: float | None = None


class ChatOption(BaseModel):
    id: str
    label: str


class ChatCTA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CTAType
    label: str = Field(min_length=1, max_length=128)
    url_key: str = Field(min_length=1, max_length=64)
    url: str | None = Field(default=None, max_length=500)
    nav_key: str | None = Field(default=None, max_length=64)
    path: str | None = Field(default=None, max_length=256)
    target: CTATarget


class ChatResponse(BaseModel):
    response_id: str
    session_id: str
    status: ChatStatus
    error_code: str | None = None
    answer: str
    mode: ChatMode = "ai"
    next_action: NextAction = "none"
    required_slots: list[str] = Field(default_factory=list)
    options: list[ChatOption] = Field(default_factory=list)
    flow_version: str | None = None
    input_enabled: bool = True
    handoff_occurred: bool = False
    previous_selection: list[dict[str, str]] = Field(default_factory=list)
    cta: ChatCTA | None = None
    sources: list[Source] = Field(default_factory=list)
    retrieval_version: str | None = None
    timing_ms: TimingMs = Field(default_factory=TimingMs)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    environment: str


class InternalRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


class InternalRetrieveResponse(BaseModel):
    status: Literal["ok", "service_error"]
    sources: list[Source] = Field(default_factory=list)
    message: str | None = None


class RouteDecision(BaseModel):
    route: RouteType
    next_action: NextAction
    required_slots: list[str] = Field(default_factory=list)
    answer: str | None = None
