import json
from pathlib import Path

from chat_api.faq.models import FAQFlowConfig
from chat_api.faq.validator import validate_faq_config


DEFAULT_FAQ_CONFIG_PATH = Path(__file__).resolve().parent / "default_flow.zh-TW.json"


def load_faq_config(path: Path = DEFAULT_FAQ_CONFIG_PATH) -> FAQFlowConfig:
    with path.open("r", encoding="utf-8") as file:
        config = FAQFlowConfig.model_validate(json.load(file))
    validate_faq_config(config)
    return config
