"""变异检验：回写后下游联动不得静默失败（snapshot_writer Step 8）。

用法::

    python backend/scripts/check/mutate_snapshot_writer_downstream.py
    python backend/scripts/check/mutate_snapshot_writer_downstream.py --check-anchors

背景：`SnapshotWriter._write_workpaper_cell` 的 Step 8（orchestrator.after_save）原本被
一个 ``except Exception`` 整块吞成 WARNING，连「ORM 取不到实例」都不记 —— file_version
没++、prefill_stale 没标、WORKPAPER_SAVED 没发，而用户看到「保存成功」。这是最贵的一类
fail-open。同域那条集成测试也名不副实：捕获了 publish 却从不断言。

现改为记 ERROR + 返回体带 ``warnings``，并把测试补成真断言。本组锚定该行为不得回退。

harness 共用 ``mutate_common``。
"""

from __future__ import annotations

import argparse
import sys

from mutate_common import Mutation, check_group_anchors, run_group

GUARD = "backend/tests/test_workpaper_save_orchestrator_integration.py"
WRITER = "backend/app/services/custom_query/snapshot_writer.py"

DOWNSTREAM_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "S01",
            WRITER,
            """        # 下游联动没跑起来时必须让调用方看得见（Step 8 非致命但不静默）
        if downstream_warnings:
            payload["warnings"] = downstream_warnings
        return payload""",
            "        return payload  # 变异：联动失败不再暴露",
            "test_downstream_failure_is_surfaced_not_silent",
            "联动失败不再进返回体（回到静默 fail-open）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "S02",
            WRITER,
            """            if wp_obj is None:""",
            """            if False:  # 变异：不再识别 ORM 取不到实例""",
            "test_downstream_failure_is_surfaced_not_silent",
            "ORM 取不到实例时不记 ERROR 也不提示（原缺陷形态）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "S03",
            WRITER,
            """                await save_orchestrator.after_save(
                    db, wp_obj, user,
                    trigger="custom_query_writeback",""",
            """                await _mut_noop(  # 变异：不再调 orchestrator
                    db, wp_obj, user,
                    trigger="custom_query_writeback",""",
            "test_writeback_triggers_main_event_bus",
            "不再调 orchestrator.after_save（事件不发、联动全断）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "S05",
            "backend/app/routers/custom_query.py",
            """    if write_result.get("warnings"):
        response["warnings"] = write_result["warnings"]
    return response""",
            "    return response  # 变异：router 丢掉 service 的 warnings",
            "test_warnings_reach_response",
            "router 不透传 warnings（service 加了没人消费 = 死数据）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "S04",
            WRITER,
            '            "audit_logged": True,\n        }',
            '            "audit_logged": True,\n            "warnings": ["恒有警告"],  # 变异\n        }',
            "test_writeback_triggers_main_event_bus",
            "成功路径也带警告（反向：正常时不该有 warnings）",
        ),
        GUARD,
    ),
)

LABEL = "回写下游联动"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(DOWNSTREAM_MUTATIONS, LABEL)
    return run_group(DOWNSTREAM_MUTATIONS, LABEL)


if __name__ == "__main__":
    sys.exit(main())
