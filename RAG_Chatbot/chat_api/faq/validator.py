from collections import deque

from chat_api.faq.errors import FAQValidationError
from chat_api.faq.models import FAQFlowConfig, FAQNode, FAQOption


ALLOWED_SLOT_KEYS = {"country", "product_type", "intent", "rma_action"}
TERMINAL_ACTIONS = {"handoff_ai", "contact_page", "external_url", "reset"}


def validate_faq_config(config: FAQFlowConfig) -> None:
    if config.start_node not in config.nodes:
        raise FAQValidationError(f"start_node does not exist: {config.start_node}")

    for key, node in config.nodes.items():
        _validate_node_key(key, node)
        _validate_node_options(config, node)
        _validate_slot_updates(node)

    _validate_reachability(config)
    _validate_acyclic(config)


def _validate_node_key(key: str, node: FAQNode) -> None:
    if node.id != key:
        raise FAQValidationError(f"node id must match nodes map key: {key} != {node.id}")


def _validate_node_options(config: FAQFlowConfig, node: FAQNode) -> None:
    option_ids: set[str] = set()
    for option in node.options:
        if option.id in option_ids:
            raise FAQValidationError(f"duplicate option id in node {node.id}: {option.id}")
        option_ids.add(option.id)
        _validate_option(config, node, option)

    if node.node_type == "faq" and not node.options:
        raise FAQValidationError(f"faq node must define options: {node.id}")
    if node.node_type == "terminal" and node.options:
        raise FAQValidationError(f"terminal node must not define options: {node.id}")
    if node.node_type == "ai_handoff" and node.options:
        raise FAQValidationError(f"ai_handoff node must not define options: {node.id}")


def _validate_option(config: FAQFlowConfig, node: FAQNode, option: FAQOption) -> None:
    if option.action in {"next_node", "set_slot"}:
        if not option.next_node:
            raise FAQValidationError(f"{option.action} option requires next_node: {node.id}.{option.id}")
        if option.next_node not in config.nodes:
            raise FAQValidationError(f"next_node does not exist: {node.id}.{option.id} -> {option.next_node}")

    if option.action == "set_slot":
        if option.slot not in ALLOWED_SLOT_KEYS or not option.value:
            raise FAQValidationError(f"set_slot option requires allowed slot and value: {node.id}.{option.id}")

    if option.action == "handoff_ai" and option.next_node:
        raise FAQValidationError(f"handoff_ai option must not define next_node: {node.id}.{option.id}")

    if option.action in {"contact_page", "external_url"} and not option.url_key:
        raise FAQValidationError(f"{option.action} option requires url_key: {node.id}.{option.id}")


def _validate_slot_updates(node: FAQNode) -> None:
    for update in node.slot_updates:
        if update.slot not in ALLOWED_SLOT_KEYS:
            raise FAQValidationError(f"slot_updates contains unsupported slot: {node.id}.{update.slot}")


def _validate_reachability(config: FAQFlowConfig) -> None:
    reachable = set()
    queue: deque[str] = deque([config.start_node])

    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        node = config.nodes[node_id]
        for option in node.options:
            if option.next_node:
                queue.append(option.next_node)

    unreachable = set(config.nodes) - reachable
    if unreachable:
        raise FAQValidationError(f"unreachable node(s): {', '.join(sorted(unreachable))}")


def _validate_acyclic(config: FAQFlowConfig) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise FAQValidationError(f"cycle detected at node: {node_id}")
        if node_id in visited:
            return

        visiting.add(node_id)
        for option in config.nodes[node_id].options:
            if option.next_node:
                visit(option.next_node)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(config.start_node)
