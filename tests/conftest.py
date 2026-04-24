import re

import allure
import pytest
from playwright.sync_api import Page

from config.environments import ENVIRONMENT_LABELS
from config.settings import settings
from pages.login_page import LoginPage
from pages.main_page import MainPage
from utils.auth_storage import seed_fake_auth
from utils.model_metrics import ModelMetricsRecorder, append_row, utc_now_iso


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

    # На CI headless `wait_for_url(lambda ...)` нестабилен — ждём регексом + маркер UI
    page.wait_for_url(re.compile(r"^(?!.*/login).*$"), timeout=30_000)
    return page


# ═══════════════════════════════════════════
# СКРИНШОТ ПРИ ПАДЕНИИ + РЕЗУЛЬТАТ ТЕСТА НА item
# ═══════════════════════════════════════════
#
# Параллельно со скриншотом кладём результат каждой фазы (`setup`, `call`,
# `teardown`) на сам `item` как атрибут `rep_<phase>`. Это стандартный
# pytest-идиом: фикстурам в teardown становится известно, прошёл ли тест
# — без него нельзя безопасно «убирать за собой только на зелёном».

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    setattr(item, "rep_" + report.when, report)

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


# ═══════════════════════════════════════════
# CHAT CLEANER — удаляем созданные в тесте чаты только на успехе
# ═══════════════════════════════════════════

@pytest.fixture
def chat_cleaner(request, authenticated_page: Page):
    """Собирает id созданных в тесте чатов и удаляет их после прохождения.

    Использование из теста::

        def test_x(authenticated_page, chat_cleaner):
            ...
            chat_cleaner.add(main.get_current_chat_id())
            ...

    Семантика:
      - если тест прошёл (`rep_call.passed`) — пробегаемся по собранным id
        и шлём `DELETE /api/v1/chats/<uuid>` из контекста той же страницы
        (cookies сессии подцепляются автоматически);
      - если тест упал/скипнут — НИЧЕГО не трогаем, чтобы QA мог открыть
        чат и вручную разобраться, что не так.

    Безопасность:
      - удаляются только те uuid, которые тест ЯВНО добавил через
        `chat_cleaner.add(...)` — это всегда id чатов, созданных прямо
        в этом прогоне (берётся из URL `/chat/<uuid>` после отправки
        первого сообщения);
      - `MainPage.delete_chat_via_api` дополнительно проверяет формат
        uuid v4, так что «что-то левое» физически не улетит.
    """

    class _Cleaner:
        def __init__(self) -> None:
            self._ids: list[str] = []

        def add(self, chat_id: str | None) -> None:
            if chat_id and chat_id not in self._ids:
                self._ids.append(chat_id)

        @property
        def ids(self) -> list[str]:
            return list(self._ids)

    cleaner = _Cleaner()
    yield cleaner

    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is None or not rep_call.passed:
        if cleaner.ids:
            # Намеренно не удаляем — чат остаётся у пользователя для разбора.
            allure.attach(
                "\n".join(cleaner.ids),
                name="chat_cleaner: чаты оставлены (тест не passed)",
                attachment_type=allure.attachment_type.TEXT,
            )
        return

    if not cleaner.ids:
        return

    main_page = MainPage(authenticated_page)
    results: list[str] = []
    for chat_id in cleaner.ids:
        try:
            result = main_page.delete_chat_via_api(chat_id)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        results.append(f"{chat_id} → {result}")

    allure.attach(
        "\n".join(results),
        name="chat_cleaner: итог удаления",
        attachment_type=allure.attachment_type.TEXT,
    )


# ═══════════════════════════════════════════
# MODEL METRICS — CSV-журнал времени ответов моделей
# ═══════════════════════════════════════════

@pytest.fixture
def model_metrics_recorder(request):
    """Аккумулирует данные о прогоне модельного теста и пишет CSV-строку.

    Тест заполняет поля через `recorder.set(...)`:

        recorder.set(
            model=model_name,
            prompt=prompt,
            first_completion_ms=first_ms,
            total_ms=total_ms,
            chat_id=chat_id,
        )

    На teardown фикстура сама:
      - подтягивает статус теста (`passed` / `failed` / `error` / `skipped`)
        из `rep_call` / `rep_setup` (см. `pytest_runtest_makereport`);
      - добавляет `timestamp_utc` и `env` из окружения;
      - пишет одну строку в `reports/model_response_times.csv`.

    Если тест ничего не замерил (упал на setup до `recorder.set`) — запись
    не добавляется, чтобы CSV не замусоривался «пустыми» строками.
    """
    env = settings.CURRENT_ENV or "dev"
    recorder = ModelMetricsRecorder(env=env)
    yield recorder

    if not recorder.is_armed():
        return

    # Определяем статус теста по стандартным отчётам pytest.
    # `rep_call` есть, если тест дошёл до фазы call. На setup-failures
    # rep_call не создаётся — фиксируем через rep_setup.
    rep_call = getattr(request.node, "rep_call", None)
    rep_setup = getattr(request.node, "rep_setup", None)

    if rep_call is not None:
        if rep_call.passed:
            status = "passed"
        elif rep_call.failed:
            status = "failed"
        elif rep_call.skipped:
            status = "skipped"
        else:
            status = "unknown"
        error = "" if rep_call.passed else _short_error(rep_call)
    elif rep_setup is not None and not rep_setup.passed:
        status = "setup_error"
        error = _short_error(rep_setup)
    else:
        status = "unknown"
        error = ""

    row = recorder.snapshot()
    row["timestamp_utc"] = utc_now_iso()
    row["status"] = status
    row["error"] = error

    # prompt_len заполняется автоматически, если сам prompt есть.
    if "prompt" in row and "prompt_len" not in row:
        row["prompt_len"] = len(row["prompt"])

    try:
        path = append_row(row)
        allure.attach(
            f"{path}\n\n{row}",
            name="model_metrics: CSV-строка",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception as exc:  # noqa: BLE001
        # Метрики — вторичны, никогда не роняем из-за них тест.
        allure.attach(
            f"Не смогли записать метрики: {exc}\nrow={row}",
            name="model_metrics: ошибка записи",
            attachment_type=allure.attachment_type.TEXT,
        )


def _short_error(report) -> str:
    """Короткое описание ошибки для CSV — чтобы колонка не разрасталась
    до мегабайт трейсбека."""
    raw = getattr(report, "longreprtext", None) or str(report.longrepr or "")
    raw = raw.strip().replace("\r", " ").replace("\n", " | ")
    return raw[:500]
