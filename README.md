# Neurokey Autotests

E2E автотесты для фронтенда [Нейроключа](https://wmt1.acm-ai.ru/) — мультимодельного AI-чата (React 19 + Vite + TypeScript). Написаны на **Playwright + Python + pytest**, отчёты — **Allure**.

## О проекте

Neurokey / Нейроключ — SPA-чат с доступом к различным LLM / image / video моделям. В автотестах покрываем:

- **Авторизация**: UI, HTML5-валидация, реальный логин, неверные креды (через мок `/api/v1/auths/signin`).
- **Создание чата**, **сообщения**, **переключение моделей** — поверх реального логина.
- **Адаптивная вёрстка**: small (≤440px) / medium (441–975px) / large (≥976px).

## Стенды

| Env  | URL                          | Запуск в CI      |
| ---- | ---------------------------- | ---------------- |
| dev  | https://wmt1.acm-ai.ru/      | на каждый push   |
| prod | https://app.neiroklyuch.ru/  | только вручную   |

## Локальный запуск

```bash
# 1. Создать venv и поставить зависимости
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install --with-deps chromium

# 2. Заполнить .env (файл создан, не коммитится)
#    ADMIN_EMAIL=...
#    ADMIN_PASSWORD=...
#    HEADLESS=false

# 3. Запуск
pytest --env dev                       # все тесты на dev
pytest --env prod -m smoke             # smoke на prod
pytest -m login                        # только логин
pytest -k test_successful_login        # по имени
pytest -n 4                            # параллельно (xdist)

# Или .bat-обвязка
run_tests.bat --env dev -m smoke
```

## Маркеры

```text
smoke        - критический путь
login        - тесты логина
auth         - общие тесты авторизации / редиректы
chat         - создание чата
messaging    - сообщения
models       - переключение моделей
responsive   - адаптивная вёрстка
real_backend - требуют реальных кредов
```

## Allure локально

```bash
# Запустить тесты → результаты улетают в allure-results/
pytest --env dev

# Сгенерировать отчёт
allure generate allure-results --clean -o allure-report
allure open allure-report
```

## CI (GitHub Actions)

Workflow `.github/workflows/tests.yml`:

- **push в main** → прогон только на `dev`.
- **workflow_dispatch** → выбор: `dev` / `prod` / `all` + область тестов.
- Каждый стенд деплоится в gh-pages отдельной подпапкой (`/dev/`, `/prod/`).
- На корне — индексная страница с кнопками для переключения между стендами.

### Secrets, которые нужно завести в репозитории

- `ADMIN_EMAIL_DEV`, `ADMIN_PASSWORD_DEV`
- `ADMIN_EMAIL_PROD`, `ADMIN_PASSWORD_PROD`

## Структура

```text
neurokey-autotests/
├── config/                 # environments.py, settings.py
├── pages/                  # POM: base_page, login_page, main_page
├── tests/                  # test_*.py + conftest.py (фикстуры страниц)
├── utils/                  # auth_storage, mocks, helpers
├── components/             # общие компоненты UI (расширяемо)
├── test_data/              # данные для параметризации
├── scripts/                # вспомогательные скрипты
├── .github/workflows/      # tests.yml
├── conftest.py             # pytest_addoption --env
├── pytest.ini
├── requirements.txt
├── run_tests.bat
├── .env / .env.example     # (.env gitignored)
└── .gitignore
```

## Что уже покрыто

| Файл                        | Сценарии                                        |
| --------------------------- | ----------------------------------------------- |
| `test_auth.py`              | UI логина, невалидные креды, редиректы          |
| `test_login.py`             | UI / позитив / регистр / пробелы / XSS / a11y   |
| `test_chat_creation.py`     | Попадание в чат, сайдбар, кнопка "Новый чат"   |
| `test_messaging.py`         | Поле ввода сообщений, ввод текста               |
| `test_model_switching.py`   | Популярные модели, переключение                 |
| `test_responsive.py`        | small / medium / large брейкпоинты              |

## Конвенции

- **Локаторы** — через `get_by_role` / `get_by_placeholder` / `get_by_text`, не через классы.
- **Ожидания** — через `expect(...)` из `playwright.sync_api` (автоматический ретрай).
- **Скриншот при падении** — автоматически, через `pytest_runtest_makereport`.
- **Лейбл стенда** в Allure выставляется в `tests/conftest.py` через `allure.dynamic.label("parentSuite", ...)`.
