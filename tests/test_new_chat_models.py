"""
Сценарий:
    1. Логинимся (фикстура `authenticated_page`).
    2. Нажимаем "Новый чат".
    3. Вводим рандомную фразу.
    4. Отправляем сообщение.
    5. Пока ждём ответа — открываем селектор модели и проверяем,
       что на стенде отображается ВЕСЬ ожидаемый список нейросетей
       (Диалоговые + Изображения).
    6. Закрываем селектор и дожидаемся непустого ответа ассистента.

Селекторы зафиксированы по результатам живого обследования UI
через MCP-Playwright (wmt1.acm-ai.ru).
"""

import allure
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from pages.main_page import MainPage
from test_data.models import ALL_MODELS, DIALOG_MODELS, IMAGE_MODELS, SECTION_HEADERS


fake = Faker("ru_RU")


RANDOM_PROMPTS = [
    "Привет! Расскажи короткий интересный факт о космосе.",
    "Предложи три идеи для завтрака из подручных продуктов.",
    "Напиши в одно предложение афоризм про понедельник.",
    "Переведи на английский: 'Сегодня отличный день для кода'.",
    "Какая столица у Монголии?",
    "Дай один совет, как сосредоточиться за 20 секунд.",
]


def _random_prompt() -> str:
    # Смешиваем заготовленные фразы с fake-текстом, чтобы в отчёте было видно,
    # что именно уехало на бэкенд в этом прогоне.
    prompt = fake.random_element(elements=RANDOM_PROMPTS)
    return f"{prompt} ({fake.word()}-{fake.random_int(min=1000, max=9999)})"


@allure.epic("Чат")
@allure.feature("Новый чат + проверка списка моделей")
@pytest.mark.real_backend
class TestNewChatModelsAvailable:

    @allure.title("Новый чат → сообщение → во время ожидания видим все модели")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.smoke
    @pytest.mark.chat
    @pytest.mark.models
    def test_new_chat_shows_full_model_list(self, authenticated_page: Page):
        main = MainPage(authenticated_page)

        with allure.step("1. Открыть главную и закрыть онбординг-попап"):
            main.open()
            main.dismiss_group_chats_popup()
            main.should_be_loaded()

        with allure.step("2. Нажать 'Новый чат'"):
            main.click_new_chat()
            main.should_show_chat_input()

        prompt = _random_prompt()
        allure.attach(prompt, name="Отправленный запрос", attachment_type=allure.attachment_type.TEXT)

        with allure.step(f"3. Ввести и отправить сообщение: {prompt!r}"):
            main.send_message(prompt, submit_with="enter")

        with allure.step("4. URL должен смениться на /chat/<uuid>"):
            main.wait_for_chat_url(timeout=20_000)
            expect(authenticated_page).to_have_url(main.CHAT_URL_PATTERN)

        with allure.step("5. Сообщение пользователя отобразилось в истории"):
            expect(authenticated_page.locator(main.USER_MESSAGE_TEXT).last).to_have_text(
                prompt, timeout=10_000
            )

        with allure.step("6. Пока идёт ответ — открыть селектор моделей"):
            main.open_model_picker()

        with allure.step("7. В попапе видны оба заголовка секций"):
            popup = main.model_picker_popup()
            for header in SECTION_HEADERS:
                expect(popup.get_by_text(header, exact=True)).to_be_visible()

        with allure.step(f"8. Видны все {len(DIALOG_MODELS)} диалоговые модели"):
            for name in DIALOG_MODELS:
                expect(popup.get_by_text(name, exact=True)).to_be_visible()

        with allure.step(f"9. Видны все {len(IMAGE_MODELS)} модели для изображений"):
            for name in IMAGE_MODELS:
                expect(popup.get_by_text(name, exact=True)).to_be_visible()

        with allure.step("10. Лишних пунктов в списке моделей нет"):
            actual_names = _read_picker_item_names(authenticated_page)
            allure.attach(
                "\n".join(actual_names),
                name="Модели в попапе (как видит UI)",
                attachment_type=allure.attachment_type.TEXT,
            )
            unexpected = sorted(set(actual_names) - set(ALL_MODELS) - set(SECTION_HEADERS))
            assert not unexpected, (
                f"В попапе есть элементы, которых нет в ожидаемом списке: {unexpected}"
            )
            missing = sorted(set(ALL_MODELS) - set(actual_names))
            assert not missing, f"В попапе отсутствуют модели: {missing}"

        with allure.step("11. Закрыть селектор моделей"):
            main.close_model_picker()

        with allure.step("12. Дождаться ответа ассистента"):
            main.wait_for_assistant_response(timeout=60_000)
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
            assert response_text.strip(), "Ответ ассистента пустой"


def _read_picker_item_names(page: Page) -> list[str]:
    """Вернуть тексты всех прямых детей .model-picker-content.

    Попап содержит смешанные элементы:
      SPAN 'Диалоговые модели'  (заголовок)
      DIV  'GPT-5.2'            (модель)
      ...
      SPAN 'Изображения'
      DIV  'Nano Banana Pro (Google/Gemini)'
      ...
    """
    return page.evaluate(
        """() => {
            const root = document.querySelector('.model-picker-content');
            if (!root) return [];
            return Array.from(root.children)
                .map(el => (el.innerText || '').trim())
                .filter(Boolean);
        }"""
    )
