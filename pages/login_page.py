import re

from playwright.sync_api import expect

from pages.base_page import BasePage


class LoginPage(BasePage):
    PATH = "/login"

    # ─── Локаторы (по role/placeholder/text — тексты на русском из UI) ───
    EMAIL_INPUT = "input[placeholder='Введите эл. почту']"
    PASSWORD_INPUT = "input[placeholder='Введите пароль']"
    LOGIN_BUTTON = "button:has-text('Войти в аккаунт')"
    HEADING = "h1, h2, h3, h4, h5, h6"
    HEADING_TEXT = "Вход в Нейроключ"
    ERROR_MESSAGE = (
        "div[role='alert'], div[role='status'], "
        "[class*='error'], [class*='Error']"
    )

    def open(self):
        self.navigate(self.PATH)
        self.wait_for_visible(self.EMAIL_INPUT)
        return self

    def enter_email(self, email: str):
        self.fill(self.EMAIL_INPUT, email)
        return self

    def enter_password(self, password: str):
        self.fill(self.PASSWORD_INPUT, password)
        return self

    def click_login(self):
        self.page.get_by_role("button", name="Войти в аккаунт").click()
        return self

    def login(self, email: str, password: str):
        self.enter_email(email)
        self.enter_password(password)
        self.click_login()
        return self

    def press_enter_in_password(self):
        self.page.locator(self.PASSWORD_INPUT).press("Enter")
        return self

    def press_enter_in_email(self):
        self.page.locator(self.EMAIL_INPUT).press("Enter")
        return self

    def tab_from_email_to_password(self):
        self.page.locator(self.EMAIL_INPUT).press("Tab")
        return self

    # ─── Проверки ───

    def should_be_opened(self):
        self.page.wait_for_url(lambda url: "/login" in url, timeout=15_000)
        expect(self.page).to_have_url(re.compile(r"/login"))
        self.should_be_visible(self.LOGIN_BUTTON)
        return self

    def should_show_heading(self):
        expect(
            self.page.get_by_role("heading", name=self.HEADING_TEXT)
        ).to_be_visible()
        return self

    def should_show_error(self, expected_text: str):
        expect(self.page.get_by_text(expected_text)).to_be_visible()
        return self

    def should_email_be_invalid(self):
        self.should_be_invalid(self.EMAIL_INPUT)
        return self

    def should_email_have_validation(self, expected_text: str):
        self.should_have_validation_message(self.EMAIL_INPUT, expected_text)
        return self

    def should_password_be_invalid(self):
        self.should_be_invalid(self.PASSWORD_INPUT)
        return self

    # ─── Геттеры атрибутов ───

    def get_email_placeholder(self) -> str:
        return self.page.locator(self.EMAIL_INPUT).get_attribute("placeholder") or ""

    def get_password_placeholder(self) -> str:
        return self.page.locator(self.PASSWORD_INPUT).get_attribute("placeholder") or ""

    def get_password_input_type(self) -> str:
        return self.page.locator(self.PASSWORD_INPUT).get_attribute("type") or ""

    def is_password_focused(self) -> bool:
        return self.page.locator(self.PASSWORD_INPUT).evaluate(
            "el => document.activeElement === el"
        )

    def is_login_button_enabled(self) -> bool:
        return self.page.get_by_role("button", name="Войти в аккаунт").is_enabled()
