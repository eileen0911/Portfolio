import httpx
from openai import APITimeoutError, OpenAI, OpenAIError

from chat_api.config import Settings
from chat_api.generation.errors import GenerationError


class InferenceClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model_checked = False
        self._client = OpenAI(
            base_url=settings.inference_base_url,
            api_key=settings.inference_api_key or "EMPTY",
            timeout=settings.inference_timeout_seconds,
            http_client=httpx.Client(trust_env=settings.use_env_proxy),
        )

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.validate_model_available()

        try:
            response = self._client.chat.completions.create(
                model=self._settings.inference_model,
                messages=messages,
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            answer = response.choices[0].message.content or ""
        except APITimeoutError as exc:
            raise GenerationError("inference_timeout", "Inference API timed out", exc) from exc
        except (OpenAIError, IndexError, AttributeError, TypeError) as exc:
            raise GenerationError("inference_unavailable", "Inference API request failed", exc) from exc

        if not answer.strip():
            raise GenerationError("inference_empty_response", "Inference API returned an empty answer")
        return answer

    def stream_complete(self, messages: list[dict[str, str]]):
        self.validate_model_available()

        try:
            stream = self._client.chat.completions.create(
                model=self._settings.inference_model,
                messages=messages,
                temperature=0,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            emitted = False
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) or ""
                if not content:
                    continue
                emitted = True
                yield content
            if not emitted:
                raise GenerationError("inference_empty_response", "Inference API returned an empty answer")
        except GenerationError:
            raise
        except APITimeoutError as exc:
            raise GenerationError("inference_timeout", "Inference API timed out", exc) from exc
        except (OpenAIError, IndexError, AttributeError, TypeError) as exc:
            raise GenerationError("inference_unavailable", "Inference API request failed", exc) from exc

    def validate_model_available(self) -> None:
        if not self._settings.inference_model:
            raise GenerationError("inference_model_missing", "INFERENCE_MODEL is required before calling inference")
        if self._model_checked:
            return

        try:
            response = self._client.models.list()
            available_models = {model.id for model in response.data if getattr(model, "id", None)}
        except APITimeoutError as exc:
            raise GenerationError("inference_timeout", "Inference model endpoint timed out", exc) from exc
        except (OpenAIError, AttributeError, TypeError) as exc:
            raise GenerationError("inference_unavailable", "Inference model endpoint request failed", exc) from exc

        if self._settings.inference_model not in available_models:
            raise GenerationError(
                "inference_model_unavailable",
                f"Configured INFERENCE_MODEL is not available from inference endpoint: {self._settings.inference_model}",
            )

        self._model_checked = True
