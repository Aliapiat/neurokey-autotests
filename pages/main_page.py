from playwright.sync_api import expect

from pages.base_page import BasePage


class MainPage(BasePage):
    """Главная страница (авторизованный шелл) Нейроключа."""

    PATH = "/"

    WELCOME_HEADING = "Добро пожаловать в Нейроключ!"
    CHAT_INPUT = "textarea[placeholder='Спросите что-нибудь...'], input[placeholder='Спросите что-нибудь...']"
    SIDEBAR = "aside"
    NEW_CHAT_BUTTON_NAME = "новый чат"
    CHAT_SEARCH_INPUT = "input[placeholder='Поиск по чатам']"
    POPULAR_MODELS_HEADING = "Самые популярные модели"
    SEARCH_BUTTON = "button:has-text('Поиск')"

    def open(self):
        self.navigate(self.PATH)
        return self

    def should_be_loaded(self, timeout: int = 15_000):
        expect(
            self.page.get_by_role("heading", name=self.WELCOME_HEADING)
        ).to_be_visible(timeout=timeout)
        return self

    def should_show_chat_input(self, timeout: int = 15_000):
        expect(self.page.locator(self.CHAT_INPUT)).to_be_visible(timeout=timeout)
        return self

    def type_message(self, text: str):
        self.page.locator(self.CHAT_INPUT).fill(text)
        return self

    def get_chat_input_value(self) -> str:
        return self.page.locator(self.CHAT_INPUT).input_value()

    def should_show_sidebar(self, timeout: int = 15_000):
        expect(self.page.locator(self.SIDEBAR).first).to_be_visible(timeout=timeout)
        return self

    def should_show_new_chat_button(self, timeout: int = 15_000):
        import re
        expect(
            self.page.get_by_role(
                "button", name=re.compile(self.NEW_CHAT_BUTTON_NAME, re.I)
            ).first
        ).to_be_visible(timeout=timeout)
        return self

    def click_new_chat(self):
        import re
        self.page.get_by_role(
            "button", name=re.compile(self.NEW_CHAT_BUTTON_NAME, re.I)
        ).first.click()
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
        expect(self.page.get_by_role("button", name="Поиск")).to_be_visible(timeout=timeout)
        return self

    def get_scroll_width(self) -> int:
        return self.page.evaluate("() => document.documentElement.scrollWidth")
