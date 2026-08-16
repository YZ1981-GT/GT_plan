"""章节映射守卫的变异检验（soe/listed 附注转换正确性）。

spec: soe-listed-note-conversion-correctness / Task 11（Task 18 在此基础上扩清单）（已归档）
迁移：2026-08-15 由 `e1-variant-recalc-and-mutation-denominator-closure` Task 12 迁到
`_mutation_kit` 共享件 —— 原先 277 行里约 150 行是自带样板（md5 / 跑测试 / 按行号或整行
定位 / 备份还原 / 三态判定），现全部来自共享件，本文件只保留 9 条变异声明。

被测守卫 = ``backend/tests/test_note_conversion_section_mapping.py``（Property 5~10 /
16~19 / 24~26 / 35 / 36）。design.md「变异检验清单」里属章节映射的 4 条
（``_map_disclosure_notes`` 改回 ``count(*)`` / 去掉 ``legacy_section_ids`` 追加 /
改 ``note_section`` 而不改 ``binding_id`` 前缀 / 对 ``section_id IS NULL`` 静默跳过）
已在 M1/M2/M3/M4 落地；另补 5 条（失败隔离、归档留痕、新建章节号、``format_adapted``
无条件计数、**Property 24 判据被改严**）。

🔴 **M9 是口径锁死**：design.md Property 24 明写「同类内调用也算」。M9 把判据改成
「必须有服务文件之外的调用方」，守卫必须打红 —— 否则 ``_map_*`` 这类正常私有子步骤
会被误判成孤儿，逼人把私有子步骤提成公开 API（制造第二个入口 = 双真源）。
（M9 改的是 `test_note_conversion_v2_removal.py` 里的一行，而断言它的两条测试在
被测文件里做源码级检查 —— 2026-08-15 迁移时已复核该链路成立。）

## 迁移时保留的一处原有形态

M1/M5 用 **绝对行号** `line` 消歧（同形锚点在文件内多处出现）。原脚本注释记录过它
漂移一次（L1189 → L2000）。共享件已提供更稳的 `scope`+`offset` **相对定位**
（只要 scope 行还唯一就有效，不受上下增删行影响），但迁移**不擅自改判据形态** ——
2026-08-15 迁移时复核两处行号仍精确命中（L1781 / L2000，文件 2321 行）。
建议后续单独改为 scope 相对定位。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

SVC = "backend/app/services/note_conversion_service.py"
V2R = "backend/tests/test_note_conversion_v2_removal.py"

BE_ARGS = [
    "backend/tests/test_note_conversion_section_mapping.py",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:cacheprovider",
]

#: 冻结基线（2026-08-15 实测 40 passed / 0 failed）。改这个数必须同时说明来源。
BASELINE_BE_PASSED = 40

#: 覆盖面分母 —— 本脚本反证的守卫文件全集。
GUARD_FILES: dict[str, str] = {
    "test_note_conversion_section_mapping.py":
        "章节映射（Property 5~10 / 16~19 / 24~26 / 35 / 36）",
}

MUTATIONS: list[Mut] = [
    Mut(
        id="M1", side="be", path=SVC, kind="replace",
        anchor="        notes = list(notes_result.scalars().all())",
        new='        notes = list(notes_result.scalars().all()); result["mapped"] = len(notes)  # MUT',
        # 🔴 Task 15/16 落地后该行形态在 `_rollback_section_state`(L954) 也出现一次
        # ⇒ 必须按行号锚定到 `_map_disclosure_notes`(1638-2146) 内那一处，否则
        # 「锚点命中 2 处」= ANCHOR-MISS，变异根本没施加（既不是 RED 也不是 GREEN）。
        line=1781,
        want="test_zero_common_sections_returns_mapped_zero",
        why="mapped 改回 count(*) 冒充（存量行数当映射数）—— 映射数虚高，"
            "零共同章节时也报有映射",
    ),
    Mut(
        id="M2", side="be", path=SVC, kind="replace",
        anchor='            changed |= _append_unique(lineage, "legacy_section_ids", legacy_section_id)',
        new="            pass  # MUT: 不再追加 legacy_section_ids",
        want="test_legacy_section_ids_recorded_for_every_mapped",
        why="去掉 template_lineage.legacy_section_ids 追加 —— 转换后无法回溯源章节 id",
    ),
    Mut(
        id="M3", side="be", path=SVC, kind="replace",
        anchor="                        rewritten = _rewrite_binding_id_prefix(new_td, old_number, new_number)",
        new="                        rewritten = 0  # MUT: 不改 binding 前缀",
        want="test_prefix_rewritten_and_old_number_recorded",
        why="改 note_section 但不改 binding_id 前缀 —— binding 静默失联，"
            "底稿推送落不到新章节",
    ),
    Mut(
        id="M4", side="be", path=SVC, kind="replace",
        anchor='                            await skip(how, detail="按 (note_section, section_title) 回填源侧 sid 失败")',
        new="                            pass  # MUT: 静默跳过，不登记原因码",
        want="test_unresolvable_rows_are_skipped_with_reason_not_silently",
        why="section_id IS NULL 回填不出时静默跳过（不登记 skipped）—— "
            "失败被吞成「没有这条数据」",
    ),
    Mut(
        id="M5", side="be", path=SVC, kind="replace",
        anchor="            except Exception as exc:  # noqa: BLE001 — 逐章节隔离，失败不阻断其余",
        new="            except ValueError as exc:  # MUT: 只捕 ValueError，注入的 RuntimeError 会冒泡",
        # 🔴 行号随 Task 15/16（preview 端点 + rollback）增长而漂移：1189 现在是
        # `)`。目标是 `_map_disclosure_notes` 的 **map_section** 阶段隔离（注入点
        # `_record_lineage` 在其内），不是 2105 的 create_section 阶段。
        line=2000,
        want="test_single_section_failure_does_not_block_the_rest",
        why="逐章节失败隔离失效（异常冒出 _map_disclosure_notes）—— 一个章节出错"
            "整批转换中断",
    ),
    Mut(
        id="M6", side="be", path=SVC, kind="replace",
        anchor='                lineage["archived_sections"] = items',
        new="                pass  # MUT: 不写 archived_sections",
        want="test_source_only_archived_with_sid_and_reason",
        why="归档不写 template_lineage.archived_sections —— 源侧独有章节被归档但无留痕",
    ),
    Mut(
        id="M7", side="be", path=SVC, kind="replace",
        anchor="                        note_section=new_number,",
        new="                        note_section=tgt_sid,  # MUT: legacy compat 缺陷形态",
        want="test_created_notes_are_empty_drafts_with_real_chapter_number",
        why="新建空章节把 note_section 写成 sid（历史 v2 缺陷形态）—— 章节号变成 UUID",
    ),
    Mut(
        id="M8", side="be", path=SVC, kind="replace",
        anchor="                            if report.changed:",
        new="                            if True:  # MUT: 无条件计数",
        want="test_format_adapted_is_zero_while_field_mapping_all_null",
        why="format_adapted 改回无条件计数 —— 空操作被上报成已适配，进度虚高",
    ),
    Mut(
        id="M9", side="be", path=V2R, kind="replace",
        anchor='        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):',
        new='        if "/tests/" in f"/{rel}" or path.name.startswith("test_") or rel.endswith("note_conversion_service.py"):  # MUT',
        wants=(
            "test_self_call_counts_as_consumer",
            "test_no_method_is_orphaned",
        ),
        want="",
        why="把 Property 24 判据改严：排除服务文件自身 ⇒ 私有子步骤会被误判成孤儿，"
            "逼人把 _map_* 提成公开 API（制造第二个入口 = 双真源）。"
            "用多目标 wants 声明，两条断言都应打红",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="章节映射守卫变异检验",
            backend_args=BE_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
