from dataclasses import dataclass, field
from collections.abc import Callable
from time import time


DEFAULT_PRODUCT_FLOW_SLOTS = ["country", "product_type"]


@dataclass
class ConversationState:
    session_id: str
    current_flow: str | None = None
    current_node: str | None = None
    slots: dict[str, str] = field(default_factory=dict)
    required_slots: list[str] = field(default_factory=list)
    previous_selection: list[dict[str, str]] = field(default_factory=list)
    contact_page: bool = False
    updated_at: float = field(default_factory=time)

    def touch(self) -> None:
        self.updated_at = time()

    def reset(self) -> None:
        self.current_flow = None
        self.current_node = None
        self.slots.clear()
        self.required_slots.clear()
        self.previous_selection.clear()
        self.contact_page = False


class InMemoryConversationStore:
    def __init__(self, timeout_seconds: float = 1800.0, now: Callable[[], float] = time) -> None:
        self._timeout_seconds = timeout_seconds
        self._now = now
        self._states: dict[str, ConversationState] = {}

    def get_or_create(self, session_id: str) -> ConversationState:
        state = self._states.get(session_id)
        if state is None or self._is_expired(state):
            self._states[session_id] = ConversationState(session_id=session_id, updated_at=self._now())
        return self._states[session_id]

    def save(self, state: ConversationState) -> None:
        state.updated_at = self._now()
        self._states[state.session_id] = state

    def _is_expired(self, state: ConversationState) -> bool:
        if self._timeout_seconds <= 0:
            return False
        return self._now() - state.updated_at > self._timeout_seconds
