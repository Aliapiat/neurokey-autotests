import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, List, Optional

from playwright.sync_api import Locator, Response, expect

from pages.base_page import BasePage


@dataclass(frozen=True)
class CompletionsResult:
    """Результат ожидания двух POST /api/chat/completions.

    Поля `*_done_at` — это `time.perf_counter()` в момент, когда у
    соответствующего Response.finished() вернулось управление, т.е.
    тело ответа полностью прочитано. Их удобно вычитать из
    `t_send`, который тест фиксирует перед `send_message`, чтобы
    получить «сколько прошло от клика Enter до готового ответа».
    """

    first: Response
    second: Response
    first_done_at: float
    second_done_at: float


@dataclass(frozen=True)
class BalanceSnapshot:
    """Срез баланса организации в конкретный момент.

    Соответствует схеме ответа `GET /api/v1/organizations/my/balance`:
        {
          "organization_id": "...",
          "organization_name": "WMT",
          "credit_limit": 10000,
          "credits_used": 2022.7064,
          "credits_remaining": 7977.2936,
          "is_demo": false,
          "status": "ok"
        }
    """

    credits_remaining: float
    credits_used: float
    credit_limit: float
    organization_id: str
    organization_name: str
    is_demo: bool


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

    # Footer под ответом — содержит (слева направо):
    #   1) кнопку .model-picker-trigger с именем модели, которая ответила
    #   2) иконочные кнопки (копировать / перегенерировать и т.п.)
    # Это наш источник истины «какая нейронка реально ответила».
    RESPONSE_MODEL_TRIGGER = (
        ".response-actions-container button.model-picker-trigger"
    )

    # ─── Сообщения в чате ───
    MESSAGE_PAIR = ".message-pair"
    USER_MESSAGE_TEXT = ".user-message-text"
    ASSISTANT_RESPONSE = ".response-container"

    # ─── URL pattern после отправки первого сообщения ───
    CHAT_URL_PATTERN = re.compile(
        r"/chat/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    CHAT_ID_PATTERN = re.compile(
        r"/chat/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    )

    # Точки контакта с бэкендом для ожидания ответа модели.
    # На каждое отправленное сообщение фронт делает ДВА POST-а:
    #   1) `/api/chat/completions` со `stream: true` — собственно SSE-ответ
    #      модели (chunks с `chat.completion.chunk`, финальный `[DONE]`);
    #   2) `/api/chat/completions` (уже без stream) — короткий запрос на
    #      генерацию заголовка чата (возвращает объект `chat.completion`).
    # Стабильное состояние чата (заголовок в сайдбаре, сохранённая история)
    # наступает только ПОСЛЕ того, как прошёл второй запрос.
    COMPLETIONS_URL_SUBSTRING = "/api/chat/completions"
    # Endpoint для удаления чата по uuid — используется в teardown-фикстурах.
    CHATS_DELETE_URL_TEMPLATE = "/api/v1/chats/{chat_id}"
    # Баланс кредитов организации — фронт сам дёргает этот GET после
    # каждого `/api/chat/completions`, чтобы обновить .subscription-badge.
    BALANCE_URL = "/api/v1/organizations/my/balance"
    # UI-виджет с балансом (sanity-check: что пользователь реально видит).
    # Значение отформатировано по-русски: '7&nbsp;980,433' — неразрывный
    # пробел как разделитель тысяч, запятая как десятичный разделитель.
    BALANCE_UI_VALUE = ".subscription-badge__value"
    BALANCE_UI_LABEL = ".subscription-badge__label"

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

    def select_model(self, model_name: str, timeout: int = 10_000):
        """Открыть селектор и выбрать модель по точному имени.

        Попап закрывается автоматически после выбора.
        """
        self.open_model_picker(timeout=timeout)
        popup = self.model_picker_popup()
        option = popup.get_by_text(model_name, exact=True).first
        expect(option).to_be_visible(timeout=timeout)
        option.click()
        self.model_picker_popup().wait_for(state="hidden", timeout=5_000)
        expect(self.model_picker_trigger()).to_have_text(model_name, timeout=timeout)
        return self

    def response_model_trigger(self) -> Locator:
        return self.page.locator(self.RESPONSE_MODEL_TRIGGER).first

    def wait_for_response_model_trigger(self, timeout: int = 90_000):
        """Ждём, пока под ответом появится кнопка с именем модели."""
        trigger = self.response_model_trigger()
        trigger.wait_for(state="visible", timeout=timeout)
        expect(trigger).not_to_have_text("", timeout=timeout)
        return self

    def get_response_model_name(self) -> str:
        return (self.response_model_trigger().inner_text() or "").strip()

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

    # ═══════════════════════════════════════════
    # CHAT ID / CLEANUP API
    # ═══════════════════════════════════════════

    def get_current_chat_id(self) -> Optional[str]:
        """Достать uuid чата из URL `/chat/<uuid>`.

        Возвращает None, если мы ещё не на странице конкретного чата.
        """
        match = self.CHAT_ID_PATTERN.search(self.page.url)
        return match.group(1) if match else None

    def delete_chat_via_api(self, chat_id: str) -> dict:
        """Удалить чат по uuid через `DELETE /api/v1/chats/<uuid>`.

        Запрос идёт из контекста самой страницы (`page.evaluate` + fetch),
        поэтому автоматически подцепляются сессионные cookies, как и у UI.

        Возвращает dict `{ok: bool, status: int}` с результатом, ничего не
        роняет — решение, падать или нет, принимает вызывающий код (обычно
        это teardown-фикстура, которой важно сохранить состояние теста).
        """
        if not chat_id:
            return {"ok": False, "status": 0, "error": "empty chat_id"}
        # Дополнительный страховочный чек: бэкенд отдаёт только uuid v4,
        # и мы ни при каких обстоятельствах не хотим дёрнуть DELETE на
        # что-то произвольное, что могло приехать из URL.
        if not re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            chat_id,
        ):
            return {"ok": False, "status": 0, "error": f"invalid uuid: {chat_id!r}"}

        url = self.CHATS_DELETE_URL_TEMPLATE.format(chat_id=chat_id)
        return self.page.evaluate(
            """
            (url) => fetch(url, {
                method: 'DELETE',
                credentials: 'include',
                headers: { 'Accept': 'application/json' },
            })
            .then(r => ({ ok: r.ok, status: r.status }))
            .catch(e => ({ ok: false, status: 0, error: String(e) }))
            """,
            url,
        )

    # ═══════════════════════════════════════════
    # ОЖИДАНИЕ ДВУХ COMPLETION-ЗАПРОСОВ
    # ═══════════════════════════════════════════

    @contextmanager
    def capture_completions(self) -> Iterator[List[Response]]:
        """Контекст, который копит все `POST /api/chat/completions`
        ответы, приходящие на страницу, пока мы внутри `with`-блока.

        Использование:
            with main.capture_completions() as completions:
                main.send_message(prompt)
                main.wait_for_two_completions(completions, timeout_ms=180_000)

        Подписку обязательно поднимать ДО `send_message` — иначе есть риск
        пропустить очень быстрый первый ответ (актуально для локальных
        моделей и для повторных прогонов с кэшем).
        """
        collected: List[Response] = []

        def _on_response(response: Response) -> None:
            try:
                if (
                    response.request.method == "POST"
                    and self.COMPLETIONS_URL_SUBSTRING in response.url
                ):
                    collected.append(response)
            except Exception:
                # response.request может упасть, если контекст страницы
                # уже закрыт — на жизнь теста это не влияет, просто игнорим.
                pass

        self.page.on("response", _on_response)
        try:
            yield collected
        finally:
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:
                pass

    def wait_for_two_completions(
        self,
        collected: List[Response],
        *,
        timeout_ms: int = 180_000,
        poll_interval_ms: int = 500,
    ) -> CompletionsResult:
        """Явное ожидание ДВУХ ответов `POST /api/chat/completions`.

        Это не «sleep на N секунд», а ожидание условия `len(collected) >= 2`
        с периодической проверкой. `Response.finished()` дополнительно
        гарантирует, что тело (в т.ч. стрим SSE у первого и короткий JSON
        у второго) прочитано до конца — именно после этого в UI появляется
        финальный заголовок и футер с именем модели.

        В тестах на медленных моделях (YandexGPT, GigaChat, image-пайп)
        таймаут надо поднимать. По умолчанию 180с — эмпирически с запасом.

        Возвращает `CompletionsResult` с обоими Response-ами и
        монотонными отметками времени `first_done_at` / `second_done_at`.
        Их не нужно сравнивать между собой по значению — только вычитать
        из зафиксированного тестом `t_send` (time.perf_counter() до
        `send_message`), чтобы получить миллисекунды отклика.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if len(collected) >= 2:
                first, second = collected[0], collected[1]
                try:
                    first.finished()
                except Exception:
                    pass
                first_done_at = time.perf_counter()
                try:
                    second.finished()
                except Exception:
                    pass
                second_done_at = time.perf_counter()
                return CompletionsResult(
                    first=first,
                    second=second,
                    first_done_at=first_done_at,
                    second_done_at=second_done_at,
                )
            # Это не «timeout», это интервал polling'а условия. Playwright
            # сам предоставляет sync-овое ожидание, другой кооперативной
            # паузы в нём нет. Сам deadline — у цикла выше.
            self.page.wait_for_timeout(poll_interval_ms)

        raise AssertionError(
            f"Не дождались двух POST {self.COMPLETIONS_URL_SUBSTRING} "
            f"за {timeout_ms} ms (получено {len(collected)}). "
            "Возможно, модель не ответила или упала на бэке."
        )

    # ═══════════════════════════════════════════
    # БАЛАНС КРЕДИТОВ
    # ═══════════════════════════════════════════

    def get_balance(self) -> BalanceSnapshot:
        """Сходить в `GET /api/v1/organizations/my/balance` из контекста
        страницы (cookies сессии прилетают сами) и вернуть разобранный снимок.
        """
        raw = self.page.evaluate(
            """
            async (url) => {
                const r = await fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    headers: { 'Accept': 'application/json' },
                });
                return { status: r.status, body: await r.json() };
            }
            """,
            self.BALANCE_URL,
        )
        status = raw.get("status") if isinstance(raw, dict) else None
        body = raw.get("body") if isinstance(raw, dict) else None
        if status != 200 or not isinstance(body, dict):
            raise AssertionError(
                f"Не смогли прочитать баланс: status={status}, body={body!r}"
            )
        try:
            return BalanceSnapshot(
                credits_remaining=float(body["credits_remaining"]),
                credits_used=float(body["credits_used"]),
                credit_limit=float(body["credit_limit"]),
                organization_id=str(body.get("organization_id", "")),
                organization_name=str(body.get("organization_name", "")),
                is_demo=bool(body.get("is_demo", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AssertionError(
                f"Неожиданная схема ответа баланса: {body!r} ({exc})"
            ) from exc

    def get_balance_from_ui(self) -> Optional[float]:
        """Прочитать баланс из виджета `.subscription-badge__value`.

        Используется как sanity-check API против UI. Если виджет не
        виден (например, на странице чата он может быть скрыт на узких
        вьюпортах) — возвращаем None.

        Парсинг: '7&nbsp;980,433' -> 7980.433
        """
        locator = self.page.locator(self.BALANCE_UI_VALUE).first
        try:
            if locator.count() == 0 or not locator.is_visible():
                return None
            raw = locator.inner_text() or ""
        except Exception:
            return None
        return self._parse_ui_balance(raw)

    @staticmethod
    def _parse_ui_balance(raw: str) -> Optional[float]:
        """Убираем все пробелы (обычные, неразрывные `\xa0`, тонкие `\u202f`)
        и меняем запятую на точку перед `float()`."""
        if raw is None:
            return None
        cleaned = (
            raw.replace("\u00a0", "")
            .replace("\u202f", "")
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def wait_for_balance_change(
        self,
        baseline: BalanceSnapshot,
        *,
        timeout_ms: int = 15_000,
        poll_interval_ms: int = 500,
    ) -> BalanceSnapshot:
        """Дождаться, пока `credits_remaining` отличается от `baseline`.

        Бэкенд списывает токены не мгновенно после завершения
        `/api/chat/completions`: сначала закрывается стрим, потом
        usage-накладные из последнего chunk попадают в ledger, потом
        баланс обновляется. На практике это единицы секунд. 15 с — с
        хорошим запасом.

        Если за deadline изменений не случилось — возвращаем последний
        прочитанный снимок, и вызывающий код сам решает, это ошибка
        или «модель ничего не стоила» (например, локальная/бесплатная).
        """
        deadline = time.monotonic() + timeout_ms / 1000
        current = baseline
        while time.monotonic() < deadline:
            current = self.get_balance()
            if current.credits_remaining != baseline.credits_remaining:
                return current
            self.page.wait_for_timeout(poll_interval_ms)
        return current
