"""
Ported from `neurokey-react/e2e/tests/messaging.spec.ts`.
"""

import allure
import pytest
from playwright.sync_api import Page, expect

from pages.main_page import MainPage


@allure.epic("Чат")
@allure.feature("Отправка сообщений")
class TestMessaging:

    @allure.title("Поле ввода чата видно на главной")
    @pytest.mark.smoke
    @pytest.mark.messaging
    def test_chat_input_visible(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_chat_input()

    @allure.title("Пользователь может ввести сообщение")
    @pytest.mark.messaging
    def test_user_can_type_message(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_chat_input()

        main.type_message("Привет, модель!")
        assert main.get_chat_input_value() == "Привет, модель!"

    @allure.title("Кнопка 'Поиск' доступна на десктопе")
    @pytest.mark.messaging
    def test_search_button_visible_desktop(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_search_button()

    @allure.title("Поле ввода очищается между значениями")
    @pytest.mark.messaging
    def test_input_clears_between_values(self, authenticated_page: Page):
        main = MainPage(authenticated_page)
        main.open()
        main.should_show_chat_input()

        main.type_message("первое сообщение")
        assert main.get_chat_input_value() == "первое сообщение"

        main.type_message("")
        assert main.get_chat_input_value() == ""

        main.type_message("второе")
        assert main.get_chat_input_value() == "второе"
