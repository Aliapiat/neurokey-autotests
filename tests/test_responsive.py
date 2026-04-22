"""
Ported from `neurokey-react/e2e/tests/responsive.spec.ts`.

Брейкпоинты из `src/theme/breakpoints.ts`:
    small:  ≤ 440px (mobile, min 375px)
    medium: 441–975px
    large:  ≥ 976px
"""

import allure
import pytest
from playwright.sync_api import Page, expect

from pages.login_page import LoginPage
from pages.main_page import MainPage


SMALL = {"width": 375, "height": 812}
MEDIUM = {"width": 768, "height": 1024}
LARGE = {"width": 1440, "height": 900}


@allure.epic("Адаптивность")
@allure.feature("Авторизованный шелл")
class TestResponsiveAuthed:

    @allure.title("Desktop (≥976px) — сайдбар виден inline")
    @pytest.mark.responsive
    def test_desktop_sidebar_inline(self, authenticated_page: Page):
        authenticated_page.set_viewport_size(LARGE)
        main = MainPage(authenticated_page)
        main.open()

        main.should_show_sidebar()
        main.should_be_loaded()

    @allure.title("Tablet (441–975px) — нет горизонтального overflow")
    @pytest.mark.responsive
    def test_tablet_no_overflow(self, authenticated_page: Page):
        authenticated_page.set_viewport_size(MEDIUM)
        main = MainPage(authenticated_page)
        main.open()
        main.should_be_loaded()

        scroll_width = main.get_scroll_width()
        assert scroll_width <= MEDIUM["width"] + 2, (
            f"Ожидали scrollWidth ≤ {MEDIUM['width'] + 2}, получили {scroll_width}"
        )

    @allure.title("Mobile (≤440px) — есть поле ввода чата")
    @pytest.mark.responsive
    def test_mobile_chat_composer(self, authenticated_page: Page):
        authenticated_page.set_viewport_size(SMALL)
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_chat_input()

        scroll_width = main.get_scroll_width()
        assert scroll_width <= SMALL["width"] + 2


@allure.epic("Адаптивность")
@allure.feature("Страница логина")
class TestResponsiveLogin:

    @allure.title("Mobile (≤440px) — форма логина вмещается в экран")
    @pytest.mark.responsive
    def test_mobile_login_form(self, page: Page, login_page: LoginPage):
        page.set_viewport_size(SMALL)
        login_page.open()

        expect(page.get_by_role("heading", name="Вход в Нейроключ")).to_be_visible()
        expect(page.get_by_placeholder("Введите эл. почту")).to_be_visible()
        expect(page.get_by_placeholder("Введите пароль")).to_be_visible()

        scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
        assert scroll_width <= SMALL["width"] + 2

    @allure.title("Desktop — форма логина видна")
    @pytest.mark.responsive
    def test_desktop_login_form(self, page: Page, login_page: LoginPage):
        page.set_viewport_size(LARGE)
        login_page.open()

        expect(page.get_by_role("heading", name="Вход в Нейроключ")).to_be_visible()
        expect(page.get_by_placeholder("Введите эл. почту")).to_be_visible()
