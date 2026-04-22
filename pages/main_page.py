import re

from playwright.sync_api import Locator, expect

from pages.base_page import BasePage


class MainPage(BasePage):
    """Главная страница (авторизованный шелл) Нейроключа."""

    PATH = "/"

    # ─── Приветствие / landing ───
    WELCOME_HEADING = "Добро пожаловать в Нейроключ!"
    NEW_CHAT_HEADING = "С чего начнем общение?"
    POPULAR_MODELS_HEADING = "Самые популярные модели"

    # ─── Сайдбар ───
    SIDEBAR = "aside"
    NEW_CHAT_BUTTON_NAME = "Новый чат"
    CHAT_SEARCH_INPUT = "input[placeholder='Поиск по чатам']"

    # ─── Композер (строка ввода) ───
    CHAT_INPUT = "textarea.prompt-form__textarea"
    CHAT_INPUT_FALLBACK = (
        "textarea[placeholder='Спросите что-нибудь...'], "
        "input[placeholder='Спросите что-нибудь...']"
    )
    SEND_BUTTON = ".prompt-form__body button.button-primary"
    SEARCH_BUTTON = "button:has-text('Поиск')"

    # ─── Селектор модели ───
    # Класс .model-picker-trigger встречается ДВАЖДЫ: в композере
    # и в футере ответа ассистента (`.response-actions-container`).
    # Нам нужен только композерный — скоупим к .prompt-form__body.
    MODEL_PICKER_TRIGGER = ".prompt-form__body button.model-picker-trigger"
    MODEL_PICKER_POPUP = ".model-picker-content"

    # ─── Сообщения в чате ───
    MESSAGE_PAIR = ".message-pair"
    USER_MESSAGE_TEXT = ".user-message-text"
    ASSISTANT_RESPONSE = ".response-container"

    # ─── URL pattern после отправки первого сообщения ───
    CHAT_URL_PATTERN = re.compile(
        r"/chat/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )

    # ═══════════════════════════════════════════
    # НАВИГАЦИЯ
    # ═══════════════════════════════════════════

    def open(self):
        self.navigate(self.PATH)
        return self

    def should_be_loaded(self, timeout: int = 15_000):
        expect(
            self.page.get_by_role("heading", name=self.WELCOME_HEADING)
        ).to_be_visible(timeout=timeout)
        return self

    # ═══════════════════════════════════════════
    # СООБЩЕНИЯ / КОМПОЗЕР
    # ═══════════════════════════════════════════

    def chat_input(self) -> Locator:
        locator = self.page.locator(self.CHAT_INPUT)
        if locator.count() == 0:
            locator = self.page.locator(self.CHAT_INPUT_FALLBACK)
        return locator

    def should_show_chat_input(self, timeout: int = 15_000):
        expect(self.chat_input()).to_be_visible(timeout=timeout)
        return self

    def type_message(self, text: str):
        self.chat_input().fill(text)
        return self

    def get_chat_input_value(self) -> str:
        return self.chat_input().input_value()

    def send_message(self, text: str, submit_with: str = "enter"):
        """Ввести сообщение и отправить.

        submit_with: 'enter' → нажатие Enter в textarea,
                     'button' → клик по кнопке .button-primary.
        """
        self.type_message(text)
        if submit_with == "enter":
            self.chat_input().press("Enter")
        else:
            self.page.locator(self.SEND_BUTTON).click()
        return self

    def wait_for_chat_url(self, timeout: int = 30_000):
        """После отправки первого сообщения URL меняется на /chat/<uuid>."""
        self.page.wait_for_url(self.CHAT_URL_PATTERN, timeout=timeout)
        return self

    # ═══════════════════════════════════════════
    # СЕЛЕКТОР МОДЕЛЕЙ
    # ═══════════════════════════════════════════

    def model_picker_trigger(self) -> Locator:
        return self.page.locator(self.MODEL_PICKER_TRIGGER)

    def model_picker_popup(self) -> Locator:
        return self.page.locator(self.MODEL_PICKER_POPUP)

    def open_model_picker(self, timeout: int = 10_000):
        trigger = self.model_picker_trigger()
        trigger.wait_for(state="visible", timeout=timeout)
        trigger.click()
        self.model_picker_popup().wait_for(state="visible", timeout=timeout)
        return self

    def close_model_picker(self):
        self.page.keyboard.press("Escape")
        self.model_picker_popup().wait_for(state="hidden", timeout=5_000)
        return self

    def get_current_model_name(self) -> str:
        return (self.model_picker_trigger().inner_text() or "").strip()

    # ═══════════════════════════════════════════
    # ОТВЕТ АССИСТЕНТА
    # ═══════════════════════════════════════════

    def wait_for_assistant_response(self, timeout: int = 60_000):
        """Ждать, пока появится блок ответа ассистента с непустым текстом."""
        response = self.page.locator(self.ASSISTANT_RESPONSE).first
        response.wait_for(state="visible", timeout=timeout)
        # Ждём появления непустого текста (начало стрима)
        expect(response).not_to_have_text("", timeout=timeout)
        return self

    def last_user_message_text(self) -> str:
        return (
            self.page.locator(self.USER_MESSAGE_TEXT).last.inner_text() or ""
        ).strip()

    # ═══════════════════════════════════════════
    # САЙДБАР / КНОПКИ
    # ═══════════════════════════════════════════

    def should_show_sidebar(self, timeout: int = 15_000):
        expect(self.page.locator(self.SIDEBAR).first).to_be_visible(timeout=timeout)
        return self

    def should_show_new_chat_button(self, timeout: int = 15_000):
        expect(
            self.page.get_by_role("button", name=self.NEW_CHAT_BUTTON_NAME).first
        ).to_be_visible(timeout=timeout)
        return self

    def click_new_chat(self):
        self.page.get_by_role("button", name=self.NEW_CHAT_BUTTON_NAME).first.click()
        # После клика ждём, пока появится приветствие нового чата
        # либо URL сбросится на "/"
        self.page.wait_for_timeout(300)
        return self

    def dismiss_group_chats_popup(self):
        """Закрыть onboarding-попап 'Групповые чаты', если он появился."""
        close = self.page.get_by_role("button", name="Close")
        try:
            if close.count() and close.first.is_visible():
                close.first.click()
                self.page.wait_for_timeout(200)
        except Exception:
            pass
        return self

    def should_show_search_input(self, timeout: int = 15_000):
        expect(self.page.locator(self.CHAT_SEARCH_INPUT)).to_be_visible(timeout=timeout)
        return self

    def should_show_popular_models(self, timeout: int = 15_000):
        expect(
            self.page.get_by_role("heading", name=self.POPULAR_MODELS_HEADING)
        ).to_be_visible(timeout=timeout)
        return self

    def should_show_search_button(self, timeout: int = 15_000):
        expect(self.page.get_by_role("button", name="Поиск")).to_be_visible(
            timeout=timeout
        )
        return self

    def get_scroll_width(self) -> int:
        return self.page.evaluate("() => document.documentElement.scrollWidth")
