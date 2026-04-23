"""
Параметризованный smoke на КАЖДУЮ диалоговую модель:

1. Логинимся (фикстура `authenticated_page`).
2. В композере открываем селектор моделей и выбираем целевую модель.
3. Фейкером генерируем запрос из 3 слов и отправляем его.
4. Дожидаемся непустого ответа ассистента.
5. Проверяем, что:
   - ответ не пустой,
   - в ответе нет типовых маркеров ошибки,
   - под ответом в `.response-actions-container` стоит имя ИМЕННО той
     модели, которую мы выбрали.

Источник правды «кто ответил» — кнопка `.model-picker-trigger` в
`.response-actions-container` (слева от иконочных кнопок).

Селекторы подтверждены живым обследованием UI через MCP-Playwright
на `wmt1.acm-ai.ru` 2026-04-23.

Image-модели (Nano Banana / GPT Image / Seedream) в этот параметр
не входят: у них другой пайп ответа (генерация картинки), ждём там
дольше и проверяются они отдельным набором — см. отдельный issue.
"""

import allure
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from pages.main_page import MainPage
from test_data.models import DIALOG_MODELS


# Faker с дефолтной (англ.) локалью — слова короткие и гарантированно
# читаются любой моделью, включая YandexGPT / GigaChat.
fake = Faker()


def _three_word_prompt() -> str:
    """Ровно три слова, разделённые пробелом. Никакой пунктуации — чтобы
    промпт был детерминированно из трёх слов."""
    return " ".join(fake.words(nb=3))


# Типовые текстовые маркеры, которые фронт/бэк могут показать вместо
# корректного ответа. Если что-то из этого попадает в тело ответа —
# считаем, что модель фактически не ответила.
ERROR_MARKERS = (
    "произошла ошибка",
    "что-то пошло не так",
    "сервис временно недоступен",
    "ошибка подключения",
    "ошибка сервера",
    "error:",
    "rate limit",
    "timeout",
)


@allure.epic("Модели")
@allure.feature("Каждая модель отвечает на запрос")
@pytest.mark.real_backend
@pytest.mark.models
@pytest.mark.chat
class TestModelAnswers:

    @pytest.mark.parametrize("model_name", DIALOG_MODELS, ids=DIALOG_MODELS)
    @allure.title("{model_name} отвечает на запрос из 3 слов (faker)")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_model_answers_three_word_prompt(
        self, authenticated_page: Page, model_name: str
    ):
        main = MainPage(authenticated_page)

        with allure.step("1. Открыть главную и закрыть онбординг-попап"):
            main.open()
            main.dismiss_group_chats_popup()
            main.should_be_loaded()
            main.should_show_chat_input()

        with allure.step(f"2. Выбрать в композере модель {model_name!r}"):
            main.select_model(model_name)

        prompt = _three_word_prompt()
        allure.attach(
            prompt,
            name="Промпт (3 слова от faker)",
            attachment_type=allure.attachment_type.TEXT,
        )

        with allure.step(f"3. Отправить сообщение: {prompt!r}"):
            main.send_message(prompt, submit_with="enter")

        with allure.step("4. URL должен смениться на /chat/<uuid>"):
            main.wait_for_chat_url(timeout=20_000)
            expect(authenticated_page).to_have_url(main.CHAT_URL_PATTERN)

        with allure.step("5. Сообщение пользователя появилось в истории"):
            expect(
                authenticated_page.locator(main.USER_MESSAGE_TEXT).last
            ).to_have_text(prompt, timeout=10_000)

        with allure.step("6. Дождаться непустого ответа ассистента"):
            main.wait_for_assistant_response(timeout=90_000)
            response_text = (
                authenticated_page.locator(main.ASSISTANT_RESPONSE)
                .first.inner_text()
                or ""
            )
            allure.attach(
                response_text[:2000],
                name="Ответ ассистента (первые 2000 символов)",
                attachment_type=allure.attachment_type.TEXT,
            )

            assert response_text.strip(), (
                f"{model_name} вернула пустой ответ на промпт {prompt!r}"
            )

            lowered = response_text.lower()
            hit = next((m for m in ERROR_MARKERS if m in lowered), None)
            assert hit is None, (
                f"{model_name} вернула сообщение об ошибке "
                f"(маркер {hit!r}): {response_text[:300]!r}"
            )

        with allure.step(
            "7. Под ответом показано имя модели — и оно совпадает с выбранной"
        ):
            main.wait_for_response_model_trigger(timeout=10_000)
            actual = main.get_response_model_name()
            allure.attach(
                f"Выбрали: {model_name}\nОтветила (по UI): {actual}",
                name="Проверка авторства ответа",
                attachment_type=allure.attachment_type.TEXT,
            )
            assert actual == model_name, (
                f"Ответила не та модель: выбрали {model_name!r}, "
                f"а футер ответа показывает {actual!r}"
            )
