"""
Журнал прогонов модельных тестов.

Каждый прогон параметризованного теста (одна модель → одна строка) дописывает
в `reports/model_response_times.csv` запись в фиксированном формате:

    A. Дата/время              (локальное, ISO `YYYY-MM-DD HH:MM:SS`)
    B. Модель                  (display-имя, как в селекторе композера)
    C. Токенов ДО              (credits_remaining до отправки запроса)
    D. Токенов ПОСЛЕ           (credits_remaining после биллинга)
    E. Списалось (=C-D)        ← Excel-формула, не редактируется руками
    F. Списалось (тест)        (то же значение, но посчитанное в тесте —
                                нужно для перекрёстной сверки с биллингом)
    G. Совпало                 ← Excel-формула =E=F (TRUE/FALSE)
    H. Время ответа, сек       (от отправки до второго `chat/completions` —
                                полностью завершённый поток + title-gen)
    I. Запросов ДО             (счётчик «Сегодня» по этой модели в /settings)
    J. Запросов ПОСЛЕ          (тот же счётчик после прогона)
    K. Разница (=J-I)          ← Excel-формула
    L. Разница = 1             ← Excel-формула =K=1 (должно быть TRUE)
    M. Окружение               (dev / stage / prod — из settings.CURRENT_ENV)
    N. Промпт                  (текст, который ушёл в модель)
    O. Длина промпта           (len(prompt) — для дашборда «короткие/длинные»)
    P. Время 1-го ответа, сек  (когда пришёл ПЕРВЫЙ chat/completions —
                                полезно отделять «модель ответила» от
                                «UI всё дорендерил»)
    Q. Запросов всего ДО       (глобальный счётчик «Сегодня: N запросов»)
    R. Запросов всего ПОСЛЕ    (он же после прогона)
    S. Разница всего (=R-Q)    ← Excel-формула
    T. Разница ≥ 1             ← Excel-формула =S>=1 (должно быть TRUE; точное
                                +1 не гарантировано — параллельные тесты
                                других моделей увеличивают тот же счётчик)
    U. chat_id                 (uuid созданного чата, для разбора падений)
    V. Статус                  (passed / failed / skipped / setup_error)
    W. Ошибка                  (короткое описание исключения, если упало)
    X. timestamp_utc           (UTC ISO-8601 — для CI и кросс-таймзон)

Формат файла:
- кодировка `utf-8-sig` (BOM) — Excel-RU открывает кириллицу без танцев;
- разделитель `;` — стандарт для русской локали Excel;
- формулы пишутся литерально (`=C2-D2`), Excel вычисляет их при открытии.

Если файл уже существует, но его заголовок не совпадает с текущей схемой
(например, осталась старая структура от прошлой версии тестов), мы
переименовываем его в `model_response_times.<UTC>.bak.csv` и стартуем
с чистого листа — иначе строки разъедутся относительно колонок.

Под `pytest-xdist` каждый воркер пишет в собственный суффиксный файл
(`...gw0.csv`, `...gw1.csv`) — так избегаем гонок на append'ах.
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Mapping

# Одна блокировка на процесс — защищает append внутри одного pytest-воркера.
# Между процессами xdist блокировка не действует — мы разносим файлы по
# воркерам, см. `_csv_path()`.
_WRITE_LOCK = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────
# Схема CSV
# ─────────────────────────────────────────────────────────────────────────
#
# `FIELDNAMES` — внутренние ключи, по которым тест/фикстура передают данные.
# `HEADERS`    — то, что видит пользователь в первой строке файла.
# Порядок строго совпадает: i-й ключ соответствует i-й колонке.

FIELDNAMES: tuple[str, ...] = (
    "timestamp",                  # A
    "model",                      # B
    "tokens_before",              # C
    "tokens_after",                # D
    "tokens_diff_formula",        # E (Excel-формула)
    "tokens_spent_test",          # F
    "tokens_match_formula",       # G (Excel-формула)
    "response_time_s",            # H
    "requests_before",            # I
    "requests_after",             # J
    "requests_delta_formula",     # K (Excel-формула)
    "requests_one_formula",       # L (Excel-формула)
    "env",                        # M
    "prompt",                     # N
    "prompt_len",                 # O
    "first_response_s",           # P
    "total_requests_before",      # Q
    "total_requests_after",       # R
    "total_delta_formula",        # S (Excel-формула)
    "total_delta_ge1_formula",    # T (Excel-формула)
    "chat_id",                    # U
    "status",                     # V
    "error",                      # W
    "timestamp_utc",              # X
)

HEADERS: tuple[str, ...] = (
    "Дата/время",                      # A
    "Модель",                          # B
    "Токенов ДО",                      # C
    "Токенов ПОСЛЕ",                   # D
    "Списалось (=C-D)",                # E
    "Списалось (тест)",                # F
    "Совпало (=E=F)",                  # G
    "Время ответа, сек",               # H
    "Запросов ДО",                     # I
    "Запросов ПОСЛЕ",                  # J
    "Разница запросов (=J-I)",         # K
    "Разница = 1 (=K=1)",              # L
    "Окружение",                       # M
    "Промпт",                          # N
    "Длина промпта",                   # O
    "Время 1-го ответа, сек",          # P
    "Запросов всего ДО",               # Q
    "Запросов всего ПОСЛЕ",            # R
    "Разница всего (=R-Q)",            # S
    "Разница всего ≥ 1 (=S>=1)",       # T
    "chat_id",                         # U
    "Статус",                          # V
    "Ошибка",                          # W
    "timestamp_utc",                   # X
)

assert len(FIELDNAMES) == len(HEADERS), "Схема CSV рассинхронизирована"

# Колонки-формулы. Ключ — имя поля в FIELDNAMES, значение — шаблон Excel'я,
# где `{n}` подставится номером строки в файле (1-индексированно, шапка = 1).
_FORMULA_TEMPLATES: dict[str, str] = {
    "tokens_diff_formula":      "=C{n}-D{n}",
    "tokens_match_formula":     "=E{n}=F{n}",
    "requests_delta_formula":   "=J{n}-I{n}",
    "requests_one_formula":     "=K{n}=1",
    "total_delta_formula":      "=R{n}-Q{n}",
    "total_delta_ge1_formula":  "=S{n}>=1",
}

_CSV_DIALECT = {
    "delimiter": ";",
    "quoting": csv.QUOTE_MINIMAL,
}
_CSV_ENCODING = "utf-8-sig"  # BOM, чтобы Excel-RU видел кириллицу


# ─────────────────────────────────────────────────────────────────────────
# Пути
# ─────────────────────────────────────────────────────────────────────────

def _reports_dir() -> Path:
    """Папка `reports/` в корне autotests-проекта.

    Этот файл лежит в `utils/`, поэтому корень — родитель нашего каталога.
    Не полагаемся на CWD: запуск из любой директории (pytest, IDE, CI)
    пишет ровно в одно и то же место.
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


# ─────────────────────────────────────────────────────────────────────────
# Утилиты
# ─────────────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    """ISO-8601 UTC с точностью до секунды — оставлено для обратной
    совместимости со старыми вызовами (некоторые тесты могут писать в
    `recorder` поле `timestamp_utc` руками)."""
    return (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def local_now_iso() -> str:
    """Локальное время в формате `YYYY-MM-DD HH:MM:SS` — то, что пишем в
    колонку A. Локальное удобнее, потому что отчёт смотрят глазами в Excel,
    и UTC ломает интуицию («запустил в 22:00, а в файле 19:00»)."""
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_number(value: Any) -> Any:
    """Округлить float'ы для записи в CSV.

    Сам формат (точка vs запятая) подменяется уже при записи в файле —
    см. `_format_for_csv(...)`. Здесь только округляем, чтобы в JSON-
    дампах снапшотов в Allure-аттаче не висели хвосты `0.099999...`.
    """
    if isinstance(value, float):
        return round(value, 6)
    return value


def _format_for_csv(value: Any) -> str:
    """Привести любое значение к строке для записи в ячейку CSV.

    Главное правило для русского Excel: десятичный разделитель — запятая,
    а не точка. Иначе Excel-RU видит «7898.296» как ТЕКСТ, а не число —
    и формулы (=C-D и т.п.) перестают считать. Делимитер у нас `;`,
    поэтому замена `.` → `,` не ломает CSV-парсинг (запятая нигде не
    разделитель столбцов).

    Округление float'ов до 6 знаков — чтобы не было хвостов
    `0.0999999999...` после арифметики с балансом.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # bool — подкласс int, но в CSV его лучше писать словами.
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return f"{round(value, 6)}".replace(".", ",")
    return str(value)


def _to_csv_row(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Перевод «богатого» снапшота фикстуры в плоскую строку CSV-схемы.

    Тест/фикстура работают со своими ключами (`balance_before`,
    `model_today_after`, `total_ms`...) — здесь они мапятся на наши
    A..L. Поля, которых нет в снапшоте, оставляем пустыми: формулы Excel
    с пустой ячейкой считаются как 0, что корректно отражает ситуацию
    «тест не дошёл до этого замера».
    """
    def _ms_to_s(ms: Any) -> Any:
        if isinstance(ms, (int, float)) and ms > 0:
            return round(ms / 1000.0, 2)
        return ""

    prompt = snapshot.get("prompt", "")
    # Длина считается здесь, а не на стороне теста, чтобы CSV всегда был
    # консистентен (если кто-то забыл `recorder.set(prompt_len=...)` — у
    # нас всё равно будет валидное число рядом с самим промптом).
    prompt_len: Any = len(prompt) if isinstance(prompt, str) and prompt else ""

    return {
        "timestamp":         snapshot.get("timestamp_local") or local_now_iso(),
        "model":             snapshot.get("model", ""),
        "tokens_before":     _fmt_number(snapshot.get("balance_before", "")),
        "tokens_after":      _fmt_number(snapshot.get("balance_after", "")),
        # E — формула, заполняется в `append_row` по номеру строки.
        "tokens_diff_formula": "",
        "tokens_spent_test": _fmt_number(snapshot.get("tokens_spent", "")),
        # G — формула.
        "tokens_match_formula": "",
        "response_time_s":   _ms_to_s(snapshot.get("total_ms")),
        "requests_before":   snapshot.get("model_today_before", ""),
        "requests_after":    snapshot.get("model_today_after", ""),
        # K, L — формулы.
        "requests_delta_formula": "",
        "requests_one_formula":   "",
        # M..X — расширенные метаданные прогона.
        "env":               snapshot.get("env", ""),
        "prompt":            prompt,
        "prompt_len":        prompt_len,
        "first_response_s":  _ms_to_s(snapshot.get("first_completion_ms")),
        "total_requests_before": snapshot.get("total_today_before", ""),
        "total_requests_after":  snapshot.get("total_today_after", ""),
        # S, T — формулы.
        "total_delta_formula":     "",
        "total_delta_ge1_formula": "",
        "chat_id":           snapshot.get("chat_id", ""),
        "status":            snapshot.get("status", ""),
        "error":             snapshot.get("error", ""),
        "timestamp_utc":     snapshot.get("timestamp_utc") or utc_now_iso(),
    }


def _existing_header_matches(path: Path) -> bool:
    """Считываем первую строку и сравниваем с эталонной шапкой.

    Если файл пустой / битый / по другой схеме — вернётся False, и
    `append_row` отправит его в `.bak`. Любая ошибка чтения трактуется
    как «несовпадение» — мы лучше переименуем и стартуем с нуля,
    чем будем дописывать в кривое.
    """
    try:
        with path.open("r", encoding=_CSV_ENCODING, newline="") as fh:
            reader = csv.reader(fh, **_CSV_DIALECT)
            first = next(reader, None)
    except Exception:
        return False
    return tuple(first or ()) == HEADERS


def _archive_with_old_schema(path: Path) -> Path:
    """Переименовать существующий файл в `.<utc>.bak.csv`.

    Используем именно копирование+удаление: Path.rename на Windows может
    падать, если файл открыт в Excel. shutil.move с фолбэком надёжнее.
    """
    suffix = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(f"{path.stem}.{suffix}.bak.csv")
    shutil.move(str(path), str(bak))
    return bak


# ─────────────────────────────────────────────────────────────────────────
# Запись
# ─────────────────────────────────────────────────────────────────────────

def append_row(snapshot: Mapping[str, Any]) -> Path:
    """Дописать одну запись в CSV. Создаёт файл и шапку при первом вызове.

    Возвращает путь к файлу, в который физически записали (полезно
    приклеить в Allure).
    """
    path = _csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    row = _to_csv_row(snapshot)

    with _WRITE_LOCK:
        # 1) Если есть файл, но шапка чужая — отправляем в архив.
        if path.exists() and path.stat().st_size > 0:
            if not _existing_header_matches(path):
                _archive_with_old_schema(path)

        file_exists = path.exists() and path.stat().st_size > 0

        # 2) Считаем номер новой строки в файле (1-индексированный).
        # Header (если уже есть) занимает строку 1, дальше идут данные.
        if file_exists:
            with path.open("rb") as fh:
                # Достаточно посчитать `\n` — последний перевод строки
                # после writerow гарантирован csv.writer.
                line_count = sum(1 for _ in fh)
            next_row_idx = line_count + 1
        else:
            # Пишем шапку (строка 1) и сразу данные (строка 2).
            next_row_idx = 2

        # 3) Подставляем формулы под этот номер строки.
        for key, template in _FORMULA_TEMPLATES.items():
            row[key] = template.format(n=next_row_idx)

        # 4) Пишем.
        # newline="" обязателен для csv (иначе на Windows получим пустые
        # строки между записями). Каждое значение прогоняем через
        # `_format_for_csv` — там же float'ы превращаются в "X,YYY"
        # (запятая вместо точки) для корректного открытия в Excel-RU.
        with path.open("a", newline="", encoding=_CSV_ENCODING) as fh:
            writer = csv.writer(fh, **_CSV_DIALECT)
            if not file_exists:
                writer.writerow(HEADERS)
            writer.writerow([_format_for_csv(row[k]) for k in FIELDNAMES])

    return path


# ─────────────────────────────────────────────────────────────────────────
# Recorder — фасад для теста
# ─────────────────────────────────────────────────────────────────────────

class ModelMetricsRecorder:
    """Аккумулятор данных одного теста.

    Используется как фикстура — см. `conftest.model_metrics_recorder`.
    Тест заполняет поля через `.set(...)`, а фикстура на teardown
    кладёт собранное в CSV. Имена ключей — «человеческие» (balance_before,
    model_today_after, total_ms и т.п.), а маппинг в колонки A..L делается
    в `_to_csv_row(...)`.
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
        """Копия данных — чтобы фикстура не правила внутреннее состояние."""
        return dict(self._data)
