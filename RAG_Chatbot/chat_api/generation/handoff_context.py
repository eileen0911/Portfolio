from pydantic import BaseModel, ConfigDict, Field


MAX_HANDOFF_ITEMS = 8
MAX_FIELD_CHARS = 128


class HandoffSelection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slot: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=MAX_FIELD_CHARS)
    label: str | None = Field(default=None, max_length=MAX_FIELD_CHARS)


class FAQHandoffContext(BaseModel):
    selections: list[HandoffSelection] = Field(default_factory=list)

    @classmethod
    def from_previous_selection(cls, previous_selection: list[dict[str, str]]) -> "FAQHandoffContext | None":
        selections: list[HandoffSelection] = []
        for item in previous_selection[:MAX_HANDOFF_ITEMS]:
            try:
                selections.append(HandoffSelection.model_validate(item))
            except Exception:
                continue
        if not selections:
            return None
        return cls(selections=selections)

    def format_for_prompt(self) -> str:
        lines = ["FAQ handoff context:"]
        for selection in self.selections:
            label = selection.label or selection.value
            if label == selection.value:
                lines.append(f"- {selection.slot}: {selection.value}")
            else:
                lines.append(f"- {selection.slot}: {selection.value} ({label})")
        lines.append(
            "Use this only to understand the user's selected support path. "
            "Do not treat it as retrieved knowledge-base evidence."
        )
        return "\n".join(lines)
