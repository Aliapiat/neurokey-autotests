"""
Журнал времени ответов моделей.

Каждый прогон модельного теста приписывает одну строку в CSV:

    timestamp_utc, env, model, prompt, prompt_len, first_completion_ms,
    total_ms, status, chat_id, error

Файл живёт в `reports/model_response_times.csv` (gitignored). Если запуск
идёт под `pytest-xdist`, каждый воркер пишет в собственный суффиксный файл
(`...gw0.csv`, `...gw1.csv`), чтобы избежать гонок на append'ах — а потом
их можно просто склеить `cat` или импортировать каждый отдельно в Excel.

Для одиночного запуска всё попадает в один `model_response_times.csv`.

Почему CSV, а не sqlite/duckdb/parquet:
- минимум зависимостей, ни один CI-раннер не сломается;
- открывается в Excel / Google Sheets / pandas за один клик;
- append append атомарен на строку при разумных размерах записи
  (единицы килобайт << PIPE_BUF).
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import threading
from pathlib import Path
from typing import Any, Mapping

# Одна блокировка на процесс — защищает append внутри одного pytest-воркера
# (когда-нибудь может появиться многопоточный тест). Между процессами xdist
# блокировка не действует, но мы разносим файлы по воркерам — см. ниже.
_WRITE_LOCK = threading.Lock()

# Единый порядок колонок в CSV. Менять — только с версионированием файла,
# иначе ранее записанные строки начнут ехать относительно заголовка.
FIELDNAMES: tuple[str, ...] = (
    "timestamp_utc",
    "env",
    "model",
    "prompt",
    "prompt_len",
    "first_completion_ms",
    "total_ms",
    "balance_before",
    "balance_after",
    "tokens_spent",
    "status",
    "chat_id",
    "error",
)


def _reports_dir() -> Path:
    """Папка `reports/` в корне autotests-проекта.

    Этот файл лежит в `utils/`, поэтому корень — родитель нашего каталога.
    Не полагаемся на CWD, чтобы запуск из любой директории (`pytest tests/`,
    из IDE, из CI) писал ровно в одно и то же место.
    """
    return Path(__file__).resolve().parent.parent / "reports"


def _csv_path() -> Path:
    """Путь к CSV с учётом воркера xdist.

    Без xdist переменной `PYTEST_XDIST_WORKER` нет — тогда просто
    `model_response_times.csv`. Под xdist получим `...gw0.csv` и т.д.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    name = (
        f"model_response_times.{worker}.csv"
        if worker
        else "model_response_times.csv"
    )
    return _reports_dir() / name


def append_row(row: Mapping[str, Any]) -> Path:
    """Дописать одну запись в CSV. Создаёт файл и заголовок при первом вызове.

    Неизвестные ключи из `row` игнорируются. Отсутствующие заполняются ''.
    """
    path = _csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = {field: row.get(field, "") for field in FIELDNAMES}

    with _WRITE_LOCK:
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=FIELDNAMES,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(normalized)

    return path


def utc_now_iso() -> str:
    """ISO-8601 UTC с точностью до секунды — ровно как принято в логах."""
    return (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class ModelMetricsRecorder:
    """Аккумулятор данных одного теста.

    Используется как фикстура — см. `conftest.model_metrics_recorder`.
    Тест заполняет поля через `.set(...)`, а фикстура на teardown
    пишет собранное в CSV вместе со статусом (passed/failed/...).
    """

    def __init__(self, *, env: str) -> None:
        self._data: dict[str, Any] = {"env": env}
        self._armed = False

    def set(self, **kwargs: Any) -> None:
        """Записать/перезаписать поля. Безопасно для повторных вызовов."""
        self._data.update(kwargs)
        self._armed = True

    def is_armed(self) -> bool:
        """True, если в тесте было хоть одно `.set(...)`.

        Если тест свалился на подготовке (логин/открытие страницы) и
        ничего не замерил — строку в CSV не пишем, чтобы не плодить шум.
        """
        return self._armed

    def snapshot(self) -> dict[str, Any]:
        """Копия данных — для предохранительной передачи наружу."""
        return dict(self._data)
