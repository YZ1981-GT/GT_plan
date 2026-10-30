# -*- coding: utf-8 -*-
"""jieba / pypinyin 延迟到首次真实能力调用（R5.2）。

6 轮交替 fresh-process A/B：app.main 基线中位 4247.9ms，候选 3940.9ms，净省 307.0ms；
候选 import app.main 后两个第三方包都不在 sys.modules。只有超过 50ms 门槛才保留本改动。
"""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace


def test_app_main_defers_both_packages_until_first_real_call():
    backend = Path(__file__).resolve().parents[1]
    code = r'''
import sys
import app.main
assert "jieba" not in sys.modules
assert "pypinyin" not in sys.modules
from app.services._zh_tokenize import zh_tokenize
from app.services.global_search_service import _pinyin_initials
assert "应收账款" in zh_tokenize("应收账款")
assert _pinyin_initials("应收账款") == "yszk"
assert "jieba" in sys.modules
assert "pypinyin" in sys.modules
print("ok")
'''
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=backend,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "ok"


def test_jieba_concurrent_first_use_imports_once(monkeypatch):
    from app.services import _zh_tokenize as mod

    calls = 0

    class FakeJieba:
        @staticmethod
        def load_userdict(_path):
            return None

        @staticmethod
        def cut(text):
            return [text]

    def fake_import(name: str):
        nonlocal calls
        assert name == "jieba"
        calls += 1
        return FakeJieba()

    monkeypatch.setattr(mod, "JIEBA_AVAILABLE", True)
    monkeypatch.setattr(mod, "jieba", None)
    monkeypatch.setattr(mod, "_DICT_LOADED", False)
    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(mod.zh_tokenize, ["应收账款"] * 16))
    assert results == [["应收账款"]] * 16
    assert calls == 1


def test_pypinyin_concurrent_first_use_imports_once(monkeypatch):
    from app.services import global_search_service as mod

    calls = 0

    def fake_lazy(text: str, *, style):
        assert style == "first"
        return ["y", "s", "z", "k"] if text else []

    def fake_import(name: str):
        nonlocal calls
        assert name == "pypinyin"
        calls += 1
        return SimpleNamespace(lazy_pinyin=fake_lazy, Style=SimpleNamespace(FIRST_LETTER="first"))

    monkeypatch.setattr(mod, "_PYPINYIN_AVAILABLE", True)
    monkeypatch.setattr(mod, "_PINYIN_TOOLS", None)
    monkeypatch.setattr(mod.importlib, "import_module", fake_import)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(mod._pinyin_initials, ["应收账款"] * 16))
    assert results == ["yszk"] * 16
    assert calls == 1
