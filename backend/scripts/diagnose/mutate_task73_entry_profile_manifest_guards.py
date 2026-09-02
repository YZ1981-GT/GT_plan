# -*- coding: utf-8 -*-
"""Task 73 变异检验：manifest 的 source-backed profile 三字段与 RG-15/16/17 真实可达性
的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Task 73（Task 1 欠账收口）
Requirements: 1.2（owner）/ 1.3 / 1.4 / 1.5 / 1.7 / 1.8 / 12.12 / 12.14
Properties: **P3**（未注册 adapter 不得宣称双向）/ **P6**（doc_key 与 mtime 解耦）

═══ 变异改的是**生产代码**，不是守卫 ═══

落点五处：

* `workpaper_sync/entry_source_facts.py` —— 反重言式 AST 判据短路、可达性入边判据
  （`.d.ts` 排除 / 模板标签边 / import 解析）短路、注释剥离短路、端点正则放回跨行、
  doc_key 行为探针降级成静态判定、room service 接线态假阳、observe_room_facts 改成读
  manifest（重言式）、observe_descriptor_facts 改读 capability-tainted flags
* `scripts/gen/generate_workpaper_sync_manifest.py` —— **把 room_model 从 capability 派生
  （核心反重言式变异）**、profile 字段不写进 entry、`_REQUIRED_ENTRY_FIELDS` 缺字段、
  provenance 不进 `profile_source_digest`、复核期望比对短路、可达性↔裁决交叉核对短路、
  反重言式守卫不再被调用
* `workpaper_sync/adapters/registry.py` —— RG-15 不跑、RG-16/17 观察器分支短路、
  漂移不计入报告
* `scripts/check/check_workpaper_sync_closure.py` —— 漂移事实不登记、不传实测观察器
* 前端 `GtOnlyOfficeSheet.vue` —— `readonly` prop 默认值翻成 true（editability 的组件
  侧真源）

判定四态：打红=RED（守卫有效）；不红=GREEN（**守卫缺陷**）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。GREEN 一律当守卫缺陷逐条归因，不降标。

═══ M01 是本任务的核心判据 ═══

「把 `room_model` 从 `capability` 派生」是本任务被反复警告的陷阱：一旦这么做，
`_CAPABILITY_ROOM_MODEL` 与 RG-15/16/17 就变成「用 A 推出 B 再断言 B 与 A 一致」——
恒真、永远发现不了真实漂移（假绿第③源），而且守卫会**永远绿**，比原来的欠账更糟。
M01 就是这条变异，它必须打红 `test_flipping_every_capability_leaves_the_profile_byte_identical`。

═══ 无效变异的三个陷阱（本清单刻意避开）═══

1. **只改「已经是空集」的判据 = 行为不变**。例如把 `room_service_wiring()` 的正则
   改成 `if False`：今天 room service 本来就零调用点，改了还是空集 ⇒ 全绿而这不是守卫
   缺陷。→ M11 改成**反向**注入一个假调用点，让 `room_service_state` 真的翻转。
2. **改只影响磁盘产物的代码，对读磁盘的守卫无效**。本任务大量判据读的是**已生成**的
   `workpaper_sync_entry_manifest.json`；改生成器不会改磁盘文件。所以生成器侧变异的
   `want` 一律指向会重新 `build_manifest(...)` 的那几条判据。
3. **删只在坏输入上生效的防御 = 行为不变**。例如把 `_assert_comment_stripping()` 调用
   删掉：正常源码走下来结果一样。→ M07 直接让 `strip_source_comments` 不剥 HTML 注释，
   逼那条自检真的失败。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task73_entry_profile_manifest_guards.py --list
    python backend/scripts/diagnose/mutate_task73_entry_profile_manifest_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task73_entry_profile_manifest_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/\\
evidence/task73-entry-profile-manifest/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

EF = "backend/app/services/workpaper_sync/entry_source_facts.py"
GEN = "backend/scripts/gen/generate_workpaper_sync_manifest.py"
REG = "backend/app/services/workpaper_sync/adapters/registry.py"
CLOSURE = "backend/scripts/check/check_workpaper_sync_closure.py"
SHEET = "audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue"

T = "test_task73_entry_profile_manifest.py"
C = "test_workpaper_sync_manifest_contract.py"
R = "test_task13_contract_registry.py"

GUARD_FILES = {
    T: "Task 73 新建：profile 三字段 / 反重言式 / RG-15~17 真实可达性 / 闭合门接线",
    C: "Task 1 入口清册契约（本任务补齐三字段进 `_REQUIRED_FIELDS`）",
    R: "Task 13 registry 守卫（本任务改写 missing_profile 不变式的另一半）",
}


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # A. 反重言式（本任务的核心，Requirement 1.2 / RG-15~17 的存在意义）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=GEN, kind="replace",
        anchor="        entry.update(derived.as_entry_fields())",
        new='        entry.update({**derived.as_entry_fields(), "room_model": "none" if capability == "single_html" else "shared"})  # MUT: room_model 改从 capability 派生',
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_flipping_every_capability_leaves_the_profile_byte_identical",
        wants=(
            f"{C}::test_manifest_and_frontend_projection_are_current",
        ),
        why="这就是本任务被反复警告的陷阱：从 capability 派生 room_model 后，"
            "`_CAPABILITY_ROOM_MODEL` 与 RG-15/16/17 变成恒真重言式，守卫从此永远绿，"
            "比原来的欠账更糟（假绿第③源）。是最现实的「让 RG-15 别再报错」的错误改法",
    ),
    Mutation(
        id="M02", side="be", path=EF, kind="replace",
        anchor="            if isinstance(node, ast.Constant) and isinstance(node.value, str):",
        new="            if False:  # MUT: 不再检查推导链路里的业务字段字面量",
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_ast_guard_rejects_a_derivation_that_reads_capability",
        why="反重言式判据的字面量分支被掏空 ⇒ `entry[\"capability\"]` 这种最常见的"
            "重言式写法不再 fail closed。判据靠合成源码双向验证，因此这条能真的打红",
    ),
    Mutation(
        id="M03", side="be", path=EF, kind="replace",
        anchor='            if isinstance(node, ast.Attribute) and node.attr in BUSINESS_ADJUDICATION_KEYS:',
        new="            if False:  # MUT: 不再检查 .capability 属性读取",
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_ast_guard_rejects_a_derivation_that_reads_capability",
        why="属性形态（`host.capability`）与字面量形态是两条独立分支；合成一条时删掉任一"
            "都会被另一条遮蔽 ⇒ 变异判 GREEN。这条证明两个分支各自有判据",
    ),
    Mutation(
        id="M04", side="be", path=EF, kind="replace",
        anchor="                if callee in functions and callee not in visited:",
        new="                if False:  # MUT: 不再做传递闭包",
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_ast_guard_rejects_a_derivation_that_reads_capability",
        why="加一个 `_sneak(host)` helper 再从 derive_* 调用，就能绕过只看直接函数体的"
            "检查。传递闭包是这条门唯一能拦住间接重言式的机制",
    ),
    Mutation(
        id="M05", side="be", path=GEN, kind="replace",
        anchor="        _facts.assert_derivation_ignores_business_adjudication()",
        new="        pass  # MUT: 生成器不再调用反重言式守卫",
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_generator_calls_the_guard_before_deriving",
        why="守卫只剩测试在调 ⇒ 它自己成了 additive 死代码（假绿第①源）。"
            "「新增能力是否真被生产消费」正是本任务要证明的那类判据",
    ),
    Mutation(
        id="M06", side="be", path=EF, kind="replace",
        anchor="    providers = doc_key_providers()",
        # `providers = doc_key_providers()` 在 derive_room_model 与 observe_room_facts 各一处；
        # 用 observe_room_facts 里唯一的「不可达即无 room」return 行做相对定位。
        scope="        return RoomFacts(shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=False)",
        offset=1,
        new='    return RoomFacts(shared_doc_key=str(entry.get("room_model")) == "shared", doc_key_includes_mtime=False, participant_lease=True)  # MUT: 从 manifest 读回裁决',
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_room_observation_ignores_the_manifest_room_model",
        # 原先这里还挂着第二个目标
        # `TestCrossRulesRunAgainstTheRealManifest::test_rg17_exercises_two_distinct_branches_on_real_data`。
        # 那条判据本身要求「真实 manifest 仍然同时命中 mtime 耦合与缺 lease 两条 RG-17
        # 分支」——即要求生产保持破损。Task 21 接线后两条都修好，它被改写成合成事实的
        # 分支存活性判据（`test_rg17_branches_are_alive_under_synthetic_non_conformant_facts`），
        # 不再调用 `observe_room_facts`，因此对本变异**结构性不敏感**。
        # 留着那个 pattern 会变成永不命中的死目标：`matched()` 取 want/wants 并集，
        # 死目标平时无声，等哪天主目标被削弱就直接翻 GREEN 而没人解释得清为什么。
        # 故删掉，不另找替补 —— 主目标 `test_room_observation_ignores_the_manifest_room_model`
        # 正是这条变异要锁的那个属性（把 manifest 裁决读回来当运行时事实）。
        why="RG-17 比的是「冻结的 manifest 裁决 ↔ 运行时真实行为」。把另一侧也改成读 "
            "manifest 后，它退化成自我比对：doc_key 实现漂移（mtime 回归、lease 消失）"
            "永远发现不了",
    ),
    Mutation(
        id="M07", side="be", path=EF, kind="replace",
        anchor='        (legacy.get("ui_characterization") or {}).get("mode_switch_visible")',
        new='        (legacy.get("flags") or {}).get("single_mode_switch_visible")  # MUT: 改读 capability-tainted flag',
        want=f"{T}::TestDerivationIsIndependentOfBusinessAdjudication::"
             "test_descriptor_observation_never_reads_capability_tainted_baseline_flags",
        why="红基线的 `flags.single_mode_switch_visible` = `capability ∈ {single_*} AND "
            "mode_evidence`，已经把 capability 揉进去了；拿它当 descriptor 事实会让 RG-16 "
            "部分重言。行为上两者数量接近（132 vs 176）⇒ 只有结构判据能拦住",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # B. 可达性入边事实（editability=unreachable 的独立来源 · Requirement 1.7）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M08", side="be", path=EF, kind="replace",
        anchor='    if name.endswith(".d.ts"):',
        new="    if False:  # MUT: 把自动生成的全量声明文件也算作入边证据",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_declaration_files_are_not_reachability_evidence",
        wants=(
            f"{T}::TestSourceFactsAreObservedNotAssumed::"
            "test_unreachable_host_is_derived_from_zero_inbound_references",
        ),
        why="`components.d.ts` 由 unplugin 自动生成、提到**每一个**组件 ⇒ 算进入边后"
            "可达性判据恒真，实测过：连 overlay 已裁决的 G6 旧桩都会被判成可达",
    ),
    Mutation(
        id="M09", side="be", path=EF, kind="replace",
        anchor="        hits = {item for item in self.imports.get(host_path, ()) if item != host_path}",
        new="        hits = set()  # MUT: 不再把 import 目标算作入边",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_unreachable_host_is_derived_from_zero_inbound_references",
        wants=(
            f"{C}::test_manifest_and_frontend_projection_are_current",
        ),
        why="🔴 首版这条打在**模板标签**边上，实测 GREEN：当前 185 个宿主 tag-only 为 0"
            "（57 both / 127 import-only），删掉标签边对真实数据行为不变 = 无效变异。"
            "load-bearing 的是 import 边：删掉它 127 个宿主立刻零入边、被判不可达，"
            "editability 批量变 unreachable。标签边的能力另由合成索引判据锁住",
    ),
    Mutation(
        id="M10", side="be", path=EF, kind="replace",
        anchor="            return candidate",
        new="            return None  # MUT: import 说明符一律解析不到目标",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_unreachable_host_is_derived_from_zero_inbound_references",
        wants=(
            f"{C}::test_manifest_and_frontend_projection_are_current",
        ),
        why="🔴 首版把 `if candidate.is_file()` 改成 `if True`，实测 GREEN：`'./GtX.vue'` 的"
            "第一个候选本来就是正确路径，改了也照样命中 = 无效变异。改成解析恒失败才真的"
            "掏空 import 边",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # C. room 身份事实（room_model 的独立来源 · Property 6）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=EF, kind="replace",
        anchor="    hits: list[str] = []",
        scope="    app_root = _BACKEND / \"app\"", offset=-1,
        new='    hits: list[str] = ["backend/app/routers/fake.py#L1"]  # MUT: 假装 room service 已接线',
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_room_service_is_still_unwired_and_reported_as_such",
        why="「尚不可观测」必须是机器可读状态。谎称已接线时 participant_lease 会变 True、"
            "RG-17 的 lease 门失效、`room_service_state` 与 manifest 不符 —— 三处都得打红。"
            "反向（把正则改成 if False）是无效变异：今天本来就是空集",
    ),
    Mutation(
        id="M12", side="be", path=EF, kind="replace",
        anchor="            behavioral = _behavioral_mtime_probe(tree, text, expression)",
        # 🔴 缩进必须与锚点一致（12 空格）：首版写成 4 空格 ⇒ IndentationError ⇒ pytest
        # 直接 `1 error in 1.09s`，四态判定按「新增失败集合为空」判 GREEN（实为 ERROR 态）。
        new="            behavioral = None  # MUT: 放弃真执行探针，只按静态表达式判定",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_doc_key_provider_probe_finds_both_real_routes",
        why="静态看表达式里有没有 `st_mtime` 会被注释/间接 helper 骗过（rooms.py 已记录过"
            "同一个坑）。判据要求 xlsx provider 必须是 `probe_kind == behavioral`",
    ),
    Mutation(
        id="M13", side="be", path=EF, kind="replace",
        anchor='    without_html = re.sub(r"<!--[\\s\\S]*?-->", blank, source)',
        new="    without_html = source  # MUT: 不再剥 HTML 注释",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::test_comment_only_endpoints_are_not_counted",
        why="`GtB60DocxPane.vue` 文件头注释里写着「切到在线编辑前先 GET onlyoffice-config」，"
            "不剥注释会把它当成真实请求端点 ⇒ 该 entry 的 room_model 得到假事实（实测踩过）",
    ),
    Mutation(
        id="M14", side="be", path=EF, kind="replace",
        anchor='    r"""[\'"`]([^\'"`\\n]*onlyoffice-config[^\'"`\\n]*)[\'"`]"""',
        new='    r"""[\'"`]([^\'"`]*onlyoffice-config[^\'"`]*)[\'"`]"""  # MUT: 允许端点字面量跨行',
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::test_endpoint_regex_never_spans_lines",
        why="首版就是这个正则：一对跨 12 行的引号把整段注释吞成「端点」，b60 entry 因此被判"
            "`frontend_endpoint_without_backend_route` ⇒ room_model 假事实。"
            "⚠️ 它的**行为**后果被 `startswith(\"/\")` 过滤器挡住（吞出来的串以 `>` 开头），"
            "所以只能用针对正则本身的判据打红 —— 那个过滤器是纵深防御，单独删它行为不变",
    ),
    Mutation(
        id="M27", side="be", path=EF, kind="replace",
        anchor='    return re.sub(r"(?m)^([ \\t]*)//.*$", r"\\1", without_block)',
        new='    return re.sub(r"(?m)^\\s*//.*$", "", without_block)  # MUT: 行注释吃掉前面的空行',
        want=f"{T}::TestProfileFieldsExistOnEveryEntry::test_provenance_points_at_real_source_lines",
        wants=(
            f"{T}::TestSourceFactsAreObservedNotAssumed::test_comment_only_endpoints_are_not_counted",
            f"{C}::test_manifest_and_frontend_projection_are_current",
        ),
        why="`^\\s*//` 里的 `\\s` 也匹配换行 ⇒ 一串空行 + 一条 `//` 被整段吞掉、行数不守恒"
            "（实测 WorkpaperWordEditor.vue 1365 → 1332 行），provenance 的 `#Lnn` 全部左移"
            "指错行。只断言「文件存在」的判据对此全绿 —— 所以判据必须校验那一行真的含该事实",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # D. 字段真的写进 manifest / digest / 必填集合（Requirement 1.2）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M15", side="be", path=GEN, kind="replace",
        anchor="    \"editability\",",
        new="    # MUT: `editability` 不再是必填字段",
        want=f"{T}::TestGeneratorFailsClosed::"
             "test_required_entry_fields_cover_the_three_profile_fields",
        wants=(
            f"{T}::TestGeneratorFailsClosed::test_a_dropped_profile_field_is_rejected",
        ),
        why="Task 1 的欠账正是这样发生的：字段没进必填集合，于是缺了也没人打红，静默消失",
    ),
    Mutation(
        id="M16", side="be", path=GEN, kind="replace",
        anchor="        missing = _REQUIRED_ENTRY_FIELDS - entry.keys()",
        new="        missing = set()  # MUT: 不再检查必填字段",
        want=f"{T}::TestGeneratorFailsClosed::test_a_dropped_profile_field_is_rejected",
        why="必填集合列全了但检查被短路 = 好看的常量。这条与 M15 是两条独立判据",
    ),
    Mutation(
        id="M17", side="be", path=GEN, kind="replace",
        anchor='            "editability": entry["editability"],',
        new="            # MUT: editability 不进 profile_source_digest",
        want=f"{T}::TestProfileParticipatesInTheManifestDigest::"
             "test_flipping_a_profile_field_changes_both_digests",
        why="Requirement 1.2 要求「source-backed 字段与来源摘要进入 manifest digest」。"
            "字段不进摘要 ⇒ profile 变了 evidence 不会 stale（design 的 stale policy 失效）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # E. overlay 双向锁死与可达性↔裁决交叉核对
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=GEN, kind="replace",
        anchor="        if actual not in approved:",
        new="        if False:  # MUT: 复核期望不再与推导值比对",
        want=f"{T}::TestGeneratorFailsClosed::test_reviewed_expectation_mismatch_is_rejected",
        why="双向锁死的一半：复核过的取值域与源码推导值必须逐条相等。短路后 overlay 变成"
            "一段无人核对的说明文字（AC 1.2 明禁自由文本决定 profile）",
    ),
    Mutation(
        id="M19", side="be", path=GEN, kind="replace",
        anchor="            if stale_values:",
        new="            if False:  # MUT: 不再检测过期的复核取值",
        want=f"{T}::TestGeneratorFailsClosed::test_stale_reviewed_expectation_is_rejected",
        why="双向锁死的另一半：复核过但已无人派生的取值必须打红，否则 overlay 会攒下一堆"
            "描述早已不存在的源码形态的「批准」",
    ),
    Mutation(
        id="M20", side="be", path=GEN, kind="replace",
        anchor="        if bool(unreachable_rule) != (not host_facts.host_reachable):",
        new="        if False:  # MUT: 可达性事实与 reviewed 裁决不再交叉核对",
        want=f"{T}::TestGeneratorFailsClosed::"
             "test_reachability_and_reviewed_unreachable_rule_must_agree",
        why="这条是 `editability=unreachable` 唯一的独立复核：源码入边为 0 ↔ overlay "
            "unreachable_rule 必须同时成立。短路后 Requirement 1.7 的裁决无人交叉验证",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # F. RG-15/16/17 真的跑在真实 manifest 上（本任务要收口的死代码）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M21", side="be", path=REG, kind="replace",
        anchor="                    assert_profile_consistent_with_capability(profile, capability)",
        new="                    pass  # MUT: 报告不再跑 RG-15",
        want=f"{T}::TestCrossRulesRunAgainstTheRealManifest::"
             "test_drift_shrinks_to_the_rg15_layer_under_conformant_facts",
        why="RG-15 只需 manifest 自身字段，是唯一**无条件**能跑在全量真实 entry 上的交叉"
            "判据。不跑它，registry 报告对真实数据又退回零覆盖",
    ),
    Mutation(
        id="M22", side="be", path=REG, kind="replace",
        anchor="                    if facts_observer is not None:",
        new="                    if False:  # MUT: 报告不再消费实测 descriptor/room 事实",
        want=f"{T}::TestCrossRulesRunAgainstTheRealManifest::"
             "test_drift_shrinks_to_the_rg15_layer_under_conformant_facts",
        wants=(
            f"{T}::TestCrossRulesRunAgainstTheRealManifest::"
            "test_report_has_no_missing_profile_and_real_drift",
        ),
        why="这正是本任务要修的欠账形态：RG-16/17 只在手搓 fixture 上跑，对真实 manifest "
            "结构性不可达（假绿第①源）",
    ),
    Mutation(
        id="M23", side="be", path=REG, kind="replace",
        anchor="                    profile_drift.append(entry_id)",
        new="                    pass  # MUT: 漂移被吞掉，不进报告",
        want=f"{T}::TestCrossRulesRunAgainstTheRealManifest::"
             "test_report_has_no_missing_profile_and_real_drift",
        why="算出来了却不上报 = 闭合门永远看不到，Requirement 1.8「可见且阻断」失效",
    ),
    Mutation(
        id="M24", side="be", path=CLOSURE, kind="replace",
        anchor='    "registry_profile_drift",',
        new="    # MUT: 漂移事实不再登记进阻断键",
        want=f"{T}::TestClosureGateConsumesProfileDrift::"
             "test_profile_drift_is_a_registered_blocking_fact",
        wants=(
            f"{R}::TestRegistryReportHasAProductionConsumer::"
            "test_closure_gate_consumes_the_registry_report",
        ),
        why="未登记的事实会被 `evaluate_closure` 判成 unregistered 或干脆不计入阻断总数 ⇒ "
            "142 条真实漂移静默消失",
    ),
    Mutation(
        id="M25", side="be", path=CLOSURE, kind="replace",
        anchor="            contract_ids=available_contract_ids(), facts_observer=observer",
        new="            contract_ids=available_contract_ids()  # MUT: 不传实测观察器",
        want=f"{T}::TestClosureGateConsumesProfileDrift::test_gate_passes_the_live_observer_not_a_stub",
        wants=(
            f"{T}::TestClosureGateConsumesProfileDrift::"
            "test_profile_drift_is_a_registered_blocking_fact",
        ),
        why="唯一的生产消费方不传观察器 ⇒ RG-16/17 在生产路径上仍然是死代码，漂移条数从 "
            "142 掉到 5（只剩 RG-15）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # G. editability 的组件侧真源（前端）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M26", side="be", path=SHEET, kind="replace",
        anchor="  readonly: false,",
        new="  readonly: true,  // MUT: 组件默认改成只读",
        want=f"{T}::TestSourceFactsAreObservedNotAssumed::"
             "test_editability_falls_back_to_the_component_prop_default",
        wants=(
            f"{C}::test_manifest_and_frontend_projection_are_current",
        ),
        why="47 条 entry 的宿主没有传 readonly，其 editability 完全由组件 prop 默认值决定。"
            "翻掉它必须让 manifest 与复核期望同时打红 —— 否则 editability 只是个手填值",
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 73 source-backed entry profile 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task73_entry_profile_manifest.py",
                "backend/tests/test_workpaper_sync_manifest_contract.py",
                "backend/tests/workpaper_sync/test_task13_contract_registry.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=295,
        )
    )
