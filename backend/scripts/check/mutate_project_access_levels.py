"""变异检验：项目权限级别名 fail-closed（拼错不得静默放行）。

用法::

    python backend/scripts/check/mutate_project_access_levels.py
    python backend/scripts/check/mutate_project_access_levels.py --check-anchors

背景：``require_project_access`` 用 ``PERMISSION_HIERARCHY.get(min_permission, 0)`` 取所需
层级，未登记的级别名静默取到 0 ⇒ ``user_level < 0`` 恒为假 ⇒ 任何项目成员（含 readonly）
都能通过。全仓实测 4 个写端点因此被降级（disclosure_notes 的删除/状态/恢复写 "editor"，
wp_editor_router 的签署状态更新写 "member"）。现改为工厂调用期（模块导入期）硬失败。

harness 共用 ``mutate_common``。
"""

from __future__ import annotations

import argparse
import sys

from mutate_common import Mutation, check_group_anchors, run_group

GUARD = "backend/tests/test_project_access_level_registry.py"
DEPS = "backend/app/deps.py"
NOTES = "backend/app/routers/disclosure_notes.py"
WPED = "backend/app/routers/wp_editor_router.py"

ACCESS_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "A01",
            DEPS,
            """    if min_permission not in PERMISSION_HIERARCHY:
        raise ValueError(""",
            """    if False:  # 变异：取消 fail-closed 校验
        raise ValueError(""",
            "test_unknown_level_raises_at_factory_time",
            "取消导入期级别校验（拼错重新静默放行）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "A02",
            DEPS,
            'PERMISSION_HIERARCHY: dict[str, int] = {"edit": 3, "review": 2, "readonly": 1}',
            'PERMISSION_HIERARCHY: dict[str, int] = {"edit": 3, "review": 2, "readonly": 0}  # 变异',
            "test_hierarchy_is_strictly_ordered",
            "readonly 层级降为 0（与「未登记取 0」是同一个洞）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "A03",
            NOTES,
            """    await require_project_access("edit")(
        project_id=project_id, current_user=current_user, db=db
    )""",
            """    await require_project_access("editor")(
        project_id=project_id, current_user=current_user, db=db
    )""",
            "test_all_call_sites_use_registered_levels",
            "附注统一编辑门禁写成 editor（未登记级别；五个写端点一起降级）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "A04",
            WPED,
            'current_user: User = Depends(require_project_access("edit")),\n):\n    """更新 word-template 底稿签署状态',
            'current_user: User = Depends(require_project_access("member")),\n):\n    """更新 word-template 底稿签署状态',
            "test_known_downgraded_endpoints_now_require_edit",
            "签署状态端点写回 member（readonly 成员即可改签署状态）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "A05",
            GUARD,
            'CALL_RE = re.compile(r"""require_project_access\\(\\s*["\']([^"\']*)["\']""")',
            'CALL_RE = re.compile(r"""__never_matches__""")  # 变异：扫描器失效',
            "test_scanner_finds_call_sites",
            "扫描器正则失效（反向自检：全仓判据必须先证明自己扫到了东西）",
        ),
        GUARD,
    ),
)

LABEL = "项目权限级别"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(ACCESS_MUTATIONS, LABEL)
    return run_group(ACCESS_MUTATIONS, LABEL)


if __name__ == "__main__":
    sys.exit(main())
