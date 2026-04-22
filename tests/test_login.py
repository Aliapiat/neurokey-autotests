"""
Комплексные тесты логина — по мотивам relevanter-autotests/test_login.py.

Адаптировано под UI Нейроключа:
    - Заголовок:           'Вход в Нейроключ'
    - Placeholder email:   'Введите эл. почту'
    - Placeholder password:'Введите пароль'
    - Кнопка:              'Войти в аккаунт'
    - Ошибка invalid:      'Неверный пароль'

В Нейроключе НЕТ чекбокса 'Запомнить меня' и 'Забыли пароль?' —
соответствующие сценарии из reference-проекта опущены.
"""

import allure
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from config.settings import settings, has_real_credentials
from pages.login_page import LoginPage
from pages.main_page import MainPage
from utils.helpers import randomize_case


fake = Faker("ru_RU")

WRONG_CREDS_ERROR = "Неверный пароль"


def _skip_if_no_creds():
    if not has_real_credentials():
        pytest.skip("ADMIN_EMAIL / ADMIN_PASSWORD не заданы")


# ═══════════════════════════════════════════
# UI / ОТОБРАЖЕНИЕ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("UI — отображение элементов")
class TestLoginUI:

    @allure.title("Поле email отображается")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_email_field_visible(self, login_page: LoginPage):
        login_page.open()
        login_page.should_be_visible(login_page.EMAIL_INPUT)

    @allure.title("Поле пароля отображается")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_password_field_visible(self, login_page: LoginPage):
        login_page.open()
        login_page.should_be_visible(login_page.PASSWORD_INPUT)

    @allure.title("Кнопка 'Войти в аккаунт' отображается")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_login_button_visible(self, login_page: LoginPage):
        login_page.open()
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_visible()

    @allure.title("Заголовок страницы логина")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_login_heading(self, login_page: LoginPage):
        login_page.open()
        login_page.should_show_heading()

    @allure.title("Плейсхолдер email корректен")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_email_placeholder(self, login_page: LoginPage):
        login_page.open()
        placeholder = login_page.get_email_placeholder()
        assert "почт" in placeholder.lower() or "email" in placeholder.lower(), (
            f"Неверный плейсхолдер: {placeholder}"
        )

    @allure.title("Плейсхолдер пароля корректен")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_password_placeholder(self, login_page: LoginPage):
        login_page.open()
        placeholder = login_page.get_password_placeholder()
        assert "пароль" in placeholder.lower(), f"Неверный плейсхолдер: {placeholder}"

    @allure.title("Пароль скрыт (type=password)")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_password_is_masked(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_password("TestPassword")
        assert login_page.get_password_input_type() == "password"


# ═══════════════════════════════════════════
# ПОЗИТИВНЫЕ СЦЕНАРИИ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Позитивные сценарии")
@pytest.mark.real_backend
class TestLoginPositive:

    @allure.title("Успешный логин")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.smoke
    @pytest.mark.login
    def test_successful_login(self, login_page: LoginPage, main_page: MainPage):
        _skip_if_no_creds()
        login_page.open()
        login_page.login(settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)
        main_page.should_be_loaded()

    @allure.title("Enter в поле пароля отправляет форму")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.login
    def test_enter_in_password_submits(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        login_page.enter_email(settings.ADMIN_EMAIL)
        login_page.enter_password(settings.ADMIN_PASSWORD)
        login_page.press_enter_in_password()
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Enter в поле email отправляет форму")
    @pytest.mark.login
    def test_enter_in_email_submits(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        login_page.enter_email(settings.ADMIN_EMAIL)
        login_page.enter_password(settings.ADMIN_PASSWORD)
        login_page.press_enter_in_email()
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)


# ═══════════════════════════════════════════
# РЕГИСТР EMAIL
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Регистр email")
@pytest.mark.real_backend
class TestLoginEmailCase:

    @allure.title("Email полностью в верхнем регистре")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.login
    def test_email_all_upper(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        upper_email = settings.ADMIN_EMAIL.upper()
        with allure.step(f"Вводим email: {upper_email}"):
            login_page.login(upper_email, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Email полностью в нижнем регистре")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.login
    def test_email_all_lower(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        lower_email = settings.ADMIN_EMAIL.lower()
        with allure.step(f"Вводим email: {lower_email}"):
            login_page.login(lower_email, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Email с рандомным регистром букв")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.login
    def test_email_random_case(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        mixed = randomize_case(settings.ADMIN_EMAIL)
        with allure.step(f"Вводим email: {mixed}"):
            login_page.login(mixed, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Email с рандомным регистром (повтор для стабильности)")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.login
    @pytest.mark.parametrize("attempt", range(3), ids=lambda i: f"attempt-{i + 1}")
    def test_email_random_case_repeated(self, login_page: LoginPage, attempt: int):
        _skip_if_no_creds()
        login_page.open()
        mixed = randomize_case(settings.ADMIN_EMAIL)
        with allure.step(f"Попытка {attempt + 1}: email = {mixed}"):
            login_page.login(mixed, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)


# ═══════════════════════════════════════════
# ПРОБЕЛЫ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Пробелы в email / пароле")
@pytest.mark.real_backend
class TestLoginSpaces:

    @allure.title("Пробелы перед email")
    @pytest.mark.login
    def test_email_leading_spaces(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        spaced = f"   {settings.ADMIN_EMAIL}"
        with allure.step(f"Вводим email: '{spaced}'"):
            login_page.login(spaced, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Пробелы после email")
    @pytest.mark.login
    def test_email_trailing_spaces(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        spaced = f"{settings.ADMIN_EMAIL}   "
        with allure.step(f"Вводим email: '{spaced}'"):
            login_page.login(spaced, settings.ADMIN_PASSWORD)
        login_page.page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)

    @allure.title("Пробелы перед паролем — логин должен упасть")
    @pytest.mark.login
    def test_password_leading_spaces(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        spaced = f"   {settings.ADMIN_PASSWORD}"
        with allure.step("Вводим пароль с пробелами в начале"):
            login_page.login(settings.ADMIN_EMAIL, spaced)
        # Пароль не должен триммиться — ожидаем что мы остались на /login
        # с сообщением об ошибке
        login_page.page.wait_for_timeout(1500)
        assert "/login" in login_page.page.url, (
            "Пароль с пробелами должен отклоняться, но логин прошёл"
        )

    @allure.title("Пробелы после пароля — логин должен упасть")
    @pytest.mark.login
    def test_password_trailing_spaces(self, login_page: LoginPage):
        _skip_if_no_creds()
        login_page.open()
        spaced = f"{settings.ADMIN_PASSWORD}   "
        with allure.step("Вводим пароль с пробелами в конце"):
            login_page.login(settings.ADMIN_EMAIL, spaced)
        login_page.page.wait_for_timeout(1500)
        assert "/login" in login_page.page.url


# ═══════════════════════════════════════════
# НЕГАТИВНЫЕ — ПУСТЫЕ ПОЛЯ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Негативные — пустые поля")
class TestLoginEmptyFields:

    @allure.title("Кнопка задизейблена при пустой форме")
    @pytest.mark.login
    def test_button_disabled_on_empty_form(self, login_page: LoginPage):
        login_page.open()
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_disabled()

    @allure.title("Кнопка остаётся неактивной при одном заполненном поле (email)")
    @pytest.mark.login
    def test_button_disabled_only_email(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email("someone@example.com")
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_disabled()

    @allure.title("Кнопка остаётся неактивной при одном заполненном поле (пароль)")
    @pytest.mark.login
    def test_button_disabled_only_password(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_password("somepassword")
        expect(
            login_page.page.get_by_role("button", name="Войти в аккаунт")
        ).to_be_disabled()


# ═══════════════════════════════════════════
# НЕВЕРНЫЕ CREDENTIALS (через мок /auths/signin)
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Неверные credentials")
class TestLoginInvalidCredentials:

    @staticmethod
    def _mock_signin_400(login_page: LoginPage):
        login_page.page.route(
            "**/api/v1/auths/signin",
            lambda route: route.fulfill(
                status=400,
                content_type="application/json",
                body='{"detail": "email or password provided is incorrect"}',
            ),
        )

    @allure.title("Неверный пароль — инлайн-ошибка")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.login
    def test_wrong_password(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login(settings.ADMIN_EMAIL or "user@example.com", fake.password())
        login_page.should_show_error(WRONG_CREDS_ERROR)

    @allure.title("Несуществующий пользователь")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.login
    def test_nonexistent_user(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login(fake.email(), fake.password())
        login_page.should_show_error(WRONG_CREDS_ERROR)

    @allure.title("Очень длинный email (500+ символов)")
    @pytest.mark.login
    def test_very_long_email(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login(f"{'a' * 500}@mail.com", fake.password())
        login_page.should_show_error(WRONG_CREDS_ERROR)

    @allure.title("Очень длинный пароль (1000+ символов)")
    @pytest.mark.login
    def test_very_long_password(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login("user@example.com", "a" * 1000)
        login_page.should_show_error(WRONG_CREDS_ERROR)


# ═══════════════════════════════════════════
# HTML5 ВАЛИДАЦИЯ EMAIL
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("HTML5 валидация email")
class TestLoginEmailValidation:

    @allure.title("Email без @ — поле невалидно")
    @pytest.mark.login
    def test_email_without_at(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email(fake.user_name())
        login_page.enter_password(fake.password())
        # Пытаемся засабмитить через Enter — кнопка может быть disabled
        login_page.press_enter_in_password()
        login_page.should_email_be_invalid()

    @allure.title("Email без домена (user@)")
    @pytest.mark.login
    def test_email_without_domain(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email(f"{fake.user_name()}@")
        login_page.enter_password(fake.password())
        login_page.press_enter_in_password()
        login_page.should_email_be_invalid()

    @allure.title("Email с двойной точкой в домене")
    @pytest.mark.login
    def test_email_double_dot(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email(f"{fake.user_name()}@mail..com")
        login_page.enter_password(fake.password())
        login_page.press_enter_in_password()
        login_page.should_email_be_invalid()


# ═══════════════════════════════════════════
# БЕЗОПАСНОСТЬ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Безопасность")
class TestLoginSecurity:

    @staticmethod
    def _mock_signin_400(login_page: LoginPage):
        login_page.page.route(
            "**/api/v1/auths/signin",
            lambda route: route.fulfill(
                status=400,
                content_type="application/json",
                body='{"detail": "email or password provided is incorrect"}',
            ),
        )

    @allure.title("SQL-инъекция в email")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.login
    def test_sql_injection_email(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email("' OR 1=1 --")
        login_page.enter_password(fake.password())
        login_page.press_enter_in_password()
        login_page.should_email_be_invalid()

    @allure.title("XSS в поле email")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.login
    def test_xss_in_email(self, login_page: LoginPage):
        login_page.open()
        login_page.enter_email("<script>alert('xss')</script>@mail.com")
        login_page.enter_password(fake.password())
        login_page.press_enter_in_password()
        login_page.should_email_be_invalid()

    @allure.title("Спецсимволы в пароле — корректно отклоняются")
    @pytest.mark.login
    def test_special_chars_password(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login("user@example.com", "!@#$%^&*()_+-=[]{}|;':\",./<>?")
        login_page.should_show_error(WRONG_CREDS_ERROR)

    @allure.title("XSS в поле пароля — корректно отклоняется")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.login
    def test_xss_in_password(self, login_page: LoginPage):
        self._mock_signin_400(login_page)
        login_page.open()
        login_page.login("user@example.com", "<script>alert('xss')</script>")
        login_page.should_show_error(WRONG_CREDS_ERROR)


# ═══════════════════════════════════════════
# UX / ACCESSIBILITY
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("UX / Accessibility")
class TestLoginAccessibility:

    @allure.title("Tab из email переводит фокус на пароль")
    @pytest.mark.login
    def test_tab_navigation(self, login_page: LoginPage):
        login_page.open()
        login_page.page.locator(login_page.EMAIL_INPUT).focus()
        login_page.tab_from_email_to_password()
        assert login_page.is_password_focused(), "Фокус должен быть на поле пароля"


# ═══════════════════════════════════════════
# НАВИГАЦИЯ / РЕДИРЕКТЫ
# ═══════════════════════════════════════════

@allure.epic("Авторизация")
@allure.feature("Навигация и редиректы")
class TestLoginNavigation:

    @allure.title("Неавторизованный пользователь редиректится на /login")
    @pytest.mark.smoke
    @pytest.mark.login
    def test_redirect_unauth_to_login(self, page: Page):
        import re as _re
        page.goto(settings.BASE_URL)
        page.wait_for_url(lambda url: "/login" in url, timeout=15_000)
        expect(page).to_have_url(_re.compile(r"/login"))

    @allure.title("Прямой переход на /login открывает страницу логина")
    @pytest.mark.login
    def test_direct_login_url(self, login_page: LoginPage):
        login_page.open()
        login_page.should_show_heading()
