from chat_api.clients.inference import InferenceClient
from chat_api.generation.handoff_context import FAQHandoffContext
from chat_api.generation.prompt_builder import PromptBuilder
from chat_api.models import ChatIntake, Source


class AnswerGenerator:
    def __init__(self, inference_client: InferenceClient, prompt_builder: PromptBuilder) -> None:
        self._inference_client = inference_client
        self._prompt_builder = prompt_builder

    @property
    def prompt_version(self) -> str:
        return self._prompt_builder.version

    def generate(
        self,
        question: str,
        sources: list[Source],
        intake: ChatIntake | None = None,
        handoff_context: FAQHandoffContext | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        messages = self._prompt_builder.build_messages(question, sources, intake, handoff_context, history)
        return self._inference_client.complete(messages)

    def generate_stream(
        self,
        question: str,
        sources: list[Source],
        intake: ChatIntake | None = None,
        handoff_context: FAQHandoffContext | None = None,
        history: list[dict[str, str]] | None = None,
    ):
        messages = self._prompt_builder.build_messages(question, sources, intake, handoff_context, history)
        yield from self._inference_client.stream_complete(messages)
