import allure
import pytest
from playwright.sync_api import Page

from config.environments import ENVIRONMENT_LABELS
from config.settings import settings
from pages.login_page import LoginPage
from pages.main_page import MainPage
from utils.auth_storage import seed_fake_auth


# ═══════════════════════════════════════════
# НАСТРОЙКИ БРАУЗЕРА
# ═══════════════════════════════════════════

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {
        **browser_type_launch_args,
        "headless": settings.HEADLESS,
        "slow_mo": settings.SLOW_MO,
    }


# ═══════════════════════════════════════════
# ALLURE — метка стенда для фильтрации в отчёте
# ═══════════════════════════════════════════

@pytest.fixture(autouse=True)
def _tag_environment():
    env = settings.CURRENT_ENV or "dev"
    label = ENVIRONMENT_LABELS.get(env, env)
    allure.dynamic.label("env", env)
    allure.dynamic.label("parentSuite", label)
    yield


# ═══════════════════════════════════════════
# СТРАНИЦЫ
# ═══════════════════════════════════════════

@pytest.fixture
def login_page(page: Page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def main_page(page: Page) -> MainPage:
    return MainPage(page)


# ═══════════════════════════════════════════
# АВТОРИЗОВАННЫЕ СОСТОЯНИЯ
# ═══════════════════════════════════════════

@pytest.fixture
def fake_authed_page(page: Page) -> Page:
    """Страница с подменённым токеном — без реального логина.

    Используется для тестов которые работают поверх замоканного API
    (mock_all_api) — аналог `seedFakeAuth` из TS-тестов.
    """
    seed_fake_auth(page)
    return page


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    """Реальный логин с кредами из env. Пропускает тест, если креды не заданы."""
    if not (settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD):
        pytest.skip("ADMIN_EMAIL / ADMIN_PASSWORD не заданы — реальный логин невозможен")

    login = LoginPage(page)
    login.open()
    login.login(settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)

    page.wait_for_url(lambda url: "/login" not in url, timeout=20_000)
    return page


# ═══════════════════════════════════════════
# СКРИНШОТ ПРИ ПАДЕНИИ
# ═══════════════════════════════════════════

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page:
            try:
                allure.attach(
                    page.screenshot(full_page=True),
                    name="failure_screenshot",
                    attachment_type=allure.attachment_type.PNG,
                )
            except Exception:
                pass
