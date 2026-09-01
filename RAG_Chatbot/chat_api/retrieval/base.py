from abc import ABC, abstractmethod

from chat_api.models import ChatIntake, Source


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, question: str, intake: ChatIntake | None = None) -> list[Source]:
        raise NotImplementedError
