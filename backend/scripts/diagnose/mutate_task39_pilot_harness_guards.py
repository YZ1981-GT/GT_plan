# -*- coding: utf-8 -*-
"""Task 39 守卫的变异检验（pilot harness / evidence freshness / capacity profile）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 39
Properties: P25 / P26 / P49 / P69 / P70 / P71 / P72

═══ 为什么本任务的变异检验特别关键 ═══

Task 39 建的是**判据本身的载体** —— 它决定哪些行会被写进 evidence 表、以及一个 entry
是否算"已验收"。所以「守卫没打红 = 守卫有缺陷」在这里的代价最高：一条空转的守卫直接
等于"平台可以自称双向回写已通过"。

═══ 已踩过的坑（本脚本按它们写死）═══

* `want` 必须是**短 nodeid**（`file.py::Class::test`，不带目录前缀）；
* pytest 参数传 `-rfE`；
* 锚点单行（工作树 CRLF，跨行锚点必 ANCHOR-MISS）；
* **替换体保持语法合法**：条件语句用 `if False and <原式>:` / `if False:`，
  表达式用 `return True or <原式>`；整行替换让后续行悬空会变成 collection error，
  被误判成 WRONG-TEST；
* 同形态锚点用 `scope` + `offset` 相对定位，不用绝对 `line`。

用法::

    py -3 backend/scripts/diagnose/mutate_task39_pilot_harness_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task39_pilot_harness_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task39_pilot_harness_guards.py --run all
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PH = "backend/app/services/workpaper_sync/pilot_harness.py"
EF = "backend/app/services/workpaper_sync/evidence_freshness.py"
CP = "backend/app/services/workpaper_sync/capacity_profile.py"

T39 = "test_task39_pilot_harness.py"
T39PG = "test_task39_pilot_harness_pg.py"
T15 = "test_task15_content_mutation.py"
T14 = "test_task14_merge_conflicts.py"

_REG = f"{T39}::TestOracleRegistryTwoWayLock"
_DERIVE = f"{T39}::TestRequiredSetDerivationOnRealManifest"
_REJECT = (
    f"{T39}::TestRejectionKindsReachableAndDistinct"
    "::test_rejection_kinds_are_reachable_and_mutually_distinct"
)
_P25 = f"{T39}::TestProperty25DifferentFieldMergeOracle"
_P26 = f"{T39}::TestProperty26SameFieldConflictOracle"
_BLACK = f"{T39}::TestNoRealOnlyOfficeMeansUnverifiable"
_TIME = f"{T39}::TestTimelineOracle"
_FRESH = f"{T39}::TestBundleFreshnessAxes"
_CAP = f"{T39}::TestCapacityProfileRegisteredOnly"
_PILOT = f"{T39}::TestPilotClassCoverage"
_HAND = f"{T39}::TestResultCannotBeHandFilled"

MUTATIONS: list[Mutation] = [
    # ── oracle 登记表双向锁 ────────────────────────────────────────────
    Mutation(
        id="M01", side="be", path=PH, kind="replace",
        anchor="    if missing:",
        new="    if False:",
        scope="    missing = sorted(declared - registered)",
        offset=1,
        want=f"{_REG}::test_an_incomplete_registry_raises_in_both_directions",
        why="声明了场景却没有 oracle 时不再抛 ⇒ 那条场景永远不会被提交，而"
            "「跑完全部场景」的计数仍然满分（分母虚高）",
        tags=("registry",),
    ),
    Mutation(
        id="M02", side="be", path=PH, kind="replace",
        anchor="    if extra:",
        new="    if False:",
        want=f"{_REG}::test_an_incomplete_registry_raises_in_both_directions",
        why="oracle 表可以追加不对应任何声明的自由项 ⇒ required set 不再只由推导产生",
        tags=("registry",),
    ),
    Mutation(
        id="M03", side="be", path=PH, kind="replace",
        anchor="        if not hasattr(module, attr):",
        new="        if False:",
        want=f"{_REG}::test_a_renamed_production_symbol_is_caught",
        why="生产符号被改名/删除不再打红 ⇒ 场景声明还在、被测的东西早已不在"
            "（死代码型假绿）",
        tags=("registry",),
    ),
    Mutation(
        id="M04", side="be", path=PH, kind="replace",
        anchor="        if not module_name or not attr:",
        new="        if False:",
        want=f"{_REG}::test_a_missing_module_and_a_malformed_ref_are_both_caught",
        why="`module:attr` 形态不再校验 ⇒ 缺 `:` 的 ref 会掉到 `hasattr(module, \"\")` 那条"
            "分支上报同一个 kind，形态校验变成不可达。首轮 GREEN 的原因正是判据只断 kind ——"
            "改成同时断诊断文案后才能 falsify（共享错误码的经典形态）",
        tags=("registry",),
    ),
    Mutation(
        id="M05", side="be", path=PH, kind="replace",
        anchor="        except Exception as exc:  # noqa: BLE001 - 转成分型拒绝，不降级",
        new="        except ImportError as exc:",
        want=f"{_REG}::"
             "test_a_module_that_fails_to_import_for_a_non_import_reason_still_fails_closed",
        why="import 失败只捕 ImportError ⇒ 模块内语法错/依赖缺失原样穿透，调用侧看到的不是"
            "可归因的 oracle_unresolvable。首轮 GREEN 的原因是三个样例全落 "
            "ModuleNotFoundError（ImportError 子类）—— 必须用真放盘的语法错模块才可 falsify",
        tags=("registry",),
    ),
    # ── required set 推导与零场景 ───────────────────────────────────────
    Mutation(
        id="M06", side="be", path=PH, kind="replace",
        anchor="    if not required.scenarios:",
        new="    if False:",
        want=f"{_DERIVE}::test_unreachable_entry_yields_zero_scenarios_and_must_fail_closed",
        wants=(
            f"{T39PG}::TestPlanIsDerivedFromSourceFacts"
            "::test_unreachable_entry_is_refused_by_the_harness_itself",
        ),
        why="🔴 零场景不再 fail closed ⇒ 「0/0 全部通过」被当成通过，"
            "unreachable 入口可以被记为已验收",
        tags=("denominator",),
    ),
    Mutation(
        id="M07", side="be", path=PH, kind="replace",
        anchor="        assert_required_set_non_empty(required)",
        new="        _ = required",
        want=f"{T39PG}::TestPlanIsDerivedFromSourceFacts"
             "::test_unreachable_entry_is_refused_by_the_harness_itself",
        why="plan 不再调用非空判据 ⇒ 纯函数变成死代码（本 spec 第①号假绿形态："
            "判据正确但没有消费方）",
        tags=("denominator", "wiring"),
    ),
    Mutation(
        id="M08", side="be", path=PH, kind="replace",
        anchor="            resolve_production_refs(oracle_for(scenario_id))",
        new="            _ = scenario_id",
        want=f"{T39PG}::TestPlanIsDerivedFromSourceFacts"
             "::test_plan_really_resolves_every_scenarios_production_symbol",
        why="plan 不再逐场景解析生产符号 ⇒ 接线是否存在这条判据在生产路径上不可达。"
            "首轮 GREEN 的原因是判据只看 plan 产出的场景 id（少了解析并不改变它）——"
            "改成「把某场景的生产符号换成不存在的名字，plan 必须拒」后才可 falsify",
        tags=("registry", "wiring"),
    ),
    # ── 结果推导：判定顺序不可交换 ─────────────────────────────────────
    Mutation(
        id="M09", side="be", path=PH, kind="replace",
        anchor="    if scenario.scenario_id in SCHEMA_UNREPRESENTABLE_SCENARIOS:",
        new="    if False:",
        want=f"{_BLACK}::test_schema_debt_scenario_is_unverifiable_and_still_required",
        why="已登记的 schema 欠账场景不再被识别 ⇒ 它会走别的分支，"
            "「为什么永远差这一条」失去归因",
        tags=("verdict",),
    ),
    Mutation(
        id="M10", side="be", path=PH, kind="replace",
        anchor="    if oracle.upstream_debt:",
        new="    if False:",
        want=f"{_BLACK}::test_upstream_gap_scenarios_are_failed_not_unverifiable",
        wants=(
            f"{T39PG}::TestScenarioRowsAreRealAndSchemaValid"
            "::test_upstream_gap_scenarios_are_failed_with_task32_attribution",
        ),
        why="上游实现缺口不再判 failed ⇒ 两条 Task 32 欠账场景会显示成 unverifiable，"
            "于是「接了 OO 就自动变绿」—— 而生产上那道校验根本不存在",
        tags=("verdict", "debt"),
    ),
    Mutation(
        id="M11", side="be", path=PH, kind="replace",
        anchor="    if oracle.needs_black_box:",
        new="    if False:",
        want=f"{_BLACK}::test_every_black_box_scenario_is_unverifiable_without_a_real_build",
        wants=(
            f"{T39PG}::TestScenarioRowsAreRealAndSchemaValid"
            "::test_no_black_box_scenario_was_recorded_as_passed",
        ),
        why="🔴 没有真实 OO/浏览器也能判 passed ⇒ 直接违反 Property 49"
            "（probe/pilot 未实际通过时必须保持 UNVERIFIABLE）",
        tags=("verdict", "p49"),
    ),
    Mutation(
        id="M12", side="be", path=PH, kind="replace",
        anchor="        if EvidenceInput.onlyoffice_forcesave in oracle.requires and (",
        new="        if False and (",
        want=f"{T39PG}::TestScenarioRowsAreRealAndSchemaValid"
             "::test_black_box_scenarios_carry_the_not_executed_error_code",
        why="只看 browser build、不看 OO build ⇒ 只需要真实 OO（不需要浏览器）的场景"
            "（identity retention / dedupe / 动态行列）会被判 passed",
        tags=("verdict", "p49"),
    ),
    Mutation(
        id="M13", side="be", path=PH, kind="replace",
        anchor="    if missing_inputs:",
        new="    if False:",
        want=f"{_BLACK}::test_missing_evidence_input_is_unverifiable",
        why="证据种类缺失不再拦 ⇒ 一条什么都不提交的观测也能走到判据并 passed",
        tags=("verdict",),
    ),
    Mutation(
        id="M14", side="be", path=PH, kind="replace",
        anchor="        if observation.merge_evidence is None:",
        new="        if False:",
        want=f"{_BLACK}::test_a_merge_scenario_without_three_way_input_is_unverifiable",
        why="字段级场景缺三方 projection 也放行 ⇒ oracle 拿 None 去执行（AttributeError），"
            "P25/P26 的判定退化成「什么都没查」。首轮 GREEN 的原因是 want 指向直接调 "
            "`evaluate_*` 的判据 —— 那道门在 `run_scenario_oracle` 里，必须走它才测得到",
        tags=("verdict", "p25", "p26"),
    ),
    Mutation(
        id="M15", side="be", path=PH, kind="replace",
        anchor="        if scenario.family is ScenarioFamily.merge:",
        new="        if False:",
        want=f"{_BLACK}::test_a_merge_scenario_with_three_way_input_is_judged_by_the_oracle",
        why="merge 家族与 conflict 家族的 oracle 分派错位 ⇒ P25 的场景会用 P26 的判据"
            "（要求同字段冲突），互相把对方判失败",
        tags=("verdict", "p25", "p26"),
    ),
    # ── Property 25 ────────────────────────────────────────────────────
    Mutation(
        id="M16", side="be", path=PH, kind="replace",
        anchor="    if outcome.conflict_count != 0:",
        new="    if False:",
        want=f"{_P25}::test_oracle_fails_when_a_conflict_appears",
        why="不同字段并行修改产生冲突也算通过 ⇒ P25 的核心判据（conflict_count=0）失效。"
            "首轮 GREEN 的原因是判据用的三方本来就零冲突 ⇒ 该分支在真实数据上不可达 ——"
            "必须专门构造一份会冲突的三方（真实数据上分支不可达 = 永久 GREEN）",
        tags=("p25",),
    ),
    Mutation(
        id="M17", side="be", path=PH, kind="replace",
        anchor="    if merged_a != want_a:",
        new="    if False:",
        want=f"{_P25}::test_oracle_fails_when_the_current_side_is_lost",
        why="🔴 不再检查 current 侧是否存活 ⇒ 「incoming 整体覆盖 current」同样零冲突，"
            "会被判 passed 而 A 已经丢了",
        tags=("p25",),
    ),
    Mutation(
        id="M18", side="be", path=PH, kind="replace",
        anchor="    if merged_b != want_b:",
        new="    if False:",
        want=f"{_P25}::test_oracle_fails_when_the_incoming_side_is_lost",
        why="不再检查 incoming 侧是否被采纳 ⇒ 「current 整体保留」也算自动合并。"
            "首轮 GREEN 的原因是只测了 current 侧那一半 —— 两侧必须成对",
        tags=("p25",),
    ),
    Mutation(
        id="M19", side="be", path=PH, kind="replace",
        anchor="    if evidence.current_changed_key is None or evidence.incoming_changed_key is None:",
        new="    if False:",
        want=f"{_P25}::test_oracle_is_unverifiable_without_explicit_keys",
        why="不给两侧改动键也判定 ⇒ 判据退化成「零冲突」，而整体覆盖也满足零冲突",
        tags=("p25",),
    ),
    Mutation(
        id="M20", side="be", path=PH, kind="replace",
        anchor="    if evidence.current_changed_key == evidence.incoming_changed_key:",
        new="    if False:",
        want=f"{_P25}::test_same_key_on_both_sides_is_not_a_p25_scenario",
        why="两侧给同一个键也当 P25 ⇒ 那是 P26 的场景，会把「必冲突」误判成「必合并」",
        tags=("p25",),
    ),
    # ── Property 26 ────────────────────────────────────────────────────
    Mutation(
        id="M21", side="be", path=PH, kind="replace",
        anchor="    if record is None:",
        new="    if False:",
        want=f"{_P26}::test_oracle_fails_when_no_conflict_is_raised",
        why="同字段异值没产生冲突也算通过 ⇒ 有一侧被静默采纳（P26 的反面）",
        tags=("p26",),
    ),
    Mutation(
        id="M22", side="be", path=PH, kind="replace",
        anchor="        if got[side] != expected:",
        new="        if False:",
        want=f"{_P26}::test_oracle_fails_when_the_three_conflict_values_do_not_match_the_inputs",
        why="冲突三值不再与输入逐一比对 ⇒ 裁决界面可能显示错值而守卫全绿"
            "（P26 的「冲突三值完整」）。首轮 GREEN 的原因是没有任何判据构造过"
            "「三值与输入不一致」的冲突记录",
        tags=("p26",),
    ),
    Mutation(
        id="M23", side="be", path=PH, kind="replace",
        anchor='    if outcome.value_of(key) == want["incoming"]:',
        new="    if False:",
        want=f"{_P26}::test_oracle_fails_when_incoming_is_silently_applied",
        why="🔴 冲突未裁决时 merged 已等于 incoming 也算通过 ⇒ 等于自动选了 OO 侧",
        tags=("p26",),
    ),
    Mutation(
        id="M24", side="be", path=PH, kind="replace",
        anchor="    if key is None:",
        new="    if False:",
        want=f"{_P26}::test_oracle_is_unverifiable_without_a_conflict_key",
        why="不给冲突键也判定 ⇒ 无法断言「三值完整」，判据空转",
        tags=("p26",),
    ),
    # ── 时序 oracle ────────────────────────────────────────────────────
    Mutation(
        id="M25", side="be", path=PH, kind="replace",
        anchor="    if missing:",
        new="    if False:",
        scope="    missing = [stage for stage in expected_order if observed.get(stage) is None]",
        offset=1,
        want=f"{_TIME}::test_missing_stage_is_unverifiable_not_failed",
        why="缺服务端时序阶段不再报 ⇒ 「没跑」与「跑了但顺序错」合成一类，"
            "而下一步的 `observed[stage]` 会 KeyError 穿透",
        tags=("timeline",),
    ),
    Mutation(
        id="M26", side="be", path=PH, kind="replace",
        anchor="        if not prev <= current:",
        new="        if False:",
        want=f"{_TIME}::test_out_of_order_stages_fail",
        why="时序不再校验 ⇒ AC 14.8 的 `request frozen < command accepted < incoming "
            "durable < terminal` 完全空转",
        tags=("timeline",),
    ),
    Mutation(
        id="M27", side="be", path=PH, kind="replace",
        anchor="            if scenario.family is ScenarioFamily.recovery",
        new="            if False",
        want=f"{_TIME}::test_a_recovery_scenario_is_judged_against_the_recovery_order",
        why="recovery 场景改用 OO→HTML 的时序序列 ⇒ AC 14.8 为 no-userdata crash 单列的"
            "`incoming durable < recovery case(no operation) < claim` 不再被检查。"
            "首轮 GREEN 的原因是判据只比「行结果 == decision 结果」——两者一起变，"
            "必须落到「喂 recovery 序列必 passed / 喂 OO 序列必缺阶段」",
        tags=("timeline", "recovery"),
    ),
    # ── close capture ──────────────────────────────────────────────────
    Mutation(
        id="M28", side="be", path=PH, kind="replace",
        anchor="        if got is None:",
        new="        if False:",
        want=f"{_BLACK}::test_close_capture_count_must_be_measured_and_exact",
        why="close-capture 数不再要求实测 ⇒ partial unique 只证明 at-most-one，"
            "AC 4.10 要的是 exactly-one",
        tags=("close",),
    ),
    Mutation(
        id="M29", side="be", path=PH, kind="replace",
        anchor="        if got != scenario.expected_close_captures:",
        new="        if got is None:",
        want=f"{_BLACK}::test_close_capture_count_must_be_measured_and_exact",
        wants=(f"{_BLACK}::test_zero_capture_scenario_expects_zero_not_one",),
        why="实测数与期望不再精确相等 ⇒ 两个 capture 也算通过，"
            "「无 successor 时零 capture」也测不出来",
        tags=("close",),
    ),
    # ── entity 形态（V151 三条约束的写入侧镜像）─────────────────────────
    Mutation(
        id="M30", side="be", path=PH, kind="replace",
        anchor="    if scenario.kind in zero_entity_kinds:",
        new="    if False:",
        want=_REJECT,
        wants=(
            f"{T39PG}::TestWriteSideFailClosedIsWired"
            "::test_download_only_with_entities_is_refused",
        ),
        why="download_only / recovery_reject 带 operation/application 不再拦 ⇒ 真库会抛"
            "`ck_wpees_download_only_zero_entities`（首轮实测），而离线守卫看不出来",
        tags=("entity",),
    ),
    Mutation(
        id="M31", side="be", path=PH, kind="replace",
        anchor="    elif not scenario.expects_application and observation.application_ids:",
        new="    elif False:",
        want=_REJECT,
        why="quarantined 场景（standard kind）带 application 不再拦 ⇒ AC 5.6 的"
            "「永不创建 application」在库层完全不管，判据只能在写入侧",
        tags=("entity",),
    ),
    Mutation(
        id="M32", side="be", path=PH, kind="replace",
        anchor="    if scenario.expects_recovery_case and not observation.recovery_case_ids:",
        new="    if False:",
        want=_REJECT,
        why="recovery 场景不绑 case 也放行 ⇒ 「claim 前零 operation」这条无处观测",
        tags=("entity",),
    ),
    Mutation(
        id="M33", side="be", path=PH, kind="replace",
        anchor="    if scenario.expects_application and not (",
        new="    if False and (",
        want=_REJECT,
        why="声明需要 operation+application 的场景可以两手空空 ⇒ 「一条 applied operation "
            "代表全部场景」的反面：干脆一条都不给",
        tags=("entity",),
    ),
    Mutation(
        id="M34", side="be", path=PH, kind="replace",
        anchor="        and observation.recovery_precondition_zero_entities is False",
        new="        and False",
        want=_REJECT,
        why="claim 前已存在三实体也放行 ⇒ AC 5.8 的「三者在 claim 成功前均不存在」空转",
        tags=("entity", "recovery"),
    ),
    # ── 跨场景 / 跨 entry 复用（Property 70）─────────────────────────────
    Mutation(
        id="M35", side="be", path=PH, kind="replace",
        anchor="        overlap = sorted(mine & theirs)",
        scope="    for scenario_id, theirs in recorded:",
        offset=1,
        new="        overlap = []",
        want=_REJECT,
        why="同 run 内跨场景复用不再检出 ⇒ 一条 applied operation 可以填满 24 个场景"
            "（AC 12.10 明令禁止）",
        tags=("p70",),
    ),
    Mutation(
        id="M36", side="be", path=PH, kind="replace",
        anchor="        overlap = sorted(mine & theirs)",
        scope="    for entry_id, scenario_id, theirs in foreign:",
        offset=1,
        new="        overlap = []",
        want=_REJECT,
        wants=(
            f"{T39PG}::TestWriteSideFailClosedIsWired"
            "::test_borrowing_another_entrys_application_is_refused",
        ),
        why="🔴 跨 entry 复制证据不再检出 ⇒ 一个 entry 的 pilot 证据可以复制给另外 177 个",
        tags=("p70",),
    ),
    Mutation(
        id="M37", side="be", path=PH, kind="replace",
        anchor="            observation=observation, foreign=await self._foreign_entities(run=run)",
        new="            observation=observation, foreign=[]",
        want=f"{T39PG}::TestWriteSideFailClosedIsWired"
             "::test_borrowing_another_entrys_application_is_refused",
        why="跨 entry 判据接了但喂空集 ⇒ 纯函数正确、生产路径永远查不到东西"
            "（本 spec 的死代码型假绿）",
        tags=("p70", "wiring"),
    ),
    # ── trace bundle ───────────────────────────────────────────────────
    Mutation(
        id="M38", side="be", path=PH, kind="replace",
        anchor="    if artifact is None or str(artifact.state) != ArtifactState.published.value:",
        new="    if False:",
        want=f"{T39}::TestRejectionKindsReachableAndDistinct"
             "::test_trace_bundle_rejection_covers_all_three_failure_shapes",
        why="trace bundle 未 published 也算证据 ⇒ 截图/自由文本可以冒充逐 scenario 证据",
        tags=("trace",),
    ),
    Mutation(
        id="M39", side="be", path=PH, kind="replace",
        anchor="    if str(artifact.sha256) != observation.trace_bundle_sha256:",
        new="    if False:",
        want=f"{T39}::TestRejectionKindsReachableAndDistinct"
             "::test_trace_bundle_rejection_covers_all_three_failure_shapes",
        why="登记的 sha256 与 artifact 行不符也放行 ⇒ trace bundle 可以指向另一份文件",
        tags=("trace",),
    ),
    Mutation(
        id="M40", side="be", path=PH, kind="replace",
        anchor="            artifact=await self._artifact(observation.trace_bundle_artifact_id),",
        new="            artifact=_artifact_stub_never_used(),",
        want=f"{T39PG}::TestWriteSideFailClosedIsWired"
             "::test_a_scenario_without_a_trace_bundle_is_refused",
        why="trace 判据不再读真 artifact 行 ⇒ 生产路径上「published + hash 相符」两条都空转。"
            "替换体引用一个不存在的名字，调用即 NameError ⇒ 走 harness 的那条路径必红",
        tags=("trace", "wiring"),
    ),
    # ── bundle 身份（authority model 只能从 approved bundle 链上读）──────
    Mutation(
        id="M41", side="be", path=PH, kind="replace",
        anchor='    if str(bundle.state) != DefinitionState.approved.value:',
        new="    if False:",
        want=_REJECT,
        wants=(
            f"{T39PG}::TestPlanIsDerivedFromSourceFacts"
            "::test_candidate_bundle_is_refused_by_the_harness_itself",
        ),
        why="candidate bundle 也能进 evidence ⇒ AC 12.1 的「approved non-null bundle」空转",
        tags=("bundle",),
    ),
    Mutation(
        id="M42", side="be", path=PH, kind="replace",
        anchor="        model = AuthorityModel(authority.authority_model_type)",
        new='        model = AuthorityModel.opaque_single_onlyoffice',
        want=_REJECT,
        why="🔴 authority model 不再从 definition 行解析而是写死 ⇒ 「未知枚举或自由文本豁免"
            "fail closed」空转，任何入口都能拿到 opaque 从而少跑两个字段级场景",
        tags=("bundle", "authority"),
    ),
    Mutation(
        id="M43", side="be", path=PH, kind="replace",
        anchor="    if str(authority.kind) != DefinitionKind.authority_model.value:",
        new="    if False:",
        want=f"{T39}::TestRejectionKindsReachableAndDistinct"
             "::test_authority_child_of_the_wrong_kind_is_caught_by_its_own_branch",
        why="bundle 的 authority child 可以是 contract/template ⇒ authority model 的身份"
            "来源被打通。首轮 GREEN 的原因是触发点用的是非法枚举值 —— 枚举分支抛同一个码，"
            "kind 分支被遮蔽（共享错误码形态）",
        tags=("bundle", "authority"),
    ),
    Mutation(
        id="M44", side="be", path=PH, kind="replace",
        anchor="    if authority is None or str(authority.state) != DefinitionState.approved.value:",
        new="    if authority is None:",
        want=f"{T39}::TestRejectionKindsReachableAndDistinct"
             "::test_bundle_not_approved_covers_both_the_bundle_and_its_authority_child",
        why="authority model definition 未 approved 也放行 ⇒ AC 6.2 的「独立先行批准」空转。"
            "首轮 GREEN 的原因是触发点只用了 approved 的 child ⇒ state 分支不可达",
        tags=("bundle", "authority"),
    ),
    # ── plan/run 交叉身份 ──────────────────────────────────────────────
    Mutation(
        id="M45", side="be", path=PH, kind="replace",
        anchor="    if plan.bundle.bundle_sha256 != str(run.definition_bundle_sha256):",
        new="    if False:",
        want=_REJECT,
        why="plan 与 run 的 bundle 可以不一致 ⇒ 落库证据声称「按 bundle A 验的」，"
            "判定其实按 bundle B 的 required set 做（跨 bundle 复用，Property 70）",
        tags=("identity",),
    ),
    Mutation(
        id="M46", side="be", path=PH, kind="replace",
        anchor="    if plan.bundle.authority_model_definition_sha256 != str(",
        new="    if False and (",
        want=_REJECT,
        why="authority model digest 可以不一致 ⇒ 字段级两场景是否被替换与落库声明脱钩",
        tags=("identity",),
    ),
    Mutation(
        id="M47", side="be", path=PH, kind="replace",
        anchor="    if run.finished_at is not None:",
        new="    if False:",
        want=_REJECT,
        why="已 finalize 的 run 还能追加场景 ⇒ 可以先 finalize 成 passed 再补一条失败场景",
        tags=("identity",),
    ),
    # ── finalize / open_run：结果只能由重算写入 ─────────────────────────
    Mutation(
        id="M48", side="be", path=PH, kind="replace",
        anchor='        run.aggregate_result = "passed" if recomputed.verified else "failed"',
        new='        run.aggregate_result = "passed"',
        want=f"{T39PG}::TestFinalizeWritesOnlyRecomputedResult"
             "::test_a_run_without_real_onlyoffice_cannot_be_passed",
        wants=(f"{_HAND}::test_finalize_writes_only_recomputed_result",),
        why="🔴 aggregate_result 不再由服务端重算决定 ⇒ 一个全 unverifiable 的 run 也会"
            "落 passed，平台可以自称双向回写已通过",
        tags=("finalize", "p49"),
    ),
    Mutation(
        id="M49", side="be", path=PH, kind="replace",
        anchor="        run.finished_at = datetime.now(timezone.utc)",
        new="        run.finished_at = None",
        want=f"{T39PG}::TestFinalizeWritesOnlyRecomputedResult"
             "::test_finalize_sets_finished_at_and_a_recomputed_result",
        wants=(f"{_HAND}::test_finalize_writes_only_recomputed_result",),
        why="finished_at 不落 ⇒ V151 的 `ck_wpstr_result_requires_finish` 会拒非 unverified"
            "结果，且「已完成但未通过」与「还没跑」在库里同形",
        tags=("finalize",),
    ),
    Mutation(
        id="M50", side="be", path=PH, kind="replace",
        anchor='            aggregate_result="unverified",',
        new='            aggregate_result="passed",',
        want=f"{T39PG}::TestOpenRunFreezesDerivedIdentity"
             "::test_run_starts_unverified_with_no_finish_time",
        why="run 一开就是 passed ⇒ 「开了但没跑完」的 run 直接计入已验收",
        tags=("finalize",),
    ),
    Mutation(
        id="M51", side="be", path=PH, kind="replace",
        anchor="            required_scenario_set_digest=plan.required.digest,",
        new='            required_scenario_set_digest="0" * 64,',
        want=f"{T39PG}::TestOpenRunFreezesDerivedIdentity"
             "::test_identity_columns_are_derived_not_supplied",
        why="required set digest 不再由推导写入 ⇒ AC 14.16 的「scenario set 变化即 stale」"
            "失去锚点（旧 evidence 永远新鲜）",
        tags=("finalize", "p71"),
    ),
    Mutation(
        id="M52", side="be", path=PH, kind="replace",
        anchor="        if environment.runner_version != self._runner_version:",
        new="        if False:",
        want=f"{T39}::TestHarnessVersionParticipatesInStaleness"
             "::test_open_run_refuses_a_mismatched_runner_identity",
        why="runner 身份不再自洽校验 ⇒ 每个 run 一开始就 stale（runner_changed），"
            "而 stale 的 run 不参与已验收计数 ⇒ 「跑了但永远不算」变成静默状态。"
            "首轮 GREEN 的原因是判据是源码级 presence（`if False:` 之下 "
            "`self._runner_version` 仍留在 raise 体里）—— 改成行为判据后才可 falsify",
        tags=("finalize", "p71"),
    ),
    # ── freshness 三条 bundle 轴（Property 71）───────────────────────────
    Mutation(
        id="M53", side="be", path=EF, kind="replace",
        anchor="    if str(run.authority_model_definition_sha256) != current.authority_model_definition_sha256:",
        new="    if False:",
        want=f"{_FRESH}::test_authority_change_is_its_own_axis",
        wants=(
            f"{T39PG}::TestFreshnessAxesOnRealRows"
            "::test_bundle_and_authority_change_are_two_axes",
        ),
        why="🔴 authority model 变化不再 stale ⇒ 该枚举成员回到「声明存在、判据为空」的状态"
            "（Task 29 交付时就是这样）",
        tags=("p71",),
    ),
    Mutation(
        id="M54", side="be", path=EF, kind="replace",
        anchor="    if str(run.definition_bundle_sha256) != current.bundle_sha256:",
        new="    if False:",
        want=f"{_FRESH}::test_bundle_change_is_its_own_axis",
        wants=(
            f"{T39PG}::TestFreshnessAxesOnRealRows"
            "::test_bundle_and_authority_change_are_two_axes",
        ),
        why="bundle 换了也不 stale ⇒ AC 14.16 明文列出的失效轴不可达",
        tags=("p71",),
    ),
    Mutation(
        id="M55", side="be", path=EF, kind="replace",
        anchor="    if frozen_child_digest is not None and frozen_child_digest != current.typed_child_digest:",
        new="    if False:",
        want=f"{_FRESH}::test_typed_child_change_is_its_own_axis",
        wants=(
            f"{T39PG}::TestFreshnessAxesOnRealRows"
            "::test_typed_child_change_is_reported_on_its_own_axis",
        ),
        why="typed child 变化不再单独成轴 ⇒ 「child 被换掉而 bundle digest 未变」（篡改）"
            "与「bundle 整体升级」（正常）分不出来",
        tags=("p71",),
    ),
    Mutation(
        id="M56", side="be", path=EF, kind="replace",
        anchor="    if recomputed != identity.bundle_sha256:",
        new="    if False:",
        want=f"{_FRESH}::test_tampered_child_inventory_fails_closed",
        why="bundle 行的 digest 与 child 现算值不符也不报 ⇒ 绕过发布器直接 UPDATE child "
            "的篡改完全不可见",
        tags=("p71", "tamper",),
    ),
    Mutation(
        id="M57", side="be", path=EF, kind="replace",
        anchor="        if self.defects:",
        new="        if False:",
        scope="    def result(self) -> EvidenceResult:",
        offset=6,
        want=f"{_FRESH}::test_defects_outrank_stale_in_the_composed_verdict",
        why="缺陷不再优先于 stale ⇒ 「既过期又有缺陷」显示成 stale，读者会以为"
            "「重跑一次就好了」，而它其实结构上不成立",
        tags=("p71",),
    ),
    # ── 容量 profile（Property 72）───────────────────────────────────────
    Mutation(
        id="M58", side="be", path=CP, kind="replace",
        anchor="    if drift:",
        new="    if False:",
        want=f"{_CAP}::test_lowering_a_target_is_caught",
        why="🔴 登记的容量目标与需求原文脱钩 ⇒ 把 6000 会话改成 600 不会打红"
            "（自证式同义反复的反面判据失效）",
        tags=("p72",),
    ),
    Mutation(
        id="M59", side="be", path=CP, kind="replace",
        anchor="        if match is None:",
        new="        if False:",
        scope="        match = re.search(pattern, text)",
        offset=1,
        want=f"{_CAP}::"
             "test_reworded_requirement_text_fails_closed_instead_of_silently_skipping",
        why="需求措辞变了、正则抠不到时静默跳过 ⇒ 锁默默失效（fail-open）。"
            "首轮 GREEN 的原因是真实 requirements.md 上 7 条正则全命中 ⇒ 该分支在真实数据上"
            "不可达 —— 必须用合成副本（改掉数字措辞）让分支可达",
        tags=("p72",),
    ),
    Mutation(
        id="M60", side="be", path=CP, kind="replace",
        anchor="    if shortfalls and not (measurement.capacity_adr_ref or \"\").strip():",
        new="    if False:",
        want=f"{_CAP}::test_a_shortfall_without_an_adr_is_refused",
        why="未达标且无 ADR 也放行 ⇒ AC 14.12 的「不得静默放宽」空转",
        tags=("p72",),
    ),
    Mutation(
        id="M61", side="be", path=CP, kind="replace",
        anchor="    if outcome is None:",
        new="    if False:",
        want=f"{_CAP}::test_asking_whether_capacity_passed_without_a_run_raises",
        why="🔴 没有执行记录也能宣称容量门已过 ⇒ 直接违反「容量 profile 仅登记待 Task 71 "
            "执行，不宣称真实 OO probe/pilot 已通过」",
        tags=("p72",),
    ),
    Mutation(
        id="M62", side="be", path=CP, kind="replace",
        anchor="        if got < target:",
        new="        if False:",
        want=f"{_CAP}::test_a_shortfall_with_an_adr_is_executed_requires_adr_not_passed",
        wants=(f"{_CAP}::test_a_shortfall_without_an_adr_is_refused",),
        why="负载实测低于目标不再记 shortfall ⇒ 1000 个会话也算达标 6000",
        tags=("p72",),
    ),
    Mutation(
        id="M63", side="be", path=CP, kind="replace",
        anchor="        if got > budget:",
        new="        if False:",
        want=f"{_CAP}::test_a_p95_over_budget_is_a_shortfall",
        why="延迟预算不再校验 ⇒ p95 超预算也算达标（AC 14.12 的两条 p95 判据空转）。"
            "首轮 GREEN 的原因是 want 指向 digest 判据（根本不调 `evaluate_capacity_run`）——"
            "负载与延迟是两条独立循环，各需一条直接判据",
        tags=("p72",),
    ),
    Mutation(
        id="M64", side="be", path=CP, kind="replace",
        anchor="            raise CapacityError(",
        scope="        if missing:",
        offset=1,
        new="            _ = CapacityError(",
        want=f"{_CAP}::test_missing_environment_record_is_refused",
        why="容量实测缺环境记录只构造异常不抛 ⇒ AC 14.12 的「记录硬件/OO build/载荷」空转，"
            "结果不可重复（Property 72）",
        tags=("p72",),
    ),
    # ── 四类 pilot 覆盖（Property 49）────────────────────────────────────
    Mutation(
        id="M65", side="be", path=PH, kind="replace",
        anchor="            if capability_of(entries[eid]) is Capability.bidirectional",
        new="            if True",
        want=f"{_PILOT}::test_no_class_is_verified_today_because_there_is_no_bidirectional_entry",
        why="pilot 覆盖不再要求 capability=bidirectional ⇒ 179 个 single_onlyoffice entry "
            "全被算成候选双向入口",
        tags=("p49",),
    ),
    Mutation(
        id="M66", side="be", path=PH, kind="replace",
        anchor="        verified = tuple(eid for eid in bidirectional if eid in verified_entry_ids)",
        new="        verified = bidirectional",
        want=f"{_PILOT}::test_bidirectional_without_a_verified_run_stays_unverifiable",
        why="🔴 只要是 bidirectional 就算 verified（不再要求通过服务端重算）⇒ "
            "Property 49 的「probe/pilot 未实际通过时必须保持 UNVERIFIABLE」空转",
        tags=("p49",),
    ),
    Mutation(
        id="M67", side="be", path=PH, kind="replace",
        anchor="        if self.verified_entry_ids:",
        new="        if self.candidate_entry_ids:",
        want=f"{_PILOT}::test_no_class_is_verified_today_because_there_is_no_bidirectional_entry",
        wants=(f"{_PILOT}::test_free_text_evidence_claims_cannot_flip_the_status",),
        why="status 由「有候选 entry」决定而不是「有已重算通过的 entry」⇒ 四类立刻全绿，"
            "而真实 OO 一次都没跑过",
        tags=("p49",),
    ),
    # ── 只读消费方边界（Task 15 的唯一 commit 边界判据）───────────────────
    Mutation(
        id="M68", side="be", path=PH, kind="insert",
        anchor="from app.services.workpaper_sync.contracts import SyncContract",
        new="from app.services.workpaper_sync.content_mutation import "
            "ContentMutationService  # noqa: F401",
        want=f"{T15}::TestTask15ScopeBoundary::test_merge_domain_deferral_is_retired",
        why="harness 一旦 import `content_mutation`，它就从「只读 merge 消费方」变成潜在的"
            "第二个内容写入边界（Property 61）。本任务把 Task 15 的判据从「必须声明 "
            "commits_through」扩成「要么声明、要么由 AST 证明零写入面」，这条变异证明新分支"
            "**真的**在拦人 —— 否则那个允许分支就是一句放宽",
        tags=("boundary",),
    ),
]

GUARD_FILES = {
    T39: "Task 39 新建（离线：oracle 登记表双向锁、19 码 rejection、P25/P26 oracle、"
         "容量登记、四类 pilot 覆盖、freshness 三轴）",
    T39PG: "Task 39 新建（真库：harness 真的接上判据、结果只由重算写入、V151 CHECK 接受面）",
    T15: "Task 15（唯一 commit 边界：本任务把 merge 只读消费方这一形态接进它的判据）",
    T14: "Task 14（merge 域消费方 ↔ 退役登记双向等值：本任务追加了一条只读消费方登记）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 39 pilot harness / evidence freshness / capacity 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task39_pilot_harness.py",
                "backend/tests/workpaper_sync/test_task39_pilot_harness_pg.py",
                # 🔴 Task 15 的 scope boundary 只挑那一个类：本任务把「merge 只读消费方」
                #    这一形态接进了它的判据，因此它必须进变异分母；整文件跑会把并发会话
                #    在途的其它红拖进差集。
                "backend/tests/workpaper_sync/test_task15_content_mutation.py"
                "::TestTask15ScopeBoundary",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=None,
        )
    )
