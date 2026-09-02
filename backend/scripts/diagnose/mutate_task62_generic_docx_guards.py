"""Task 62 守卫变异检验 —— 18 个 generic DOCX entry 的裁决记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 62

被检验的守卫：``backend/tests/workpaper_sync/test_task62_generic_docx_entries.py``

## 为什么每条变异都不是无效变异

本任务的产物是**裁决**而不是契约，所以它最贵的三类缺陷与前几轮完全不同：

1. **裁决被悄悄放宽** —— 把某个 blocked 分支短路掉，18 个 entry 里就会冒出「可迁移」
   的假结论，而下游 Task 66/67/70 会照着它去删 legacy、去刷 evidence。五个 verdict
   分支 + 阻塞原因表各一条变异（M01~M06）。
2. **事实检测器变成空转** —— 「parser 不认的占位形态」、重叠分类、合并单元格去重、
   原始 XML verbatim 计数，任一退化成恒假/恒真，对应那一族计数就变成 0 而记录照样
   自称通过（M07~M11）。
3. **越权供给被放行** —— 把 F2 lane 的契约算成本任务的、把 Word adapter 禁令读空、
   把 AC 7.7 的声明数抓不到当没事、把「能实证的必须实证」这条自锁摘掉（M12~M16）。

另有三条落在**记录本身**（M17~M19）：手改 JSON 里的 verdict 与计数器 —— 记录是给
Task 67 结构复核读的，只要它能被手改而守卫不红，整套裁决就没有约束力。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷：锚点未命中
或命中 >1）/ WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task62_generic_docx_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task62_generic_docx_guards.py --run all
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task62_generic_docx_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GEN = "backend/scripts/gen/generate_task62_generic_docx_adjudication.py"
REC = "backend/data/workpaper_sync_task62_generic_docx_adjudication.json"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task62_generic_docx_entries.py"

_SELF = f"{_T}::TestGuardSelfChecks"
_LOCK = f"{_T}::TestThreeWayLock"
_COUNT = f"{_T}::TestCountersRecomputeFromEntries"
_VERD = f"{_T}::TestVerdictsAreDerivedNotDeclared"
_SPLIT = f"{_T}::TestSplitAcrossRunsIsProvedByTwoViews"
_SUPPLY = f"{_T}::TestNoForgedSupply"
_GATE = f"{_T}::TestBlockedCarriersAndAnchorsAreRefused"
_PROBE = f"{_T}::TestMechanismProbeIsNotAContract"
_ISO = f"{_T}::TestCrossEntryIsolation"
_BP = f"{_T}::TestBlockingPreconditions"
_IDEM = f"{_T}::TestGeneratorIsIdempotentAndCheckIsStrict"


MUTATIONS: list[Mutation] = [
    # ═══ 一、五个 verdict 分支 + 阻塞原因表（裁决被悄悄放宽）════════════════
    Mutation(
        id="M01", side="be", path=GEN, kind="replace",
        anchor='    if int(ov["identical"]) or int(ov["contained"]) or int(ov["partial"]):',
        new="    if False:",
        want=f"{_VERD}::test_each_verdict_branch_is_reachable_on_synthetic_facts",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="`blocked_nested_literal_anchor` 分支。B5-5/S12A 的候选 span 互相嵌套"
            "（`202X年` 落在 `202X年12月31日` 内），两者同时注入 SDT 结构上不可能；"
            "短路后这两个 entry 会掉进「锚点不具区分度」甚至「可迁移」，"
            "而真正的原因（无法同时注入）就此消失",
    ),
    Mutation(
        id="M02", side="be", path=GEN, kind="replace",
        anchor='    if int(an["max_literal_anchor_multiplicity"]) > 1:',
        new="    if False:",
        want=f"{_VERD}::test_each_verdict_branch_is_reachable_on_synthetic_facts",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="`blocked_non_discriminating_literal_anchor` 分支 —— 18 个里占 10 个的主因。"
            "`WordFieldInjection` 一个 literal token 只能绑一个 stable key 且全部出现处"
            "注入同一 tag，而 `××` 在单份约定书里最多出现 22 次、语义各不相同。"
            "短路后这 10 个 entry 会被判成可迁移，逐字段注入却根本构造不出来",
    ),
    Mutation(
        id="M03", side="be", path=GEN, kind="replace",
        anchor='    if an["literals_not_verbatim_in_raw_xml"]:',
        new="    if False:",
        want=f"{_VERD}::test_each_verdict_branch_is_reachable_on_synthetic_facts",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="`blocked_literal_anchor_split_across_runs` 分支。这一族是本轮**新发现**的："
            "`instrument_docx_bytes._token_paragraphs` 要求 token verbatim 出现在原始 "
            "`word/document.xml`，而 python-docx 会把跨 run 的 `w:t` 拼起来 —— A26-3 的 "
            "`202X年` 在原始 XML 里连 `202X` 都搜不到。短路后它会被判成可注入，"
            "真跑时引擎抛「命中 0 个段落」",
    ),
    Mutation(
        id="M04", side="be", path=GEN, kind="replace",
        anchor='    if int(an["occurrences_whose_container_has_unrecognised_form"]) > 0:',
        new="    if False:",
        want=f"{_VERD}::test_each_verdict_branch_is_reachable_on_synthetic_facts",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="`blocked_partial_field_fragment_anchor` 分支。A26-1/A26-4 的锚点技术上能注入，"
            "但它只是 `截至202X年X月X日` / `202X年第YY次` 的**片段** —— 注入后旁边的 "
            "`X月X日` / `第YY次` 仍是死文本。短路后这两个会被判成可迁移，"
            "做出来的受管字段名不副实（AC 7.1 的「已替换 placeholder 不得作协议」同源）",
    ),
    Mutation(
        id="M05", side="be", path=GEN, kind="replace",
        anchor='        return "no_managed_field_candidate"',
        new='        return "instrumentable_literal_anchor"',
        want=f"{_VERD}::test_each_verdict_branch_is_reachable_on_synthetic_facts",
        wants=(
            f"{_VERD}::test_every_verdict_recomputes_from_the_recorded_facts",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="A26-2/A8-2/B1-7 三个 entry 一个受管字段候选都没有。把它们判成可迁移 ⇒ "
            "会为「零字段」的 entry 发布 projection 契约，`fields` 为空集时"
            "「注入成功 / 等值通过」全部恒真（假绿第⑥源）",
    ),
    Mutation(
        id="M06", side="be", path=GEN, kind="replace",
        anchor="    return sorted(set(reasons))",
        new="    return []",
        want=f"{_VERD}::test_every_blocked_entry_lists_at_least_one_reason",
        wants=(
            f"{_VERD}::test_every_verdict_recomputes_from_the_recorded_facts",
            f"{_COUNT}::test_verdict_and_reason_histograms_match",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="阻塞原因表整表清空。verdict 还在，但「为什么阻塞」没了 ⇒ 无法区分"
            "「真阻塞」与「懒得裁决」，BP-20/21/22 的解除条件也失去对应",
    ),

    # ═══ 二、事实检测器退化成空转 ═════════════════════════════════════════
    Mutation(
        id="M07", side="be", path=GEN, kind="replace",
        anchor="            found[name] = found.get(name, 0) + 1",
        new="            pass",
        want=f"{_SELF}::test_the_unrecognised_detector_really_fires",
        wants=(
            f"{_SELF}::test_the_unrecognised_detector_excludes_covered_spans",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="「parser 不认的占位形态」检测器恒返回空。它是两条判据的分母："
            "`partial_field_fragment_anchor`（A26-1/A26-4 的 verdict）与 "
            "`unrecognised_placeholder_forms_present`（17/18 个 entry 命中）。"
            "恒空之后「候选分母不完整」这个实证彻底消失，18 个 entry 的字段集合看起来"
            "就像已经完整了",
    ),
    Mutation(
        id="M08", side="be", path=GEN, kind="replace",
        anchor="            if any(lo <= m.start() and m.end() <= hi for lo, hi in covered):",
        new="            if False:",
        want=f"{_SELF}::test_the_unrecognised_detector_excludes_covered_spans",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="排除「已被 legacy 正则命中的 span」这一步。不排除时 `202X年XX月XX日` 会"
            "同时被算作 legacy 候选**和**未识别形态 ⇒ 未识别计数虚高，"
            "`partial_field_fragment_anchor` 会误伤本来干净的 entry",
    ),
    Mutation(
        id="M09", side="be", path=GEN, kind="replace",
        anchor='                counts["contained"] += 1',
        new="                pass",
        want=f"{_SELF}::test_overlap_classifier_distinguishes_three_kinds",
        wants=(
            f"{_COUNT}::test_every_recomputable_counter_matches",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="重叠分类器的 contained 一档（实测 6 处，全是 `202X年` 嵌在完整日期里）。"
            "只留 identical 会漏掉真正常见的那种嵌套 ⇒ B5-5/S12A 掉出 nested 判据",
    ),
    Mutation(
        id="M10", side="be", path=GEN, kind="replace",
        anchor="                is_dup = tc_id in seen_tc",
        new="                is_dup = False",
        want=f"{_IDEM}::test_check_matches_the_file_on_disk",
        wants=(f"{_COUNT}::test_every_recomputable_counter_matches",),
        why="横向合并单元格去重。python-docx 的 `row.cells` 会把合并单元格按跨列数重复"
            "返回（A26-1 的 4 个 `audit_year` 实为 1 个合并单元格，`parse_template` 因此"
            "虚增候选数）。不去重 ⇒ A26-1 的锚点重数从 1 变 4，verdict 从 fragment 变"
            "non-discriminating，机制探针也不再跑",
    ),
    Mutation(
        id="M11", side="be", path=GEN, kind="replace",
        anchor="    raw_xml_counts = {lit: document_xml.count(lit) for lit in sorted(literal_counter)}",
        new="    raw_xml_counts = {lit: 1 for lit in sorted(literal_counter)}",
        want=f"{_SPLIT}::test_raw_xml_verbatim_counts_recompute",
        wants=(
            f"{_SPLIT}::test_the_two_views_really_disagree_somewhere",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="原始 XML 的 verbatim 计数被写成恒 1。两个视图（python-docx vs 原始 XML）"
            "就此永远一致 ⇒ split-across-runs 这一族恒为 0，而它是真实存在的"
            "（6 个 entry 命中）。恒 1 还会让机制探针拿错的 "
            "`expected_token_occurrences` 去注入",
    ),

    # ═══ 三、越权供给被放行 ═══════════════════════════════════════════════
    Mutation(
        id="M12", side="be", path=GEN, kind="replace",
        anchor="        if p.stem not in known_f2",
        new="        if True",
        want=f"{_SUPPLY}::test_staged_contract_dir_holds_only_the_f2_lane_files",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="把 F2 lane 的两份 staged 契约算进「本任务的契约文件」。"
            "`task62_contract_files_in_staged_dir` 会从 0 变 2 —— 反过来说，"
            "真有人往那个目录塞 Task 62 的契约时，这条判据必须能看见",
    ),
    Mutation(
        id="M13", side="be", path=GEN, kind="replace",
        anchor="_AC_7_7_RE = re.compile(",
        new='_AC_7_7_RE = re.compile("(?P<generic>0)(?P<subcode>0)zzz-never-matches") or re.compile(',
        want=f"{_LOCK}::test_requirement_7_7_declared_count_is_read_live",
        wants=(
            f"{_IDEM}::test_build_record_is_byte_stable",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="AC 7.7 声明数的抓取正则失效。生成器必须 fail closed（抓不到就抛），"
            "而不是退回硬编码 18/9 —— 那样清册与 AC 的交叉锁就形同虚设",
    ),
    Mutation(
        id="M14", side="be", path=GEN, kind="replace",
        anchor='        "forbidden_paths": list(row.get("forbidden_paths") or ()),',
        new='        "forbidden_paths": [],',
        want=f"{_SUPPLY}::test_no_word_adapter_landed",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="Word adapter 禁令的 `forbidden_paths` 被读空。空清单让「这些路径不得存在」"
            "变成空集恒真 ⇒ 有人真落地 `adapters/word.py` 时记录照样自称合规"
            "（BP-21 的唯一实证来源）",
    ),
    Mutation(
        id="M15", side="be", path=GEN, kind="replace",
        anchor='    occurrences = int(an["raw_xml_verbatim_counts"][anchor])',
        new='    occurrences = int(an["literal_anchor_multiplicity"][anchor])',
        want=f"{_PROBE}::test_probe_occurrence_count_comes_from_the_raw_xml_view",
        why="机制探针的 `expected_token_occurrences` 改用 python-docx 视图的计数。"
            "🔴 首轮实测判 **GREEN**，追因后确认是**等价变异**而非守卫缺陷：当前两个"
            "探针 entry 上两侧恰好都等于 1（该 literal 没落在合并单元格里），"
            "任何数值断言都测不出差别。修法不是删掉这条变异，而是把**取值来源**做成"
            "结构判据（`occurrences` 的下标必须是 `raw_xml_verbatim_counts`）—— "
            "两侧只要有一个探针 entry 落在合并单元格里就会分叉，"
            "而分叉的后果是 `_inject` 的 fail-closed 计数直接拒绝注入",
    ),
    Mutation(
        id="M16", side="be", path=GEN, kind="replace",
        anchor='    "A26-4": (',
        new='    "ZZZ-9": (',
        want=f"{_PROBE}::test_probe_eligibility_is_derived",
        wants=(
            f"{_IDEM}::test_build_record_is_byte_stable",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="把机制探针声明表的 key 改成一个不存在的 wp_code。生成器必须两侧都抛："
            "实测合格却没声明（能实证的不实证）、有声明却不合格（给 blocked entry "
            "偷偷挂探针）—— 少了任一侧，「探针集合 == 实测合格集合」就不再成立",
    ),

    # ═══ 四、记录本身被手改 ══════════════════════════════════════════════
    Mutation(
        id="M17", side="be", path=REC, kind="replace",
        anchor='      "verdict": "blocked_literal_anchor_split_across_runs",',
        new='      "verdict": "instrumentable_literal_anchor",',
        want=f"{_VERD}::test_every_verdict_recomputes_from_the_recorded_facts",
        wants=(
            f"{_COUNT}::test_verdict_and_reason_histograms_match",
            f"{_PROBE}::test_probe_eligibility_is_derived",
            f"{_IDEM}::test_check_matches_the_file_on_disk",
        ),
        why="直接把 A26-3 的裁决手改成「可迁移」。记录是 Task 67 结构复核的输入，"
            "能被手改而守卫不红 ⇒ 整套裁决没有约束力。守卫必须把记录里的事实"
            "喂回推导函数重算才拦得住",
    ),
    Mutation(
        id="M18", side="be", path=REC, kind="replace",
        anchor='    "adapters_registered": 0,',
        new='    "adapters_registered": 1,',
        want=f"{_COUNT}::test_every_recomputable_counter_matches",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="计数器被手改成「注册了 1 个 adapter」。18 个 entry 的 `adapter_id` 全是 "
            "null，计数必须由 entries 现算 —— 否则「adapters_registered=0」只是一句话",
    ),
    Mutation(
        id="M19", side="be", path=REC, kind="replace",
        anchor='    "entries_with_instrumentable_verdict": 0,',
        new='    "entries_with_instrumentable_verdict": 1,',
        want=f"{_COUNT}::test_every_recomputable_counter_matches",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="把「可迁移 entry 数」手改成 1。这个数字是 Task 62 是否真有进展的唯一"
            "对外口径，必须由 verdict 现算",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files={
                _T: "Task 62 裁决记录守卫（三边锁 / counters / verdict 推导 / "
                    "零供给 / 机制探针 ≠ 契约 / 阻塞前置）",
            },
            repo=REPO,
            description="Task 62 —— 18 个 generic DOCX entry 裁决记录守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task62_generic_docx_entries.py",
                "-q",
                "--tb=no",
            ],
        )
    )
