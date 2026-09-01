from chat_api.generation.handoff_context import FAQHandoffContext
from chat_api.models import ChatIntake, Source


PROMPT_VERSION = "grounded-v1"
MAX_SOURCE_CHARS = 3500
MAX_CONTEXT_CHARS = 8000

SYSTEM_PROMPT = """You are a polite and helpful Demo Knowledge Base Assistant.

Strict grounding rules:
1. Answer only from the provided <source> tags.
2. Do not use pre-trained knowledge for factual claims.
3. Answer the user's exact question first; do not replace it with a broad product summary unless the user asked for a summary.
4. If the sources contain multiple product-line values for the requested field, list each value separately and do not average or invent a range.
5. If the sources do not contain enough relevant information, say that the information is not available and direct the user to the official support contact page.
6. If a source contains a policy, refusal, NON-DISCLOSURE statement, or "not available" statement, convey that policy directly.
7. Reply in the same language as the user.
"""


class PromptBuilder:
    @property
    def version(self) -> str:
        return PROMPT_VERSION

    def build_messages(
        self,
        question: str,
        sources: list[Source],
        intake: ChatIntake | None = None,
        handoff_context: FAQHandoffContext | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        context = self._build_context(sources)
        user_parts = []
        if intake:
            user_parts.append(self._format_intake(intake))
        if handoff_context:
            user_parts.append(handoff_context.format_for_prompt())
        if history:
            user_parts.append(self._format_history(history))
        user_parts.append(context)
        user_parts.append(f"User question:\n{question}")
        user_parts.append("Answer the user's exact question using only the retrieved context above.")
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(part for part in user_parts if part)},
        ]

    def _build_context(self, sources: list[Source]) -> str:
        parts = ["[Retrieved Knowledge Base Context]"]
        used_chars = 0
        seen: set[tuple[int | str | None, int | None, str]] = set()

        for source_id, source in enumerate(sources, start=1):
            key = (source.page_id, source.chunk_index, source.title)
            if key in seen:
                continue
            seen.add(key)

            text = self._truncate(source.text, MAX_SOURCE_CHARS)
            block = (
                f'<source id="{source_id}" title="{source.title}" score="{source.score:.4f}">\n'
                f"{text}\n"
                "</source>"
            )
            if used_chars + len(block) > MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            used_chars += len(block)

        parts.append("[End of Context - Answer ONLY based on the sources above. Do NOT use pre-trained knowledge.]")
        return "\n".join(parts)

    def _format_intake(self, intake: ChatIntake) -> str:
        items = [
            ("service", intake.service),
            ("country", intake.country),
            ("product_type", intake.product_type),
            ("intent", intake.intent),
        ]
        values = [f"{key}: {value}" for key, value in items if value]
        return "User intake:\n" + "\n".join(values) if values else ""

    def _format_history(self, history: list[dict[str, str]]) -> str:
        lines = [
            "Recent conversation history:",
            "Use this only to resolve references in the current question. Do not treat it as retrieved knowledge-base evidence.",
        ]
        for message in history:
            role = message.get("role", "").strip()
            content = message.get("content", "").strip()
            if role in {"user", "assistant"} and content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n[truncated]"

