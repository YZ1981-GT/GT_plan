# -*- coding: utf-8 -*-
"""Task 20 变异检验：writer/version domain 门的**判据机器**被放宽时，守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 20
Requirements: 2.1, 2.2, 2.12, 9.11 · Property 4、Property 61

═══ 本任务的「生产代码」是判据机器 ═══

Task 20 交付的不是业务功能，而是**判断**：清册生成器
（`backend/scripts/gen/generate_workpaper_writer_inventory.py`）与门
（`backend/scripts/check/check_workpaper_writer_revision_gate.py`）。所以变异落在它们身上，
守卫（`backend/tests/**`）保持不动 —— 这与「变异改生产、不改守卫」是同一条规矩。

业务源码侧的注入由 `inject_task20_legacy_version_paths.py` 负责（那条脚本注入旧
`_version`/`file_version`/直接 commit 路径，重生成清册后量门的准则计数）。本脚本只多保留一条
生产注入（M12），用来证明**不重生成**时清册是 fail-closed 的 —— 否则「注入后守卫为什么会红」
这件事就只有一条解释路径。

═══ 判据设计上的一个坑（本任务实测）═══

大部分守卫读的是**磁盘上的清册**。变异生成器后如果不重生成清册，这些守卫看到的还是旧文件 ⇒
GREEN，但那是**脚本缺陷**而不是守卫缺陷。所以每条变异的 `want` 一律指向**合成输入**的守卫
（现场跑 `_resolved_calls_in_test` / `_tests_for` / `build_inventory` / `evaluate_gate`），
只把 `test_inventory_on_disk_matches_the_ast`（源码↔清册新鲜度）放在 `wants` 里作第二证人。

═══ 四态 ═══

RED=守卫有效 · GREEN=守卫缺陷或无效变异（须逐条归因）· WRONG-TEST=红了但不是预期项 ·
ANCHOR-MISS=脚本缺陷（锚点未命中/命中多处）。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task20_writer_gate_guards.py --list
    python backend/scripts/diagnose/mutate_task20_writer_gate_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task20_writer_gate_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task20-writer-gate/mutation_report.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GEN = "backend/scripts/gen/generate_workpaper_writer_inventory.py"
GATE = "backend/scripts/check/check_workpaper_writer_revision_gate.py"
STORAGE = "backend/app/services/wp_storage_service.py"

T20 = "test_task20_writer_gate"
INV = "test_workpaper_writer_inventory"

TASKS_MD = (
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"
)
#: tasks.md「14 条准则的归属」**整行**（M21 的锚点）。行级唯一（实测全文出现 1 次、600 字符）。
#:
#: 🔴 必须逐字整行：`_mutation_kit` 的 `replace` 是行级替换。M21 的 `new` 由本常量
#: `.replace("归属 Task 71：", "归属 Task 30：")` 派生 —— 只让 `multi_resolver` 的**归属数字**
#: 变一个，14 个 key 一个不少，于是 `test_the_gate_evaluates_exactly_the_criteria_the_spec_names`
#: 的 `set(homing) == set(issues)` 仍绿，红只落在被测的那一条上（否则 WRONG-TEST 无从归因）。
HOMING_LINE = (
    "  - **14 条准则的归属**（门的 `has_debt` 就是这 14 条的 `any()`；一条准则从报告里消失与它"
    "归零逐字相同，故守卫双向校验：门里有的 key 必须在本行有归属、本行点名的 key 必须在门里有"
    "实现）。归属 Task 20：`keeps_legacy_write_path_beside_unified_commit`、"
    "`after_save_still_increments_revision`、"
    "`representation_upgrade_increments_business_revision`、"
    "`artifact_snapshot_writer_not_verifiable`、`retired_writer_not_verifiable`、"
    "`missing_required_domain`；归属 Task 74：`unadjudicated_writer`、"
    "`bypasses_unified_commit`、`unadjudicated_resolver`、`writes_legacy_version_field`、"
    "`owns_direct_commit`、`non_canonical_resolver_only`、"
    "`writer_without_characterization_test`；归属 Task 71：`multi_resolver`。"
)

#: 覆盖面分母：Task 20 新建 / 同批搬动的守卫文件。
GUARD_FILES = {
    "test_task20_writer_gate.py":
        "Task 20 新建：characterization 判据必须落在调用点（提及 / 同模块兄弟 / 同名不同接收者 / "
        "打桩字符串四种 false credit 形态）、artifact-snapshot 正面类别（爆炸半径 + 两个扣分项各有"
        "实测代表 + 三条正面义务）、双 revision 准则（legacy 字段 / 自己 bump / 第二事务边界四种注入）、"
        "representation upgrade lane（源码分母非空 + 参与新鲜度契约）、门是否真的评过 Task 20 点名的五条"
        "（原六条，`多 resolver writer` 已移交 Task 30）、移交出去的那一条是否仍被门评估"
        "（键在 + 行为级点名 + 归属与 tasks.md 双向锁死）、以及 §7 的**分母**判据："
        "发现面 = `backend/app` 全部生产模块（独立重算后逐模块比对）、非交付目录排除双向、"
        "两个内容存储都留在分母里、universal scope 的 spec provenance 与「lane 枚举是地板」反证",
    "test_workpaper_writer_inventory.py":
        "Task 3 清册守卫，随 Task 20 同批搬动：bypass 的再推导加入 `artifact_snapshot_only` 项、"
        "bypass 计数算式显式减去具名的快照类别行；`test_inventory_on_disk_matches_the_ast` 在本轮"
        "充当「源码↔清册新鲜度」的第二证人",
}

MUTATIONS: list[Mutation] = [
    # ═══ 一、characterization 判据（Task 19 交接的 fail-open）═════════════════
    Mutation(
        id="M01", side="be", path=GEN, kind="replace",
        anchor="        origin = _receiver_origin(receiver)",
        new="        origin = next(iter(symbol_bindings.values()), None)",
        want=f"{T20}.py::test_a_same_named_call_on_an_unrelated_receiver_credits_nothing",
        wants=(f"{INV}.py::test_inventory_on_disk_matches_the_ast",),
        why="把接收者解析换成「文件里随便一个被导入的符号」⇒ 复现 false credit #2："
            "`session.rollback()` 会被记成 `WpMigrationService.rollback` 的调用点。"
            "只按 leaf 名匹配调用点仍是名称就近，只是名字换了一层",
    ),
    Mutation(
        id="M02", side="be", path=GEN, kind="replace",
        anchor='    return sorted(test_index.get(f"{module}::{qualname}", []))',
        new='    return sorted({f for k, v in test_index.items()'
            ' if k.startswith(f"{module}::") for f in v})',
        want=f"{T20}.py::test_a_sibling_in_the_same_module_is_not_credited",
        wants=(f"{INV}.py::test_inventory_on_disk_matches_the_ast",),
        why="把取证退回「同模块任一 key 命中」⇒ 复现 false credit #1：一条只调用 "
            "`save_version` 的守卫会连没被碰过的 `list_versions` 一起点亮",
    ),
    Mutation(
        id="M03", side="be", path=GEN, kind="insert",
        anchor="    invoked: set[str] = set()",
        new="    invoked.update(f\"{m}::{s}\" for m, s in symbol_bindings.values())\n",
        want=f"{T20}.py::test_a_mention_without_a_call_site_credits_nothing",
        wants=(f"{INV}.py::test_inventory_on_disk_matches_the_ast",),
        why="把「导入即算证据」加回去 ⇒ 提及/导入不再需要调用点。这是旧谓词最宽的那一档，"
            "也是「有测试」这条证据能被 import 一行伪造的形态",
    ),
    Mutation(
        id="M04", side="be", path=GEN, kind="insert",
        anchor="        if isinstance(node, ast.Import):",
        new="            module_bindings.update({a.name: a.name for a in node.names})\n",
        want="*",
        why="对照组（**预期无效变异**）：`ast.Import` 分支本来就登记了同样的绑定，这条只是把"
            "它重写一遍。它存在的意义是证明判定不是「改任何一行都红」—— 报告里它应当 GREEN，"
            "且归因为无效变异而非守卫缺陷",
    ),
    # ═══ 二、artifact-snapshot 正面类别 ═══════════════════════════════════════
    Mutation(
        id="M05", side="be", path=GEN, kind="replace",
        anchor='            and all(item["target"] == "snapshot" for item in artifact_targets)',
        new='            and any(item["target"] == "snapshot" for item in artifact_targets)',
        want=f"{T20}.py::test_one_authoritative_write_removes_the_category",
        why="`all` → `any`：只要有**一次**快照写就给类别 ⇒ 一个同时改写权威 artifact 的 writer "
            "也能靠「顺手存了个备份」离开门。这正是类别最容易被放宽成豁免的那一步",
    ),
    Mutation(
        id="M06", side="be", path=GEN, kind="replace",
        anchor="            and not writes_business_content",
        new="            and writes_business_content is not None",
        want=f"{T20}.py::test_the_snapshot_category_is_exactly_the_snapshot_destination_writers",
        wants=(
            f"{T20}.py::test_writers_that_also_snapshot_do_not_get_the_category",
            f"{T20}.py::test_a_snapshot_writer_that_invents_a_version_blocks_again",
            f"{INV}.py::test_inventory_on_disk_matches_the_ast",
        ),
        why="去掉「零业务内容」这一项 ⇒ `save_univer_data`（artifact 写全落 `.versions/`，"
            "但同时推进 `file_version` 并写 `working_paper`）会拿到类别、离开门。首轮此条判"
            "WRONG-TEST，归因是**判据缺陷**而非脚本缺陷：两条清册级判据当时读的是**磁盘**上的"
            "清册，而变异只改生成器、不重生成 ⇒ 它们看到的还是旧文件。现已改读 `regenerated`"
            "（现场从源码推导），本条因此能直接命中爆炸半径判据",
    ),
    Mutation(
        id="M07", side="be", path=GEN, kind="replace",
        anchor="                    and not artifact_snapshot_only",
        new="                    and artifact_snapshot_only is not None",
        want=f"{T20}.py::test_one_authoritative_write_removes_the_category",
        wants=(f"{INV}.py::test_inventory_on_disk_matches_the_ast",),
        why="让类别不再影响 bypass 派生 ⇒ 快照行重新被记成「绕过统一 commit」。方向相反的"
            "falsifier：证明类别**确实**在改判据结果，而不是一个装饰性的布尔",
    ),
    Mutation(
        id="M08", side="be", path=GATE, kind="replace",
        anchor='                or "content_revision" not in version_reads',
        new="                or False",
        want=f"{T20}.py::test_the_snapshot_writer_carries_its_own_positive_obligations",
        why="拿掉「快照名必须跟随统一计数器」这条正面义务 ⇒ 一个把快照名改回 `file_version` 的"
            "writer 仍算合格。类别一旦没有可打红的义务，就退化成豁免",
    ),
    # ═══ 三、双 revision（Task 20 点名的注入形态）═════════════════════════════
    Mutation(
        id="M09", side="be", path=GEN, kind="replace",
        anchor='                        or facts["commit_receivers"]',
        new="                        or False",
        want=f"{T20}.py::test_a_private_write_path_beside_the_unified_commit_is_reported",
        why="把「第二个事务边界」从双 revision 准则里去掉 ⇒ 注入一个裸 `db.commit()` 不再打红。"
            "它既不写 legacy 字段也不写 content_revision，是三种注入里唯一只能靠 commit 事实"
            "抓到的一种（Requirement 2.4 / 13.1）",
    ),
    Mutation(
        id="M10", side="be", path=GATE, kind="replace",
        anchor="    if not unified_commit_writers:",
        new="    if False:",
        want=f"{T20}.py::test_the_double_revision_criterion_has_a_real_denominator",
        why="拿掉空分母拒绝 ⇒ 「零个 writer 经过统一入口」时这条准则恒为零、报绿。恒真的准则"
            "比没有准则更糟：它在报告里长得和「已经清零」一样",
    ),
    # ═══ 四、representation upgrade lane ═════════════════════════════════════
    Mutation(
        id="M11", side="be", path=GATE, kind="replace",
        anchor="    if not isinstance(lane, list) or not lane:",
        new="    if False:",
        want=f"{T20}.py::test_an_empty_upgrade_lane_is_refused_not_reported_green",
        why="同上，另一条空分母：升级器一旦从发现面消失（改名/换 marker），Property 4 的"
            "「纯表示升级不得增业务 revision」就在空集上评估",
    ),
    Mutation(
        id="M12", side="be", path=GATE, kind="replace",
        anchor='    if expected["representation_upgrade_lane"] != stored_lane:',
        new="    if False:",
        want=f"{T20}.py::test_the_lane_is_part_of_the_freshness_contract",
        why="拿掉 lane 的新鲜度比对 ⇒ 手改 lane（或升级器的版本事实漂移）后门照旧评估。"
            "lane 不在 `entries` 里，没有这条比对它就完全不受源码约束",
    ),
    Mutation(
        id="M13", side="be", path=GATE, kind="delete",
        anchor='        "representation_upgrade_increments_business_revision": [],',
        want=f"{T20}.py::test_the_gate_evaluates_exactly_the_criteria_the_spec_names",
        why="删掉一条准则的 key ⇒ 报告里它「消失」而不是「为零」。Task 20 正文点名五条，"
            "门少评一条与「评过且为零」在输出里无法区分，这就是最省事的一种造绿。"
            "🔴 2026-09-02（Task 74 复跑）修 `want`：该判据在 Task 30 的移交整改里改名为 "
            "`test_the_gate_evaluates_exactly_the_criteria_the_spec_names`，而这里仍写着旧名 "
            "`..._every_criterion_task20_names` ⇒ 判定报 **WRONG-TEST**（实际打红的正是改名后的"
            "那条，见 `mutation_task20_rerun.json` 的 `added`）。**脚本缺陷、非守卫缺陷**：`want` "
            "过期会把一条真 RED 误报成 WRONG-TEST，也会在真出问题时误报成 GREEN",
    ),
    Mutation(
        id="M15", side="be", path=GATE, kind="replace",
        anchor='        if verdicts.get("multi_resolver"):',
        new="        if False:",
        want=f"{T20}.py::test_the_gate_still_evaluates_the_relocated_criterion",
        wants=(f"{T20}.py::test_the_gate_names_exactly_the_rows_the_owner_must_clear",),
        why="`多 resolver writer=0` 已从 Task 20 移交给 Task 30、再由 Task 30 移交给 Task 71"
            "（两跳的成环理由见 tasks.md），门必须"
            "**继续算** `multi_resolver` —— 当前归属方靠它验零。这条把判定短路成 `if False`：key "
            "还在、计数恒为零，报告与「已清零」逐字相同，M13 那种「键是否存在」的判据抓不到。"
            "所以移交侧的守卫必须是行为级的（喂一条真的多 resolver 行看它被点名），"
            "「移交」才不会静默变成「无人守」",
    ),
    # ═══ 五、分母（scope）本身 ═══════════════════════════════════════════════
    #
    # 关掉 Task 20 最便宜的假路径是把**分母**改小：只算 Task 3 正文点名的那几个 lane，其余
    # 宣布「不在范围内」，`unadjudicated_writer` 与 `bypasses_unified_commit` 当场归零，而门的
    # 输出和真的迁完一模一样。这四条各自演一次收窄手法。
    Mutation(
        id="M16", side="be", path=GEN, kind="replace",
        anchor='_APP_ROOT = _REPO / "backend" / "app"',
        new='_APP_ROOT = _REPO / "backend" / "app" / "routers"',
        want=f"{T20}.py::test_the_writer_denominator_is_every_production_module_under_backend_app",
        why="把发现面收窄到单个包 ⇒ services 侧的 writer 整批离开分母。这是「改小分母」最直接"
            "的一刀，且改完清册照旧能生成、门照旧能跑，只是数字变小",
    ),
    Mutation(
        id="M17", side="be", path=GEN, kind="replace",
        anchor='    return not ({"tests", "test", "__pycache__", "migrations"} & parts)',
        new='    return not ({"tests", "test", "__pycache__", "migrations", "routers"} & parts)',
        want=f"{T20}.py::test_the_production_source_predicate_excludes_exactly_the_non_shipping_trees",
        wants=(
            f"{T20}.py::test_the_writer_denominator_is_every_production_module_under_backend_app",
        ),
        why="给「非交付目录」排除表加一个**业务**包 ⇒ 同样是把生产 writer 移出分母，但伪装成"
            "一条看起来无害的排除规则。判据必须双向断言（该挡的挡住 + 不该挡的没挡），"
            "只断言前者时这条会 GREEN",
    ),
    Mutation(
        id="M18", side="be", path=GEN, kind="delete",
        anchor='    "checklist_responses": frozenset({"remark", "conclusion"}),',
        want=f"{T20}.py::test_both_workpaper_content_stores_stay_in_the_denominator",
        wants=(f"{INV}.py::test_two_content_stores_hold_workpaper_business_content",),
        why="删掉第二个内容存储 ⇒ 97 行写 `checklist_responses.remark/conclusion` 的 writer "
            "一次性离开分母。Requirement 9.11 点名的「第二权威」正是这张没有版本列的表，"
            "把它从内容存储表里拿掉等于把该 AC 的实证面删掉",
    ),
    Mutation(
        id="M19", side="be", path=GATE, kind="insert",
        anchor='    "html_save",',
        new='    "template_provisioning",\n'
            '    "checklist_response_store",\n'
            '    "unified_commit_substrate",\n'
            '    "read_only_evaluation",\n',
        want=f"{T20}.py::test_the_universal_scope_is_the_specs_own_definition_not_this_files",
        why="把 overlay 里**所有**落在门必需集之外的 lane 一次收进 `_REQUIRED_DOMAINS` ⇒ 「裁决"
            "越过了正文枚举」这条反证消失（`adjudicated - required` 变空），窄读法就再没有实证"
            "反驳了。它不改任何计数，只抹掉**反驳窄读法的那条证据** —— 这类变异最难察觉。"
            "🔴 2026-09-02（Task 74 复跑）扩写：原变异只加 `template_provisioning`，那是 Task 3 "
            "时代**唯一**的越界 lane；Task 74 裁决 270 行后又多了 `checklist_response_store` / "
            "`unified_commit_substrate` / `read_only_evaluation` 三个证人 ⇒ 只抹一个证人已经不能"
            "让判据变空，实测转 **GREEN**（无效变异，非守卫缺陷）。四个一起加才恢复成真 falsifier",
    ),
    Mutation(
        id="M20", side="be",
        path=".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/design.md",
        kind="replace",
        anchor="### Property 61: 所有 writer 进入唯一 revision 域",
        new="### Property 61: 清册内 writer 进入唯一 revision 域",
        want=f"{T20}.py::test_the_universal_scope_is_the_specs_own_definition_not_this_files",
        why="直接改 spec 原话，把「所有 writer」换成自指的「清册内 writer」（窄读法的落脚点）。"
            "provenance 判据存在的意义就是让收窄 scope 这个动作**必须先改 spec** ⇒ 浮到人面前。"
            "标题仍是 `### Property 61:` 形态，所以不是靠格式校验红的",
    ),
    # ═══ 六、生产注入 → 清册 fail-closed ═════════════════════════════════════
    Mutation(
        id="M14", side="be", path=STORAGE, kind="insert",
        anchor="        shutil.copy2(str(file_path), str(version_path))",
        new="        wp.file_version = int(wp.file_version or 0) + 1\n",
        want=f"{INV}.py::test_inventory_on_disk_matches_the_ast",
        wants=(f"{T20}.py::test_the_snapshot_category_is_exactly_the_snapshot_destination_writers",),
        why="往已迁移的快照 writer 里注入旧 `file_version` 计数器，且**不**重生成清册 ⇒ 证明"
            "「源码动了清册没跟上」是 fail-closed 的，同时让重新推导出的清册丢掉快照类别。"
            "初版锚在 `wp_html_save.py` 的 `try:` 行上，插入落进 try 块内层缩进 ⇒ 源码"
            "SyntaxError ⇒ 生成器直接抛、守卫全变 ERROR 而不是 FAIL（首轮 WRONG-TEST 的"
            "真因，是**脚本缺陷**）。改锚到一条同缩进的独立语句后成立。门的准则侧证据由 "
            "`inject_task20_legacy_version_paths.py` 给（那条会重生成后量准则计数）",
    ),
    # ═══ 七、准则归属的**两套派生**必须互锁 ═══════════════════════════════════
    Mutation(
        id="M21", side="be", path=TASKS_MD, kind="replace",
        anchor=HOMING_LINE,
        new=HOMING_LINE.replace("归属 Task 71：", "归属 Task 30："),
        want=f"{T20}.py::test_the_criteria_homing_agrees_with_tasks_md",
        why="把全量归属行里 `multi_resolver` 的归属从 Task 71 改成 Task 30（14 个 key 一个不少，"
            "只动一个数字）⇒ tasks.md 对「谁负责清零」给出两个各自自洽的答案：**全量归属行**"
            "（当前状态）说 30，**显式交接语**（`已移交/自 Task N 移交至本门`，交接事件）推出 71。"
            "两套派生此前从未互相核对过 —— `_gate_criteria_homing_from_tasks_md()` 的 docstring "
            "写着「两者在同一个 key 上不一致即红（见 test_the_criteria_homing_agrees_with_tasks_md）」，"
            "而那条判据里根本没调用它，承诺是空的。本变异证明补上的那条断言承重。"
            "🔴 它替代的是旧判据 `key not in set(_TASK20_CRITERIA.values())`：那条用「从基线里"
            "消失」冒充「换了归属」，与 fail-open 同形，且在准则表从 5 条扩到 14 条（`multi_resolver` "
            "必须留在冻结基线里报出实测计数 4）之后自相矛盾、恒红",
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 20 writer/version domain 门判据变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task20_writer_gate.py",
                "backend/tests/test_workpaper_writer_inventory.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            # 53 → 56：`多 resolver writer` 从 Task 20 移交至 Task 30 时，
            # `test_task20_writer_gate.py` 新增 3 条判据（门仍评估被移交的准则、门报出的行
            # 与 Task 30 点名的 4 行一致、准则归属与 tasks.md 双向锁死）。
            # 56 → 60：§7 新增 4 条**分母**判据（发现面逐模块比对、非交付目录排除双向、
            # 两个内容存储留在分母、universal scope provenance + 「枚举是地板」反证）。实测
            # `pytest <两个守卫文件> -q --tb=no -rf -p no:randomly` = 60 passed。
            #
            # 60 → 71（2026-08-31 修正）：60 这个值早已与实测不符，每跑一次变异都报一条
            # `[WARN] 后端基线 passed 数与冻结值不符` —— 那种长期 WARN 会训练人忽略 WARN，
            # 与「假绿」同源。来源是**准则表 5 → 14 条的扩容那一轮**：`_TASK20_CRITERIA` 从 5
            # 条扩到 14 条后，`test_task20_writer_gate.py` 里按准则参数化的判据（逐准则归属、
            # 门是否真评估该准则、与 tasks.md 双向锁死）随分母一起长了 11 条，而本常量没跟。
            # 实测（仓库根，`.\\.venv\\Scripts\\python.exe -m pytest <两个守卫文件> -q --tb=no
            # -rf -p no:randomly`）收集 71 条：`2 failed, 69 passed`。那 2 条红
            # （`test_the_lane_is_part_of_the_freshness_contract`、
            # `test_inventory_on_disk_matches_the_ast`）是并发会话在途改动造成的，不属本脚本
            # 的判据面 —— 基线非空时 kit 会直接 ABORT（`allow_dirty_baseline` 未开），所以本
            # 常量记的是**全绿时的 passed 数 = 收集总数 71**，等那 2 条红被其 owner 修掉后
            # 基线自然对上。
            baseline_backend_passed=71,
        )
    )
