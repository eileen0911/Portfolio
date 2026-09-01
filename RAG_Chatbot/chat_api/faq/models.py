from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FAQNodeType = Literal["faq", "terminal", "ai_handoff", "contact", "external"]
FAQAction = Literal["next_node", "set_slot", "handoff_ai", "contact_page", "external_url", "reset"]
FAQMode = Literal["faq", "ai", "contact", "system"]


class FAQSlotUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=128)


class FAQOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    action: FAQAction
    next_node: str | None = Field(default=None, max_length=128)
    slot: str | None = Field(default=None, max_length=64)
    value: str | None = Field(default=None, max_length=128)
    url_key: str | None = Field(default=None, max_length=64)


class FAQNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    node_type: FAQNodeType
    message: str = Field(min_length=1, max_length=1000)
    options: list[FAQOption] = Field(default_factory=list)
    slot_updates: list[FAQSlotUpdate] = Field(default_factory=list)
    cta_key: str | None = Field(default=None, max_length=64)


class FAQFlowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=16)
    start_node: str = Field(min_length=1, max_length=128)
    nodes: dict[str, FAQNode] = Field(min_length=1)


class FAQResponseOption(BaseModel):
    id: str
    label: str


class FAQFlowResponse(BaseModel):
    mode: FAQMode
    flow_version: str
    node_id: str
    answer: str
    options: list[FAQResponseOption] = Field(default_factory=list)
    input_enabled: bool = False
    handoff_occurred: bool = False
    previous_selection: list[dict[str, str]] = Field(default_factory=list)
    cta_key: str | None = None
