"""一次性诊断脚本：先 import 全部 workpaper_sync 测试模块（触发 import 期污染），
再在同进程内跑 test_task13_contract_registry.py。用完即删。"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TESTS = BACKEND / "tests" / "workpaper_sync"
TARGET = "test_task13_contract_registry"

failed_imports: list[str] = []
imported = 0
for path in sorted(TESTS.glob("test_*.py")):
    name = path.stem
    if name == TARGET:
        continue
    try:
        importlib.import_module(f"tests.workpaper_sync.{name}")
        imported += 1
    except Exception as exc:  # noqa: BLE001
        failed_imports.append(f"{name}: {type(exc).__name__}: {exc}")

print(f"[probe] imported={imported} failed={len(failed_imports)}")
for line in failed_imports:
    print("  [import-fail]", line)

import pytest  # noqa: E402

code = pytest.main(
    [
        str(TESTS / f"{TARGET}.py"),
        "-p", "no:randomly",
        "-q", "--no-header", "--tb=line",
    ]
)
print(f"[probe] pytest exit={code}")
sys.exit(int(code))
