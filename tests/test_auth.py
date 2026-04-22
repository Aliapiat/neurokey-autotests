"""
Ported from `neurokey-react/e2e/tests/auth.spec.ts`.

UI / навигация / невалидные креды.
"""

import re

import allure
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings, has_real_credentials
from pages.login_page import LoginPage
from utils.mocks import mock_auth_endpoints


@allure.epic("Авторизация")
@allure.feature("Страница логина")
class TestLoginPageUI:

    @allure.title("Страница логина открывается по /login")
    @pytest.mark.smoke
    @pytest.mark.auth
    def test_login_page_renders(self, login_page: LoginPage):
        login_page.open()
        expect(
            login_page.page.get_by_role("heading", name="Вход в Нейроключ")
        ).to_be_visible()
        expect(login_page.page.get_by_placeholder("Введите эл. почту")).to_be_visible()
        expect(login_page.page.get_by_placeholder("Введите пароль")).to_be_visible()
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_visible()

    @allure.title("Кнопка 'Войти в аккаунт' задизейблена при пустой форме")
    @pytest.mark.smoke
    @pytest.mark.auth
    def test_submit_disabled_when_empty(self, login_page: LoginPage):
        login_page.open()
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_disabled()

    @allure.title("Неавторизованный редиректится на /login")
    @pytest.mark.smoke
    @pytest.mark.auth
    def test_redirect_to_login(self, page: Page):
        page.goto(settings.BASE_URL)
        page.wait_for_url(lambda url: "/login" in url, timeout=15_000)
        expect(page).to_have_url(re.compile(r"/login"))


@allure.epic("Авторизация")
@allure.feature("Невалидные креды (мок бэкенда)")
class TestLoginInvalid:

    @allure.title("Инлайн-ошибка при неверных кредах")
    @pytest.mark.auth
    def test_invalid_credentials_inline_error(self, login_page: LoginPage):
        # Мокаем 400 от /auths/signin — независимо от стенда
        login_page.page.route(
            "**/api/v1/auths/signin",
            lambda route: route.fulfill(
                status=400,
                content_type="application/json",
                body='{"detail": "email or password provided is incorrect"}',
            ),
        )

        login_page.open()
        login_page.login("wrong@example.com", "badpassword")
        expect(login_page.page.get_by_text("Неверный пароль")).to_be_visible()

    @allure.title("Успешный логин (мок) редиректит из /login")
    @pytest.mark.auth
    def test_successful_login_mocked(self, login_page: LoginPage):
        mock_auth_endpoints(login_page.page)

        login_page.open()
        login_page.login("e2e@example.com", "secret")
        login_page.page.wait_for_url(
            lambda url: "/login" not in url, timeout=15_000
        )


@allure.epic("Авторизация")
@allure.feature("Реальный бэкенд")
@pytest.mark.real_backend
class TestRealLogin:

    @allure.title("Логин с реальными кредами")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.smoke
    @pytest.mark.auth
    def test_real_login(self, login_page: LoginPage):
        if not has_real_credentials():
            pytest.skip("ADMIN_EMAIL / ADMIN_PASSWORD не заданы")

        login_page.open()
        login_page.login(settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(
            lambda url: "/login" not in url, timeout=20_000
        )
