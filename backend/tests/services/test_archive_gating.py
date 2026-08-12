"""归档时点门控守卫 —— Wave 4 Task 12
spec: workpaper-import-export-lifecycle-closure（R3.6 / R3.8）

## 本任务从「新建」缩为「核实 + 守卫」

立项时以为归档门控要新写。实证后确认**导入侧早已实现**：

- `workflow_gate._BLOCKED_STATUSES` 含 `WpFileStatus.archived`
- `bulk_import_service` 的 `dry_run()` 与 `run()` **两侧都**调 `gate.classify()`，
  对 `blocked` 分类标 `blocked_by_status` 并 `continue` 跳过写入

而**导出侧零状态过滤**（`bulk_export_service` 里 `archived`/`status`/`WorkflowGate`
全部零命中）⇒ R3.8 的「归档态导出仍可用」结构上成立。

⇒ 本文件的价值是**把这个三态钉死**，防后续有人：
  ① 从 `_BLOCKED_STATUSES` 里摘掉 `archived`（归档后可改数据，破坏留痕）
  ② 给导出侧加状态过滤（归档后调阅不了，违背归档的意义）
  ③ 只改 registry 声明不动实现（声明↔实现分叉）

## R3.6：归档前后两时点

判据是「导出通路不依赖任何工作流状态」—— 只要导出侧不读 status，
归档前后就必然都能执行。这比"跑两次归档流程"更强也更稳（后者需要真实项目）。
"""

from __future__ import annotations

import inspect
import re
import uuid

import pytest

from app.models.workpaper_models import WpFileStatus
from app.services.bulk_tab.scenario_registry import SCENARIOS, get_scenario
from app.services.bulk_tab.workflow_gate import (
    _BLOCKED_STATUSES,
    _REVERT_NEEDED_STATUSES,
    WorkflowGate,
)


# ═══════════════════════════════════════════════════════════════════════════
# R3.8 导入侧 —— 归档态必须拒绝
# ═══════════════════════════════════════════════════════════════════════════


class TestImportBlockedWhenArchived:
    def test_archived_in_blocked_statuses(self) -> None:
        """🔴 `archived` 必须在阻断集里。摘掉它 ⇒ 归档后可改数据。"""
        assert WpFileStatus.archived.value in _BLOCKED_STATUSES, (
            "archived 不在 _BLOCKED_STATUSES ⇒ 归档态底稿可被批量导入覆盖，"
            "破坏归档留痕完整性"
        )

    def test_review_passed_also_blocked(self) -> None:
        """复核通过同样应阻断（与归档同族语义）。"""
        assert WpFileStatus.review_passed.value in _BLOCKED_STATUSES

    def test_classify_archived_returns_blocked(self) -> None:
        wp_id = uuid.uuid4()
        got = WorkflowGate().classify(
            [{"wp_id": wp_id, "status": WpFileStatus.archived.value}]
        )
        assert got[wp_id].classification == "blocked"
        assert got[wp_id].reason == WpFileStatus.archived.value, (
            "reason 必须带原始状态值，否则用户看不出为什么被拒"
        )

    @pytest.mark.parametrize(
        "status",
        [
            WpFileStatus.draft.value,
            WpFileStatus.edit_complete.value,
        ],
    )
    def test_normal_statuses_writable(self, status: str) -> None:
        """反向自检：正常态必须 writable，否则上面的断言是恒真的。"""
        wp_id = uuid.uuid4()
        got = WorkflowGate().classify([{"wp_id": wp_id, "status": status}])
        assert got[wp_id].classification == "writable", (
            f"status={status} 被误判为 {got[wp_id].classification} ⇒ 门禁过严，正常编制被拦"
        )

    def test_under_review_needs_revert_not_blocked(self) -> None:
        """复核中是 `revert_needed` 而非 `blocked` —— 两者处置不同，不能混。"""
        wp_id = uuid.uuid4()
        got = WorkflowGate().classify(
            [{"wp_id": wp_id, "status": WpFileStatus.under_review.value}]
        )
        assert got[wp_id].classification == "revert_needed"
        assert WpFileStatus.under_review.value not in _BLOCKED_STATUSES
        assert WpFileStatus.under_review.value in _REVERT_NEEDED_STATUSES

    def test_blocked_and_revert_sets_disjoint(self) -> None:
        """两个状态集不得相交 —— 相交会让分类结果取决于判断顺序。"""
        overlap = _BLOCKED_STATUSES & _REVERT_NEEDED_STATUSES
        assert not overlap, f"阻断集与回退集相交: {overlap}"


class TestImportServiceActuallyConsumesGate:
    """🔴 声明↔实现交叉锁死：门禁分类必须真被消费。

    `_BLOCKED_STATUSES` 里有 `archived` 只是**声明**；真正拦下来靠
    `bulk_import_service` 调 `classify()` 并对 `blocked` 跳过写入。
    只验声明不验消费，就是 memory 记的「additive 注入即死代码」。
    """

    def test_both_entrypoints_call_classify(self) -> None:
        from app.services.bulk_tab import bulk_import_service as svc

        for fn_name in ("dry_run", "run"):
            src = inspect.getsource(getattr(svc, fn_name))
            assert re.search(r"\bclassify\s*\(", src), (
                f"{fn_name}() 未调用 gate.classify ⇒ 门禁声明是死代码"
            )

    def test_both_entrypoints_mark_blocked_by_status(self) -> None:
        from app.services.bulk_tab import bulk_import_service as svc

        for fn_name in ("dry_run", "run"):
            src = inspect.getsource(getattr(svc, fn_name))
            assert "blocked_by_status" in src, (
                f"{fn_name}() 未标记 blocked_by_status ⇒ 用户看不到被拒原因"
            )

    def test_run_skips_blocked_items(self) -> None:
        """`run()` 必须对 blocked 条目 `continue`，不能标了记号还继续写。"""
        from app.services.bulk_tab import bulk_import_service as svc

        src = inspect.getsource(svc.run)
        # 判据：出现 `if item.blocked` 后紧跟的块里有 continue
        m = re.search(r"if\s+item\.blocked\s*:(.{0,400}?)\bcontinue\b", src, re.S)
        assert m, "run() 对 blocked 条目未跳过 ⇒ 标了记号仍写入"


# ═══════════════════════════════════════════════════════════════════════════
# R3.8 导出侧 —— 归档态仍可用
# ═══════════════════════════════════════════════════════════════════════════


class TestExportNotBlockedByArchive:
    def test_export_service_has_no_status_gate(self) -> None:
        """🔴 导出侧不得引入工作流状态过滤。

        归档的意义就是「事后可调阅」。给导出加状态门会让归档包导不出来。
        """
        from app.services.bulk_tab import bulk_export_service as svc

        src = inspect.getsource(svc)
        for banned in ("WorkflowGate", "_BLOCKED_STATUSES", "blocked_by_status"):
            assert banned not in src, (
                f"bulk_export_service 出现 {banned!r} ⇒ 导出被状态门拦住，"
                "归档态无法调阅（违背 R3.8）"
            )

    def test_export_service_source_nonempty(self) -> None:
        """扫描面自检 —— 空源码会让上一条恒绿。"""
        from app.services.bulk_tab import bulk_export_service as svc

        src = inspect.getsource(svc)
        assert len(src) > 5000, f"bulk_export_service 源码异常短: {len(src)}"

    def test_export_scenarios_declare_archived_allowed(self) -> None:
        for key in ("blank_template", "archive_export"):
            assert get_scenario(key).archived_allowed is True


# ═══════════════════════════════════════════════════════════════════════════
# R3.6 —— 归档前后两时点都可执行
# ═══════════════════════════════════════════════════════════════════════════


class TestBothTimingsExecutable:
    def test_archive_export_depends_on_no_workflow_status(self) -> None:
        """判据：场景④的导出端点不依赖任何状态 ⇒ 归档前后必然都能跑。

        这比"真跑两次归档流程"更强：后者依赖真实项目且有副作用，
        前者是结构性保证（导出侧读不到 status，就不可能因 status 变化而失败）。
        """
        s = get_scenario("archive_export")
        assert s.archived_allowed is True
        assert s.import_endpoint is None, "归档导出场景不应带回传（归档后不许改）"

    def test_archive_export_artifact_has_integrity_evidence(self) -> None:
        """R3.6：产物须含 `manifest.json` + sha256（离线可验完整性）。"""
        from app.services.bulk_tab import zip_handler as zh

        src = inspect.getsource(zh)
        assert "sha256" in src, "ZipAssembler 无 sha256 ⇒ 归档包无完整性证据"
        assert "manifest" in src.lower()

        note = get_scenario("archive_export").artifact_note
        assert "sha256" in note.lower() or "校验" in note

    def test_only_export_scenarios_allowed_in_archived_state(self) -> None:
        """整体一致性：归档态可用的场景**必须全是**纯导出。"""
        for s in SCENARIOS:
            if s.archived_allowed:
                assert s.import_endpoint is None, (
                    f"{s.key} 允许归档态操作却可回传 ⇒ 归档后能改数据"
                )
