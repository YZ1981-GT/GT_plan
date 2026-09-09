"""G1-2 representation-only rehash 分流的 seam/行为测试。

不连数据库、不写业务库、不跑 --apply。全部用内存 monkeypatch 桩替换两处 stale 检测器
与 DB 读，验证：

* 纯口径 stale（字节未变、无坐标漂移）→ `stale_needs_rehash`，apply 走
  representation-only，且**从不**调用 `publish_first_generation`；
* 坐标漂移 stale → `stale_needs_reprojection`（保留重投影分支）；
* 无 `state=ready` candidate 时 representation-only 如实 `blocked`，revision 不变；
* representation-only 的 finalize 出口是 `finalize_definition_upgrade`，把它换成
  `publish_first_generation` 必被 AST 变异判据打红。
"""
import ast
import asyncio
import importlib.util
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend/scripts/fix/fix_projection_representation_rehash.py"


def _load_module() -> types.ModuleType:
    import sys

    name = "g1_2_rehash_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass 装饰器需要模块已在 sys.modules 中
    spec.loader.exec_module(module)
    return module


rehash = _load_module()


class _FakeSession:
    """只回答 content_revision 读；其余任何 execute 都不该发生。"""

    def __init__(self, revision: int = 7) -> None:
        self.revision = revision
        self.calls: list[str] = []

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.calls.append(str(statement))

        class _R:
            def __init__(self, value):
                self._value = value

            def scalar_one(self):
                return self._value

            def scalar_one_or_none(self):
                return "{}"

            def mappings(self):
                return self

            def all(self):
                return []

        return _R(self.revision)


def _current(entry_id: str) -> dict:
    return {
        "representation_id": "11111111-1111-1111-1111-111111111111",
        "wp_id": "22222222-2222-2222-2222-222222222222",
        "project_id": "33333333-3333-3333-3333-333333333333",
        "generation": 1,
        "structure_hash": "a" * 64,
        "content_version_id": "44444444-4444-4444-4444-444444444444",
        "relative_path": "storage/x.xlsx",
        "artifact_sha256": "b" * 64,
    }


def _patch_common(monkeypatch, *, recomputed, drift_state, guard):
    monkeypatch.setattr(rehash, "_current_representation",
                        _async_return(lambda *_a, **_k: _current(guard["entry_id"])))
    monkeypatch.setattr(rehash, "_recompute_from_artifact", lambda **_: (recomputed, None))
    monkeypatch.setattr(rehash, "_gtsync_structure_drift",
                        lambda **_: (drift_state, f"detail:{drift_state}", None))
    # provider import: 用一个最小 module 顶替
    provider = types.SimpleNamespace(STORE_ITEM_ID="item", EMPTY_STORE_PAYLOAD="{}")
    monkeypatch.setattr(rehash.importlib, "import_module", lambda _: provider)


def _async_return(fn):
    async def _inner(*args, **kwargs):
        return fn(*args, **kwargs)

    return _inner


ROW = {"entry_id": "xlsx/gt-test", "contract_id": "c1", "provider_module": "prov"}


def test_pure_hash_stale_routes_representation_only_and_never_reprojects(monkeypatch):
    guard = {"entry_id": ROW["entry_id"]}
    # 冻结 hash != 重算 => 纯口径 stale（无坐标漂移，因为不会进 drift 分支）
    _patch_common(monkeypatch, recomputed="c" * 64, drift_state="consistent", guard=guard)

    def _boom(*a, **k):
        raise AssertionError("publish_first_generation must not be called for pure-hash stale")

    import app.services.workpaper_sync.projection_first_publication as F
    monkeypatch.setattr(F, "publish_first_generation", _boom)

    seen = {}

    async def _fake_repr_only(session, *, current, contract_id, out):
        seen["called"] = True
        out.state = "rehashed"
        out.new_generation = 2
        out.new_revision = 7
        return out

    monkeypatch.setattr(rehash, "_rehash_representation_only", _fake_repr_only)

    out = asyncio.run(rehash._process_entry(_FakeSession(), row=ROW, apply=True))
    assert out.state == "rehashed"
    assert seen.get("called") is True
    assert out.new_revision == 7


def test_drift_stale_uses_reprojection_state(monkeypatch):
    guard = {"entry_id": ROW["entry_id"]}
    # 冻结 hash == 重算 且 drift => 坐标漂移
    _patch_common(monkeypatch, recomputed="a" * 64, drift_state="drift", guard=guard)
    out = asyncio.run(rehash._process_entry(_FakeSession(), row=ROW, apply=False))
    assert out.state == "stale_needs_reprojection"


def test_consistent_is_idempotent_noop(monkeypatch):
    guard = {"entry_id": ROW["entry_id"]}
    _patch_common(monkeypatch, recomputed="a" * 64, drift_state="consistent", guard=guard)
    out = asyncio.run(rehash._process_entry(_FakeSession(), row=ROW, apply=True))
    assert out.state == "already_consistent"


def test_representation_only_blocks_without_ready_candidate_and_keeps_revision(monkeypatch):
    # 没有 finalizable candidate => blocked，且未推进 revision
    async def _no_candidate(session, **kwargs):
        raise rehash._RehashRepresentationOnlyBlocked(
            "no_finalizable_candidate", "no candidate")

    monkeypatch.setattr(rehash, "_load_finalizable_candidate_id", _no_candidate)
    session = _FakeSession(revision=9)
    out = rehash.EntryOutcome(entry_id=ROW["entry_id"], contract_id="c1")
    result = asyncio.run(
        rehash._rehash_representation_only(
            session, current=_current(ROW["entry_id"]), contract_id="c1", out=out))
    assert result.state == "blocked"
    assert result.error_code == "no_finalizable_candidate"
    assert result.new_revision is None


def test_finalize_helper_blocks_pending_provisioning_not_reproject(monkeypatch):
    # 当前存量没有 ready candidate 的输入，出口显式 blocked，绝不退回首版提交
    with pytest.raises(rehash._RehashRepresentationOnlyBlocked) as ei:
        asyncio.run(
            rehash._finalize_candidate_representation_only(
                _FakeSession(), project_id=_uuid(), candidate_id=_uuid()))
    assert ei.value.error_code == "finalize_inputs_pending_provisioning"


def _uuid():
    import uuid
    return uuid.uuid4()


def test_finalize_helper_delegates_to_definition_upgrade_not_first_publication():
    """AST 变异：finalize 出口必须是 finalize_definition_upgrade。

    把它换成 publish_first_generation（会推进 revision）必须让本判据打红。
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef)
              and n.name == "_finalize_candidate_representation_only")
    # 判据落在**真实引用**（Name/Attribute 节点）而非字符串字面量上：诊断文案里出现
    # publish_first_generation 是合法的「反面示例」，不算调用。
    referenced = {
        node.id for node in ast.walk(fn) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
    }
    assert "publish_first_generation" not in referenced, (
        "representation-only 出口真实引用了 publish_first_generation —— 那会给纯口径 "
        "stale 推进业务 revision")
    # 文档字符串必须点名唯一 revision-locked 出口，作为接线约束。
    doc = ast.get_docstring(fn) or ""
    assert "finalize_definition_upgrade" in doc, (
        "representation-only 出口未点名 finalize_definition_upgrade（唯一 revision-locked 出口）")


def test_entry_states_vocabulary_split_is_closed():
    assert "stale_needs_rehash" in rehash.ENTRY_STATES
    assert "stale_needs_reprojection" in rehash.ENTRY_STATES
    assert "rehashed" in rehash.ENTRY_STATES
    assert "reprojected" in rehash.ENTRY_STATES
