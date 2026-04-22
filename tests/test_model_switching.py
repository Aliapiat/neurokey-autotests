"""
Ported from `neurokey-react/e2e/tests/model-switching.spec.ts`.
"""

import re

import allure
import pytest
from playwright.sync_api import Page, expect

from pages.main_page import MainPage


MODEL_NAME_RE = re.compile(r"claude|gpt|gemini|nano banana|seedream", re.I)


@allure.epic("Модели")
@allure.feature("Переключение моделей")
class TestModelSwitching:

    @allure.title("Блок популярных моделей содержит несколько карточек")
    @pytest.mark.models
    def test_popular_models_section(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_popular_models()

        expect(
            authenticated_page.get_by_role("heading", name=MODEL_NAME_RE).first
        ).to_be_visible()

    @allure.title("Заголовок описывает мультимодельный value prop")
    @pytest.mark.models
    def test_headline_mentions_multi_model(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_be_loaded()

        expect(
            authenticated_page.get_by_text(re.compile(r"ChatGPT.*другим нейросетям", re.I))
        ).to_be_visible()

    @allure.title("Клик по карточке модели оставляет пользователя в авторизованной зоне")
    @pytest.mark.models
    def test_click_model_card_keeps_authed(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()

        card = authenticated_page.get_by_role("heading", name=MODEL_NAME_RE).first
        expect(card).to_be_visible(timeout=15_000)
        card.click()

        expect(authenticated_page).not_to_have_url(re.compile(r"/login"))
