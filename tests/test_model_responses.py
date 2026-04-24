"""
Параметризованный smoke на КАЖДУЮ диалоговую модель:

1. Логинимся (фикстура `authenticated_page`).
2. В композере открываем селектор моделей и выбираем целевую модель.
3. Фейкером генерируем запрос из 3 слов и отправляем его.
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

import time

import allure
import pytest
from faker import Faker
from playwright.sync_api import Page, expect

from pages.main_page import MainPage
from test_data.models import DIALOG_MODELS


# Faker с дефолтной (англ.) локалью — слова короткие и гарантированно
# читаются любой моделью, включая YandexGPT / GigaChat.
fake = Faker()


def _three_word_prompt() -> str:
    """Ровно три слова, разделённые пробелом. Никакой пунктуации — чтобы
    промпт был детерминированно из трёх слов."""
    return " ".join(fake.words(nb=3))


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
COMPLETIONS_TIMEOUT_MS = 180_000


@allure.epic("Модели")
@allure.feature("Каждая модель отвечает на запрос")
@pytest.mark.real_backend
@pytest.mark.models
@pytest.mark.chat
class TestModelAnswers:

    @pytest.mark.parametrize("model_name", DIALOG_MODELS, ids=DIALOG_MODELS)
    @allure.title("{model_name} отвечает на запрос из 3 слов (faker)")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_model_answers_three_word_prompt(
        self,
        authenticated_page: Page,
        chat_cleaner,
        model_metrics_recorder,
        model_name: str,
    ):
        main = MainPage(authenticated_page)

        with allure.step("1. Открыть главную и закрыть онбординг-попап"):
            main.open()
            main.dismiss_group_chats_popup()
            main.should_be_loaded()
            main.should_show_chat_input()

        with allure.step(f"2. Выбрать в композере модель {model_name!r}"):
            main.select_model(model_name)

        prompt = _three_word_prompt()
        allure.attach(
            prompt,
            name="Промпт (3 слова от faker)",
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
                main.wait_for_chat_url(timeout=20_000)
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
                ).to_have_text(prompt, timeout=10_000)

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
            expect(response_locator).to_be_visible(timeout=30_000)
            expect(response_locator).not_to_have_text("", timeout=30_000)
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
            main.wait_for_response_model_trigger(timeout=15_000)
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
            # 1-3 секунд после закрытия стрима, иногда дольше на медленных
            # моделях/платформах.
            balance_after = main.wait_for_balance_change(
                balance_before, timeout_ms=15_000
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
