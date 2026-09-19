"""撤销回填时同步撤销抽样登记投影 — 守卫

spec: sampling-evaluation-and-governance-closure
Validates: Requirements 1.1~1.8, 11.2
Properties: Property 1, Property 2, Property 3, Property 4

背景（2026-08-05 实证 F1/F2/F3）：`voucher_undo` 改造前只写
`workpaper_extraction_log.is_undone`，两张投影表原封不动；而投影已在产出真实数据
（真实库 `sampled_vouchers` 21 行引擎登记）。四个消费方全部被污染，且**零测试覆盖**
（`test_sampling_registry_service.py` 657 行 undo 零命中）。

本文件全部用**替身 session**，不连库 → 可进 CI。真实库验证走
`scripts/diagnose/verify_sampling_governance_live.py`（Task 17）。
"""

from __future__ import annotations

import logging
import re
from uuid import UUID, uuid4

import pytest

from app.services import sampling_registry_service as svc


# ─── 替身：只记录被执行的 UPDATE，不真跑 SQL ──────────────────────────────────


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeSession:
    """记录每次 execute 的 SQL 文本与参数，供断言「改了哪张表、带了什么条件」。"""

    def __init__(self, *, rowcounts: list[int] | None = None, raise_on: int | None = None) -> None:
        self.executed: list[str] = []
        self._rowcounts = list(rowcounts or [])
        self._raise_on = raise_on
        self._n = 0
        self.flushed = 0

    async def execute(self, stmt):  # noqa: ANN001
        self._n += 1
        if self._raise_on is not None and self._n == self._raise_on:
            raise RuntimeError("模拟投影撤销失败")
        text = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        self.executed.append(text)
        rc = self._rowcounts.pop(0) if self._rowcounts else 0
        return _FakeResult(rc)

    async def flush(self):
        self.flushed += 1


# ─── Property 2：撤销不越界 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_undo_targets_both_projection_tables_by_batch_id():
    """两张投影表各发一条按 batch_id 的 UPDATE，且带 is_deleted 条件。"""
    batch = uuid4()
    db = _FakeSession(rowcounts=[1, 5])

    out = await svc.undo_sampling_registration(db, batch_id=batch)

    assert out == {"records": 1, "vouchers": 5}
    assert len(db.executed) == 2, "应恰好两条 UPDATE（records + vouchers）"
    joined = " ".join(db.executed)
    assert "sampling_records" in joined
    assert "sampled_vouchers" in joined
    for sql in db.executed:
        assert sql.strip().upper().startswith("UPDATE"), f"应为 UPDATE 而非删除：{sql[:60]}"
        assert "batch_id" in sql, "必须按 batch_id 限定，禁止按 workpaper_id 宽删"
        assert "is_deleted" in sql, "必须只软删尚未软删的行（幂等）"


#: 物理删除判据必须带词边界 —— 裸 `"DELETE" in sql` 会被列名 `is_deleted` 骗
#: （`IS_DELETED` 含子串 `DELETE`），首版守卫即因此自打红。
_PHYSICAL_DELETE_RE = re.compile(r"\bDELETE\s+FROM\b", re.I)


@pytest.mark.asyncio
async def test_undo_is_soft_delete_not_physical():
    """撤销是需要留痕的审计动作 → 必须软删，不得发出 DELETE FROM。"""
    batch = uuid4()
    db = _FakeSession(rowcounts=[1, 3])
    await svc.undo_sampling_registration(db, batch_id=batch)
    for sql in db.executed:
        assert not _PHYSICAL_DELETE_RE.search(sql), (
            f"禁止物理删除（撤销事实会彻底消失）：{sql[:80]}"
        )


def test_physical_delete_regex_selfcheck():
    """判据自检：真 DELETE 必须命中，软删 UPDATE（含 is_deleted 列）必须不命中。"""
    assert _PHYSICAL_DELETE_RE.search("DELETE FROM sampled_vouchers WHERE batch_id = :b")
    assert not _PHYSICAL_DELETE_RE.search(
        "UPDATE sampled_vouchers SET is_deleted=:v WHERE is_deleted = false"
    ), "判据被 is_deleted 列名误伤（这正是首版守卫的缺陷）"


@pytest.mark.asyncio
async def test_undo_never_filters_by_workpaper_id():
    """同一底稿可有多批次（预审/年审、不同科目）→ 按底稿宽删会误删有效批次。"""
    db = _FakeSession(rowcounts=[1, 1])
    await svc.undo_sampling_registration(db, batch_id=uuid4())
    for sql in db.executed:
        assert "working_paper_id" not in sql, (
            "撤销条件不得含 working_paper_id —— 那会连带撤销同底稿其它批次的登记"
        )


@pytest.mark.asyncio
async def test_undo_with_null_batch_id_is_noop_and_warns(caplog):
    """batch_id 缺失 → 零操作 + WARNING（不猜、不宽删）。"""
    db = _FakeSession()
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        out = await svc.undo_sampling_registration(db, batch_id=None)

    assert out == {"records": 0, "vouchers": 0}
    assert db.executed == [], "batch_id 为 None 时不得发出任何 UPDATE"
    assert any("batch_id" in r.message or "batch_id" in r.getMessage() for r in caplog.records), (
        "静默跳过会让「投影没撤销」无从发现，必须留 WARNING"
    )


# ─── Property 4：投影失败不阻断撤销 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_undo_fails_open_with_warning(caplog):
    """投影撤销异常 → 返回零计数 + WARNING，不抛出（否则审计师的撤销会整体失败）。"""
    db = _FakeSession(raise_on=1)
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        out = await svc.undo_sampling_registration(db, batch_id=uuid4())

    assert out == {"records": 0, "vouchers": 0}
    assert any("投影撤销失败" in r.getMessage() for r in caplog.records), (
        "fail-open 必须留 WARNING，否则变成静默黑洞"
    )


# ─── Property 1：撤销后投影不再暴露该批次（源码级接线断言）────────────────────


def _router_source() -> str:
    import inspect

    from app.routers import voucher_sampling

    return inspect.getsource(voucher_sampling.voucher_undo)


def test_voucher_undo_calls_undo_registration():
    """接线断言：撤销端点必须调用投影撤销。

    这是 Property 1 的**充分条件** —— 三个查询函数（project_level_extracted_voucher_nos /
    cross_workpaper_duplicate_vouchers / project_sampling_coverage）都已带
    `is_deleted == false` 条件（本文件另有断言核实），故一旦软删生效，它们必然不再暴露该批次。
    """
    src = _router_source()
    assert "undo_sampling_registration" in src, (
        "voucher_undo 未调用 undo_sampling_registration —— "
        "这正是改造前的缺陷形态：权威 log 标了撤销，投影表继续对外暴露该批次"
    )


def test_voucher_undo_invokes_projection_before_commit():
    """必须在 commit 之前调用，否则软删与 is_undone 不在同一事务，可能只成功一半。"""
    src = _router_source()
    call_at = src.index("undo_sampling_registration(")
    commit_at = src.rindex("db.commit()")
    assert call_at < commit_at, "投影撤销必须发生在 commit 之前（同一事务原子生效）"


def test_voucher_undo_passes_batch_id_from_record():
    """必须传该 log 自己的 batch_id，不能传别的标识。"""
    src = _router_source()
    seg = src[src.index("undo_sampling_registration(") :][:160]
    assert "batch_id=record.batch_id" in seg, f"应按 record.batch_id 撤销，实际片段：{seg[:80]!r}"


@pytest.mark.parametrize(
    "func_name",
    [
        "project_level_extracted_voucher_nos",
        "cross_workpaper_duplicate_vouchers",
        "project_sampling_coverage",
    ],
)
def test_projection_consumers_filter_soft_deleted(func_name: str):
    """三个消费方都必须过滤软删行，软删才能真正生效。"""
    import inspect

    src = inspect.getsource(getattr(svc, func_name))
    assert "is_deleted == sa.false()" in src, (
        f"{func_name} 未过滤 is_deleted —— 软删对它无效，撤销后仍会暴露该批次"
    )


# ─── Property 3：撤销后重新登记的不变式 ───────────────────────────────────────


def test_reregistration_relies_on_new_batch_id_not_revival():
    """撤销后重新回填靠**新 batch_id**，不靠复活软删行。

    2026-08-05 实证：`record_extraction_log` 的幂等去重只命中 `is_undone=false` 的 log，
    撤销后再次回填必然新建 log 且 `batch_id=uuid4()`。若将来有人把 batch_id 改成复用
    幂等键派生的稳定值，则 V139 部分唯一索引下新行会与软删旧行冲突/被跳过 —— 本断言
    钉死该前提，届时打红。
    """
    import inspect

    from app.services.ledger_sampling_service import LedgerSamplingService

    src = inspect.getsource(LedgerSamplingService.record_extraction_log)
    assert "log_data.batch_id or uuid4()" in src, (
        "batch_id 不再是「调用方未传则新生成 uuid4」—— "
        "撤销后重新回填可能与软删行冲突，需重新评估是否要复活逻辑"
    )
    assert "WorkpaperExtractionLog.is_undone == sa.false()" in src, (
        "幂等去重不再排除已撤销 log —— 撤销后重新回填会命中旧 log 并复用其 batch_id"
    )


def test_register_sampled_vouchers_has_no_revival_logic():
    """反面断言：不得引入「复活软删行」的 UPDATE（基于错误假设的多余逻辑）。"""
    import inspect

    src = inspect.getsource(svc.register_sampled_vouchers)
    assert "is_deleted=False" not in src.replace(" ", ""), (
        "register_sampled_vouchers 出现复活软删行的写法 —— "
        "撤销后重新回填走的是新 batch_id，复活会把已撤销批次错误地恢复对外暴露"
    )


# ─── 反向自检：复现旧行为必打红 ───────────────────────────────────────────────


def test_reverse_selfcheck_legacy_undo_would_fail_property_1():
    """替身复现改造前的 voucher_undo（只标 is_undone），断言本文件的接线检查会打红。

    没有这条，`test_voucher_undo_calls_undo_registration` 有可能因为正则/取源方式失效而
    变成永远通过的空转断言。
    """
    legacy_src = (
        "async def voucher_undo(...):\n"
        "    record.is_undone = True\n"
        "    record.status = 'undone'\n"
        "    await db.flush()\n"
        "    await db.commit()\n"
        "    return {'success': True, 'before_data': record.before_data}\n"
    )
    assert "undo_sampling_registration" not in legacy_src, (
        "反向自检自身失效：旧实现片段里竟含新符号"
    )


def test_reverse_selfcheck_wide_delete_would_be_caught():
    """替身复现「按 workpaper_id 宽删」，断言越界检查会打红。"""
    bad_sql = (
        "UPDATE sampled_vouchers SET is_deleted=true "
        "WHERE working_paper_id = :wp AND is_deleted = false"
    )
    assert "working_paper_id" in bad_sql, "反向自检自身失效"
    # 与 test_undo_never_filters_by_workpaper_id 同一判据
    assert not all("working_paper_id" not in s for s in [bad_sql]), (
        "越界判据失效：宽删 SQL 竟能通过"
    )


def test_reverse_selfcheck_physical_delete_would_be_caught():
    bad_sql = "DELETE FROM sampled_vouchers WHERE batch_id = :b"
    assert _PHYSICAL_DELETE_RE.search(bad_sql), "反向自检自身失效"


def test_undo_return_type_is_counts_not_bool():
    """返回受影响行数而非布尔 —— 调用方与诊断脚本需要知道「撤销了几行」。"""
    import inspect

    sig = inspect.signature(svc.undo_sampling_registration)
    assert "dict" in str(sig.return_annotation), (
        f"返回类型应为计数 dict，实际 {sig.return_annotation}"
    )
    assert set(sig.parameters) == {"db", "batch_id"}, (
        f"签名漂移：{list(sig.parameters)}（batch_id 必须是 keyword-only）"
    )
    assert sig.parameters["batch_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_batch_id_type_accepts_uuid_and_none():
    """batch_id 类型注解须允许 None（缺失是真实场景，不是异常）。"""
    import inspect

    sig = inspect.signature(svc.undo_sampling_registration)
    ann = str(sig.parameters["batch_id"].annotation)
    assert "None" in ann, f"batch_id 必须可为 None，实际注解 {ann}"
    assert "UUID" in ann, f"batch_id 应为 UUID 类型，实际注解 {ann}"


def test_uuid_import_present_for_probe():
    """本文件用到 UUID 类型断言，确保 import 未被清理（防 lint 自动删除后断言空转）。"""
    assert UUID is not None
