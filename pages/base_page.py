import allure
from playwright.sync_api import Page, expect, Locator
from config.settings import settings


class BasePage:
    def __init__(self, page: Page):
        self.page = page
        self.page.set_default_timeout(settings.DEFAULT_TIMEOUT)

    def navigate(self, path: str = "/"):
        base = settings.BASE_URL.rstrip("/")
        target = f"{base}/{path.lstrip('/')}" if path else base + "/"
        self.page.goto(target, wait_until="domcontentloaded")
        return self

    def click(self, selector: str):
        self.page.locator(selector).click()
        return self

    def fill(self, selector: str, text: str):
        self.page.locator(selector).fill(text)
        return self

    def get_text(self, selector: str) -> str:
        return self.page.locator(selector).text_content() or ""

    def get_element(self, selector: str) -> Locator:
        return self.page.locator(selector)

    def wait_for_visible(self, selector: str, timeout: int | None = None):
        self.page.locator(selector).wait_for(
            state="visible", timeout=timeout or settings.DEFAULT_TIMEOUT
        )
        return self

    def should_be_visible(self, selector: str):
        expect(self.page.locator(selector)).to_be_visible()
        return self

    def should_contain_text(self, selector: str, text: str):
        expect(self.page.locator(selector)).to_contain_text(text)
        return self

    def should_have_url(self, url_pattern: str):
        expect(self.page).to_have_url(url_pattern)
        return self

    def take_screenshot(self, name: str = "screenshot"):
        screenshot = self.page.screenshot()
        allure.attach(screenshot, name=name, attachment_type=allure.attachment_type.PNG)
        return self

    def get_validation_message(self, selector: str) -> str:
        return self.page.locator(selector).evaluate("el => el.validationMessage")

    def should_have_validation_message(self, selector: str, expected_text: str):
        message = self.get_validation_message(selector)
        assert expected_text in message, (
            f"Ожидали '{expected_text}' в validation message, получили: '{message}'"
        )

    def should_be_invalid(self, selector: str):
        is_valid = self.page.locator(selector).evaluate("el => el.checkValidity()")
        assert not is_valid, f"Поле {selector} должно быть невалидным"
