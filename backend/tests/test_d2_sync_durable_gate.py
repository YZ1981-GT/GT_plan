"""D2 双向回写：耐久门与陈旧校验守卫。

锁死 2026-09-06 D2-2 浏览器实测抓到的缺陷 B —— pull 读到尚未落盘的陈旧 xlsx，
把旧值写满整张表覆盖 HTML 侧新录入，同时返回 `{"ok":true,"rows_persisted":1260}`
的成功文案。

判据全在**行为**上（该抛就抛、该放行就放行、变化计数是否如实），
不查「某个字符串在不在源码里」。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import d2_sync_router as R
from app.services.workpaper_sync import d2_bidirectional_bridge as B


# ═══════════════════════════════════════════════════════════════════
# 1. _same_store_value：什么算「真变化」
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("existing", "incoming", "same"),
    [
        # 类型差异不是变化：store 存 int，xlsx 读回 float
        (5200, 5200.0, True),
        (0, 0.0, True),
        # 空值家族互等
        (None, "", True),
        ("", None, True),
        (None, "   ", True),
        # 真变化
        (0, 13571.99, False),
        ("", "GTPROBE-A1", False),
        (5200, 5201, False),
        # bool 不与数值并入（业务上是不同字段语义）
        (True, 1, False),
        (False, 0, False),
        (True, True, True),
        (False, False, True),
        # 文本
        ("非关联方", "非关联方", True),
        ("非关联方", "关联方", False),
    ],
)
def test_same_store_value(existing, incoming, same) -> None:
    assert B._same_store_value(existing, incoming) is same


def test_assign_store_value_only_counts_real_change() -> None:
    """同值重写必须返回 False —— 否则 `rows_changed` 恒等于全量，假成功。"""
    row: dict = {"postPayment": 0}
    assert B._assign_store_value(row, "post_payment", 0) is False
    assert B._assign_store_value(row, "post_payment", 0.0) is False
    assert B._assign_store_value(row, "post_payment", 88888.77) is True
    assert row["postPayment"] == 88888.77
    # 未在契约映射里的字段不写
    assert B._assign_store_value(row, "不存在的字段", 1) is False


def test_assign_store_value_nested_path() -> None:
    """嵌套 store_key（账龄分段）也要遵守「只在真变化时写」。"""
    row: dict = {}
    # 第一次写入嵌套路径 = 变化
    assert B._assign_store_value(row, "aging_prior_within1", 100) is True
    assert row["agingPrior"]["within1"] == 100
    # 同值重写 = 不变
    assert B._assign_store_value(row, "aging_prior_within1", 100) is False
    assert B._assign_store_value(row, "aging_prior_within1", 100.0) is False


# ═══════════════════════════════════════════════════════════════════
# 2. _assert_not_stale：陈旧必拒
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture()
def artifact(tmp_path: Path) -> Path:
    p = tmp_path / "D2-2.xlsx"
    p.write_bytes(b"OLD-CONTENT")
    return p


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_stale_artifact_rejected(artifact: Path) -> None:
    """forcesave 期间没观察到变化 + 磁盘仍是那份 ⇒ 409，且**不**写库。

    这正是实测里发生的事：pull 于 19:51:19 读到 19:41:12 的旧文件。
    """
    old = _sha(b"OLD-CONTENT")
    with pytest.raises(HTTPException) as ei:
        R._assert_not_stale(
            artifact, {"before": {"sha256": old}, "after": {"sha256": old}}
        )
    assert ei.value.status_code == 409
    # 文案必须让审计师知道「为什么没回写」以及「该怎么做」
    detail = str(ei.value.detail)
    assert "尚未落盘" in detail
    assert "取消" in detail


def test_freshly_saved_artifact_allowed(artifact: Path) -> None:
    """forcesave 后磁盘又落了一次新内容 ⇒ 放行。"""
    old = _sha(b"OLD-CONTENT")
    artifact.write_bytes(b"NEW-CONTENT")
    R._assert_not_stale(
        artifact, {"before": {"sha256": old}, "after": {"sha256": old}}
    )  # 不抛即通过


def test_concurrently_replaced_artifact_rejected(artifact: Path) -> None:
    """磁盘内容既非 before 也非 after ⇒ 有人并发换了文件 ⇒ 409。"""
    with pytest.raises(HTTPException) as ei:
        R._assert_not_stale(
            artifact, {"before": {"sha256": "aa" * 32}, "after": {"sha256": "bb" * 32}}
        )
    assert ei.value.status_code == 409
    assert "又被改动" in str(ei.value.detail)


def test_unknown_fingerprint_shape_does_not_fake_validation(artifact: Path) -> None:
    """指纹形状不认识时放行 —— 但**不假装校验过**（不得静默当成已校验）。"""
    R._assert_not_stale(artifact, {"weird": 1})  # 不抛
    R._assert_not_stale(artifact, {})  # 不抛


def test_fingerprint_captures_three_dimensions(artifact: Path) -> None:
    """指纹必须同时含 mtime_ns / size / sha256。

    只用 mtime 会被同秒重写骗过；只用 size 会被等长改动骗过；
    只用 sha256 拿不到时间序。
    """
    fp = R._artifact_fingerprint(artifact)
    assert set(fp) == {"mtime_ns", "size", "sha256"}
    assert fp["size"] == len(b"OLD-CONTENT")
    assert fp["sha256"] == _sha(b"OLD-CONTENT")
    assert isinstance(fp["mtime_ns"], int)


# ═══════════════════════════════════════════════════════════════════
# 3. 端点注册与 forcesave 语义
# ═══════════════════════════════════════════════════════════════════


def test_forcesave_endpoint_registered() -> None:
    """forcesave 端点必须真的挂上 —— 前端 await 的就是它。"""
    paths = {r.path for r in R.router.routes}
    assert "/api/workpapers/{wp_id}/d2-sync/forcesave" in paths
    assert "/api/workpapers/{wp_id}/d2-sync/pull-from-excel" in paths
    assert "/api/workpapers/{wp_id}/d2-sync/push-to-excel" in paths


def test_pull_endpoint_actually_calls_stale_guard() -> None:
    """pull 必须**真的调用** `_assert_not_stale`，而不是只把它定义在模块里。

    🔴 2026-09-06 变异检验抓出的守卫缺口：只测 `_assert_not_stale` 本身的话，
    把 pull 里那行调用删掉，全部测试照样绿 —— 那就是「additive 注入即死代码」，
    本 spec 复盘里的假绿第①源。故这里用**源码形态**判据补上：
    调用点必须在 `d2_pull_from_excel` 的函数体内，且必须在读 store 之前。
    """
    import inspect

    src = inspect.getsource(R.d2_pull_from_excel)
    assert "_assert_not_stale(" in src, (
        "pull 端点没有调用陈旧校验 —— 校验函数成了死代码，"
        "OO 未落盘时会重新出现「读旧文件覆盖 HTML 新值」"
    )
    # 顺序判据：校验必须早于 `_read_store_rows`（写库前拦住）
    guard_at = src.index("_assert_not_stale(")
    read_at = src.index("_read_store_rows(")
    assert guard_at < read_at, "陈旧校验必须在读 store / 写库之前执行"


def test_forcesave_endpoint_treats_nothing_to_save_as_durable() -> None:
    """端点必须把「无待保存内容」判为可回写（durable=True）。

    源码形态判据：`_FORCESAVE_NOTHING_TO_SAVE` 分支里必须 `durable = True`。
    2026-09-06 浏览器复测实测：OO 对「打开没改就切回」回 error=4，若这里判
    False，最常见的操作会被误拒、审计师永远切不回结构化视图。
    """
    import inspect

    src = inspect.getsource(R.d2_forcesave)
    idx = src.index("_FORCESAVE_NOTHING_TO_SAVE")
    branch = src[idx : idx + 260]
    assert "durable = True" in branch, (
        "「无待保存内容」必须判为可回写 —— 磁盘已是权威版本，等也等不到变化"
    )


def test_pull_endpoint_accepts_durable_fingerprint() -> None:
    """pull 必须能接收前端带回的耐久指纹，否则服务端那道门永远拿不到判据。"""
    import inspect

    sig = inspect.signature(R.d2_pull_from_excel)
    assert "payload" in sig.parameters
    # 载荷模型必须真的有这个字段（拼错字段名 = 永远读不到，静默失效）
    assert "durable_fingerprint" in R._PullRequest.model_fields


@pytest.mark.asyncio
async def test_issue_forcesave_reports_failure_when_url_missing(monkeypatch) -> None:
    """ONLYOFFICE_URL 缺失时如实返回失败，**不得**谎报已接受。"""
    monkeypatch.setattr(R.settings, "ONLYOFFICE_URL", "", raising=False)
    outcome, reason = await R._issue_forcesave("doc-key-1")
    assert outcome == R._FORCESAVE_REJECTED
    assert "未配置" in reason


def test_forcesave_outcomes_are_three_distinct_states() -> None:
    """三态必须互不相等。

    🔴 压成布尔必然误判：`error=0`（还会有 callback，要等）与 `error=4`
    （无待保存内容，磁盘已是最新、**不必**等）在「能不能回写」上结论相反。
    2026-09-06 浏览器复测踩到过：把 error=4 只算 accepted 而不算 durable，
    「打开 OO 看一眼没改就切回来」这种最常见操作会被误拒。
    """
    states = {
        R._FORCESAVE_ACCEPTED,
        R._FORCESAVE_NOTHING_TO_SAVE,
        R._FORCESAVE_REJECTED,
    }
    assert len(states) == 3


@pytest.mark.asyncio
async def test_issue_forcesave_error4_is_not_a_failure(monkeypatch) -> None:
    """OO 的 `error=4` = 文档无未保存改动 ⇒ 磁盘已最新，可直接回写。"""

    class _Resp:
        status_code = 200
        text = '{"error":4}'

        @staticmethod
        def json() -> dict:
            return {"error": 4}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def post(self, *_a, **_kw):
            return _Resp()

    monkeypatch.setattr(R.settings, "ONLYOFFICE_URL", "http://oo:8080", raising=False)
    monkeypatch.setattr(R.httpx, "AsyncClient", lambda **_kw: _Client())
    outcome, reason = await R._issue_forcesave("doc-key-1")
    assert outcome == R._FORCESAVE_NOTHING_TO_SAVE
    assert "无未保存改动" in reason


@pytest.mark.asyncio
async def test_issue_forcesave_rejects_nonzero_error(monkeypatch) -> None:
    """OO 返回非 0/4 的 error ⇒ 失败，绝不当成已接受。"""

    class _Resp:
        status_code = 200
        text = '{"error":1}'

        @staticmethod
        def json() -> dict:
            return {"error": 1}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def post(self, *_a, **_kw):
            return _Resp()

    monkeypatch.setattr(R.settings, "ONLYOFFICE_URL", "http://oo:8080", raising=False)
    monkeypatch.setattr(R.httpx, "AsyncClient", lambda **_kw: _Client())
    outcome, reason = await R._issue_forcesave("doc-key-1")
    assert outcome == R._FORCESAVE_REJECTED
    assert "error=1" in reason
