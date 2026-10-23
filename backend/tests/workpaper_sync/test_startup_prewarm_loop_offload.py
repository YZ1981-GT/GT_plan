"""启动预热 / 冷注册不得长时间占住事件循环（spec writeback-followup-issue-closure R4 / D6）。

实测（重药安徽真库，预热两段）：事件循环停顿合计 32.2 s、单次最长 3.3 s → 19.4 s、0.56 s。三处改动：

1. ``normalized_structure_hash`` 按字节摘要记忆化（只存 64 字符结果）—— 结构指纹的 LRU 只有 16 份，
   而冷注册要算 36 份模板 ⇒ 第二轮（基线预热 / 目标底稿绑定）全部重新整册解析；
2. 冷注册的 attach 之前，在工作线程按同一组 provider 先算模板结构 hash
   （``registration_template_warmup``）⇒ 事件循环上只剩 sha256；
3. ``load_entry_manifest`` 按 (路径, mtime_ns, size) 缓存（冷注册里 143 次解析 1.27 MB）。

另：callback 后 apply 改走共享注册入口（锁 + 缓存 + pilot 隔离），判据在
``test_target_bound_registration_wiring.py``。
"""
from __future__ import annotations

import ast
import io
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync import entry_profile as EP
from app.services.workpaper_sync import excel_instrumentation as EI
from app.services.workpaper_sync import registration_template_warmup as W
from app.services.workpaper_sync import structure_hash_memo as SHM

_ROUTER = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_sync_router.py"


def _workbook_bytes(a1: str = "x") -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = a1
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def counted(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """数结构指纹被真正算了几次（经 normalized_structure_hash 的那一条路径）。"""
    SHM.clear()
    calls: list[bytes] = []
    real = EI.structure_fingerprint

    def counting(data: bytes) -> Any:
        calls.append(data)
        return real(data)

    monkeypatch.setattr(EI, "structure_fingerprint", counting)
    yield calls
    SHM.clear()


class TestStructureHashMemo:
    def test_same_bytes_are_fingerprinted_once_even_as_a_copy(self, counted: list[bytes]) -> None:
        data = _workbook_bytes()
        first = EI.normalized_structure_hash(data)
        assert EI.normalized_structure_hash(bytes(bytearray(data))) == first
        assert len(counted) == 1

    def test_different_bytes_get_their_own_hash(self, counted: list[bytes]) -> None:
        one, two = _workbook_bytes("a"), _workbook_bytes("b")
        assert EI.normalized_structure_hash(one) != EI.normalized_structure_hash(two)
        assert len(counted) == 2

    def test_memo_result_equals_the_uncached_algorithm(self, counted: list[bytes]) -> None:
        data = _workbook_bytes("same")
        memoized = EI.normalized_structure_hash(data)
        SHM.clear()
        assert EI.normalized_structure_hash(data) == memoized
        assert len(counted) == 2

    def test_failures_are_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        SHM.clear()
        data = _workbook_bytes("bad")
        attempts: list[int] = []

        def broken(_data: bytes) -> Any:
            attempts.append(1)
            return SimpleNamespace(errors=["style A1: boom"])

        monkeypatch.setattr(EI, "structure_fingerprint", broken)
        for _ in range(2):
            with pytest.raises(EI.InstrumentationError):
                EI.normalized_structure_hash(data)
        assert len(attempts) == 2, "失败结果占了缓存 key"

    def test_memo_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        SHM.clear()
        monkeypatch.setattr(SHM, "MEMO_MAX", 3)
        fake = SimpleNamespace(errors=[], aspect_digests=lambda: {"a": "1"})
        monkeypatch.setattr(EI, "structure_fingerprint", lambda _data: fake)
        for i in range(6):
            EI.normalized_structure_hash(f"wb-{i}".encode())
        assert len(SHM._MEMO) == 3
        SHM.clear()


class TestManifestCache:
    def _manifest(self, tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        return path

    def test_same_file_is_parsed_once(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = self._manifest(tmp_path, [{"entry_id": "a"}])
        monkeypatch.setattr(EP, "ENTRY_MANIFEST_PATH", path)
        EP.load_entry_manifest.cache_clear()
        parsed: list[str] = []
        real_loads = json.loads
        monkeypatch.setattr(EP.json, "loads", lambda text: parsed.append(text) or real_loads(text))
        first = EP.load_entry_manifest()
        assert EP.load_entry_manifest() is first
        assert len(parsed) == 1

    def test_edit_is_picked_up_without_restart(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = self._manifest(tmp_path, [{"entry_id": "a"}])
        monkeypatch.setattr(EP, "ENTRY_MANIFEST_PATH", path)
        EP.load_entry_manifest.cache_clear()
        assert [e["entry_id"] for e in EP.load_entry_manifest()["entries"]] == ["a"]
        path.write_text(json.dumps({"entries": [{"entry_id": "a"}, {"entry_id": "bb"}]}), encoding="utf-8")
        later = time.time() + 5
        os.utime(path, (later, later))
        assert [e["entry_id"] for e in EP.load_entry_manifest()["entries"]] == ["a", "bb"]

    def test_switching_path_is_a_different_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        one = self._manifest(tmp_path, [{"entry_id": "one"}])
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        two = self._manifest(other_dir, [{"entry_id": "two"}])
        monkeypatch.setattr(EP, "ENTRY_MANIFEST_PATH", one)
        assert EP.load_entry_manifest()["entries"][0]["entry_id"] == "one"
        monkeypatch.setattr(EP, "ENTRY_MANIFEST_PATH", two)
        assert EP.load_entry_manifest()["entries"][0]["entry_id"] == "two"

    def test_missing_file_still_fails_closed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(EP, "ENTRY_MANIFEST_PATH", tmp_path / "nope.json")
        with pytest.raises(EP.EntryProfileError):
            EP.load_entry_manifest()


class TestTemplateWarmup:
    def _plan_registry(self, items: list[Any]) -> Any:
        return SimpleNamespace(registration_plan=tuple(items))

    def test_provider_modules_follow_supplied_entries_and_include_pilots(self) -> None:
        item = lambda entry, module, blocked=None: SimpleNamespace(  # noqa: E731
            entry_id=entry, provider_module=module, blocked_reason=blocked
        )
        registry = self._plan_registry([
            item("e1", "mod.one"),
            item("e2", "mod.two"),
            item("e3", "mod.three", blocked="unreachable"),
        ])
        modules = W.provider_modules_for(registry, {"e1", "e3"})
        assert modules == (*W.PILOT_PROVIDER_MODULES, "mod.one")

    def test_registry_without_plan_warms_pilots_only(self) -> None:
        class NoPlan:
            @property
            def registration_plan(self) -> Any:
                raise RuntimeError("未绑定注册计划")

        assert W.provider_modules_for(NoPlan(), {"e1"}) == W.PILOT_PROVIDER_MODULES

    def test_warm_skips_disabled_and_swallows_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        import types

        called: list[str] = []

        def module(name: str, *, enabled: bool, fails: bool = False) -> None:
            mod = types.ModuleType(name)
            mod.manifest_capability_enabled = lambda: enabled

            def payload() -> dict[str, Any]:
                called.append(name)
                if fails:
                    raise RuntimeError("模板读不到")
                return {}

            mod.template_definition_payload = payload
            monkeypatch.setitem(sys.modules, name, mod)

        module("wbf_probe.ok", enabled=True)
        module("wbf_probe.off", enabled=False)
        module("wbf_probe.broken", enabled=True, fails=True)
        warmed = W.warm_template_structure_hashes(
            ["wbf_probe.ok", "wbf_probe.off", "wbf_probe.broken", "wbf_probe.missing"]
        )
        assert warmed == 1
        assert called == ["wbf_probe.ok", "wbf_probe.broken"]


def test_cold_build_hashes_templates_on_a_worker_thread() -> None:
    """冷建分支经 ``asyncio.to_thread(warm_template_structure_hashes, …)``，且在 pilot attach 之前。"""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_attach_pilot_adapters"
    )
    order: list[str] = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
        if name == "to_thread" and call.args and isinstance(call.args[0], ast.Name):
            order.append(f"thread:{call.args[0].id}")
        elif name == "_isolated_pilot_attach":
            order.append("attach")
    assert "thread:warm_template_structure_hashes" in order, order
    assert order.index("thread:warm_template_structure_hashes") < order.index("attach"), order


def test_memo_is_safe_under_concurrent_threads(counted: list[bytes]) -> None:
    data = _workbook_bytes("concurrent")
    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(EI.normalized_structure_hash(data))) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1 and len(results) == 6
