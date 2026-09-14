"""Task 66 守卫变异检验 —— legacy 删前清册 / replacement map / rollback 隔离门。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 66

被检验的守卫：``backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py``

## 为什么每条变异都不是无效变异

清册型产物最贵的三类缺陷：

1. **名单过期 / 检测器空转** —— 剥注释、括号配对、key 前缀解析、`ref()` 判据、
   成功文案语义、import specifier 解析，任一退化，某一族就整族消失或整族虚增，
   而记录照样自称完整（M01~M07）。
2. **形态归属被短路** —— 五个「必须唯一归入 replacement 或 pending-delete」的形态各有
   一条派生分支，短路掉就等于把该形态从清册里抹掉（M08~M12）。
3. **rollback 门变成重言式** —— 把某条约束改成恒真、把删除单位判据抹平、把
   `BINDING_CONSTRAINTS` 与实测 checks 解耦（M13~M17）。

另有 owner / 范围 / 载体门 三处交叉锁（M18~M21）与四条落在**记录本身**的手改
（M22~M25）：记录是 Task 67 结构复核与 Task 72 Stage B 的输入，能被手改而守卫不红，
整份计划就没有约束力。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷：锚点未命中
或命中 >1）/ WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task66_legacy_deletion_plan_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task66_legacy_deletion_plan_guards.py --run M01,M02
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task66_legacy_deletion_plan_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GEN = "backend/scripts/gen/generate_task66_legacy_deletion_plan.py"
REC = "backend/data/workpaper_sync_task66_legacy_deletion_plan.json"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task66_legacy_deletion_plan.py"

_SELF = f"{_T}::TestGuardSelfChecks"
_LOCK = f"{_T}::TestThreeWayLock"
_BIND = f"{_T}::TestFiveBindingsArePresentAndSound"
_FORM = f"{_T}::TestFiveFormsAreUniquelyDisposed"
_GATE = f"{_T}::TestRollbackIsolationGateIsMeasured"
_PLAN = f"{_T}::TestGeneratorOnlyPlans"
_CAT = f"{_T}::TestCategoriesDispositionsAndUnits"
_COUNT = f"{_T}::TestCountersRecomputeFromItems"
_BP = f"{_T}::TestBlockingPreconditions"
_IN = f"{_T}::TestInboundObligations"
_IDEM = f"{_T}::TestGeneratorIsIdempotentAndCheckIsStrict"

_BYTE_LOCK = f"{_IDEM}::test_check_matches_the_file_on_disk"


MUTATIONS: list[Mutation] = [
    # ═══ 一、检测器退化（整族消失或整族虚增）════════════════════════════════
    Mutation(
        id="M01", side="be", path=GEN, kind="replace",
        anchor='    return "\\n".join(out)',
        new="    return text",
        want=f"{_SELF}::test_comment_stripper_really_strips_and_keeps_line_count",
        wants=(
            f"{_SELF}::test_the_import_graph_is_not_fooled_by_a_comment",
            _BYTE_LOCK,
        ),
        why="剥注释退化成恒等。🔴 这是本任务最核心的一条：`GtG7LongTermEquityMain.vue` 里"
            "有一句**注释**提到 `WorkpaperSyncEditorHost`，不剥注释就会把这句说明文字算成"
            "一个消费方 ⇒ 「替代面零生产消费方」（BP-66-1 的全部实证）被打成假绿",
    ),
    Mutation(
        id="M02", side="be", path=GEN, kind="replace",
        anchor='        elif ch == "{" and angle == 0:',
        new='        elif ch == "{":',
        want=f"{_SELF}::test_brace_matcher_skips_the_parameter_list",
        wants=(_BYTE_LOCK,),
        why="函数体截取不再跳返回类型注解。TS 的 `): Promise<{…}>` 会让第一个 `{` 落在"
            "类型注解里（教训 14），`_getStorageKey()` 这类间接键就再也解析不出前缀 ⇒ "
            "20 余个 localStorage 调用点整批消失",
    ),
    Mutation(
        id="M03", side="be", path=GEN, kind="replace",
        anchor="        body = _function_bodies(code).get(call.group(1))",
        new="        body = None",
        want=f"{_SELF}::test_key_prefix_resolver_handles_all_three_real_forms",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="key 前缀解析不再走函数间接。存量里 `localStorage.getItem(_getStorageKey())` 是"
            "真实主流形态（l1/l2/l3 等），断掉之后这些旧键在清册里彻底不存在，"
            "AC 11.8 的迁移范围就少了一大块",
    ),
    Mutation(
        id="M04", side="be", path=GEN, kind="replace",
        anchor='            if re.search(rf"\\b{field}\\b\\s*(?::[^=\\n]+)?=\\s*ref\\s*[<(]", code)',
        new='            if re.search(rf"\\b{field}\\b\\s*[:=]", code)',
        want=f"{_SELF}::test_mode_state_field_detector_requires_a_real_ref",
        wants=(_BYTE_LOCK,),
        why="状态机字段判据从「真的 `= ref(`」放宽成「出现 `field:` 或 `field=`」。"
            "165 KB 的 `workpaperSyncLegacyBaseline.generated.ts` 里存着 characterization "
            "快照的宿主模板片段字符串 `\"snippet\": \"v-if=\\\"currentMode === 'onlyoffice'\\\"\"`，"
            "宽松判据会命中 `===` 的第一个 `=` ⇒ 这份快照文件被判成一个 legacy 状态机"
            "进待删清单（实测踩过的假阳性）",
    ),
    Mutation(
        id="M05", side="be", path=GEN, kind="replace",
        anchor="        if _SUCCESS_CALL.search(line) and _OO_SEMANTICS.search(line):",
        new="        if _SUCCESS_CALL.search(line):",
        want=f"{_SELF}::test_success_site_detector_needs_both_success_and_oo_semantics",
        wants=(_BYTE_LOCK,),
        why="成功文案只看「是不是成功提示」不看「是不是 OO 同步语义」。OCR/AI/导入的成功"
            "文案会被算进 fail-open 族 ⇒ 分子虚高，AC 11.10 的真问题被噪声埋掉",
    ),
    Mutation(
        id="M06", side="be", path=GEN, kind="replace",
        anchor="            if candidate.is_file():",
        new="            if False:",
        want=f"{_LOCK}::test_import_graph_facts_recompute",
        wants=(
            f"{_SELF}::test_the_import_graph_is_not_fooled_by_a_comment",
            _BYTE_LOCK,
        ),
        why="import specifier 解析恒失败 ⇒ import 图整张空。消费方计数全变 0、"
            "「最后调用点」全变 absent、`unreachable_stub` 变成全集 —— "
            "清册看起来「什么都可以删」",
    ),
    Mutation(
        id="M07", side="be", path=GEN, kind="replace",
        anchor="        return rel_path in self.by_file",
        new="        return True",
        want=f"{_COUNT}::test_every_recomputable_counter_matches",
        wants=(_BYTE_LOCK,),
        why="清点范围不再由 source-backed manifest 划定，任何文件都算「在底稿回写面上」。"
            "`components/deliverable/OnlyOfficeEditor.vue` 这类交付物编辑器会被拉进底稿"
            "HTML↔OO 清册（实测假阳性）⇒ 待删清单里出现本 spec 管不着的文件，"
            "Stage B 照删就是计划外变更",
    ),

    # ═══ 二、五个形态的派生被短路 ═════════════════════════════════════════
    Mutation(
        id="M08", side="be", path=GEN, kind="replace",
        anchor='        row for row in replacement_rows if not row["reachable_from_production_host"]',
        new="        row for row in replacement_rows if False",
        want=f"{_FORM}::test_the_canonical_bridge_is_among_the_unconsumed_subjects",
        wants=(
            f"{_FORM}::test_each_form_subject_has_exactly_one_admissible_disposition[unconsumed_bridge]",
            _BYTE_LOCK,
        ),
        why="形态①「无消费 bridge」整族清零。统一 bridge 与统一编辑器宿主实测 0 个生产"
            "消费方（additive 注入即死代码，假绿第①源），清零后 BP-66-1 失去全部实证，"
            "Stage B 会以为「删掉 legacy 后有可用替代路径」",
    ),
    Mutation(
        id="M09", side="be", path=GEN, kind="replace",
        anchor="    if endpoint_hits:",
        new="    if False:",
        want=f"{_FORM}::test_each_form_subject_has_exactly_one_admissible_disposition[legacy_config_second_request]",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="形态②「旧 config 二次请求」整族清零。92 个 subject 全部消失 ⇒ AC 11.1 "
            "「业务组件不得自行拼 config/forcesave URL」这条在清册里查无实据",
    ),
    Mutation(
        id="M10", side="be", path=GEN, kind="replace",
        anchor="    if single_switch_entry_ids:",
        new="    if False:",
        want=f"{_FORM}::test_each_form_subject_has_exactly_one_admissible_disposition[single_fake_switch]",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="形态③「single 假切换」整族清零。132 个 entry 的 capability 都不是 "
            "bidirectional 却仍显示模式切换（AC 1.5 / 12.9），清零后这批入口"
            "在删前清册里就不存在了",
    ),
    Mutation(
        id="M11", side="be", path=GEN, kind="replace",
        anchor="    if fail_open_sites:",
        new="    if False:",
        want=f"{_FORM}::test_each_form_subject_has_exactly_one_admissible_disposition[fail_open_success_message]",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="形态④「fail-open 文案」整族清零（Property 48 的分子）",
    ),
    Mutation(
        id="M12", side="be", path=GEN, kind="replace",
        anchor='    if (production_importer_count == 0 and not is_replacement_surface) or unreachable_entry_ids:',
        new="    if False:",
        want=f"{_FORM}::test_each_form_subject_has_exactly_one_admissible_disposition[unreachable_stub]",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="形态⑤「unreachable 桩」整族清零。AC 1.7 逐字要求删除不可达旧桩；实测 44 个"
            "legacy composable 零生产 importer，清零后它们会一直挂在代码库里",
    ),
    Mutation(
        id="M13", side="be", path=GEN, kind="replace",
        anchor='            if flags.get("single_mode_switch_visible"):',
        new="            if False:",
        want=f"{_FORM}::test_single_fake_switch_subjects_trace_to_a_non_bidirectional_entry",
        wants=(_BYTE_LOCK, f"{_COUNT}::test_every_recomputable_counter_matches"),
        why="假切换的 **entry 侧分母**（Task 2 characterization 的 flag）读空。"
            "分母空集会让「每个假切换 subject 都能追到一个真 entry」恒真",
    ),

    # ═══ 三、rollback 门变成重言式 ════════════════════════════════════════
    Mutation(
        id="M14", side="be", path=GEN, kind="replace",
        anchor='            "passed": not unrecoverable,',
        new='            "passed": True,',
        want=f"{_GATE}::test_gate_recomputes_from_the_recorded_inputs",
        wants=(_BYTE_LOCK,),
        why="「每个待删项都要有可复原的 rollback target」改成恒真。🔴 反事实多臂实验"
            "**抓不到这一条**（把前提改好那一臂上恒真判定照样会变），所以必须有正向重算"
            "把它按住 —— 这正是教训 13 的另一半",
    ),
    Mutation(
        id="M15", side="be", path=GEN, kind="replace",
        anchor='            "passed": not untracked_replacement,',
        new='            "passed": True,',
        want=f"{_GATE}::test_gate_recomputes_from_the_recorded_inputs",
        wants=(_BYTE_LOCK,),
        why="「替代面自身必须已入库」改成恒真。实测 22/22 个替代面模块是 git `??` "
            "未跟踪 ⇒ 「删 legacy 保 replacement」这笔事务整体不可逆（BP-66-2），"
            "恒真之后门会直接放行",
    ),
    Mutation(
        id="M16", side="be", path=GEN, kind="replace",
        anchor='        i["path"] for i in pending if i["deletion_unit"] == "whole_file"',
        new='        i["path"] for i in pending',
        want=f"{_GATE}::test_gate_recomputes_from_the_recorded_inputs",
        wants=(_BYTE_LOCK,),
        why="删除单位判据被抹平：站点级删除被当成整文件删除。"
            "`wp_onlyoffice_router.py` 是双重身份（7 个共用端点必须留、里面的 "
            "`paragraph_index` 回写降级必须删），抹平后这条真实约束会被当成违反 ⇒ "
            "门永远 blocked，反过来也可能让 Stage B 误删整个共用 router",
    ),
    Mutation(
        id="M17", side="be", path=GEN, kind="replace",
        anchor='        "constraint_id": "site_level_deletions_inside_shared_files_are_declared",',
        new='        "constraint_id": "zzz_declared_but_never_measured",',
        want=_BYTE_LOCK,
        wants=(f"{_GATE}::test_declared_constraints_and_measured_checks_are_the_same_set",),
        why="声明的约束与实测 checks 解耦（只声明不度量）。生成器必须 fail closed 而不是"
            "把一条没人度量的约束写进记录 —— 那是「门里列了五条、实际只跑四条」",
    ),
    Mutation(
        id="M18", side="be", path=GEN, kind="replace",
        anchor='            and item["path"] in preserved_paths',
        new="            and False",
        want=f"{_CAT}::test_shared_router_is_preserved_but_its_paragraph_fallback_is_not",
        wants=(_BYTE_LOCK,),
        why="「站点级删除落在共用文件里」不再登记。Stage B 拿到的计划就分不清"
            "「删这三行」和「删这个文件」—— 这是最容易造成计划外变更的一处",
    ),

    # ═══ 四、owner / 范围 / 载体门 三处交叉锁 ═════════════════════════════
    Mutation(
        id="M19", side="be", path=GEN, kind="replace",
        anchor='        for group in re.findall(r"([A-Z](?:/[A-Z])*)\\s*循环", title):',
        new="        for group in []:",
        want=f"{_LOCK}::test_owner_tasks_all_exist_in_tasks_md",
        wants=(_BYTE_LOCK,),
        why="cycle→owner 映射不再从 tasks.md 现算。owner 一旦退化成手抄常量，"
            "任务号漂移时清册会把责任挂到错的任务上而没人发现",
    ),
    Mutation(
        id="M20", side="be", path=GEN, kind="replace",
        anchor="    return executor",
        new='    return "66"',
        want=f"{_LOCK}::test_owner_tasks_all_exist_in_tasks_md",
        wants=(_BYTE_LOCK, f"{_LOCK}::test_deletion_owner_is_not_task66"),
        why="删除执行方被写成 Task 66 自己。本任务正文明禁执行删除，"
            "把执行方指向自己就等于允许在 Task 70 之前改 source commit",
    ),
    Mutation(
        id="M21", side="be", path=GEN, kind="replace",
        anchor="    blocked = sorted(gate.blocked_anchors)",
        new="    blocked = []",
        want=f"{_CAT}::test_paragraph_index_is_really_refused_by_the_word_gate",
        wants=(_BYTE_LOCK,),
        why="Word 载体门的 `blocked_anchors` 读空。空清单让「paragraph_index 已被拒」"
            "变成空集恒真 ⇒ paragraph fallback 的替代关系失去唯一真源（AC 7.1）",
    ),
    Mutation(
        id="M22", side="be", path=GEN, kind="replace",
        anchor="    if (site is None) == (absent_reason is None):",
        new="    if False:",
        want=f"{_BIND}::test_binding_helper_rejects_both_and_neither",
        why="「最后调用点」的 XOR 约束被删。🔴 首轮设计时就预判这会是**等价变异**："
            "当前 215 项里没有一项同时填了 site 与 absent_reason，只看记录的话删掉 XOR "
            "也不会有任何判据变红。所以守卫里专门有一条把合成输入喂回实现的自检 —— "
            "教训 11 的正用（把取值来源做成结构判据，而不是删掉这条变异）",
    ),

    # ═══ 五、记录本身被手改 ══════════════════════════════════════════════
    Mutation(
        id="M23", side="be", path=REC, kind="replace",
        anchor='    "verdict": "blocked",',
        new='    "verdict": "open",',
        want=f"{_GATE}::test_verdict_follows_the_checks",
        wants=(
            f"{_GATE}::test_the_gate_is_currently_blocked_for_a_recorded_reason",
            _BYTE_LOCK,
        ),
        why="直接把 rollback 门的裁决手改成放行。记录是 Task 72 Stage B 的输入，"
            "能被手改而守卫不红 ⇒ 整个门形同不存在",
    ),
    Mutation(
        id="M24", side="be", path=REC, kind="replace",
        anchor='    "items_category_paragraph_index_fallback": 2,',
        new='    "items_category_paragraph_index_fallback": 0,',
        want=f"{_CAT}::test_all_seven_categories_are_populated",
        wants=(f"{_COUNT}::test_every_recomputable_counter_matches", _BYTE_LOCK),
        why="把七类之一的计数手改成 0。Task 66 正文第 1 条逐字列了七类，"
            "任一类为 0 就说明该类没清点 —— 计数必须由 items 现算",
    ),
    Mutation(
        id="M25", side="be", path=REC, kind="replace",
        anchor='      "id": "BP-66-1",',
        new='      "id": "BP-1",',
        want=f"{_BP}::test_ids_are_task_scoped",
        wants=(_BYTE_LOCK,),
        why="BP 编号退回全局 `BP-NN`。全局单调编号已被 Tasks 60/61/63/64 各自重复占用、"
            "同号不同义，接回去只会制造第五份冲突（守卫用 "
            "`re.fullmatch(r'BP-66-\\d+')` 锁死）",
    ),
    Mutation(
        id="M26", side="be", path=REC, kind="replace",
        anchor='    "replacement_surface_unreachable_from_production_host": 19,',
        new='    "replacement_surface_unreachable_from_production_host": 0,',
        want=f"{_BP}::test_bp_66_1_and_2_match_the_measured_facts",
        wants=(f"{_COUNT}::test_every_recomputable_counter_matches", _BYTE_LOCK),
        why="把「替代面不可达模块数」手改成 0。这个数字是 BP-66-1 的全部实证，"
            "改成 0 就等于宣称统一 bridge 已经被宿主消费了 —— 而 BP 里列的 18 条路径"
            "还原样挂着（登记与计数必须双向锁死）",
    ),
    Mutation(
        id="M27", side="be", path=GEN, kind="replace",
        anchor='            "status": "UNVERIFIABLE",',
        new='            "status": "VERIFIED",',
        want=f"{_BIND}::test_required_scenario_evidence_is_unverifiable_and_recomputes",
        wants=(_BYTE_LOCK,),
        why="把 required scenario evidence 的状态从 UNVERIFIABLE 改成已验收。"
            "本任务不运行真实 OO 场景、approved bundle 供给实测为 0，"
            "任何「已验收」都是伪造（AC 12.10）；守卫必须同时核**现算**值，"
            "只核记录会让这条变异变成等价变异",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files={
                _T: "Task 66 删前清册守卫（三边锁 / 五绑定 / 五形态唯一归属 / "
                    "rollback 隔离门反事实 / 只生成计划的 AST 判据）",
            },
            repo=REPO,
            description="Task 66 —— legacy 删前清册与 rollback 隔离门守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py",
                "-q",
                "--tb=no",
                "-p",
                "no:randomly",
            ],
        )
    )
