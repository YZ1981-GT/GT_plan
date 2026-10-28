"""归档门禁与向导同口径（spec attachment-archive-and-a-class-evidence ADR-AE-14）。

走查实测：向导里「存在阻断项，无法继续」（QC 未跑、审计报告未生成、4 张底稿未签字），绕过向导直接调编排接口，
门禁步骤因客户端带来的评估 id「未就绪」退回只评导出门禁 ⇒ 放行，锁定步骤随即锁上项目与底稿。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services import archive_gate
from app.services.archive_completeness_service import (
    CATEGORY_LABELS,
    CheckCategory,
    CheckItem,
    CompletenessReportResponse,
)

READINESS = "app.services.qc_dashboard_service.ArchiveReadinessService.check_readiness"
COMPLETENESS = "app.services.archive_completeness_service.get_archive_completeness_report"
PID = uuid.uuid4()


def _readiness(ready=True, findings=()):
    return {"ready": ready, "gate_eval_id": "e", "groups": [
        {"id": "qc", "name": "所有底稿 QC 自检通过", "status": "blocking" if findings else "pass", "findings": list(findings)},
        {"id": "kam", "name": "关键审计事项已确认", "status": "warning",
         "findings": [{"severity": "warning", "message": "仅提示，不阻断"}]},
    ]}


def _report(**counts):
    cats = []
    for name in CATEGORY_LABELS:
        n = counts.get(name, 0)
        items = [CheckItem(wp_code=f"D{i}", wp_name=f"底稿{i}", assignee=None, status="draft") for i in range(n)]
        cats.append(CheckCategory(category=name, count=n, items=items,
                                  is_blocking=name in {"missing", "unsigned", "unresolved_reviews", "stale", "missing_files"}))
    return CompletenessReportResponse(categories=cats, can_proceed=not any(c.is_blocking and c.count for c in cats),
                                      generated_at=datetime.now(timezone.utc))


async def _problems(readiness, report):
    with patch(READINESS, new=AsyncMock(return_value=readiness)), patch(COMPLETENESS, new=AsyncMock(return_value=report)):
        return await archive_gate.archive_gate_problems(object(), PID, None)


async def test_clean_project_passes():
    assert await _problems(_readiness(), _report(evidence_gaps=3, orphan_files=1, sampling_records=2)) == []


async def test_readiness_blocking_findings_are_listed():
    got = await _problems(_readiness(False, [{"severity": "blocking", "message": "QC 未通过 0 个，未执行 4 个"}]), _report())
    assert got == ["就绪检查｜所有底稿 QC 自检通过｜QC 未通过 0 个，未执行 4 个"]


async def test_not_ready_without_findings_still_blocks():
    assert await _problems(_readiness(False), _report()) == ["就绪检查｜导出门禁｜未通过"]


async def test_completeness_blocking_items_listed_and_truncated():
    got = await _problems(_readiness(), _report(unsigned=2, missing_files=25, evidence_gaps=9))
    assert got[:2] == ["完整性自检｜未签字底稿｜D0 底稿0", "完整性自检｜未签字底稿｜D1 底稿1"]
    files = [g for g in got if "文件缺失" in g]
    assert len(files) == 21 and files[-1] == "完整性自检｜文件缺失｜……共 25 项"
    assert not any("证据缺口" in g for g in got)  # 提示类不阻断


async def test_orchestrator_gate_fails_closed_and_does_not_lock(tmp_path):
    """编排器用的就是这一个门禁：有阻断项 ⇒ 门禁步骤失败、问题清单落进度、不打包不锁定。"""
    from app.services.archive_orchestrator import ArchiveOrchestrator

    job = type("J", (), {"project_id": PID, "initiated_by": None})()
    with patch(READINESS, new=AsyncMock(return_value=_readiness())), \
            patch(COMPLETENESS, new=AsyncMock(return_value=_report(unsigned=1))):
        with pytest.raises(archive_gate.ArchiveGateBlocked) as raised:
            await ArchiveOrchestrator(db=object())._step_gate(job)
    assert raised.value.problems == ["完整性自检｜未签字底稿｜D0 底稿0"]
    assert str(raised.value) == "归档门禁未通过：1 项阻断（完整性自检｜未签字底稿｜D0 底稿0）"


def test_category_labels_match_frontend_table():
    """后端门禁原因与前端完整性报告用同一张中文名表（防两边各改一处）。"""
    ts = (Path(__file__).resolve().parents[3] / "audit-platform/frontend/src/constants/archiveLabels.ts").read_text(
        encoding="utf-8")
    block = ts.split("ARCHIVE_CATEGORY_LABELS", 1)[1].split("}", 1)[0]
    frontend = dict(re.findall(r"(\w+):\s*'([^']+)'", block))
    assert frontend == CATEGORY_LABELS
