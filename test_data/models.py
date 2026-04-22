"""
Ожидаемый список моделей в селекторе модели (композер → иконка модели).

Актуален для стенда https://wmt1.acm-ai.ru/ (проверено через MCP 2026-04-22).
Если на стенде модели добавят/уберут — правим здесь, тест сам подтянет.
"""

DIALOG_MODELS = [
    "GPT-5.2",
    "Claude Opus 4.6",
    "Claude Sonnet 4.6",
    "Gemini 3.1 Pro Preview",
    "Grok 4.1 Fast",
    "DeepSeek V3.2",
    "GigaChat 2 Pro",
    "Kimi K2.5",
    "YandexGPT 5.1 Pro",
]

IMAGE_MODELS = [
    "Nano Banana Pro (Google/Gemini)",
    "GPT Image 1.5 (OpenAI)",
    "Seedream 4.5 (ByteDance)",
]

ALL_MODELS = DIALOG_MODELS + IMAGE_MODELS

SECTION_HEADERS = ("Диалоговые модели", "Изображения")
