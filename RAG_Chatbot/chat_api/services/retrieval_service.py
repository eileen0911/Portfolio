from chat_api.models import ChatIntake, Source
from chat_api.retrieval.base import Retriever


class RetrievalService:
    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def retrieve(self, question: str, intake: ChatIntake | None = None) -> list[Source]:
        return self._retriever.retrieve(question, intake)
