"""变异检验：跨 sheet 溯源端点接线（addr_id 不得静默降级）。

用法::

    python backend/scripts/check/mutate_cross_sheet_trace_wiring.py
    python backend/scripts/check/mutate_cross_sheet_trace_wiring.py --check-anchors

背景：`/cross-sheet-trace` 是 async 端点却直调同步 BFS，``_sync_resolve`` 在 running
loop 下降级 ⇒ 链节点 addr_id 恒 None、审计记的是 ``sheet!cell`` 而非 addr_id。同一
缺口曾有两个互不接线的修复（orchestrator / 复制 BFS 的 full_resolve_async），现保留
前者接进 router、删除后者。本组锚定该接线不得回退。

harness 共用 ``mutate_common``。
"""

from __future__ import annotations

import argparse
import sys

from mutate_common import Mutation, check_group_anchors, run_group

GUARD = "backend/tests/test_cross_sheet_trace_wiring.py"
ORCH_GUARD = "backend/tests/test_cross_sheet_trace_orchestrator.py"
ROUTER = "backend/app/routers/custom_query.py"
RESOLVER = "backend/app/services/custom_query/cross_sheet_resolver.py"
ORCH = "backend/app/services/custom_query/cross_sheet_trace_orchestrator.py"

TRACE_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "T01",
            ROUTER,
            """    trace_result = await cross_sheet_trace_orchestrator.trace(
        parsed_data,
        sheet_name,
        cell_ref,
        project_id=project_id,
        db=db,
        max_depth=max_depth,
    )""",
            """    from app.services.custom_query.cross_sheet_resolver import cross_sheet_resolver

    trace_result = cross_sheet_resolver.resolve(  # 变异：回退同步 BFS
        parsed_data=parsed_data,
        sheet_name=sheet_name,
        cell_ref=cell_ref,
        max_depth=max_depth,
    )""",
            "test_endpoint_goes_through_orchestrator",
            "端点回退直调同步 BFS（addr_id 恒 None）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "T02",
            ROUTER,
            "        trace_addr_ids.extend(node.addr_id or node.uri for node in trace_result.chain)",
            "        trace_addr_ids.extend(node.uri for node in trace_result.chain)  # 变异",
            "test_audit_records_real_addr_ids",
            "审计留痕退回 uri 而非真 addr_id（违反 R14.3/R14.4）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "T03",
            ROUTER,
            """    await ownership_guard.assert_target_accessible(
        user=current_user, project_id=project_id, db=db
    )""",
            "    pass  # 变异：移除归属校验（IDOR 敞口）",
            "test_ownership_guard_still_precedes_read",
            "溯源端点不再做项目归属校验",
        ),
        GUARD,
    ),
    (
        Mutation(
            "T04",
            ROUTER,
            """        project_id=project_id,
        db=db,
        max_depth=max_depth,
    )""",
            """        max_depth=max_depth,
    )  # 变异：不传 project_id / db""",
            "test_endpoint_goes_through_orchestrator",
            "不把 project_id / db 传给 orchestrator（ACNR 无从定位与查库）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "T05",
            RESOLVER,
            "    def _is_missing(",
            """    async def full_resolve_async(
        self,
        parsed_data: dict | None,
        sheet_name: str,
        cell_ref: str,
        max_depth: int = 3,
    ) -> RefChainResponse:  # 变异：把复制的 BFS 加回来
        return self.resolve(parsed_data, sheet_name, cell_ref, max_depth)

    def _is_missing(""",
            "test_resolver_has_single_bfs",
            "resolver 又长出第二份 BFS（两份必漂移）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "T06",
            ORCH,
            "        addr_id=resolved.addr_id if resolved.found else None,",
            "        addr_id=None,  # 变异：解析结果不合并回链",
            "test_orchestrator_merges_addr_id_from_async_resolution",
            "orchestrator 解析出 addr_id 却不合并回链（接线成空操作）",
        ),
        ORCH_GUARD,
    ),
)

LABEL = "跨 sheet 溯源接线"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(TRACE_MUTATIONS, LABEL)
    return run_group(TRACE_MUTATIONS, LABEL)


if __name__ == "__main__":
    sys.exit(main())
