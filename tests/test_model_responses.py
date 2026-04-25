"""
Параметризованный smoke на КАЖДУЮ диалоговую модель:

1. Логинимся (фикстура `authenticated_page`).
2. В композере открываем селектор моделей и выбираем целевую модель.
3. Фейкером (русская локаль) генерируем запрос из 2 слов и отправляем его.
4. ЯВНО ждём, пока по сети пройдёт ДВА POST `/api/chat/completions`:
     - первый — streaming SSE с собственно ответом модели (`chat.completion.chunk`,
       финальный chunk с `finish_reason: "stop"` и затем `[DONE]`);
     - второй — короткий non-stream запрос на генерацию заголовка чата
       (возвращает объект `chat.completion` вида
       `{"id":"...","object":"chat.completion","choices":[{"message":{...}}]}`).
   Именно после второго ответа UI приходит в стабильное состояние —
   появляется финальный текст ответа, имя модели под ответом и заголовок
   чата в сайдбаре. До этого момента любые проверки флейкуют.
5. Проверяем, что:
   - URL сменился на /chat/<uuid>;
   - ответ не пустой;
   - в ответе нет типовых маркеров ошибки;
   - под ответом в `.response-actions-container` стоит имя ИМЕННО той
     модели, которую мы выбрали.
6. TEARDOWN: если тест прошёл — удаляем СВОЙ чат (uuid взяли из URL)
   через `DELETE /api/v1/chats/<uuid>`. Если тест упал — чат оставляем,
   чтобы можно было зайти руками и посмотреть, что именно сломалось.

Источник правды «кто ответил» — кнопка `.model-picker-trigger` в
`.response-actions-container` (слева от иконочных кнопок).

Селекторы и последовательность сетевых событий подтверждены живым
обследованием UI через MCP-Playwright на `wmt1.acm-ai.ru`.

Image-модели (Nano Banana / GPT Image / Seedream) в этот параметр
не входят: у них другой пайп ответа (генерация картинки), ждём там
дольше и проверяются они отдельным набором — см. отдельный issue.
"""

import re
import time

import allure
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from config.settings import settings
from pages.main_page import MainPage
from test_data.models import DIALOG_MODELS


# Faker с русской локалью — на ru_RU методы `.words()` отдают слова
# в нижнем регистре кириллицей, без пунктуации. Русский промпт лучше
# отрабатывают локальные модели (YandexGPT / GigaChat) и заодно
# тестирует, что фронт корректно проксирует UTF-8 в `/api/chat/completions`.
fake = Faker("ru_RU")


def _faker_prompt() -> str:
    """Два русских слова, разделённых пробелом. Никакой пунктуации —
    чтобы промпт был детерминированно из ровно двух токенов."""
    return " ".join(fake.words(nb=2))


# Типовые текстовые маркеры, которые фронт/бэк могут показать вместо
# корректного ответа. Если что-то из этого попадает в тело ответа —
# считаем, что модель фактически не ответила.
ERROR_MARKERS = (
    "произошла ошибка",
    "что-то пошло не так",
    "сервис временно недоступен",
    "ошибка подключения",
    "ошибка сервера",
    "error:",
    "rate limit",
    "timeout",
)


# Полный бюджет ожидания двух completion-запросов. Это верхний предел
# для МЕДЛЕННЫХ моделей (YandexGPT / GigaChat / reasoning-режимы):
# быстрые модели (Claude Haiku, Llama) укладываются в единицы секунд,
# но мы параметризуем тесты на ВСЕ модели, и общий потолок должен
# покрывать самую долгую. Если упрёмся — значит проблема на бэке.
COMPLETIONS_TIMEOUT_MS = 240_000

# Таймаут ожидания UI-реакций, которые триггерятся ПОСЛЕ `send_message`:
# - смена URL на /chat/<uuid>,
# - отрисовка сообщения пользователя в истории,
# - отрисовка блока ответа ассистента,
# - появление футера `.response-actions-container` с именем модели.
# Все эти события на холодном CI/медленном бэкенде наступают с ощутимой
# задержкой (React-рендер + /api/v1/chats/new + обновление сайдбара),
# поэтому стандартный 10-15с Playwright-овский таймаут нам тесен.
POST_SEND_UI_TIMEOUT = 60_000

# Ожидание обновления счётчика «Сегодня» в Настройках после ответа модели.
# Бэкенд начисляет статистику АСИНХРОННО: для Sonnet/GPT учёт прилетает за
# 1-3 секунды, для Opus/Gemini/GigaChat иногда уходит за 60+ секунд (видимо,
# batch на стороне биллинга). 180с — верхний потолок: если за это время
# счётчик так и не вырос — это уже похоже на баг учёта.
COUNTER_POLL_TIMEOUT_S = 180
COUNTER_POLL_STEP_MS = 4_000


# Алиасы, под которыми та или иная модель показывается в карточке
# «По нейросетям» в Настройки → Статистика использования.
#
# ВАЖНО: тут указываются ТОЛЬКО канонические слаги — ровно те строки,
# которые реально отрисованы в DOM на /settings (проверено вручную
# 2026-04-25, см. список ниже). Никаких display-name из селектора
# композера и никаких «человеческих» вариаций — иначе матчинг становится
# жадным и хватает текст из соседних карточек/тултипов.
#
# Если бэкенд однажды поменяет id (например, выкатит `claude-opus-5`),
# тест упадёт явно с "счётчик 0", и это сигнал заходить в /settings и
# обновлять словарь. Лучше явная поломка, чем мигающие зелёные.
MODEL_STATS_ALIASES: dict[str, tuple[str, ...]] = {
    "GPT-5.2":                  ("openai/gpt-5.2",),
    "Claude Opus 4.6":          ("anthropic/claude-opus-4.6",),
    "Claude Sonnet 4.6":        ("anthropic/claude-sonnet-4.6",),
    "Gemini 3.1 Pro Preview":   ("google/gemini-3.1-pro-preview",),
    "Grok 4.1 Fast":            ("x-ai/grok-4.1-fast",),
    "DeepSeek V3.2":            ("deepseek/deepseek-v3.2",),
    "GigaChat 2 Pro":           ("GigaChat-2-Pro",),
    "Kimi K2.5":                ("moonshotai/kimi-k2.5",),
    "YandexGPT 5.1 Pro":        ("yandexgpt-5.1",),
}


def _get_model_aliases(model_name: str) -> tuple[str, ...]:
    """Все варианты написания имени модели в карточке статистики."""
    configured = MODEL_STATS_ALIASES.get(model_name)
    if configured:
        return configured
    return (model_name.lower(),)


def _open_settings(page: Page) -> None:
    """Перейти на `/settings` прямой навигацией.

    Не зависит от состояния профильного дропдауна — устойчиво к гонкам
    рендера/анимации Ant Tooltip. Каждый вызов перезагружает SPA-роут,
    поэтому фронт точно перечитает статистику с бэка (своего автообновления
    у страницы нет — без goto цифры в DOM «зависнут» на старом значении).
    """
    base = settings.BASE_URL.rstrip("/")
    page.goto(f"{base}/settings", wait_until="domcontentloaded")
    expect(
        page.get_by_text(re.compile(r"настройки профиля", re.IGNORECASE)).first
    ).to_be_visible(timeout=30_000)


def _expand_stats_collapse(page: Page) -> None:
    """Раскрыть Ant Collapse «Статистика использования», если он свёрнут.

    Без раскрытия карточек моделей в секции «По нейросетям» в DOM нет
    физически — Ant рендерит содержимое только при `aria-expanded=true`.
    Поэтому до раскрытия любой `_read_model_requests_counter` вернёт 0
    даже при реально существующих запросах.
    """
    page.evaluate(
        r"""
        () => {
            const headers = Array.from(
                document.querySelectorAll('.ant-collapse-header')
            );
            const target = headers.find(
                (h) => /статистика\s+использования/i.test(h.textContent || '')
            );
            if (!target) return 'no-collapse';
            if (target.getAttribute('aria-expanded') === 'true') {
                return 'already-open';
            }
            target.click();
            return 'expanded';
        }
        """
    )
    # Признак того, что секция реально раскрыта и данные подгружены —
    # появилось «Всего запросов» (виден всегда, даже на нулевых данных).
    expect(
        page.get_by_text(re.compile(r"всего\s+запросов", re.IGNORECASE)).first
    ).to_be_visible(timeout=15_000)


def _read_total_today(page: Page) -> int:
    """Прочитать глобальный счётчик «Сегодня: HH:MM, N запросов».

    Это сводка из header'а Ant Collapse — фронт обновляет её одновременно
    с карточками моделей, поэтому используем её как «индикатор свежести»:
    если `total_after > total_before` — данные точно перечитаны.
    """
    raw = page.evaluate(
        r"""
        () => {
            const summary = document.querySelector(
                '.user-settings-stats-header-summary'
            );
            if (!summary) return null;
            const match = (summary.textContent || '').match(/(\d+)\s+запрос/iu);
            return match ? Number(match[1]) : null;
        }
        """
    )
    return int(raw) if raw is not None else 0


def _read_model_requests_counter(
    page: Page, aliases: tuple[str, ...]
) -> int:
    r"""Найти карточку модели в «По нейросетям» и достать число запросов.

    Алгоритм (slug-anchored, idempotent):

    1. На странице может быть много текстовых узлов вида «N запросов»
       (по одному на каждую карточку модели + общая сводка). Сначала
       собираем ВСЕ листовые элементы, у которых текст начинается с
       «<число> запрос…» — это и есть «цифры в карточках».
    2. Для каждой такой цифры поднимаемся вверх по DOM (не глубже 4
       уровней) и ищем первого предка, чей `textContent` СОДЕРЖИТ один
       из переданных слагов.
    3. Стоп-условие подъёма — когда в предке встречается более одного
       «(\d+) запрос…»: значит, это уже секция с несколькими
       карточками, и наличие в ней нашего слага не означает, что наш
       слаг соответствует ИМЕННО этой цифре. Дополнительно — hard-cap
       по длине текста (> 400 символов): на всякий случай.

    Если ни одна цифра не «прицепилась» к нужному слагу — возвращаем 0.
    Это нормальное состояние для свежей учётки или модели, по которой
    сегодня ещё ноль запросов; не падаем на ассерте раньше времени.

    Старая версия функции искала наоборот — от слага вниз/вбок к цифре —
    и регулярно подцепляла соседнюю карточку (топ-1 модель «съедала»
    цифру у всех остальных, см. CSV от 2026-04-25). Новая идёт от
    цифры — у каждой цифры один родитель-карточка, поэтому коллизий
    больше нет.
    """
    normalized_aliases = [
        alias.strip().lower() for alias in aliases if alias.strip()
    ]
    if not normalized_aliases:
        return 0

    result = page.evaluate(
        r"""(aliases) => {
            const norm = (s) => (s || '').trim().toLowerCase();
            const targets = aliases.map(norm).filter(Boolean);

            // 1) Собираем листовые узлы с текстом "(\d+) запрос(а|ов)?".
            // Только листья, чтобы не цеплять контейнеры выше карточки.
            const leaves = Array.from(document.querySelectorAll('*'))
                .filter((el) => el.children.length === 0);
            const counters = [];
            for (const el of leaves) {
                const txt = (el.textContent || '').trim();
                const m = txt.match(/^(\d+)\s*запрос/iu);
                if (m) counters.push({el, count: Number(m[1])});
            }

            // 2) Для каждой цифры идём вверх и ищем ближайшего предка,
            //    у которого в тексте есть слаг модели.
            //
            //    Стоп-условие подъёма — когда в предке встречается
            //    более одного «(\d+) запрос…»: это уже контейнер с
            //    несколькими карточками, и матч слага в нём не значит,
            //    что НАША карточка соответствует ЭТОЙ цифре.
            for (const {el, count} of counters) {
                let cur = el;
                for (let depth = 0; depth < 4; depth++) {
                    const parent = cur.parentElement;
                    if (!parent) break;
                    const parentText = norm(parent.textContent);
                    const countHits = parentText.match(/\d+\s*запрос/giu) || [];
                    if (countHits.length > 1) break;  // soft-cap по числу карточек
                    if (parentText.length > 400) break;  // hard-cap на всякий случай
                    if (targets.some((t) => parentText.includes(t))) {
                        return {value: count};
                    }
                    cur = parent;
                }
            }
            return {value: null};
        }""",
        normalized_aliases,
    )

    value = result.get("value") if isinstance(result, dict) else None
    return int(value) if value is not None else 0


def _snapshot_today_stats(
    page: Page, aliases: tuple[str, ...]
) -> tuple[int, int]:
    """Открыть /settings, раскрыть статистику, вернуть `(total, model)`.

    Полная навигация + раскрытие Collapse делается КАЖДЫЙ раз. Это дороже
    клика по табу, зато надёжно: SPA-роут точно перечитает данные с бэка,
    без тонких гонок Ant Segmented (повторный клик по тому же сегменту
    у Ant — no-op, фронт не делает re-fetch).
    """
    _open_settings(page)
    _expand_stats_collapse(page)
    total = _read_total_today(page)
    model = _read_model_requests_counter(page, aliases)
    return total, model


@allure.epic("Модели")
@allure.feature("Каждая модель отвечает на запрос")
@pytest.mark.real_backend
@pytest.mark.models
@pytest.mark.chat
class TestModelAnswers:

    @pytest.mark.parametrize("model_name", DIALOG_MODELS, ids=DIALOG_MODELS)
    @allure.title("{model_name} отвечает на запрос из 2 русских слов (faker)")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_model_answers_faker_prompt(
        self,
        authenticated_page: Page,
        chat_cleaner,
        model_metrics_recorder,
        model_name: str,
    ):
        main = MainPage(authenticated_page)
        aliases = _get_model_aliases(model_name)

        with allure.step(
            "0. Снапшот BEFORE: Настройки → Статистика → счётчик «Сегодня»"
        ):
            # Снимаем ДО самого теста: и глобальный счётчик «Сегодня:
            # HH:MM, N запросов», и счётчик именно нашей модели в карточке
            # «По нейросетям». Если карточки модели ещё нет — значит
            # сегодня под неё было 0 запросов, считаем `model_before = 0`.
            total_today_before, model_today_before = _snapshot_today_stats(
                authenticated_page, aliases
            )
            allure.attach(
                (
                    f"total_today_before = {total_today_before}\n"
                    f"{model_name}_today_before = {model_today_before}"
                ),
                name="Счётчики статистики ДО",
                attachment_type=allure.attachment_type.TEXT,
            )
            model_metrics_recorder.set(
                total_today_before=total_today_before,
                model_today_before=model_today_before,
            )

        with allure.step("1. Открыть главную и закрыть онбординг-попап"):
            main.open()
            main.dismiss_group_chats_popup()
            main.should_be_loaded(timeout=30_000)
            main.should_show_chat_input(timeout=30_000)

        with allure.step(f"2. Выбрать в композере модель {model_name!r}"):
            main.select_model(model_name)

        prompt = _faker_prompt()
        allure.attach(
            prompt,
            name="Промпт (2 русских слова от faker)",
            attachment_type=allure.attachment_type.TEXT,
        )

        # Сразу взводим запись в CSV — даже если дальше всё упадёт, мы хотя
        # бы знаем, какую модель и каким промптом ловили.
        model_metrics_recorder.set(model=model_name, prompt=prompt)

        with allure.step("2.5. Зафиксировать баланс ДО отправки запроса"):
            balance_before = main.get_balance()
            # sanity-check: то же значение показано пользователю в виджете
            ui_balance_before = main.get_balance_from_ui()
            model_metrics_recorder.set(
                balance_before=balance_before.credits_remaining,
            )
            allure.attach(
                (
                    f"API credits_remaining: {balance_before.credits_remaining}\n"
                    f"API credits_used:      {balance_before.credits_used}\n"
                    f"API credit_limit:      {balance_before.credit_limit}\n"
                    f"UI .subscription-badge: {ui_balance_before}"
                ),
                name="Баланс ДО отправки",
                attachment_type=allure.attachment_type.TEXT,
            )
            # Если виджет на странице виден — он обязан сходиться с API до
            # ~0.001 кредита (округление отображения). Расхождение говорит
            # либо о рассинхроне фронта, либо о том, что мы читаем не тот
            # виджет — и то и другое стоит заметить прямо в тесте.
            if ui_balance_before is not None:
                assert abs(ui_balance_before - balance_before.credits_remaining) < 0.01, (
                    f"UI показывает {ui_balance_before}, API — "
                    f"{balance_before.credits_remaining}. Рассинхрон."
                )

        # Подписку на /api/chat/completions поднимаем ДО send_message —
        # иначе быстрый первый ответ может проскочить мимо слушателя.
        with main.capture_completions() as completions:
            with allure.step(f"3. Отправить сообщение: {prompt!r}"):
                # t_send — точка отсчёта «сколько ждали ответа».
                # perf_counter монотонный, системное время не скачет.
                t_send = time.perf_counter()
                main.send_message(prompt, submit_with="enter")

            with allure.step("4. URL должен смениться на /chat/<uuid>"):
                # На медленных моделях фронт меняет URL не сразу — ждёт,
                # пока `/api/v1/chats/new` вернёт id. Поэтому пугаться
                # секунд 30-40 на YandexGPT/GigaChat нормально.
                main.wait_for_chat_url(timeout=POST_SEND_UI_TIMEOUT)
                expect(authenticated_page).to_have_url(main.CHAT_URL_PATTERN)

                # Как только мы на /chat/<uuid> — это НАШ свежесозданный
                # чат. Регистрируем id для teardown-уборки на зелёном.
                chat_id = main.get_current_chat_id()
                assert chat_id, "Не удалось распарсить chat_id из URL"
                chat_cleaner.add(chat_id)
                model_metrics_recorder.set(chat_id=chat_id)
                allure.attach(
                    chat_id,
                    name="chat_id (для teardown)",
                    attachment_type=allure.attachment_type.TEXT,
                )

            with allure.step("5. Сообщение пользователя появилось в истории"):
                expect(
                    authenticated_page.locator(main.USER_MESSAGE_TEXT).last
                ).to_have_text(prompt, timeout=POST_SEND_UI_TIMEOUT)

            with allure.step(
                "6. Явное ожидание ДВУХ POST /api/chat/completions "
                "(стрим ответа + генерация заголовка)"
            ):
                result = main.wait_for_two_completions(
                    completions, timeout_ms=COMPLETIONS_TIMEOUT_MS
                )
                first_ms = int((result.first_done_at - t_send) * 1000)
                total_ms = int((result.second_done_at - t_send) * 1000)
                model_metrics_recorder.set(
                    first_completion_ms=first_ms,
                    total_ms=total_ms,
                )
                allure.attach(
                    (
                        f"1) {result.first.request.method} {result.first.url} "
                        f"→ {result.first.status}  [{first_ms} ms]\n"
                        f"2) {result.second.request.method} {result.second.url} "
                        f"→ {result.second.status}  [{total_ms} ms]"
                    ),
                    name="Completion-запросы",
                    attachment_type=allure.attachment_type.TEXT,
                )
                assert result.first.ok, (
                    f"Первый completion вернул {result.first.status}"
                )
                assert result.second.ok, (
                    f"Второй completion вернул {result.second.status}"
                )

        with allure.step("7. Ответ ассистента отрисован и не пустой"):
            # wait_for_two_completions уже гарантирует, что стрим закрыт —
            # но React может ещё раз пересобрать DOM. Страхуемся expect.
            response_locator = authenticated_page.locator(main.ASSISTANT_RESPONSE).first
            expect(response_locator).to_be_visible(timeout=POST_SEND_UI_TIMEOUT)
            expect(response_locator).not_to_have_text("", timeout=POST_SEND_UI_TIMEOUT)
            response_text = (response_locator.inner_text() or "").strip()
            allure.attach(
                response_text[:2000],
                name="Ответ ассистента (первые 2000 символов)",
                attachment_type=allure.attachment_type.TEXT,
            )

            assert response_text, (
                f"{model_name} вернула пустой ответ на промпт {prompt!r}"
            )

            lowered = response_text.lower()
            hit = next((m for m in ERROR_MARKERS if m in lowered), None)
            assert hit is None, (
                f"{model_name} вернула сообщение об ошибке "
                f"(маркер {hit!r}): {response_text[:300]!r}"
            )

        with allure.step(
            "8. Под ответом показано имя модели — и оно совпадает с выбранной"
        ):
            # Футер `.response-actions-container` рендерится ПОСЛЕ title-gen
            # и финализации chats/new — на холодном React-дереве ему нужно
            # ощутимо больше, чем 15с, которые мы ставили ранее.
            main.wait_for_response_model_trigger(timeout=POST_SEND_UI_TIMEOUT)
            actual = main.get_response_model_name()
            allure.attach(
                f"Выбрали: {model_name}\nОтветила (по UI): {actual}",
                name="Проверка авторства ответа",
                attachment_type=allure.attachment_type.TEXT,
            )
            assert actual == model_name, (
                f"Ответила не та модель: выбрали {model_name!r}, "
                f"а футер ответа показывает {actual!r}"
            )

        with allure.step(
            "9. Баланс списался: credits_remaining уменьшился на > 0"
        ):
            # Ждём, пока бэк зачислит usage в ledger — обычно в пределах
            # 1-3 секунд после закрытия стрима, но на YandexGPT/GigaChat
            # и на загруженном CI бывает 15-40с (биллинг батчится).
            # 60с — компромисс, достаточный для всех моделей из DIALOG_MODELS.
            balance_after = main.wait_for_balance_change(
                balance_before, timeout_ms=60_000
            )
            tokens_spent = round(
                balance_before.credits_remaining - balance_after.credits_remaining,
                6,
            )
            model_metrics_recorder.set(
                balance_after=balance_after.credits_remaining,
                tokens_spent=tokens_spent,
            )
            allure.attach(
                (
                    f"before: {balance_before.credits_remaining}\n"
                    f"after:  {balance_after.credits_remaining}\n"
                    f"spent:  {tokens_spent}"
                ),
                name="Списание токенов",
                attachment_type=allure.attachment_type.TEXT,
            )
            assert tokens_spent > 0, (
                f"{model_name}: баланс не изменился после запроса "
                f"(before={balance_before.credits_remaining}, "
                f"after={balance_after.credits_remaining}). "
                "Возможно, биллинг не списал токены."
            )
            # Страховка от противоположной аномалии — если баланс вырос,
            # значит мы ошиблись с органицацией / получили стейл-кэш /
            # биллинг вернул лишнее. В любом случае — это баг, не OK.
            assert tokens_spent < balance_before.credits_remaining, (
                f"{model_name}: списание {tokens_spent} больше, чем был "
                f"на балансе {balance_before.credits_remaining}. "
                "Похоже, что-то не так с биллингом."
            )

        with allure.step(
            "10. Счётчик «Сегодня» в Настройках вырос ровно на +1"
        ):
            # Бэк начисляет статистику АСИНХРОННО, причём для разных моделей
            # с разной задержкой: Sonnet/GPT — 1-3с, Opus/Gemini/GigaChat —
            # иногда 60+с. Поэтому поллим /settings до тех пор, пока не
            # увидим ровно +1 (и одновременно глобальный счётчик
            # сдвинулся вперёд — это «индикатор свежести» данных).
            expected_model_after = model_today_before + 1

            deadline = time.monotonic() + COUNTER_POLL_TIMEOUT_S
            attempts: list[str] = []
            total_today_after = total_today_before
            model_today_after = model_today_before

            while time.monotonic() < deadline:
                total_today_after, model_today_after = _snapshot_today_stats(
                    authenticated_page, aliases
                )
                attempts.append(
                    f"total={total_today_after} {model_name}={model_today_after}"
                )
                if (
                    total_today_after > total_today_before
                    and model_today_after >= expected_model_after
                ):
                    break
                authenticated_page.wait_for_timeout(COUNTER_POLL_STEP_MS)

            model_metrics_recorder.set(
                total_today_after=total_today_after,
                model_today_after=model_today_after,
                requests_counter_delta=model_today_after - model_today_before,
            )
            allure.attach(
                "\n".join(attempts),
                name="Поллинг статистики (попытки)",
                attachment_type=allure.attachment_type.TEXT,
            )
            allure.attach(
                (
                    f"total_today_before = {total_today_before}\n"
                    f"total_today_after  = {total_today_after}\n"
                    f"{model_name}_before = {model_today_before}\n"
                    f"{model_name}_after  = {model_today_after}\n"
                    f"expected_model_after = {expected_model_after}"
                ),
                name="Счётчики статистики ПОСЛЕ vs ДО",
                attachment_type=allure.attachment_type.TEXT,
            )

            # Глобальный счётчик ОБЯЗАН вырасти — иначе бэк просто не учёл
            # наш запрос (или фронт продолжает показывать кеш — но мы же
            # на КАЖДОЙ итерации делаем page.goto, так что это исключено).
            assert total_today_after > total_today_before, (
                f"Глобальный счётчик «Сегодня» не вырос за "
                f"{COUNTER_POLL_TIMEOUT_S}с: было {total_today_before}, "
                f"осталось {total_today_after}. Бэк не учёл запрос."
            )
            assert model_today_after == expected_model_after, (
                f"Счётчик {model_name} должен увеличиться на +1, "
                f"но было {model_today_before}, стало {model_today_after}"
            )
