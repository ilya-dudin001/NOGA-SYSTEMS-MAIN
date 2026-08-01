# Проверка observability чата: логи не должны содержать body/filename/JWT.
# Запуск из корня: python backend/tests/check_chat_log_hygiene.py
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "backend" / "app" / "api" / "chat.py",
    ROOT / "backend" / "app" / "services" / "chat.py",
    ROOT / "backend" / "app" / "services" / "chat_broker.py",
    ROOT / "backend" / "app" / "services" / "chat_notifications.py",
]

# Подозрительные паттерны в строках логирования (не в Content-Disposition filename=).
FORBIDDEN = [
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*original_name", re.I),
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*\bbody\b", re.I),
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*preview", re.I),
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*Bearer", re.I),
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*access_token", re.I),
    re.compile(r"logger\.(?:info|warning|error|exception|debug)\([^)]*content\s*=", re.I),
]


def main() -> int:
    failed = []
    for path in TARGETS:
        if not path.exists():
            failed.append(f"missing {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "logger." not in line:
                continue
            for pat in FORBIDDEN:
                if pat.search(line):
                    failed.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    if failed:
        print("FAIL: возможные утечки в логах чата:")
        for item in failed:
            print(" ", item)
        return 1
    print("ok: chat log hygiene — body/filename/JWT не логируются")
    return 0


if __name__ == "__main__":
    sys.exit(main())
