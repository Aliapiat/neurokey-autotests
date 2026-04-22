"""Быстрый sanity-чек: парсим все .py файлы проекта в AST."""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
errors = []
for f in ROOT.rglob("*.py"):
    if ".venv" in f.parts or "venv" in f.parts:
        continue
    try:
        ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append((str(f), e))

if errors:
    for f, e in errors:
        print(f"SYNTAX ERROR: {f}: {e}")
    sys.exit(1)
print(f"OK: parsed {sum(1 for _ in ROOT.rglob('*.py'))} files")
