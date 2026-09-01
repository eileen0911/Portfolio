from chat_api.faq.errors import FAQFlowError
from chat_api.faq.models import FAQFlowConfig, FAQFlowResponse, FAQNode, FAQOption, FAQResponseOption
from chat_api.routing.slot_state import ConversationState


class FAQFlowService:
    def __init__(self, config: FAQFlowConfig) -> None:
        self.config = config

    def start(self, state: ConversationState) -> FAQFlowResponse:
        state.reset()
        state.current_flow = "faq"
        return self._enter_node(state, self.config.start_node)

    def select_option(self, state: ConversationState, option_id: str) -> FAQFlowResponse:
        if state.current_flow != "faq" or not state.current_node:
            raise FAQFlowError("select_option requires an active faq session")

        node = self.config.nodes[state.current_node]
        option = next((item for item in node.options if item.id == option_id), None)
        if option is None:
            raise FAQFlowError(f"invalid option_id for node {node.id}: {option_id}")

        if option.action == "reset":
            return self.start(state)
        if option.action == "set_slot":
            self._capture_option_slot(state, option)
            return self._enter_node(state, option.next_node or "")
        if option.action == "next_node":
            return self._enter_node(state, option.next_node or "")
        if option.action == "handoff_ai":
            state.current_flow = "ai"
            state.current_node = None
            return FAQFlowResponse(
                mode="ai",
                flow_version=self.config.version,
                node_id=node.id,
                answer="請描述您的其他問題。",
                input_enabled=True,
                handoff_occurred=True,
                previous_selection=list(state.previous_selection),
            )
        if option.action == "contact_page":
            state.current_flow = "contact"
            state.contact_page = True
            return FAQFlowResponse(
                mode="contact",
                flow_version=self.config.version,
                node_id=node.id,
                answer=node.message,
                input_enabled=False,
                previous_selection=list(state.previous_selection),
            )
        if option.action == "external_url":
            return FAQFlowResponse(
                mode="faq",
                flow_version=self.config.version,
                node_id=node.id,
                answer=node.message,
                input_enabled=False,
                previous_selection=list(state.previous_selection),
            )

        raise FAQFlowError(f"unsupported action: {option.action}")

    def _enter_node(self, state: ConversationState, node_id: str) -> FAQFlowResponse:
        node = self.config.nodes.get(node_id)
        if node is None:
            raise FAQFlowError(f"node does not exist: {node_id}")

        state.current_node = node.id
        for update in node.slot_updates:
            state.slots[update.slot] = update.value
            state.previous_selection.append({
                "slot": update.slot,
                "value": update.value,
                "label": update.label or update.value,
            })

        if node.node_type == "ai_handoff":
            state.current_flow = "ai"
            state.current_node = None
            return FAQFlowResponse(
                mode="ai",
                flow_version=self.config.version,
                node_id=node.id,
                answer=node.message,
                input_enabled=True,
                handoff_occurred=True,
                previous_selection=list(state.previous_selection),
            )

        return FAQFlowResponse(
            mode="faq",
            flow_version=self.config.version,
            node_id=node.id,
            answer=node.message,
            options=self._response_options(node),
            input_enabled=False,
            previous_selection=list(state.previous_selection),
            cta_key=node.cta_key,
        )

    def _capture_option_slot(self, state: ConversationState, option: FAQOption) -> None:
        if not option.slot or option.value is None:
            raise FAQFlowError(f"set_slot option is missing slot or value: {option.id}")

        state.slots[option.slot] = option.value
        state.previous_selection.append({
            "slot": option.slot,
            "value": option.value,
            "label": option.label,
        })

    def _response_options(self, node: FAQNode) -> list[FAQResponseOption]:
        return [FAQResponseOption(id=option.id, label=option.label) for option in node.options]
