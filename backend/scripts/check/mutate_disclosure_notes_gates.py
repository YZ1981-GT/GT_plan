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
            '    await assert_project_permission(db, current_user, data.project_id, "edit")',
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
            '    await _assert_note_project_access(db, current_user, note_id, "edit")',
            "    pass  # 变异：update_note 去掉项目门禁",
            "test_uses_body_gate",
            "update_note 退回仅 require_operation（可改任意项目的附注）",
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
            """    await _assert_note_project_access(
        db, current_user, note_id, "readonly", missing_ok=True
    )""",
            "    pass  # 变异：trace_cell 去掉项目门禁",
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

LABEL = "附注端点门禁"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(GATE_MUTATIONS, LABEL)
    return run_group(GATE_MUTATIONS, LABEL)


if __name__ == "__main__":
    sys.exit(main())
