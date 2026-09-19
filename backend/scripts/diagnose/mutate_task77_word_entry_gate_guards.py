r"""Task 77 变异检验 —— Word per-entry entry gate 与 candidate finalize gate 的守卫强度。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 77

被检验的守卫：

* ``backend/tests/workpaper_sync/test_task77_word_entry_gate.py``（离线）
* ``backend/tests/workpaper_sync/test_task77_word_entry_gate_pg.py``（真实 PG）

## 为什么每条变异都不是无效变异

Task 77 的三类最贵缺陷各自都有对应变异：

1. **判据被换成 Excel 的 sheet/cell 形状** —— Word 无 sheet 无 cell，套用即恒真重言式。
   短路三条 tagged-SDT 判据（tag 集合 / SDT 层级 / 实例计数）中的任一条，守卫必须打红
   （M01~M06）。
2. **降级锚点与 fallback 被放行** —— 四个被 Task 6 证伪的锚点、`row_sdt` 载体、
   段落索引 / 正则 fallback、已替换 placeholder 文本，每条禁令一条变异（M07~M12）。
3. **additive 死代码 / 越权写入** —— 把 gate 的唯一出口、发布门、证据判据或宿主脚本的
   `finalize_candidate()` 摘掉，守卫必须打红（M13~M20）。

另有三条落在**真实 PG 侧**：拒绝的 error_code 被合并、finalize 顺序被交换、
Word-only 覆盖判据被短路（M21~M23）—— 应用层承诺不算判据，真库行为才算。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷）/
WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task77_word_entry_gate_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task77_word_entry_gate_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task77_word_entry_gate_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

WG = "backend/app/services/workpaper_sync/word_entry_gate.py"
WE = "backend/app/services/workpaper_sync/word_sdt_engine.py"
CONTRACTS = "backend/app/services/workpaper_sync/contracts.py"
SCRIPT = "backend/scripts/fix/fix_task77_finalize_word_entry_representation.py"
CARRIER = "backend/data/onlyoffice_word_sdt_carrier_contract.json"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task77_word_entry_gate.py"
_G = "test_task77_word_entry_gate_pg.py"

_SHAPE = f"{_T}::TestCriterionShapeIsTagged"
_ANCHOR = f"{_T}::TestDegradedAnchorsAreRefused"
_CARRIER = f"{_T}::TestBlockedCarrierHasNoExemption"
_TAGSET = f"{_T}::TestTagSetCriterion"
_HIER = f"{_T}::TestHierarchyCriterion"
_COUNT = f"{_T}::TestInstanceCountCriterion"
_WORDONLY = f"{_T}::TestWordOnlyCriterion"
_R75 = f"{_T}::TestRequirement75Scenarios"
_FAILOPEN = f"{_T}::TestNoFailOpenAndNoWriteSurface"
_HOST = f"{_T}::TestConsumptionHost"
_ORDER = f"{_T}::TestFinalizeGateOrdering"
_EVID = f"{_T}::TestCandidateEvidence"
_PROP = f"{_T}::TestProperties"
_SELF = f"{_T}::TestGuardSelfChecks"

_PGSUPPLY = f"{_G}::TestWordSupplyLandsInTheDatabase"
_PGCAND = f"{_G}::TestCandidateStaysNonCurrent"
_PGATTACH = f"{_G}::TestAttachThenFinalizable"
_PGREFUSE = f"{_G}::TestRefusalsAreReasonScoped"
_PGFINAL = f"{_G}::TestFinalizeCreatesANewGeneration"
_PGPROP = f"{_G}::TestProperties"


MUTATIONS: list[Mutation] = [
    # ═══ 一、三条 tagged-SDT 判据各自被短路（AC 6.10 / 7.8 / 7.10）═══════════
    Mutation(
        id="M01", side="be", path=WG, kind="replace",
        anchor="    missing = [tag for tag in declared_static if tag not in observed]",
        new="    missing = []",
        want=f"{_TAGSET}::test_missing_tag_fails_closed_and_names_the_first_drift",
        wants=(f"{_PROP}::test_property_34_tag_loss_never_degrades",),
        why="WG-1 的「declared tag 缺失」分支。这一格是**只有本 gate 在守**的那条："
            "block 容器 tag 单独消失时，engine 的 `_assert_contract_fields_present`"
            "（内层同 key field 仍在）与 `_assert_hierarchy`（block 集合为空）双双放行。"
            "短路后模板被剥掉 block 包装也能 finalize ⇒ Requirement 7.8 的 tag retention 失守",
    ),
    Mutation(
        id="M02", side="be", path=WG, kind="replace",
        anchor="    unregistered = [tag for tag in observation.tags if tag not in set(inventory.tags)]",
        new="    unregistered = []",
        want=f"{_TAGSET}::test_unregistered_tag_fails_closed_with_its_xpath",
        why="WG-1 的另一半：文档里出现冻结清册未登记的受管 tag（模板被二次注入、或被"
            "别的 entry 的 tag 污染）。短路后一个不属于本 entry 的 tag 会被当受管字段读写",
    ),
    Mutation(
        id="M03", side="be", path=WG, kind="replace",
        anchor="        if got and want != got:",
        new="        if False:",
        want=f"{_HIER}::test_field_moved_into_a_table_cell_fails_closed",
        wants=(f"{_HIER}::test_container_path_drift_fails_closed",),
        why="WG-2 唯一的层级判据。engine 侧对**非行域**字段不看 container path，"
            "所以字段被搬进/搬出表格这件事只有本条在守；短路后按 tag 读到的值不再属于"
            "原来的结构位置却照样放行（AC 6.10「不得继续按旧坐标写格」）",
    ),
    Mutation(
        id="M04", side="be", path=WG, kind="replace",
        anchor="        if got and got != want:",
        new="        if False:",
        want=f"{_COUNT}::test_per_tag_count_drift_fails_closed",
        wants=(
            f"{_COUNT}::test_lost_instance_of_a_multi_field_fails_closed",
            f"{_PGPROP}::test_property_34_no_degradation_happened_on_the_success_path",
        ),
        why="WG-3 的运行期判据（逐 tag 精确实例计数）。`${entityName}` 从 2 处掉到 1 处时"
            "tag 集合完全相同、契约的 `many` 档也仍然满足、engine 的 `_assert_instance_counts`"
            "只管 `one` ⇒ 只有本条会打红。短路后「实例缺失」在 AC 7.10 上彻底无人把守",
    ),
    Mutation(
        id="M05", side="be", path=WG, kind="replace",
        anchor="        if declared != expected_bucket:",
        new="        if False:",
        want=f"{_COUNT}::test_declared_instances_must_agree_with_the_frozen_count",
        why="WG-3 的发布期判据（契约 one/many ↔ 冻结实例个数互锁）。两份 approved 声明"
            "互相矛盾时，运行期两条判据各自都「与自己那份声明一致」，谁都不打红 ⇒ "
            "这条是唯一能发现「契约说 one、instrumentation 注了 2 个」的地方",
    ),
    Mutation(
        id="M06", side="be", path=WG, kind="replace",
        anchor="            if inner not in declared:",
        new="            if False:",
        want=f"{_TAGSET}::test_block_inner_field_tag_must_be_declared",
        why="三边锁里「block 载体必须同时有内层 field tag」那一格（Task 6 实测的 depth=2 "
            "形态）。短路后 block 字段可以没有值的写入目标，而 `block_containers` 映射会"
            "变空 ⇒ 层级判据的分母被悄悄清零",
    ),

    # ═══ 二、降级锚点与 fallback 恒拒（AC 7.1 / 7.2 / 7.8）══════════════════
    Mutation(
        id="M07", side="be", path=WG, kind="replace",
        anchor="    if leaked:",
        new="    if False:",
        # 🔴 相对定位而不是绝对行号：`if leaked:` 在本文件里有两处（锚点门 / 载体门），
        #    而绝对行号会在任何上方增删（本任务清 import 时就漂了 2 行）后失效。
        scope="def assert_only_tag_anchor_is_usable(",
        offset=36,
        want=f"{_ANCHOR}::test_gate_does_not_trust_a_permissive_anchor_gate",
        wants=(f"{_ANCHOR}::test_every_blocked_anchor_really_raises",),
        why="四个降级锚点（alias_display_name / sdt_id / paragraph_index / run_index）"
            "「逐个真喂进门必须抛」的判定结果被丢弃。判据是**真实执行**而不是源码里搜"
            "字符串，所以只能在这里短路 —— 短路后 Task 6 证伪的锚点可以当定位键",
    ),
    Mutation(
        id="M08", side="be", path=WG, kind="replace",
        anchor="    if len(g.allowed_anchors) != 1:",
        new="    if False:",
        want=f"{_ANCHOR}::test_more_than_one_allowed_anchor_fails_closed",
        wants=(f"{_ANCHOR}::test_only_one_anchor_is_allowed_and_it_is_w_tag",),
        why="「allowlist 必须恰好一个锚点」。短路后往 `anchors_allowed` 里加第二个锚点"
            "不再 fail closed，`next(iter(...))` 会在集合上随机取一个 ⇒ 「唯一正式协议"
            "锚点」退化成「碰运气」",
    ),
    Mutation(
        id="M09", side="be", path=WG, kind="replace",
        anchor="    overlap = sorted(set(blocked) & set(g.allowed_carriers))",
        new="    overlap = []",
        want=f"{_CARRIER}::test_overlapping_allow_and_block_lists_fail_closed",
        why="`row_sdt` 恒拒的第一道：blocked 与 allowed 无交集。短路后把 `row_sdt` 同时"
            "写进两张表就能让它「合法」—— 那正是 Task 77 正文禁止的「因某 entry 只差 row "
            "就能过而单点豁免」",
    ),
    Mutation(
        id="M10", side="be", path=CONTRACTS, kind="replace",
        anchor='    allowed_carriers = set(node.get("carriers_allowed_into_word_engine") or ())',
        new='    allowed_carriers = set(node.get("carriers_allowed_into_word_engine") or ()) | {"row_sdt"}',
        want=f"{_CARRIER}::test_row_sdt_is_permanently_refused",
        wants=(f"{_CARRIER}::test_overlapping_allow_and_block_lists_fail_closed",),
        why="把被 Task 6 证伪的 `row_sdt` 直接塞进 allowlist —— 这就是 Task 77 正文禁止的"
            "「因某 entry 只差 row 就能过而单点豁免」的最短形态。"
            "🔴 首版这条变异写的是短路 `CarrierGate.assert_carrier` 的 blocked 分支，实测 "
            "GREEN：紧随其后的 `carrier not in self.allowed_carriers` 会把同一次调用接住 —— "
            "正是「短路一条被另一条顶住」这类无效变异。改成动 allowlist 之后，"
            "blocked ∩ allowed 非空，gate 的第一道判据必然打红",
    ),
    Mutation(
        id="M11", side="be", path=WG, kind="insert",
        anchor="import hashlib",
        new="import re  # task77-mutation: 引入文本 fallback 的入口",
        want=f"{_ANCHOR}::test_gate_has_no_paragraph_ordinal_or_chinese_regex_fallback",
        why="「gate 里不得有正则 / 中文文本 fallback」是结构判据。加一行 `import re` 就是"
            "那条 fallback 的入口 —— 判据必须对**入口**敏感，而不是等有人真写出一条正则",
    ),
    Mutation(
        id="M12", side="be", path=WG, kind="replace",
        anchor="        first.setdefault(raw, inst.xpath)",
        new="        pass  # task77-mutation: 不再记录首个实例位置",
        want=f"{_TAGSET}::test_unregistered_tag_fails_closed_with_its_xpath",
        why="AC 6.10 要求漂移必须**指出位置**。Word 没有 sheet 没有 cell，位置就是 "
            "tag + XPath；不记首个实例的 XPath 之后错误只剩 `<no-xpath>`，复核者拿不到"
            "任何可定位信息。"
            "🔴 首版这一格写的是「把实例计数的遍历基准从冻结清册换成实测集合」，实测 "
            "GREEN 后判定为**无效变异**已删：`if got and got != want` 的 `got` 守卫使"
            "两种基准在「tag 集合相同」的全部反例上行为等价（而计数类反例本就必须保持 "
            "tag 集合不变，否则会被 WG-1 遮蔽）—— 无效变异不该留在清单里冒充判据缺口",
    ),

    # ═══ 三、Word-only 等值与「不得用模板重生成」（AC 7.3 / 7.9）════════════
    Mutation(
        id="M13", side="be", path=WG, kind="replace",
        anchor="    empty = [name for name in required_coverage if int(coverage.get(name, 0)) <= 0]",
        new="    empty = []",
        want=f"{_WORDONLY}::test_coverage_must_be_non_empty",
        wants=(f"{_PGPROP}::test_property_31_word_only_equivalence_ran_with_real_coverage",),
        why="Word-only 的「覆盖计数非空」判据。手搓最小 DOCX 上 SDT 外正文是空集，"
            "此时 `equivalent=True` 是空转 —— 短路后 fixture 换成空文档也能报 Property 31 通过"
            "（假绿第⑥源「空集恒等价」）",
    ),
    Mutation(
        id="M14", side="be", path=WG, kind="replace",
        anchor="    missing_aspects = [a for a in WORD_ONLY_ASPECTS if a not in report.inspected_aspects]",
        new="    missing_aspects = []",
        want=f"{_WORDONLY}::test_missing_aspect_is_refused",
        why="「六个 aspect 必须逐项判定」。少判一格时报告仍会说 `equivalent=True` ⇒ "
            "短路后「SDT 外正文保留」可以在根本没检查那一格的情况下报通过",
    ),
    Mutation(
        id="M15", side="be", path=WG, kind="delete",
        anchor="    verification.assert_publishable()",
        want=f"{_WORDONLY}::test_gate_also_asserts_the_managed_projection_matches",
        wants=(f"{_WORDONLY}::test_word_only_drift_is_refused_not_downgraded",),
        why="把「反读受管 projection 不等值」的抛出点删掉 = 把 SDT **内**的值写坏降级成"
            "warning 后继续发布（Task 77 正文明令禁止）。删的是**调用**而不是被调方："
            "被调方是 Task 59 的单一真源，本 gate 只负责真的调它。"
            "🔴 首版把 want 指向 Word-only 漂移那条测试，实测 GREEN —— 因为 "
            "`assert_word_only_equivalent` 已经在它之前委派了 "
            "`UnmanagedRegionReport.assert_equivalent()`，Word-only 那一半有第二个所有者；"
            "唯独「受管 projection 等值」那一半只有 `assert_publishable` 在守",
    ),
    Mutation(
        id="M16", side="be", path=WG, kind="replace",
        anchor="    if extracted.conflicts:",
        new="    if False:",
        want=f"{_PROP}::test_property_32_duplicate_conflict_lists_every_location",
        why="AC 7.4：同 stable tag 多实例异值必须产生冲突且**列出全部** OO 位置，未裁决"
            "不得发布。短路后 gate 会挑 XPath 序首个实例的值直接发布",
    ),
    Mutation(
        id="M17", side="be", path=WG, kind="replace",
        anchor="    refs = getattr(conflict, \"word_instances\", None)",
        new="    refs = ()",
        want=f"{_PROP}::test_property_32_duplicate_conflict_lists_every_location",
        why="冲突位置清单的**权威来源**（Task 14 的 `ConflictRecord.word_instances`）被"
            "换成空集 ⇒ 错误里只剩 locator 那一个位置。AC 7.4 要的是「列全」，"
            "只报一个位置时裁决界面显示不出三值列",

    ),

    # ═══ 四、越权写入面 / 出口 / 宿主（AC 6.18 / 12.5 / Property 67）═════════
    Mutation(
        id="M18", side="be", path=WG, kind="delete",
        anchor="        definitions.binding.assert_may_publish()",
        want=f"{_FAILOPEN}::test_the_only_write_call_is_task25s_single_exit",
        wants=(f"{_ORDER}::test_finalize_order_is_prerequisites_then_the_single_exit",),
        why="发布门（离线模式恒抛）被摘掉。Task 59 的 `assert_may_publish` 是"
            "「缺 approved bundle 时结构上到不了发布」的那道锁；不调它之后离线 binding "
            "也能走到 Task 25 的出口",
    ),
    Mutation(
        id="M19", side="be", path=WG, kind="replace",
        anchor='    if str(payload["document_type"]) != WORD_DOCUMENT_TYPE:',
        new="    if False:",
        want=f"{_EVID}::test_non_docx_evidence_is_refused",
        why="candidate 证据的 `document_type` 门。短路后一份 **xlsx** entry 的证据可以喂进 "
            "Word gate —— 两个域的判据形状完全不同（Excel 是 sheet/cell、Word 是 tagged "
            "SDT），混用之后 Word 侧的 tag 判据会在一份没有任何 tag 的载荷上空跑。"
            "🔴 首版这一格放的是「只加注释」的**对照组**（`want=\"*\"`，期望 GREEN）。"
            "kit 的四态语义里 GREEN 恒等于「守卫缺陷」，把对照组混进来会让收尾统计"
            "永远报 1 条缺口 —— 对照组的职责改由 `--check-anchors` 的只读 md5 核验承担",
    ),
    Mutation(
        id="M20", side="be", path=SCRIPT, kind="replace",
        anchor="    outcome = await gate.finalize_candidate(",
        new="    outcome = await gate.no_such_entry_point(  # task77-mutation: 宿主不再消费 gate",
        want=f"{_HOST}::test_gate_is_consumed_by_the_host_script",
        why="additive 死代码判据：把宿主对 `finalize_candidate()` 的调用摘掉之后，"
            "整个 gate 在生产上就没有任何消费方了（本 spec 反复实测过的假绿第①源）",
    ),
    Mutation(
        id="M21", side="be", path=SCRIPT, kind="insert",
        anchor="    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)",
        new="    _ = instrument_docx_bytes  # task77-mutation: apply 侧引入模板重生成入口",
        line=0,
        scope="async def finalize_one(",
        offset=26,
        want=f"{_HOST}::test_apply_never_regenerates_from_a_template",
        why="`--apply` 的字节只能来自 candidate 自己。在它的调用图里引入 "
            "`instrument_docx_bytes` 就是「用模板重生成覆盖审计师已编辑的 Word-only 正文」"
            "的入口 —— 判据必须对入口敏感",
    ),
    Mutation(
        id="M22", side="be", path=SCRIPT, kind="insert",
        anchor='        item["db_state"] = state',
        new="        await session.commit()  # task77-mutation: `--check` 不再只读",
        # 相对定位（`item["db_state"] = state` 在 run_check / run_apply 各有一处）。
        scope="async def run_check(session: Any, targets: list[WordFinalizeTarget]) -> dict[str, Any]:",
        offset=31,
        want=f"{_HOST}::test_check_mode_is_read_only_and_really_runs_the_criteria",
        why="`--check` 必须只读（AC 2.4 的形态：预演不得落库）。插入一次 commit 之后"
            "「只读预演」就名不副实 —— 判据必须对**写入面出现**敏感。"
            "🔴 首版这一格是「刻意插一行破坏语法的内容」的锚点自检，实测 GREEN："
            "语法错误让整个 module 变 collection **ERROR**，而 kit 的差集只看 FAILED ⇒ "
            "破坏性变异反而报「未被捕获」。锚点自检的职责改由 `--check-anchors` 承担",
    ),

    # ═══ 五、真实 PG 侧（应用层承诺不算判据）════════════════════════════════
    Mutation(
        id="M23", side="be", path=WG, kind="replace",
        anchor='    error_code = "word_entry_instrumentation_digest_mismatch"',
        new='    error_code = "word_entry_frozen_bundle_digest_mismatch"',
        want=f"{_PGREFUSE}::test_every_refusal_code_is_distinct",
        wants=(
            f"{_PGREFUSE}::test_each_refusal_has_its_own_error_code_and_reason",
            f"{_FAILOPEN}::test_failure_codes_are_closed_and_distinct",
            f"{_PGPROP}::test_property_28_frozen_identity_is_enforced_on_real_rows",
        ),
        why="把两类拒绝合并成同一个 error_code。🔴 这是 Task 76 首轮三条 GREEN 里的第一条"
            "教训的对侧：判「拒绝」只比异常类型时，「bundle 被换了」与「declared 清册被换了」"
            "无法分辨，短路其中一条会被另一条接住 ⇒ 守卫必须比对 **error_code + 原因**",
    ),
    Mutation(
        id="M24", side="be", path=WG, kind="replace",
        anchor="        if str(staged_candidate.entry_id) != entry_id:",
        new="        if False:",
        want=f"{_PGREFUSE}::test_each_refusal_has_its_own_error_code_and_reason",
        wants=(f"{_PGREFUSE}::test_refusal_codes_and_reasons_are_both_load_bearing",),
        why="跨 entry 复用 candidate **字节**的禁令（Task 77 正文「不得跨 entry 复用 "
            "contract/bundle/candidate/evidence」）。candidate **行**的 entry 归属由上一条 "
            "`candidate.entry_id != entry_id` 守，本条守的是字节那一侧。"
            "🔴 首版 `_pg` 只有「行」那一个反例（`entry_id=另一个 lane`），它被行判据先"
            "接住 ⇒ 本条实测 GREEN；补了 `foreign_staged_bytes`（行对得上、字节属于另一个 "
            "entry）之后才锁得住 —— 这正是「短路一条被另一条顶住」的同款教训",
    ),
    Mutation(
        id="M25", side="be", path=WG, kind="replace",
        anchor="        if recomputed != instrumentation_slot.slot_digest.strip():",
        new="        if False:",
        want=f"{_PGREFUSE}::test_each_refusal_has_its_own_error_code_and_reason",
        wants=(f"{_PROP}::test_property_28_frozen_identity_cannot_be_swapped",),
        why="declared 清册与 bundle 的 instrumentation slot digest 的锁。短路后可以拿"
            "**另一个 entry** 的 tag 清册来校验本 entry 的文档 —— 三边锁的第一边整条失效"
            "（Property 28）",
    ),
    Mutation(
        id="M26", side="be", path=WG, kind="replace",
        anchor='        if evidence.rollback_source_sha256 != str(candidate.rollback_source_sha256 or ""):',
        new="        if False:",
        want=f"{_PGREFUSE}::test_each_refusal_has_its_own_error_code_and_reason",
        wants=(f"{_PGREFUSE}::test_refusal_codes_and_reasons_are_both_load_bearing",),
        why="回滚源 digest 的可追溯性（AC 7.8：失败时**保留原 Word 文件版本**）。"
            "candidate 行的 `rollback_source_sha256` 与证据里的不一致时，回滚目标就指不"
            "到那份原始字节；短路后「失败保留原版本」这条承诺没有任何执行面。"
            "🔴 首版这一格写的是「authority model 必须是 projection_contract」，实测 GREEN "
            "后追因判定为**不可达**（见 `word_entry_gate.load` 里那段注释）并已把那条死"
            "判据删掉 —— 不可达分支留着就是「登记了一个永久不可达的 kind」这类假绿",
    ),
    Mutation(
        id="M27", side="be", path=WG, kind="replace",
        anchor="        if evidence.instrumented_sha256 != staged_candidate.sha256:",
        new="        if False:",
        want=f"{_PGREFUSE}::test_each_refusal_has_its_own_error_code_and_reason",
        wants=(f"{_PGREFUSE}::test_refusal_codes_and_reasons_are_both_load_bearing",),
        why="「往返证据与将要发布的字节是同一份」。短路后可以用 A 份 candidate 的证据去"
            "发布 B 份字节 —— 真库侧的可观察后果就是发布字节与证据脱钩。"
            "🔴 首版没有对应反例（`_pg` 里 staged digest 恒等于证据里的）⇒ 实测 GREEN；"
            "补了 `mismatched_instrumented_digest` 反例之后才锁得住",
    ),
    Mutation(
        id="M28", side="be", path=WG, kind="replace",
        anchor="    if observed != expected_sha256:",
        new="    if False:",
        want=f"{_EVID}::test_digest_mismatch_is_refused_first",
        wants=(f"{_EVID}::test_foreign_entry_evidence_is_refused",),
        why="证据 digest 与 candidate 行登记值的比对。短路后「拿另一个 entry 的 evidence "
            "顶上」不再被拒（AC 6.18 明禁），后面读到的一切都不属于这个 candidate",
    ),
    Mutation(
        id="M29", side="be", path=WE, kind="replace",
        anchor="    pieces: list[str] = [inner[: first[0]], _render_runs(value, rpr)]",
        new="    out = inner[: first[0]] + _render_runs(value, rpr) + inner[first[3] :]\n    pieces: list[str] = [out]",
        want=f"{_R75}::test_cross_run_value_survives_the_tag_roundtrip",
        why="Task 77 实测修掉的那条真实缺陷的**反向锚点**：`_rewrite_sdt_content` 旧写法"
            "在 `sdtContent` 有 3 个以上 run 时算错删除偏移（每轮重算 shift）。"
            "本变异把它退回「只保留首个 run 的重组」形态，跨 run 场景必须打红 ⇒ "
            "证明 AC 7.5 的跨 run 判据不是重言式",
    ),
]


#: 覆盖面分母（守卫文件名 → 归属说明）。空分母会在 `run_cli` 里直接抛。
GUARD_FILES: dict[str, str] = {
    "test_task77_word_entry_gate.py": "Task 77 新建（离线判据）",
    "test_task77_word_entry_gate_pg.py": "Task 77 新建（真实 PG 判据）",
}

if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task77_word_entry_gate.py",
                "backend/tests/workpaper_sync/test_task77_word_entry_gate_pg.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=133,
        )
    )
