"""批 7 任务 7.4：合并快照端点（列表概要 + 下载还原后 JSON）的后端单元测试。

主工作台快照面板接线依赖三件事（任务 7.4）：
  - 列表端点附 v2 manifest 概要（locked / root_hash / partial / failed_sources /
    operation_ref / version_ref / counts），且对旧 v1 / 空壳快照安全降级；
  - 下载端点复用 ``restore_consol_snapshot``（解压 + SHA-256 校验），返回 UTF-8 JSON
    附件（含 Content-Disposition），不触发重算；
  - 完整性（restore）与对比（compare）端点既有，本轮不改其契约。

这些端点都是薄包装：只 ``db.execute(...)`` 读 ConsolSnapshot，再调服务层。用一个
最小 fake async session 直接驱动端点函数，既覆盖净新增的投影/下载逻辑，又不触碰
共享 PG（不写真实项目）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.report_trace import (
    download_snapshot,
    list_snapshots,
)
from app.services.consol_snapshot_service import (
    _canonical_json,
    _compress_payload,
    _sha256_hex,
)

PID = uuid4()


# ---------------------------------------------------------------------------
# fake async session：只支持端点用到的 execute(...).scalars().all() /
# execute(...).scalar_one_or_none()
# ---------------------------------------------------------------------------

class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):  # noqa: D401 — 忽略语句，直接返回预置行
        return _ExecResult(self._rows)


def _v2_snapshot_data(*, locked: bool, partial: bool, failed=(), root="roothash") -> dict:
    captured = ["tree", "trial"]
    manifest = {
        "manifest_version": 2,
        "partial": partial,
        "failed_sources": list(failed),
        "captured_sources": captured,
        "root_hash": root,
        "operation_ref": {"operation_id": "op-1", "revision": 2, "status": "succeeded"},
        "version_ref": {"digest": "vd-1", "tree_fingerprint": "tf"},
        "counts": {"trial": 3},
    }
    return {
        "_format": "manifest-v2",
        "_hash": root,
        "_locked": locked,
        "_meta": {"counts": {"trial": 3}, "captured_sources": captured, "failed_sources": list(failed)},
        "_manifest": manifest,
    }


def _make_snap(snapshot_data, *, year=2025, created_by=None):
    return SimpleNamespace(
        id=uuid4(),
        year=year,
        trigger_reason="sign",
        created_at=SimpleNamespace(isoformat=lambda: "2026-05-15T10:00:00+00:00"),
        created_by=created_by,
        project_id=PID,
        snapshot_data=snapshot_data,
    )


_USER = SimpleNamespace(id=uuid4())


# ---------------------------------------------------------------------------
# 列表概要（任务 7.4：主工作台快照面板要展示的字段）
# ---------------------------------------------------------------------------


class TestListSnapshotSummary:
    @pytest.mark.asyncio
    async def test_v2_signed_snapshot_exposes_manifest_summary(self):
        snap = _make_snap(_v2_snapshot_data(locked=True, partial=False), created_by=uuid4())
        db = _FakeDB([snap])
        rows = await list_snapshots(PID, db=db, current_user=_USER)
        assert len(rows) == 1
        r = rows[0]
        assert r["locked"] is True
        assert r["partial"] is False
        assert r["root_hash"] == "roothash"
        assert r["manifest_version"] == 2
        assert r["format"] == "manifest-v2"
        assert r["operation_ref"]["operation_id"] == "op-1"
        assert r["version_ref"]["digest"] == "vd-1"
        assert r["counts"] == {"trial": 3}
        assert r["created_by"] is not None

    @pytest.mark.asyncio
    async def test_v2_partial_manual_snapshot_lists_failed_sources(self):
        snap = _make_snap(_v2_snapshot_data(locked=False, partial=True, failed=["report", "artifact"]))
        snap.trigger_reason = "manual"
        rows = await list_snapshots(PID, db=_FakeDB([snap]), current_user=_USER)
        r = rows[0]
        assert r["locked"] is False
        assert r["partial"] is True
        assert r["failed_sources"] == ["report", "artifact"]

    @pytest.mark.asyncio
    async def test_legacy_empty_shell_snapshot_degrades_safely(self):
        """旧空壳快照（只有 {created_at}）缺 manifest/meta 键时不报错，字段安全降级。"""
        snap = _make_snap({"created_at": "2026-05-01T00:00:00Z"})
        rows = await list_snapshots(PID, db=_FakeDB([snap]), current_user=_USER)
        r = rows[0]
        assert r["locked"] is False
        assert r["root_hash"] is None
        assert r["manifest_version"] is None
        assert r["partial"] is False
        assert r["failed_sources"] == []
        assert r["operation_ref"] == {}
        assert r["version_ref"] == {}


# ---------------------------------------------------------------------------
# 下载（任务 7.4：还原后 JSON 附件，复用 restore，不重算）
# ---------------------------------------------------------------------------


class TestDownloadSnapshot:
    @pytest.mark.asyncio
    async def test_download_returns_restored_json_attachment(self):
        # 构造一个 v1 冻结快照（restore 能逐字节还原 + hash_valid=True）
        raw = {"project_id": str(PID), "year": 2025, "trial": [{"standard_account_code": "1001", "consol_amount": "100.00"}]}
        raw_json = _canonical_json(raw)
        snapshot_data = {
            "_format": "gzip+base64",
            "_payload": _compress_payload(raw_json),
            "_hash": _sha256_hex(raw_json),
            "_locked": True,
            "_meta": {"year": 2025},
        }
        snap = _make_snap(snapshot_data)
        resp = await download_snapshot(PID, snap.id, db=_FakeDB([snap]), current_user=_USER)

        assert resp.media_type == "application/json"
        cd = resp.headers["content-disposition"]
        assert cd.startswith("attachment; filename=")
        assert ".json" in cd

        payload = json.loads(resp.body.decode("utf-8"))
        assert payload["hash_valid"] is True
        assert payload["locked"] is True
        assert payload["year"] == 2025
        assert payload["project_id"] == str(PID)
        # 还原后的数据 = 签字时刻原始数据（金额字符串无精度丢失）
        assert payload["data"] == raw

    @pytest.mark.asyncio
    async def test_download_missing_snapshot_404(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await download_snapshot(PID, uuid4(), db=_FakeDB([]), current_user=_USER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_tampered_v2_marks_hash_invalid(self):
        """v2 快照被篡改（root hash 对不上）时 hash_valid=False，仍可下载供排查。"""
        data = _v2_snapshot_data(locked=True, partial=False, root="tamperedroot")
        # payload 缺失（空壳 v2）⇒ _restore_v2 走解压失败分支，hash_valid=False
        snap = _make_snap(data)
        resp = await download_snapshot(PID, snap.id, db=_FakeDB([snap]), current_user=_USER)
        payload = json.loads(resp.body.decode("utf-8"))
        assert payload["hash_valid"] is False
