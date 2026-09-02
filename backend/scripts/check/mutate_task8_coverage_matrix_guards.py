"""Task 8 变异检验：覆盖矩阵生成器、14.15 gate 与变异骨架自身的守卫是否真承重。

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 · Requirements 14.7, 14.15 · Property 57

四态判定与覆盖面分母全部复用平台共享件 `backend/scripts/_mutation_kit`，跨行锚点走本 spec
新增的 `_mutation_kit.span`（`\\n` 编写 + 按目标文件换行升级 + 还原后 sha256 自证）。
**不看退出码**：判定只用失败测试名差集。

三类变异：

* ``generator`` —— 生成器的判据（缺陷探测、overlay fail-closed、解析期断言）
* ``gate`` —— 14.15 gate 的判据（红/绿、stale 优先、未知 defect code）
* ``kit`` —— **元层面**：把变异骨架自己的约束改坏，看骨架自测是否打红。骨架是所有
  其他守卫可信度的地基，它失效不会有任何下游守卫报警。

用法（仓库根）::

    python backend/scripts/check/mutate_task8_coverage_matrix_guards.py --list
    python backend/scripts/check/mutate_task8_coverage_matrix_guards.py --check-anchors
    python backend/scripts/check/mutate_task8_coverage_matrix_guards.py --run all \\
        --report-path tmp_task8_mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GEN = "backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py"
GATE = "backend/scripts/check/check_workpaper_ac_coverage_gate.py"
KIT = "backend/scripts/_mutation_kit/span.py"
PROBE = "backend/scripts/diagnose/probe_task8_migration_version_baseline.py"
OVERLAY = "backend/data/workpaper_ac_evidence_overlay.json"
MATRIX = "backend/data/workpaper_ac_coverage_matrix.json"

MATRIX_GUARD = "test_workpaper_ac_coverage_matrix.py"
SKELETON_GUARD = "test_mutation_span_skeleton.py"
PROBE_GUARD = "test_task8_migration_version_baseline_probe.py"

#: 覆盖面分母 —— Task 8 创建的守卫文件全集。新增守卫文件必须同时加一条变异，
#: 否则全量运行的报告末尾会显示 [GAP] 欠账且退出码非零。
GUARD_FILES: dict[str, str] = {
    MATRIX_GUARD: "Task 8 新建（矩阵生成器 + 14.15 gate 守卫）",
    SKELETON_GUARD: "Task 8 新建（跨行锚点变异骨架自测）",
    PROBE_GUARD: "Task 8 新建（migration/version 只读基线探针守卫）",
}

PYTEST_ARGS = [
    f"backend/tests/{MATRIX_GUARD}",
    f"backend/tests/{SKELETON_GUARD}",
    f"backend/tests/{PROBE_GUARD}",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

#: 冻结基线（2026-08-16 实测：矩阵 50 + 骨架 32 + 探针 7）。改这个数必须同时说明来源。
#: 88 -> 89：首轮 P03 判 GREEN（真实 migrations 目录里每个 V 都有配对 R，
#: `len(rollback)` 与「有 V 对应的 R 数」恒等 ⇒ 该变异在现有数据上是无效变异，
#: 不是守卫缺陷）。给 `scan_migrations` 加 root 注入口后补 orphan R 合成用例，
#: 判据从此不依赖磁盘的巧合。
BASELINE_PASSED = 89

MUTATIONS: list[SpanMutation] = [
    # ── generator：逐个缺陷探测器 ────────────────────────────────────────────
    SpanMutation(
        id="G01",
        path=GEN,
        anchor='        defects: list[str] = []\n        if not covering:\n'
               '            defects.append("dangling_ac")',
        new='        defects: list[str] = []\n        if False:\n'
            '            defects.append("dangling_ac")',
        want="test_ac_without_any_task_is_reported_as_dangling",
        wants=("test_no_dangling_ac_or_property",),
        why="停止把「没有任何 task 引用」判成悬挂 AC ⇒ 14.15 的第一条判据整体失效。"
            "锚点跨三行是刻意的：判据本体是「初始化 defects 后紧接着这一支」，"
            "只锚 `if not covering:` 会与其他条件行同形",
    ),
    SpanMutation(
        id="G02",
        path=GEN,
        anchor='        if len(covering) == 1:\n'
               '            defects.append("self_certified_single_task")',
        new='        if False:\n            defects.append("self_certified_single_task")',
        want="test_single_covering_task_is_reported_as_self_certified",
        wants=("test_reported_self_certification_matches_an_independent_derivation",),
        why="停止探测单任务自证 —— Wave 0 硬约束第 4 条明令 pilot/单 operation 不替代逐 entry "
            "验收，其在三件套层面的等价物就是「实现 task 不能同时充当独立验证 task」",
    ),
    SpanMutation(
        id="G03",
        path=GEN,
        anchor='        elif covering and not pairs:\n'
               '            defects.append("no_dependency_edge")',
        new='        elif False:\n            defects.append("no_dependency_edge")',
        want="test_two_tasks_without_a_dependency_edge_are_not_independent_verification",
        why="两个互不依赖的 task 各自宣称覆盖同一 AC 时不再报缺陷 ⇒ 「独立验证」退化为"
            "「被提到过两次」，14.15 的「无依赖边」判据消失",
    ),
    SpanMutation(
        id="G04",
        path=GEN,
        anchor='        if not properties_by_ac.get(ac):\n'
               '            defects.append("no_property_oracle")',
        new='        if False:\n            defects.append("no_property_oracle")',
        want="test_ac_without_a_design_property_is_reported",
        wants=("test_reported_no_property_oracle_matches_an_independent_derivation",),
        why="停止探测「没有任何 Property 验证这条 AC」⇒ 当前 101 条真实欠账会静默归零，"
            "这正是「把错值当基线锁死」的反面：让判据消失比锁死更彻底",
    ),
    SpanMutation(
        id="G05",
        path=GEN,
        anchor='        if not evidence_classes:\n'
               '            defects.append("no_evidence_type")',
        new='        if False:\n            defects.append("no_evidence_type")',
        want="test_ac_whose_family_is_unadjudicated_has_no_evidence_type",
        why="未裁决 evidence type 的 oracle family 不再被报出 ⇒ overlay 可以只裁决一部分"
            "family 而 gate 照样绿",
    ),
    SpanMutation(
        id="G06",
        path=GEN,
        anchor="                if impl != verifier and impl in ancestors.get(verifier, set())",
        new="                if impl != verifier",
        want="test_two_tasks_without_a_dependency_edge_are_not_independent_verification",
        wants=("test_dependency_edge_may_be_transitive",),
        why="把「独立验证」从「依赖图上确有边」降级为「不是同一个 task」⇒ 任意两个无关 task "
            "互相充当验证者。这是本矩阵最容易被无声放宽的一条判据",
    ),
    # ── generator：overlay fail-closed（overlay 只承载裁决，不承载豁免）───────
    SpanMutation(
        id="G07",
        path=GEN,
        anchor="    unknown_top = sorted(set(overlay) - _OVERLAY_KEYS)",
        new="    unknown_top = []",
        want="test_overlay_validation_is_fail_closed",
        why="放开 overlay 顶层键白名单 ⇒ 可以加 `exempt_acs` 之类的豁免字段，"
            "而 Task 3 范式明确要求 overlay 只能承载裁决",
    ),
    SpanMutation(
        id="G08",
        path=GEN,
        anchor="        illegal = sorted(set(classes) - _EVIDENCE_CLASSES)",
        new="        illegal = []",
        want="test_overlay_validation_is_fail_closed",
        why="放开 evidence_class 封闭枚举 ⇒ 裁决可以写任意自造字符串，"
            "「有 evidence type」退化成「填了点什么」",
    ),
    SpanMutation(
        id="G09",
        path=GEN,
        anchor='        if value.get("design_evidence_text") != row["evidence_text"]:',
        new="        if False:",
        want="test_overlay_validation_is_fail_closed",
        wants=("test_real_overlay_pins_the_design_evidence_text_verbatim",),
        why="不再逐字比对 overlay 钉住的 evidence 文本与 design.md 当前值 ⇒ design 改了"
            "而裁决还停在旧语义（陈旧裁决静默生效，是最难发现的一类漂移）",
    ),
    SpanMutation(
        id="G10",
        path=GEN,
        anchor="        row = by_family.get(name)\n        if row is None:",
        new='        row = by_family.get(name) or {"evidence_text": value.get("design_evidence_text")}\n'
            "        if False:",
        want="test_overlay_validation_is_fail_closed",
        why="接受 design.md 已不存在的 oracle family 裁决 ⇒ 幽灵条目长期留存（Task 3 的"
            "`overlay adjudicates writers that no longer exist` 同型缺陷）",
    ),
    SpanMutation(
        id="G11",
        path=GEN,
        anchor='    if overlay.get("schema_version") != 1 or overlay.get("review_status") != "reviewed":',
        new='    if overlay.get("schema_version") != 1:',
        want="test_overlay_validation_is_fail_closed",
        why="未复核（draft）的 overlay 也能生效 ⇒ 「reviewed overlay」这一前提失效",
    ),
    # ── generator：解析期断言（行首锚点 + assert 的那一层）────────────────────
    SpanMutation(
        id="G12",
        path=GEN,
        anchor="        if req_num != current_req:",
        new="        if False:",
        want="test_ac_under_a_mismatched_requirement_heading_is_refused",
        why="不再校验 AC 编号与所处 `### Requirement N` 一致 ⇒ 复制粘贴的段落会被解析成"
            "另一条 Requirement 的 AC，整个矩阵的归属静默错位",
    ),
    SpanMutation(
        id="G13",
        path=GEN,
        anchor="    header_at = [i for i, line in enumerate(block) if line.strip() == _ORACLE_MATRIX_HEADER_ROW]",
        new='    header_at = [i for i, line in enumerate(block) if line.strip().startswith("| AC")]',
        want="test_oracle_matrix_header_must_match_verbatim",
        why="把表头逐字比对降级成前缀匹配 ⇒ 列顺序或列名改动后仍按旧下标取 family/evidence，"
            "读到的是别的列（错列比缺列更危险，因为它有值）",
    ),
    SpanMutation(
        id="G14",
        path=GEN,
        anchor="        if task in stack:",
        new="        if False:",
        want="test_dependency_cycle_is_refused",
        why="不再检测依赖环 ⇒ 环上的任务互相充当「独立验证 task」，且闭包计算无限递归",
    ),
    SpanMutation(
        id="G15",
        path=GEN,
        anchor='        if task["requirements_lines"] != 1:',
        new="        if False:",
        want="test_task_without_a_requirements_line_is_refused",
        why="允许任务缺 `_Requirements:` 行 ⇒ 该任务覆盖的 AC 全部变成悬挂而无人察觉，"
            "悬挂计数反而下降（假绿方向）",
    ),
    SpanMutation(
        id="G16",
        path=GEN,
        anchor='            "sha256": _sha256(raw),',
        new='            "sha256": "",',
        want="test_matrix_pins_a_digest_of_every_spec_document",
        wants=("test_matrix_on_disk_matches_the_spec_documents",),
        why="抹掉三件套逐文档 sha256 ⇒ source digest fail-closed 失效，"
            "三件套改了而矩阵没重生成时不再打红",
    ),
    # ── gate：红/绿方向与优先级 ──────────────────────────────────────────────
    SpanMutation(
        id="A01",
        path=GATE,
        anchor="    return (1 if by_code else 0), lines + _render_defects(fresh, by_code)",
        new="    return 0, lines + _render_defects(fresh, by_code)",
        want="test_gate_is_red_while_any_defect_remains",
        why="gate 在仍有 14.15 阻塞项时返回 0 ⇒ 「归档门」变成一份只打印不拦阻的报告，"
            "这正是 g7 spec 沉淀的「只打印的 --list 在 CI 里恒绿」同型缺陷",
    ),
    SpanMutation(
        id="A02",
        path=GATE,
        anchor="    unknown = sorted(set(by_code) - set(_REASONS))",
        new="    unknown = []",
        want="test_gate_refuses_defect_codes_it_cannot_explain",
        why="生成器新增 defect code 而 gate 无法解释时不再拦阻 ⇒ 新缺陷类型会被打印成"
            "一个无说明的裸计数，读者无法归因",
    ),
    SpanMutation(
        id="A03",
        path=GATE,
        anchor="    if _stored_text() != render(fresh):",
        new="    if False:",
        want="test_gate_reports_stale_before_counting_defects",
        why="陈旧矩阵不再优先于缺陷计数 ⇒ 三件套改动后 gate 会拿旧矩阵报一个过时的数字，"
            "而任何基于它的结论都是假的",
    ),
    # ── 数据文件：生成物与裁决被手改时必须打红 ───────────────────────────────
    SpanMutation(
        id="D01",
        path=OVERLAY,
        anchor='  "review_status": "reviewed",',
        new='  "review_status": "draft",',
        want="test_matrix_on_disk_matches_the_spec_documents",
        why="把 overlay 改回未复核态 ⇒ 生成器必须整体拒绝，而不是降级成「无裁决」继续出矩阵",
    ),
    SpanMutation(
        id="D02",
        path=OVERLAY,
        anchor='        "source_ast_inventory",\n        "contract_interlock",\n        "dom_projection"',
        new='        "security_trace",\n        "contract_interlock",\n        "dom_projection"',
        want="test_matrix_on_disk_matches_the_spec_documents",
        why="静默改掉一个 family 的 evidence 裁决（仍是合法枚举值）⇒ 若矩阵未与 overlay 摘要"
            "锁死，这种「合法但错」的漂移不会被任何守卫发现",
    ),
    SpanMutation(
        id="D03",
        path=MATRIX,
        anchor='  "task": "Wave 0 Task 8",',
        new='  "task": "Wave 0 Task 9",',
        want="test_matrix_on_disk_matches_the_spec_documents",
        wants=("test_hand_edited_matrix_is_rejected_by_self_consistency",),
        why="手改生成物 ⇒ 必须被「重新生成后逐字比对」与 matrix_digest 自洽两道判据同时抓住",
    ),
    # ── kit：元层面，骨架自己的约束 ──────────────────────────────────────────
    SpanMutation(
        id="K01",
        path=KIT,
        anchor="    if len(hits) > 1 and not allow_multi:",
        new="    if False:",
        want="test_multiple_hit_anchor_is_anchor_miss",
        why="删掉锚点唯一性断言 ⇒ 所有用本骨架的变异脚本静默退化成「改第一处」，"
            "同形多处时改错行而判定照常给 RED —— 一个横跨全平台的假绿入口。"
            "不能改成 `len(hits) < 1`：那样只有多命中这一支失效，打红的测试集合不同",
    ),
    SpanMutation(
        id="K02",
        path=KIT,
        anchor='    return text.replace("\\n", eol) if eol != "\\n" else text',
        new="    return text",
        why="停止把 `\\n` 编写的锚点升级为目标文件换行 ⇒ CRLF 文件上跨行锚点恒 0 命中。"
            "这正是 `_LEGACY_NOT_REQUIRED` 里 g7 变异脚本迁移受阻的那条实测缺陷",
        want="test_multiline_anchor_hits_on_both_line_endings",
        wants=("test_crlf_target_is_not_rewritten_to_lf",),
    ),
    SpanMutation(
        id="K03",
        path=KIT,
        anchor="        if restored != before_digest:",
        new="        if False:",
        want="test_restore_mismatch_raises_restore_failed",
        why="删掉还原后 sha256 自证 ⇒ 还原失败不再中止，后续每条变异都跑在被污染的工作树上，"
            "判定集体退化为 WRONG-TEST 而无人知道原因",
    ),
    SpanMutation(
        id="K04",
        path=KIT,
        anchor="        except Exception as exc:  # noqa: BLE001 - 记录并继续；还原已在 finally 完成\n"
               '            record.update(verdict=ERROR, detail=f"{type(exc).__name__}: {exc}")',
        new="        except Exception:  # noqa: BLE001\n            pass",
        want="test_runner_crash_is_recorded_as_error_not_as_success",
        why="把 runner 崩溃吞成「没有新增失败」⇒ 判定退化为 GREEN（读起来像守卫缺陷），"
            "实际是什么都没跑过。AC 5.12 明令解析异常不得被宽泛 except 降为成功",
    ),
    # ── probe：migration/version 只读基线 ────────────────────────────────────
    SpanMutation(
        id="P01",
        path=PROBE,
        anchor='        "max_forward_version": max(numbers) if numbers else None,',
        new='        "max_forward_version": (max(numbers) - 1) if numbers else None,',
        want="test_scan_reports_the_real_migration_files",
        why="最高 V 号少报 1 ⇒ 下一个 Wave 新建迁移时撞号（memory 记的「V 号必须实扫、"
            "不能信旧数」正是这类缺陷的后果）",
    ),
    SpanMutation(
        id="P02",
        path=PROBE,
        anchor='_VERSION_RE = re.compile(r"^V(\\d+)__", re.IGNORECASE)',
        new='_VERSION_RE = re.compile(r"^[VR](\\d+)__", re.IGNORECASE)',
        want="test_scan_reports_the_real_migration_files",
        wants=("test_every_sql_file_lands_in_exactly_one_bucket",),
        why="把回滚脚本也算成正向迁移 ⇒ 文件数与配对结论同时失真，而两者看起来都「有值」",
    ),
    SpanMutation(
        id="P03",
        path=PROBE,
        anchor='        "rollback_paired_count": sum(1 for n in rollback if n in forward),',
        new='        "rollback_paired_count": len(rollback),',
        want="test_orphan_rollback_script_is_not_counted_as_paired",
        why="把「配对数」改成「回滚文件总数」⇒ 存在无对应 V 的孤儿 R 脚本时仍报满配对。"
            "🔴 本条首轮判 GREEN：真实 migrations 目录里每个 V 都有配对 R，两个表达式在该"
            "数据上恒等 ⇒ 属**无效变异**（数据造成），不是守卫缺陷。处置是给 scan_migrations "
            "加 root 注入口 + 合成一个孤儿 R 用例，让判据不再依赖磁盘巧合",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            pytest_args=PYTEST_ARGS,
            description=__doc__,
            baseline_passed=BASELINE_PASSED,
        )
    )
