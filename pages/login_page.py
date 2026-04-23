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

    # Фактические тексты уведомлений Нейроключа при 400 /auths/signin.
    # Фронт показывает ОБА одновременно — под email и под паролем,
    # независимо от того, что именно не так.
    EMAIL_ERROR_TEXT = "Почта не зарегистрирована"
    PASSWORD_ERROR_TEXT = "Неверный пароль"

    # Маркер успешной авторизации — заголовок стартовой страницы.
    WELCOME_HEADING_TEXT = "Добро пожаловать в Нейроключ!"

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

    def should_show_password_error(self, timeout: int = 10_000):
        """Ошибка под полем пароля: «Неверный пароль»."""
        expect(
            self.page.get_by_text(self.PASSWORD_ERROR_TEXT, exact=False)
        ).to_be_visible(timeout=timeout)
        return self

    def should_show_email_error(self, timeout: int = 10_000):
        """Ошибка под полем email: «Почта не зарегистрирована…»."""
        expect(
            self.page.get_by_text(self.EMAIL_ERROR_TEXT, exact=False)
        ).to_be_visible(timeout=timeout)
        return self

    def should_show_login_error(self, timeout: int = 10_000):
        """Фронт показывает оба сообщения одновременно — ждём любое из них."""
        locator = self.page.get_by_text(
            re.compile(
                rf"{re.escape(self.PASSWORD_ERROR_TEXT)}|{re.escape(self.EMAIL_ERROR_TEXT)}"
            )
        ).first
        expect(locator).to_be_visible(timeout=timeout)
        return self

    def wait_for_login_success(self, timeout: int = 30_000):
        """Надёжный ожидальщик успешного логина для CI.

        Используем regex вместо lambda (Playwright стабильнее отлавливает
        SPA-редирект после 200 от /auths/signin). Дополнительно проверяем,
        что появился маркер авторизованной оболочки — заголовок стартового
        экрана. Это защищает от редких случаев, когда URL уже сменился,
        а JS ещё не отрисовал интерфейс.
        """
        self.page.wait_for_url(re.compile(r"^(?!.*/login).*$"), timeout=timeout)
        expect(
            self.page.get_by_role("heading", name=self.WELCOME_HEADING_TEXT)
        ).to_be_visible(timeout=timeout)
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
