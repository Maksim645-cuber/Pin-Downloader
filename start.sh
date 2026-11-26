#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 не найден. Установите Python 3.10 или новее."
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Нужен Python версии 3.10 или новее."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Создаём виртуальное окружение..."
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -r requirements.txt

echo "Откройте в браузере: http://127.0.0.1:5000"
python app.py
