import re
from typing import Any

from chat_api.models import Source


MODEL_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:RX\s*)?(\d{4})\s*(XTX|GRE|XT)(?![A-Z0-9])"
    r"|(?<![A-Z0-9])(?:RX\s*)?(\d{4})(?!\s*(?:XTX|GRE|XT))(?![A-Z0-9])"
    r"|(?<![A-Z0-9])(R\d{4})(?![A-Z0-9])",
    re.IGNORECASE,
)

SUPPORT_OR_PROCEDURE_PATTERN = re.compile(
    r"\b(?:bios|vbios|firmware|driver|install|installation|setup|procedure|step|steps|boot|post)\b"
    r"|\u5b89\u88dd|\u6b65\u9a5f|\u9a45\u52d5|\u97cc\u9ad4|\u958b\u6a5f|\u986f\u793a\u7570\u5e38|\u7121\u986f\u793a|\u9ed1\u5c4f",
    re.IGNORECASE,
)


def extract_product_models(text: str) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for match in MODEL_PATTERN.finditer(text):
        if match.group(4):
            model = match.group(4).upper()
        elif match.group(3):
            model = f"RX {match.group(3)}"
        else:
            suffix = match.group(2).upper() if match.group(2) else ""
            model = f"RX {match.group(1)}{f' {suffix}' if suffix else ''}"
        if model not in seen:
            seen.add(model)
            models.append(model)
    return models


def should_apply_product_rerank(question: str, intent: str | None) -> bool:
    if intent != "product_spec":
        return False
    return SUPPORT_OR_PROCEDURE_PATTERN.search(question) is None


def filter_exact_product_sources(
    question: str,
    sources: list[Source],
    intent: str | None = None,
) -> list[Source]:
    if not should_apply_product_rerank(question, intent):
        return sources

    query_models = set(extract_product_models(question))
    if not query_models:
        return sources

    matched = [source for source in sources if query_models.intersection(_source_models(source))]
    return matched or sources


def exact_product_page_ids(
    question: str,
    sources: list[Source],
    intent: str | None = None,
) -> list[int | str]:
    if not should_apply_product_rerank(question, intent):
        return []

    query_models = set(extract_product_models(question))
    if not query_models:
        return []

    page_ids: list[int | str] = []
    seen: set[str] = set()
    for source in sources:
        if source.page_id is None or not query_models.intersection(_source_models(source)):
            continue
        key = str(source.page_id)
        if key not in seen:
            seen.add(key)
            page_ids.append(source.page_id)
    return page_ids


def _source_models(source: Source) -> set[str]:
    values = [source.title]
    values.extend(_tag_values(source.tags))
    return set(extract_product_models("\n".join(value for value in values if value)))


def _tag_values(tags: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        for value in tag.values():
            if value is not None:
                values.append(str(value))
    return values
