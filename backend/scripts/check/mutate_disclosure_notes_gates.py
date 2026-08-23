"""变异检验：附注端点项目级门禁（防 IDOR）。

用法::

    python backend/scripts/check/mutate_disclosure_notes_gates.py
    python backend/scripts/check/mutate_disclosure_notes_gates.py --check-anchors

背景：34 个附注端点里 7 个存在真实归属缺口 —— 3 个门禁「挂了但校验错对象」
（project_id 在 body / 路径无 project_id 导致依赖退化为查询参数 / require_operation 无
project_id 时只按 system_role 判），4 个完全无门禁。本组锚定修好的形态不得回退。

harness 共用 ``mutate_common``。
"""

from __future__ import annotations

import argparse
import sys

from mutate_common import Mutation, check_group_anchors, run_group

GUARD = "backend/tests/test_disclosure_notes_project_gate_contract.py"
NOTES = "backend/app/routers/disclosure_notes.py"

GATE_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "D01",
            NOTES,
            """    await _assert_project_edit(
        project_id=data.project_id, current_user=current_user, db=db
    )""",
            "    pass  # 变异：generate 去掉项目门禁",
            "test_all_endpoints_gated",
            "generate 无门禁（任何登录用户可为任意项目生成附注）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D02",
            NOTES,
            """    await _assert_project_edit(
        project_id=project_id, current_user=current_user, db=db
    )

    holder: dict[str, Any] = {}

    async def _mutate() -> dict[str, Any]:
        engine = DisclosureEngine(db)""",
            """    holder: dict[str, Any] = {}

    async def _mutate() -> dict[str, Any]:
        engine = DisclosureEngine(db)  # 变异：update_note 去掉统一编辑门禁""",
            "test_uses_body_gate",
            "update_note 退回仅反查不鉴权（可改任意项目的附注）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D03",
            NOTES,
            '    await _assert_validation_project_access(db, current_user, validation_id, "edit")',
            "    pass  # 变异：confirm_finding 去掉项目门禁",
            "test_uses_body_gate",
            "confirm_finding 退回校验无关项目",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D04",
            NOTES,
            """    await ownership_guard.assert_target_accessible(
        user=current_user, project_id=project_id, db=db
    )""",
            "    pass  # 变异：trace_cell 去掉归属门禁",
            "test_all_endpoints_gated",
            "trace_cell 无门禁（可读别的项目的溯源链与试算表证据）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D05",
            NOTES,
            """    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    \"\"\"只读诊断：列出「有报表↔附注勾稽但无写值 linkage」的章节""",
            """    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    \"\"\"只读诊断：列出「有报表↔附注勾稽但无写值 linkage」的章节""",
            "test_all_endpoints_gated",
            "linkage-gaps 退回无门禁（跨项目读）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D06",
            NOTES,
            """    note_section: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):""",
            """    note_section: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):""",
            "test_all_endpoints_gated",
            "pull-from-workpapers 退回无门禁（跨项目写）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D07",
            NOTES,
            """        if missing_ok:
            return None
        raise HTTPException(status_code=404, detail=not_found_detail)
    await assert_project_permission(db, current_user, project_id, min_permission)""",
            """        if missing_ok:
            return None
        raise HTTPException(status_code=404, detail=not_found_detail)
    # 变异：反查后不鉴权""",
            "test_helper_resolves_project_before_permission_check",
            "反查型门禁只反查不鉴权（形似有门禁、实则放行）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "D08",
            NOTES,
            '    current_user: User = Depends(get_current_user),\n):\n    """确认校验发现为"已确认-无需修改" """',
            '    current_user: User = Depends(require_project_access("edit")),\n):\n    """确认校验发现为"已确认-无需修改" """',
            "test_does_not_rely_on_path_dependency",
            "confirm_finding 重新挂上 require_project_access（路径无 project_id ⇒ 变查询参数陷阱）",
        ),
        GUARD,
    ),
)

#: 第二组：mutation 协调器接线（幂等 / 单一事务边界 / commit 后才发事件）
HARDENING_GUARD = "backend/tests/test_disclosure_notes_hardening.py"

COORDINATOR_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "D09",
            NOTES,
            "    return supplied or str(uuid4())",
            "    return str(uuid4())  # 变异：忽略客户端传的 mutation_id",
            "test_mutation_id_accepts_header_or_generates_uuid",
            "忽略客户端 mutation_id（重试不再幂等，每次都当新请求）",
        ),
        HARDENING_GUARD,
    ),
    (
        Mutation(
            "D10",
            NOTES,
            """    await require_operation("note:edit")(
        current_user=current_user, project_id=project_id, db=db
    )""",
            "    pass  # 变异：统一门禁漏掉操作级检查",
            "test_p2_unified_edit_gate_orders_project_then_operation_then_lock",
            "统一门禁漏掉 note:edit 操作级检查（三段变两段）",
        ),
        HARDENING_GUARD,
    ),
    (
        Mutation(
            "D11",
            NOTES,
            "    await check_consol_lock(project_id=project_id, db=db)",
            "    pass  # 变异：统一门禁漏掉合并锁检查",
            "test_assert_project_edit_completes_before_any_db_write",
            "统一门禁漏掉合并锁（合并期间仍可改附注）",
        ),
        HARDENING_GUARD,
    ),
    (
        Mutation(
            "D12",
            NOTES,
            """    result["validation"] = await _run_validation_isolated(
        data.project_id, data.year, data.template_type,
    )""",
            """    result["validation"] = await _run_validation_best_effort(
        db, data.project_id, data.year, data.template_type,
    )  # 变异：旁路校验复用请求 session""",
            "test_generate_success_invokes_coordinator_and_returns_committed",
            "旁路校验复用请求 session（一次 mutation 两次 commit，单一事务边界被破坏）",
        ),
        HARDENING_GUARD,
    ),
    (
        Mutation(
            "D13",
            NOTES,
            """    raise HTTPException(
        status_code=501,
        detail={
            "error_code": "HISTORICAL_UPLOAD_NOT_IMPLEMENTED",
            "message": "历史 Word/PDF 解析尚未实现，请勿依赖该入口导入历史附注",
            "project_id": str(project_id),
            "year": year,
        },
    )""",
            """    return {  # 变异：退回假成功
        "message": "历史附注上传接口已就绪",
        "project_id": str(project_id),
        "year": year,
    }""",
            "test_upload_history_returns_501_no_db_dependency",
            "历史上传退回「假成功」200（用户以为导入了，其实什么都没做）",
        ),
        HARDENING_GUARD,
    ),
    (
        Mutation(
            "D14",
            NOTES,
            '        "historical_upload": False,',
            '        "historical_upload": True,  # 变异：能力清单谎称可用',
            "test_capabilities_report_historical_upload_disabled_in_chinese",
            "能力清单谎称历史上传可用（前端会把入口开着）",
        ),
        HARDENING_GUARD,
    ),
)

LABEL = "附注端点门禁"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        rc = check_group_anchors(GATE_MUTATIONS, LABEL)
        print()
        return check_group_anchors(COORDINATOR_MUTATIONS, "mutation 协调器接线") or rc
    return run_group(GATE_MUTATIONS, LABEL) or run_group(
        COORDINATOR_MUTATIONS, "mutation 协调器接线"
    )


if __name__ == "__main__":
    sys.exit(main())
