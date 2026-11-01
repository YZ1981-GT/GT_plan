"""umbrella spec 的真源优先级与引用闭合性（tasks 0.2 / 0.5）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

本文件只做三件事，每条都可伪证：

1. **真源优先级**：`requirements.md` 的 AC 集合必须恰等于 paradigm JSON 登记的 AC 集合
   （逐字比对由 `test_migration_paradigm_contract.py::TestAcceptanceCriteriaVerbatim` 负责，
   这里只管「集合不多不少」，两者合起来才是「恰等于投影」）。
2. **引用闭合**：`tasks.md` 每条 `_AC:` 引用的编号必须都已登记（不存在未定义 AC 引用），
   且每条已登记 AC 至少被一条任务引用、至少有一个**存在于磁盘**的可执行验收面承接。
3. **归档只作引用**：已勾选任务的说明块里不得把 `_archive/` 路径当完成依据 —— 归档 spec 的
   复选框是别人的审计轨迹，不是本 spec 的状态输入（spec 开头的「完成标记规则」已写明）。

🔴 判据刻意**不**写死任务条数或 AC 条数：两者都会随 spec 推进变化，写死只会在推进时打红并
   指错人。分母用「非空 + 现算集合相等」表达。
"""
from __future__ import annotations

import json
import pathlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
REQUIREMENTS = SPEC_DIR / "requirements.md"
TASKS = SPEC_DIR / "tasks.md"
PARADIGM = ROOT / "backend/data/workpaper_sync_migration_paradigm.json"

#: requirements.md 里 AC 行的形态：`1.3. …` / `12.8. …`
_AC_LINE = re.compile(r"^(?P<ac>\d+\.\d+)\.\s+(?P<text>\S.*)$", re.MULTILINE)
#: tasks.md 里的任务行与 AC 引用行
_TASK_LINE = re.compile(r"^- \[(?P<mark>[ x])\] (?P<id>\d+\.\d+) (?P<title>.+)$")
_AC_REF_LINE = re.compile(r"^\s*- _AC: (?P<refs>[\d., ]+)_\s*$")


def _registered_acs() -> set[str]:
    doc = json.loads(PARADIGM.read_text(encoding="utf-8"))
    return {
        str(item["ac"])
        for item in doc["adjudication_criteria"]["acceptance_criteria"]
    }


def _requirements_acs() -> set[str]:
    return {m.group("ac") for m in _AC_LINE.finditer(REQUIREMENTS.read_text(encoding="utf-8"))}


def _tasks() -> list[dict]:
    """逐任务取 (id, 勾选态, 标题, AC 引用集合, 说明块文本)。"""
    rows: list[dict] = []
    current: dict | None = None
    for line in TASKS.read_text(encoding="utf-8").split("\n"):
        task = _TASK_LINE.match(line)
        if task is not None:
            current = {
                "id": task.group("id"),
                "done": task.group("mark") == "x",
                "title": task.group("title"),
                "acs": set(),
                "body": [],
            }
            rows.append(current)
            continue
        if current is None:
            continue
        ref = _AC_REF_LINE.match(line)
        if ref is not None:
            current["acs"] |= {
                part.strip() for part in ref.group("refs").split(",") if part.strip()
            }
            continue
        if line.startswith("- [") or line.startswith("## "):
            current = None
            continue
        current["body"].append(line)
    return rows


#: AC → 承接它的可执行验收面（测试文件 / 检查脚本，仓库相对路径）。
#:
#: 判据是「至少一个承接面**存在于磁盘**」，不是「写了名字」—— 名字写错或文件被删都必须打红。
_ACCEPTANCE_SURFACES: dict[str, tuple[str, ...]] = {
    "1.3": (
        "backend/tests/test_workpaper_sync_manifest_contract.py",
        "backend/tests/workpaper_sync/test_current_state_projection.py",
        "backend/tests/workpaper_sync/test_cycle_current_projection.py",
    ),
    "1.4": (
        "backend/tests/workpaper_sync/test_entry_readiness.py",
        "backend/tests/workpaper_sync/test_entry_readiness_endpoint.py",
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/entrySyncPresentation.spec.ts",
    ),
    "1.5": (
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/entrySyncPresentation.spec.ts",
        "audit-platform/frontend/src/components/workpaper/sync/__tests__/workpaperEntrySyncNotice.spec.ts",
    ),
    "1.7": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py",
    ),
    "12.1": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/workpaper_sync/test_task13_contract_registry.py",
        "backend/tests/workpaper_sync/test_pending_runtime_adjudication.py",
    ),
    "12.8": (
        "backend/tests/test_workpaper_sync_manifest_contract.py",
        "backend/tests/workpaper_sync/test_pending_runtime_adjudication.py",
    ),
    "12.9": (
        "backend/scripts/check/check_workpaper_sync_closure.py",
        "backend/tests/test_workpaper_sync_manifest_contract.py",
    ),
}


# ════════════════════════════════════════════════════════════════════════════
# 1. 真源优先级
# ════════════════════════════════════════════════════════════════════════════


def test_requirements_ac_set_equals_the_paradigm_projection() -> None:
    disk, registered = _requirements_acs(), _registered_acs()
    assert disk, "requirements.md 里一条 AC 都没解析出来 —— 判据会在空集上恒真"
    assert disk == registered, (
        f"仅在 requirements.md：{sorted(disk - registered)}；"
        f"仅在 paradigm：{sorted(registered - disk)} —— "
        "requirements 是 paradigm 的投影，改 AC 必须先改 JSON 再重生成"
    )


# ════════════════════════════════════════════════════════════════════════════
# 2. 引用闭合
# ════════════════════════════════════════════════════════════════════════════


def test_task_denominator_is_not_empty() -> None:
    rows = _tasks()
    assert len(rows) >= 40, f"只解析出 {len(rows)} 条任务 —— 解析口径失锚"
    assert all(row["acs"] for row in rows), (
        "以下任务没有 _AC: 引用："
        + ", ".join(row["id"] for row in rows if not row["acs"])
    )


def test_no_task_cites_an_undefined_ac() -> None:
    registered = _registered_acs()
    offenders = {
        row["id"]: sorted(row["acs"] - registered)
        for row in _tasks()
        if row["acs"] - registered
    }
    assert not offenders, f"任务引用了未登记的 AC：{offenders}"


def test_every_registered_ac_is_carried_by_some_task() -> None:
    cited: set[str] = set()
    for row in _tasks():
        cited |= row["acs"]
    missing = sorted(_registered_acs() - cited)
    assert not missing, f"以下 AC 没有任何任务承接：{missing}"


@pytest.mark.parametrize("ac", sorted(_registered_acs()))
def test_every_registered_ac_has_an_executable_surface_on_disk(ac: str) -> None:
    surfaces = _ACCEPTANCE_SURFACES.get(ac)
    assert surfaces, f"AC {ac} 没登记可执行验收面 —— 请在 _ACCEPTANCE_SURFACES 里补"
    present = [rel for rel in surfaces if (ROOT / rel).is_file()]
    assert present, (
        f"AC {ac} 登记的验收面一个都不在磁盘上：{list(surfaces)} —— "
        "写了名字不算承接，文件必须真实存在"
    )


def test_acceptance_surface_registry_has_no_stale_entries() -> None:
    """登记表不得留失效路径（改名/删除后必须同步），也不得给未登记 AC 挂面。"""
    registered = _registered_acs()
    stale_acs = sorted(set(_ACCEPTANCE_SURFACES) - registered)
    assert not stale_acs, f"登记表里有已不存在的 AC：{stale_acs}"
    missing_files = {
        ac: [rel for rel in surfaces if not (ROOT / rel).is_file()]
        for ac, surfaces in _ACCEPTANCE_SURFACES.items()
        if any(not (ROOT / rel).is_file() for rel in surfaces)
    }
    assert not missing_files, f"登记表里有不存在的路径：{missing_files}"


# ════════════════════════════════════════════════════════════════════════════
# 3. 归档只作引用
# ════════════════════════════════════════════════════════════════════════════


def test_completed_tasks_do_not_cite_archived_specs_as_evidence() -> None:
    offenders = {
        row["id"]: [line.strip() for line in row["body"] if "_archive/" in line]
        for row in _tasks()
        if row["done"] and any("_archive/" in line for line in row["body"])
    }
    assert not offenders, (
        f"已勾选任务把归档 spec 当完成依据：{offenders} —— "
        "归档 spec 的复选框是别人的审计轨迹，不是本 spec 的状态输入"
    )


def test_completion_count_in_the_header_matches_the_checkboxes() -> None:
    """标题里的 `N/48` 必须与实际勾选数一致 —— 手改任一侧都要打红。"""
    text = TASKS.read_text(encoding="utf-8")
    header = re.search(r"\*\*状态\*\*：(?P<done>\d+)/(?P<total>\d+)", text)
    assert header is not None, "tasks.md 开头缺 `**状态**：N/M`"
    rows = _tasks()
    assert int(header.group("total")) == len(rows), (
        f"标题写总数 {header.group('total')}，实际解析 {len(rows)} 条"
    )
    done = sum(1 for row in rows if row["done"])
    assert int(header.group("done")) == done, (
        f"标题写已完成 {header.group('done')}，实际勾选 {done} 条"
    )


# ════════════════════════════════════════════════════════════════════════════
# 4. 外部机器消费方闭合（doc → 脚本解析器）
# ════════════════════════════════════════════════════════════════════════════

#: 已知读 requirements.md / tasks.md / design.md 的脚本。
#: `status` 取三值：
#:   * `ok`       —— 在当前文档形态下可运行
#:   * `retired`  —— 退役（如 generate_task66_legacy_deletion_plan 的整条判为退役）
#:   * `pending_relink` —— 锚点断开，归某个任务做前置时重接
#: 🔴 新增读 spec 文档的脚本时必须加到这里，否则改文档时不会有判据打红。
_SPEC_DOC_CONSUMERS: list[dict[str, str]] = [
    {
        "script": "backend/scripts/gen/generate_task66_legacy_deletion_plan.py",
        "reads": "tasks.md",
        "status": "retired",
        "note": "整条判为退役，由 task 5.5 执行账取代",
    },
    {
        "script": "backend/scripts/gen/generate_workpaper_sync_program_milestones.py",
        "reads": "tasks.md",
        "status": "ok",
        "note": "wave 图键名已修、里程碑归属已重映射",
    },
    {
        "script": "backend/scripts/check/check_task68_backend_chain_independent_regression.py",
        "reads": "tasks.md",
        "status": "pending_relink",
        "relink_owner": "7.2",
        "note": "TASK_NUMBER=68 不在新 tasks.md；解析器假设纯数字任务号",
    },
    {
        "script": "backend/scripts/check/check_task69_frontend_independent_regression.py",
        "reads": "tasks.md",
        "status": "pending_relink",
        "relink_owner": "7.2",
        "note": "TASK_NUMBER=69 不在新 tasks.md",
    },
    {
        "script": "backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py",
        "reads": "requirements.md",
        "status": "pending_relink",
        "relink_owner": "7.1",
        "note": "依赖 ### Requirement N: 标题结构，active 投影只有扁平 AC",
    },
    {
        "script": "backend/scripts/gen/generate_workpaper_word_template_adjudication.py",
        "reads": "requirements.md",
        "status": "pending_relink",
        "relink_owner": "7.1",
        "note": "依赖 AC 7.7 原文形态（170 条结构里的一条）",
    },
    {
        "script": "backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py",
        "reads": "requirements.md",
        "status": "pending_relink",
        "relink_owner": "7.1",
        "note": "依赖 AC 14.10 容量门定义",
    },
]


def test_spec_doc_consumer_registry_is_complete() -> None:
    """已知消费方清单不为空且每条都有必填字段。"""
    assert _SPEC_DOC_CONSUMERS, "消费方清单为空 —— 至少有 milestones 是 ok 的"
    for entry in _SPEC_DOC_CONSUMERS:
        assert "script" in entry and "reads" in entry and "status" in entry


def test_ok_consumers_can_find_their_document() -> None:
    """status=ok 的消费方必须能找到它读的文档（不是 FileNotFoundError 也不是空）。"""
    for entry in _SPEC_DOC_CONSUMERS:
        if entry["status"] != "ok":
            continue
        doc = SPEC_DIR / entry["reads"]
        assert doc.is_file(), (
            f"{entry['script']} 读 {entry['reads']}，但文件不在 {doc} —— "
            "status=ok 的消费方不该找不到文档"
        )
        assert doc.stat().st_size > 100, f"{doc} 太小（<100 bytes），可能是空壳"


def test_pending_relink_consumers_have_relink_owner() -> None:
    """status=pending_relink 的必须写明由哪个任务做前置重接。"""
    for entry in _SPEC_DOC_CONSUMERS:
        if entry["status"] != "pending_relink":
            continue
        assert entry.get("relink_owner"), (
            f"{entry['script']} 标了 pending_relink 但没写 relink_owner —— "
            "不能留没有 owner 的锚点断开项"
        )


def test_no_unknown_consumer_status() -> None:
    """status 必须在封闭集合里。"""
    allowed = {"ok", "retired", "pending_relink"}
    for entry in _SPEC_DOC_CONSUMERS:
        assert entry["status"] in allowed, f"{entry['script']} 的 status={entry['status']} 不在 {allowed}"


def test_retired_consumers_are_not_in_any_gate() -> None:
    """退役的消费方不得留在门禁里（与 test_task66_execution_ledger 同族逻辑）。"""
    for entry in _SPEC_DOC_CONSUMERS:
        if entry["status"] != "retired":
            continue
        script_name = pathlib.Path(entry["script"]).name
        for gate_rel in (
            ".github/workflows/ci.yml",
            ".github/workflows/governance-checks.yml",
            ".pre-commit-config.yaml",
            ".git-hooks/pre-commit",
            ".git-hooks/pre-push",
        ):
            gate_path = ROOT / gate_rel
            if not gate_path.is_file():
                continue
            assert script_name not in gate_path.read_text(encoding="utf-8", errors="replace"), (
                f"退役脚本 {script_name} 仍被 {gate_rel} 引用 —— 会长期全红"
            )
