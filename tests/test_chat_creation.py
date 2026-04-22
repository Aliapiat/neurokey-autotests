"""
Ported from `neurokey-react/e2e/tests/chat-creation.spec.ts`.

Работает через реальный логин (fixture `authenticated_page`). Если
кредов нет — тесты пропускаются.
"""

import re

import allure
import pytest
from playwright.sync_api import Page, expect

from pages.main_page import MainPage


@allure.epic("Чат")
@allure.feature("Создание чата")
class TestChatCreation:

    @allure.title("Авторизованный пользователь попадает на главный чат")
    @pytest.mark.smoke
    @pytest.mark.chat
    def test_authed_user_lands_on_main(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        expect(authenticated_page).not_to_have_url(re.compile(r"/login"))
        main.should_be_loaded()


@allure.epic("Чат")
@allure.feature("Сайдбар (desktop)")
class TestDesktopSidebar:

    @allure.title("В сайдбаре виден пункт 'Новый чат'")
    @pytest.mark.chat
    def test_sidebar_new_chat_visible(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_new_chat_button()

    @allure.title("В сайдбаре виден поиск по чатам")
    @pytest.mark.chat
    def test_sidebar_search_visible(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_search_input()

    @allure.title("Клик по 'Новый чат' оставляет пользователя в авторизованной зоне")
    @pytest.mark.chat
    def test_new_chat_keeps_authed(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.click_new_chat()

        # После клика URL не должен уйти на /login
        expect(authenticated_page).not_to_have_url(re.compile(r"/login"), timeout=10_000)
