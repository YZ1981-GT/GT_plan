"""Task 68 后端全链独立回归守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 68

被检验的守卫：``backend/tests/workpaper_sync/test_task68_backend_chain_regression.py``
被变异的产物：``backend/scripts/check/check_task68_backend_chain_independent_regression.py``

## 为什么每条变异都不是无效变异

独立回归型产物最贵的五类缺陷：

1. **空集恒真** —— 生产 `public` schema 里 forcesave request / application / operation /
   delivery / room / scope index / content version 等表实测 **0 行**。把 `passed` 的来源从
   「schema 侧 DDL 逐片段 + scratch schema 真造行」偷偷换成「没有违反行」，报告会全绿而
   什么都没度量（M01~M07）。
2. **判据是重言式 / 恒真** —— 把 `satisfied` 写成 `True`、把 `agrees` 写成 `True`、把否定臂
   的 signature 抹空，都会让整份报告照样自称把住了约束（M08~M13）。
3. **fail-open** —— 库读不到 / 采集失败 / 探针抛错时降级成「无数据所以通过」（M14~M17）。
4. **只读承诺被破坏 / 越界** —— 对生产库开写事务、写入目标从报告挪到别人的数据文件、
   在 scratch schema 里写 evidence 两张表冒充「有 evidence」（M18~M22）。
5. **自证与弱化被掩盖** —— 辐射面退化成目录枚举、既存红被吞、Property 落点档位被伪装成
   第一档、BP 引用常量而非现算（M23~M34）。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷：锚点未命中或
命中 >1）/ WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task68_backend_chain_regression_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task68_backend_chain_regression_guards.py --run M01,M02
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task68_backend_chain_regression_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
🔴 BP-29：kit 的 `_locate_want` 对 **parametrize nodeid 恒误报** ⇒ 本脚本的 `want` 目标
   一律是**非 parametrize** 的方法（守卫侧用循环 + 逐项断言消息表达多例）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GATE = "backend/scripts/check/check_task68_backend_chain_independent_regression.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带 `backend/tests/...`
#: 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task68_backend_chain_regression.py"

_SELF = f"{_T}::TestGuardSelfChecks"
_READ = f"{_T}::TestGateOnlyReads"
_SUB = f"{_T}::TestSixSubBulletsAreEachMeasured"
_INV = f"{_T}::TestInvariantsAreMeasured"
_EP = f"{_T}::TestEndpointChecks"
_SURF = f"{_T}::TestRadiationSurfaceAndPreexistingReds"
_PROP = f"{_T}::TestPropertyLandings"
_LIVE = f"{_T}::TestLiveRunReproducesTheRecord"
_WIRE = f"{_T}::TestProbeWiringIsStructural"
_FIN = f"{_T}::TestRestorationAndVerdict"

#: 公共锚点：几乎每条落在门上的变异都会让现算结论与磁盘记录不同。
_RECOMPUTE = f"{_INV}::test_every_invariant_recomputes_from_the_recorded_inputs"
_LIVE_VERDICT = f"{_LIVE}::test_the_live_verdict_matches_the_recorded_one"


MUTATIONS: list[Mutation] = [
    # ═══ 一、空集恒真（本任务最核心的一族）════════════════════════════════
    Mutation(
        id="M01", side="be", path=GATE, kind="replace",
        anchor="        if not self.schema_requirements and not self.schema_gap:",
        new="        if False:",
        want=f"{_SELF}::test_invariant_refuses_to_exist_without_a_schema_side",
        why="允许一条不变量**没有任何 schema 要求**。0 行的表上「逐行成立」恒真，DDL 逐片段"
            "判据是这些检查唯一的结构约束力；允许为空等于允许把正文点名的二十几条校验写成"
            "空壳还全绿（假绿第⑥源）",
    ),
    Mutation(
        id="M02", side="be", path=GATE, kind="replace",
        anchor="        if not self.arms:",
        new="        if False:",
        want=f"{_SELF}::test_invariant_refuses_to_exist_without_behaviour_arms",
        why="允许不变量**没有行为臂**。生产库这些表实测 0 行，只剩 schema 侧就等于「DDL 长得对」"
            "—— 证明不了那条约束真的会在插入时报错。正文逐字要求「真实PostgreSQL独立校验」",
    ),
    Mutation(
        id="M03", side="be", path=GATE, kind="replace",
        anchor='        if not any(a.expectation == "accepted" for a in self.arms):',
        new="        if False:",
        want=f"{_SELF}::test_invariant_refuses_to_exist_without_a_control_arm",
        why="允许没有对照组。对照组不过时「非法形态被拒」可能只是因为世界搭错了（缺 FK、"
            "digest 不合法…），整条判据度量的不是它自称的那条约束（教训 5）",
    ),
    Mutation(
        id="M04", side="be", path=GATE, kind="replace",
        anchor='        if not any(a.expectation in ("rejected", "measure") for a in self.arms):',
        new="        if False:",
        want=f"{_SELF}::test_invariant_refuses_to_exist_with_only_a_control_arm",
        why="允许只有对照组。「合法形态能插进去」不含任何否定信息 —— 把所有约束删光它照样绿",
    ),
    Mutation(
        id="M05", side="be", path=GATE, kind="replace",
        anchor="        if self.expectation == \"rejected\" and not self.reject_signature:",
        new="        if False:",
        want=f"{_SELF}::test_rejected_arm_refuses_to_exist_without_a_signature",
        why="允许否定臂不声明拒绝理由 ⇒ 判据退化成「抛了异常就算过」。NOT NULL、FK、别的 CHECK "
            "全都是 IntegrityError，教训 1 的原样复现",
    ),
    Mutation(
        id="M06", side="be", path=GATE, kind="replace",
        anchor='        if self.expectation == "measure" and not self.expect_measure:',
        new="        if False:",
        want=f"{_SELF}::test_measure_arm_refuses_to_exist_without_expectations",
        why="允许计数臂没有期望值 ⇒ 空期望恒真。N shell 收敛、exactly-one close-capture、"
            "leader 选举这三条最贵的结论全靠 `expect_measure` 逐键比对",
    ),
    Mutation(
        id="M07", side="be", path=GATE, kind="replace",
        anchor='            behaviour_state = "verified_on_rows" if arms_agree else "arm_mismatch"',
        new='            behaviour_state = "verified_on_rows"',
        want=f"{_INV}::test_behaviour_state_follows_the_arms_not_a_constant",
        why="行为侧状态恒为 `verified_on_rows`，与逐臂结论脱钩 ⇒ 报告对每条不变量都声称"
            "「在行上验过」。`verified_on_rows` 是本报告区分「DDL 把住了」与「真数据上验过」"
            "的唯一字段，恒真之后 Task 70 无法知道哪些链路还完全没被真实数据碰过",
    ),

    # ═══ 二、判据恒真 / 重言式 ════════════════════════════════════════════
    Mutation(
        id="M08", side="be", path=GATE, kind="replace",
        anchor='            "satisfied": definition is not None and not missing,',
        new='            "satisfied": True,',
        want=f"{_INV}::test_removing_any_single_ddl_requirement_flips_the_invariant",
        wants=(
            f"{_SELF}::test_ddl_requirement_detects_a_missing_fragment_not_just_presence",
            _RECOMPUTE,
        ),
        why="把 schema 判据改成恒真。这是「判据是重言式」的教科书形态：所有检查照样全绿、"
            "报告照样自称把住了 UNIQUE/CHECK/trigger/function，而实际抹掉哪条约束都无所谓。"
            "反事实多臂（逐条在内存里改名一条约束）就是为抓这条而存在",
    ),
    Mutation(
        id="M09", side="be", path=GATE, kind="replace",
        anchor='        missing = [frag for frag in self.must_contain if frag not in (definition or "")]',
        new='        missing = [frag for frag in () if frag not in (definition or "")]',
        want=f"{_SELF}::test_ddl_requirement_detects_a_missing_fragment_not_just_presence",
        wants=(_RECOMPUTE,),
        why="判据从「索引/CHECK/trigger 的定义里必须出现这几列」退化成「同名对象存在即可」。"
            "forcesave 五元键少一列 `initiated_by_participant_id` 时索引依然叫 "
            "`uq_wpfr_idempotency`，跨 participant 复用同一 Idempotency-Key 就不再 409 —— "
            "教训 16 的原样复现",
    ),
    Mutation(
        id="M10", side="be", path=GATE, kind="replace",
        anchor="        agrees = (not accepted) and len(hit) == len(arm.reject_signature)",
        new="        agrees = not accepted",
        want=f"{_SELF}::test_rejected_arm_needs_every_declared_fragment",
        wants=(_RECOMPUTE,),
        why="否定臂只要「被拒了」就算过，不再比对原因。`aif_quarantined` 与 `aif_staged` 共用"
            "同一条 RAISE 文案，只比「拒没拒」时两条臂互相冒充 —— 谁都无法证明拒绝的是"
            "**这一种**非法 state（教训 1）",
    ),
    Mutation(
        id="M11", side="be", path=GATE, kind="replace",
        anchor="    mismatched = {k: (v, measured.get(k)) for k, v in expected.items() if measured.get(k) != v}",
        new="    mismatched = {}",
        want=f"{_SELF}::test_measure_arm_compares_every_declared_key_separately",
        wants=(_RECOMPUTE,),
        why="计数臂恒过。N shell 收敛（1 primary / 3 duplicate / 0 stranded / 0 链 / 0 环）、"
            "五种 close 顺序各自 exactly-one、leader 按最高 `(intent_sequence, id)` —— "
            "这三条最贵的结论全部失效，而报告照样全绿",
    ),
    Mutation(
        id="M12", side="be", path=GATE, kind="replace",
        anchor="            if set(arm.reject_signature) == set(other.reject_signature):",
        new="            if True:",
        want=f"{_SELF}::test_cross_signature_check_only_flags_differing_reasons",
        wants=(_RECOMPUTE,),
        why="互相冒充检测被整体短路。实测有三处**真实**遮蔽（durable 双 owner 撞 exactly-one、"
            "duplicate+application 撞 duplicate_shape、跨 room 提升撞 wrong-kind），"
            "去掉这条检测后它们会被当成「各自度量了自己那条约束」",
    ),
    Mutation(
        id="M13", side="be", path=GATE, kind="replace",
        anchor='            "state": "missing_observation",',
        new='            "state": "agrees",',
        want=f"{_SELF}::test_missing_observation_is_not_a_pass",
        wants=(
            f"{_INV}::test_declared_arms_and_written_observations_are_two_way_locked",
            _RECOMPUTE,
        ),
        why="声明了却没探针写观测时算「一致」。additive 注入即死代码（假绿第①源）："
            "报告里写着 120 条臂，实际跑了几条谁也不知道",
    ),

    # ═══ 三、fail-open ════════════════════════════════════════════════════
    Mutation(
        id="M14", side="be", path=GATE, kind="replace",
        anchor="        if not catalog.readable:",
        new="        if False:",
        want=f"{_SELF}::test_db_unreadable_never_reads_as_passed",
        wants=(_RECOMPUTE,),
        why="🔴 库读不到时不再降级，而是继续走 schema 分支 —— 而目录此时是空的 ⇒ 所有 requirement "
            "的 definition 都是 None。看似安全，但报告会把「库连不上」伪装成「约束不存在」，"
            "而不是明确的 `db_unreadable`。AC 5.12 明令禁 fail-open",
    ),
    Mutation(
        id="M15", side="be", path=GATE, kind="replace",
        anchor='        catalog.error = f"{type(exc).__name__}: {exc}"',
        new='        catalog.error = None',
        want=f"{_LIVE}::test_a_failing_catalog_read_records_its_reason",
        why="库读失败时不记原因。`readable=False` 还在，但读者无从知道是连不上、权限不足还是"
            "表不存在 —— 「库不可读」这条结论没有可诊断载体",
    ),
    Mutation(
        id="M16", side="be", path=GATE, kind="replace",
        anchor='                result["probe_errors"][name] = f"{type(exc).__name__}: {exc}"',
        new='                pass  # 变异：探针异常被吞',
        want=f"{_LIVE}::test_probe_and_migration_failures_are_recorded_not_swallowed",
        why="🔴 探针抛错被静默吞掉。后果不是「少验一点」而是**整族臂消失**却没人报错 —— "
            "本 spec 记录 fail-open 掩盖接线错误是最贵的一类缺陷（函数名/列名拼错全被吞成"
            "「本项目无此数据」）",
    ),
    Mutation(
        id="M17", side="be", path=GATE, kind="replace",
        anchor="            raise Task68GateError(f\"迁移应用失败: {result['apply_errors'][:3]}\")",
        new="            pass  # 变异：迁移应用失败被忽略",
        want=f"{_LIVE}::test_probe_and_migration_failures_are_recorded_not_swallowed",
        why="迁移在 scratch schema 上应用失败后继续跑探针。表结构不完整时「非法形态被拒」会"
            "大量来自「表/列不存在」而不是被验的约束 —— 世界搭错时后续臂毫无信息量（教训 5）",
    ),

    # ═══ 四、只读承诺与越界 ═══════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=GATE, kind="replace",
        anchor="    async with engine.connect() as conn:",
        new="    async with engine.begin() as conn:",
        want=f"{_READ}::test_production_catalog_is_read_without_a_write_transaction",
        why="🔴 `connect()` 换成 `begin()` ⇒ 对**生产库**打开写事务。本门对生产 `public` schema 的"
            "唯一承诺就是只读；开了写事务之后任何一处误写都会真的提交。memory 明写「PG 只读」",
    ),
    Mutation(
        id="M19", side="be", path=GATE, kind="replace",
        anchor="    _SQL_TRIGGERS,",
        new="    # _SQL_TRIGGERS 从只读声明清单里被拿掉（变异）",
        want=f"{_READ}::test_the_declared_readonly_list_contains_the_real_targets",
        why="只读 SQL 声明清单里去掉 trigger 查询。清单是「本门只 SELECT」这条承诺的可核查载体；"
            "漏一条就等于有一条 SQL 没被任何判据看过 —— 而 trigger 定义正是十几条不变量的"
            "主要结构依据（`trg_wpfr_frozen` / `trg_wpca_mutation` / `trg_wpssi_no_delete` …）",
    ),
    Mutation(
        id="M20", side="be", path=GATE, kind="replace",
        anchor="        os.replace(tmp, OUTPUT_PATH)",
        new="        os.replace(tmp, TASK67_REPORT_PATH)",
        want=f"{_READ}::test_only_the_report_is_written_to_disk",
        why="🔴 写入目标从本报告挪到**上游任务的结构报告**。正文只授权本报告；覆盖上游产物等于"
            "替它重签结论，还会把并发会话在用的文件换掉。正文逐字：Tasks 66/67 的产物是只读输入",
    ),
    Mutation(
        id="M21", side="be", path=GATE, kind="replace",
        anchor='            "disposition": "read_only_input",',
        new='            "disposition": "regenerated",',
        want=f"{_READ}::test_upstream_inputs_are_recorded_as_read_only",
        wants=(_RECOMPUTE,),
        why="上游输入的处置从「只读」改成「重生成」。处置字段是下游（Tasks 70/72）判断"
            "「这份结构报告还能不能当真源」的唯一依据；说成重生成会让它们以为本轮已刷新",
    ),
    Mutation(
        id="M22", side="be", path=GATE, kind="replace",
        anchor='        "working_paper_entry_evidence_scenario",',
        new='        "working_paper_sync_conflict",',
        scope='    "evidence_tables_left_untouched": [',
        offset=2,
        line=0,
        want=f"{_SUB}::test_sub_bullet_6_declares_the_oo_boundary",
        wants=(_RECOMPUTE,),
        why="🔴 边界声明里把 evidence 的第二张表换掉 ⇒ `working_paper_entry_evidence_scenario` "
            "不再被断言为 0 行。正文逐字「不冒充真实 OO probe/evidence已通过」——"
            "一旦这张表可以被写，报告就能凭空制造「有 evidence」的表象（Task 70 的活）",
    ),

    # ═══ 五、辐射面 / 既存红 ══════════════════════════════════════════════
    Mutation(
        id="M23", side="be", path=GATE, kind="replace",
        anchor='    ("sync_services_module", r"app\\.services\\.workpaper_sync"),',
        new='    ("sync_services_module", r"workpaper"),',
        want=f"{_SURF}::test_surface_is_recomputed_from_references_not_hand_written",
        wants=(_RECOMPUTE,),
        why="引用判据从**模块路径级**退化成业务词。首轮实测这样会把 207 个文件（一半是别的 spec 的）"
            "拉进辐射面 —— 正文逐字「按引用关系反查辐射面，不跑无边界全量」",
    ),
    Mutation(
        id="M24", side="be", path=GATE, kind="replace",
        anchor='        "digest": digest_of(sorted(files)),',
        new='        "digest": digest_of("task68-fixed"),',
        want=f"{_SURF}::test_surface_is_recomputed_from_references_not_hand_written",
        wants=(f"{_SUB}::test_sub_bullet_1_and_6_land_on_a_real_execution",),
        why="辐射面 digest 与文件清单脱钩 ⇒ `surface_digest_matches` 恒真。那是「记录里那次 pytest "
            "跑的正是现算辐射面」的唯一锁；脱钩后改 scanner 也不会红",
    ),
    Mutation(
        id="M25", side="be", path=GATE, kind="replace",
        anchor='        "in_dir_but_out_of_surface": out_of_surface,',
        new='        "in_dir_but_out_of_surface": [],',
        want=f"{_SURF}::test_surface_extras_are_recomputed_live_not_only_read",
        wants=(f"{_SURF}::test_in_dir_but_out_of_surface_files_are_listed_not_hidden",),
        why="把「在 `workpaper_sync/` 目录里但不引用被验单元」的文件藏起来。读者会以为整目录"
            "都在辐射面内 —— 正文要求如实报告，这份差集就是「如实」的载体",
    ),
    Mutation(
        id="M26", side="be", path=GATE, kind="replace",
        anchor='        "-q", "--no-header", "--tb=no", "-rfE", "-p", "no:randomly",',
        new='        "-q", "--no-header", "--tb=no", "-rf", "-p", "no:randomly",',
        want=f"{_SURF}::test_the_suite_command_keeps_error_reporting_on",
        why="`-rfE` 退回 `-rf` ⇒ ERROR 不进短摘要。实测 6 个 collection/setup ERROR 会全部变成"
            "「无 nodeid」，既存红逐项核对永远对不上，而总计数看起来还是对的",
    ),
    Mutation(
        id="M27", side="be", path=GATE, kind="replace",
        anchor="    own_guard_failed = sorted(n for n in failed_nodeids if own_guard_stem in n)",
        new="    own_guard_failed = []",
        want=f"{_SURF}::test_suite_reconciliation_is_a_pure_function_of_the_record",
        why="本门守卫的失败集合恒空 ⇒ 守卫自己全红时 `own_guard_result.clean` 仍为真，"
            "`suite_passed` 也跟着为真。「跑了自己的守卫」与「守卫真的绿」是两件事，"
            "后者是本门唯一的自证；恒空之后分桶完整性判据也再也对不上",
    ),
    Mutation(
        id="M28", side="be", path=GATE, kind="replace",
        anchor='                "agrees": len(matched_failed) == int(entry["failed"])',
        new='                "agrees": True or len(matched_failed) == int(entry["failed"])',
        want=f"{_SURF}::test_suite_reconciliation_is_a_pure_function_of_the_record",
        why="既存红逐项核对恒真。声明 13 failed / 6 errors 与实测脱钩后：多出来的红被吞"
            "（本轮实测真的多了 4 条，其中 2 条根因是本报告自己），少了也不会提示基线过期",
    ),
    Mutation(
        id="M29", side="be", path=GATE, kind="replace",
        anchor="            and not own_guard_failed",
        new="            and True  # 变异：本门守卫的红不再影响 suite 判定",
        want=f"{_SURF}::test_suite_reconciliation_is_a_pure_function_of_the_record",
        why="本门守卫自身的红不再影响判定 ⇒ 门可以在自己的守卫全红时报 passed。"
            "「跑了自己的守卫」与「守卫真的绿」是两件事，后者是本门唯一的自证",
    ),

    # ═══ 六、Property 落点 / BP / 判定 ════════════════════════════════════
    Mutation(
        id="M30", side="be", path=GATE, kind="replace",
        anchor='            tier = "independently_executed"',
        new='            tier = "independently_expressed"',
        want=f"{_PROP}::test_tier_two_is_honestly_labelled_as_weaker",
        wants=(
            f"{_PROP}::test_property_landing_is_derived_not_hand_written",
            _RECOMPUTE,
        ),
        why="🔴 第二档伪装成第一档。48 条里 24 条本门并未重新表达，独立性只来自「由本门从仓库根"
            "真跑了辐展面文件」。伪装成第一档 = 把「跑了实现任务的测试」说成「我独立验过」，"
            "正文逐字「不得由实现任务自证」",
    ),
    Mutation(
        id="M31", side="be", path=GATE, kind="replace",
        anchor='                        "kind": "property_without_landing_or_declared_owner",',
        new='                        "kind": "property_noted",',
        want=f"{_SELF}::test_deferred_property_without_owner_is_a_structural_error",
        wants=(_RECOMPUTE,),
        why="无落点的 Property 不再归为结构错误。正文点名 48 条，缺一条就是结构错误；"
            "改成中性 kind 后下游按 kind 消费的一侧再也看不到它",
    ),
    Mutation(
        id="M32", side="be", path=GATE, kind="replace",
        anchor='            "measured": len(empty_tables),',
        new='            "measured": 13,',
        want=f"{_FIN}::test_blocking_points_are_built_from_inputs_not_constants",
        wants=(_RECOMPUTE,),
        why="🔴 BP-68-2 的度量值写死成常量。「生产库相关表 0 行 ⇒ 行为侧只能在 scratch 上验」"
            "这条结论会在供给到位后**静静过期**，Task 70 无从知道它已解除。"
            "本 spec 反复踩的坑：引用上游旧数而不是现算",
    ),
    Mutation(
        id="M33", side="be", path=GATE, kind="replace",
        anchor='BP_ID_RE: Final[re.Pattern[str]] = re.compile(r"BP-68-\\d+")',
        new='BP_ID_RE: Final[re.Pattern[str]] = re.compile(r"BP-\\d+")',
        want=f"{_SELF}::test_bp_id_regex_is_task_scoped_and_rejects_the_global_form",
        wants=(_RECOMPUTE,),
        why="BP 编号不再校验 task-scoped 形态。全局 `BP-NN` 已被 Tasks 60/61/63/64 **重复占用**"
            "（同号不同义），接回去只会制造第五份冲突；task-scoped 前缀是这套编号唯一的去歧义手段",
    ),
    Mutation(
        id="M34", side="be", path=GATE, kind="replace",
        anchor='        {key: value for key, value in report.items() if key != "report_digest"}',
        new='        {"task": report["task"]}',
        want=f"{_FIN}::test_the_digest_expression_covers_the_whole_report",
        why="`report_digest` 只覆盖一个字段 ⇒ 报告可被任意手改而 digest 不变。本报告是 Tasks "
            "70/72 的输入，能被手改而守卫不红，整份独立回归结论就没有约束力",
    ),
    Mutation(
        id="M35", side="be", path=GATE, kind="replace",
        anchor='        result = RESULT_UNVERIFIABLE',
        new='        result = RESULT_PASSED',
        want=f"{_FIN}::test_each_failure_source_drives_the_verdict_on_its_own",
        wants=(_LIVE_VERDICT,),
        why="🔴 库不可读 / 采集失败时判 **passed**。这是 fail-open 的最终形态：什么都没验成，"
            "报告说通过。正文要求如实报告，判定必须能区分「验过且通过」与「根本没验成」",
    ),
    Mutation(
        id="M36", side="be", path=GATE, kind="replace",
        anchor='    elif failed_invariants or failed_endpoints or property_errors or not restoration["restored"]:',
        new='    elif failed_invariants or failed_endpoints or property_errors:',
        want=f"{_FIN}::test_each_failure_source_drives_the_verdict_on_its_own",
        why="复原失败不再影响判定。行为侧在 scratch schema 里造了几百行，复原实证（生产 public "
            "前后逐表行数相等 + 无残留 schema）是「没污染生产」的唯一数据侧证据；"
            "被 `^C` 中断的运行可能已提交部分变更，判成败一律查数据不看 exit code",
    ),

    # ═══ 七、端点与探针接线 ═══════════════════════════════════════════════
    Mutation(
        id="M37", side="be", path=GATE, kind="replace",
        anchor='    ("post", "/versions/{version_id}/rollback", "rollback_version"),',
        new='    ("post", "/operations/{operation_id}/retry", "retry_operation"),',
        want=f"{_EP}::test_the_required_endpoint_list_names_the_real_thirteen",
        wants=(f"{_EP}::test_endpoint_checks_recompute_live",),
        why="必查端点清单里换掉 rollback。清单**写死**而不是迭代路由表，正是教训 16："
            "迭代路由表的判据在某个端点被删时照样绿。rollback 是 opaque UUID / numeric revision "
            "禁作 route key 这两条的唯一落点",
    ),
    Mutation(
        id="M38", side="be", path=GATE, kind="replace",
        anchor='        elif list(order).index("_guard") != 0:',
        new="        elif False:",
        want=f"{_EP}::test_the_guard_order_detector_itself_works",
        why="「guard 必须是第一个 await」退化成「体内有 guard 就行」。scope-index-before-resource "
            "的核心是**顺序**：先读业务对象再授权会通过 404/403 的时序泄露对象存在性",
    ),
    Mutation(
        id="M39", side="be", path=GATE, kind="replace",
        anchor="    if status == 404:",
        new="    if False:",
        want=f"{_EP}::test_the_refusal_site_classifier_itself_works",
        why="裸 404 构造点不再被统计。404 是存在性敏感码；handler 自己拼 `status_code=404` 时"
            "detail 形状与阶段都会偏离统一 oracle，跨 scope 探测就能分辨「不存在」与「无权」",
    ),
    Mutation(
        id="M40", side="be", path=GATE, kind="replace",
        anchor='    "chain": lambda run, w: _probe_chain(run, w),',
        new='    # "chain" 探针从注册表里被拿掉（变异）',
        want=f"{_WIRE}::test_every_probe_is_registered_and_every_registration_exists",
        wants=(
            f"{_INV}::test_declared_arms_and_written_observations_are_two_way_locked",
            f"{_LIVE}::test_the_live_catalog_and_harness_really_ran",
        ),
        why="子条目 5 的链路探针定义了却不注册 ⇒ 20 条链路臂全部没有观测。additive 注入即死代码"
            "（假绿第①源）：声明里写着「完整 template → instrumentation → contract → bundle → "
            "representation 已在真行上验过」，实际一行都没造",
    ),
    Mutation(
        id="M41", side="be", path=GATE, kind="replace",
        anchor="                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS \"{schema}\" CASCADE')",
        new="                pass  # 变异：不再清理 scratch schema",
        want=f"{_WIRE}::test_the_scratch_schema_lifecycle_is_complete",
        wants=(f"{_LIVE}::test_the_live_run_restores_production",),
        why="🔴 不再清理 scratch schema。每跑一次留下一套完整表结构 + 数百行数据；"
            "变异要跑几十轮，几十个残留 schema 会污染真库。复原实证的「无残留」那一半直接失效",
    ),
    Mutation(
        id="M42", side="be", path=GATE, kind="replace",
        anchor='    BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql",',
        new='    BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql",',
        want=f"{_WIRE}::test_the_scratch_ddl_is_the_production_migration_set",
        wants=(f"{_LIVE}::test_the_live_catalog_and_harness_really_ran",),
        why="🔴 scratch schema 上应用 **V153**（已占号但**未应用**到生产库）。行为侧就验在了"
            "一套生产上并不存在的 schema 上 —— 「行上验过」变成「在另一套 DDL 上验过」，"
            "而 schema 侧读的仍是生产库，两侧悄悄脱钩",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            # 🔴 `guard_files` 的**键是文件 basename**（kit 用 `rglob(key)` 定位）。
            #    写成 `{"be": "<相对路径>"}` 会让 `_locate_want` 一个 want 都定位不到，
            #    判定永远只能是 WRONG-TEST（首轮 `--list` 42/42 全报此症）。
            guard_files={_T: "Task 68 后端全链独立回归守卫"},
            repo=REPO,
            description="Task 68 后端全链独立回归守卫变异检验",
            backend_args=["backend/tests/workpaper_sync/test_task68_backend_chain_regression.py"],
            allow_dirty_baseline=True,
        )
    )
