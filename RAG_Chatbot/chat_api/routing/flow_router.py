from chat_api.models import ChatIntake, RouteDecision
from chat_api.routing.slot_state import ConversationState, DEFAULT_PRODUCT_FLOW_SLOTS


RESET_TRIGGERS = ("重來", "重新開始", "取消", "reset", "restart", "start over")
CONTACT_TRIGGERS = ("聯絡我們", "聯絡窗口", "聯絡頁", "contact", "contact page")
INTAKE_BOOTSTRAP_MESSAGES = ("開始對話", "start", "start session")
CONTACT_PAGE_MESSAGE = "目前此問題不由 AI Chat service 處理，請前往 Contact Page 與我們聯絡。"


class FlowRouter:
    def route(self, message: str, state: ConversationState, intake: ChatIntake | None = None) -> RouteDecision:
        text = message.strip()
        lowered = text.lower()

        if self._has_trigger(text, lowered, RESET_TRIGGERS):
            state.reset()
            return RouteDecision(
                route="non_rag",
                next_action="none",
                answer="已重設對話，請重新輸入您想查詢的內容。",
            )

        if intake is not None:
            return self._route_with_intake(text, lowered, state, intake)

        if self._has_trigger(text, lowered, CONTACT_TRIGGERS):
            state.reset()
            state.contact_page = True
            return RouteDecision(
                route="non_rag",
                next_action="contact_page",
                answer=CONTACT_PAGE_MESSAGE,
            )

        return RouteDecision(route="rag", next_action="answer")

    def _route_with_intake(
        self,
        text: str,
        lowered: str,
        state: ConversationState,
        intake: ChatIntake,
    ) -> RouteDecision:
        if intake.service == "contact":
            state.reset()
            state.contact_page = True
            return RouteDecision(
                route="non_rag",
                next_action="contact_page",
                answer=CONTACT_PAGE_MESSAGE,
            )

        if intake.service == "knowledge":
            return RouteDecision(route="rag", next_action="answer")

        state.current_flow = "product_inquiry"
        state.required_slots = list(DEFAULT_PRODUCT_FLOW_SLOTS)
        self._capture_intake_slots(intake, state)

        if state.required_slots:
            return self._ask_next_slot(state)

        if self._is_intake_only_message(text, lowered, intake):
            return self._complete_product_flow(state)

        return RouteDecision(route="rag", next_action="answer")

    def _ask_next_slot(self, state: ConversationState) -> RouteDecision:
        slot = state.required_slots[0]
        prompts = {
            "country": "請問您的國家或地區是？",
            "product_type": "請問您想查詢的產品別是？",
        }
        return RouteDecision(
            route="non_rag",
            next_action="ask_slot",
            required_slots=list(state.required_slots),
            answer=prompts.get(slot, "請補充必要資訊。"),
        )

    def _capture_intake_slots(self, intake: ChatIntake, state: ConversationState) -> None:
        if intake.country:
            state.slots["country"] = intake.country
            self._remove_required_slot("country", state)
        if intake.product_type:
            state.slots["product_type"] = intake.product_type
            self._remove_required_slot("product_type", state)
        if intake.intent:
            state.slots["intent"] = intake.intent

    def _remove_required_slot(self, slot: str, state: ConversationState) -> None:
        state.required_slots = [item for item in state.required_slots if item != slot]

    def _complete_product_flow(self, state: ConversationState) -> RouteDecision:
        return RouteDecision(
            route="non_rag",
            next_action="none",
            answer="已收到，接下來請輸入您的具體問題。",
        )

    def _has_trigger(self, text: str, lowered: str, triggers: tuple[str, ...]) -> bool:
        return any(trigger in lowered if trigger.isascii() else trigger in text for trigger in triggers)

    def _is_intake_only_message(self, text: str, lowered: str, intake: ChatIntake) -> bool:
        return text in INTAKE_BOOTSTRAP_MESSAGES or lowered in INTAKE_BOOTSTRAP_MESSAGES
