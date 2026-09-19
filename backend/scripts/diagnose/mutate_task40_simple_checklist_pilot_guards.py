# -*- coding: utf-8 -*-
"""Task 40 守卫变异检验 —— 简单 checklist Excel pilot。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 40

覆盖面分母 = 本任务新建的两个守卫文件 + Task 13 被翻转的那一条边界判据。

用法（仓库根）::

    py -3 backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task40_simple_checklist_pilot_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task40-simple-checklist-pilot/mutation_report.json

🔴 改**数据文件**（契约 JSON）的变异一律带 `scope_check`：锚点可能命中别处同形态行，
只看「新增失败集合」会把「改到了别的字段」误报成 GREEN（Task 58 的
`_ledger_row_field_is` 是范式）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PS = "backend/app/services/workpaper_sync/pilot_simple_checklist.py"
RG = "backend/app/services/workpaper_sync/adapters/registry.py"
ROUTER = "backend/app/routers/wp_sync_router.py"
CONTRACT = "backend/data/workpaper_sync_contracts/b60.hour_budget.json"

T40 = "test_task40_simple_checklist_pilot.py"
T40PG = "test_task40_simple_checklist_pilot_pg.py"
T13 = "test_task13_contract_registry.py"

_SEL = f"{T40}::TestFrozenEntrySelection"
_TPL = f"{T40}::TestAuthoritativeTemplate"
_GROUND = f"{T40}::TestContractIsGroundedInTheTemplate"
_DAG = f"{T40}::TestPublishDagIsOneWay"
_PROP = f"{T40}::TestPropertyOracleLanding"
_ORDER = f"{T40}::TestOrderingGate"
_WIRE = f"{T40}::TestProductionWiring"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════


def _rows_field(column_key: str, key: str, expected: str):
    """契约 JSON 的行域字段某个键必须**恰好**是 `expected`（改动落在我关心的结构里）。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for table in payload["sheets"][0]["tables"]:
            for field in table["fields"]:
                if field.get("column_key") == column_key:
                    return field.get(key) == expected
        return False

    return check


def _semantic_version_is(expected: str):
    def check(data: bytes) -> bool:
        return json.loads(data.decode("utf-8")).get("semantic_version") == expected

    return check


MUTATIONS: list[Mutation] = [
    # ── ① 权威模板哨兵（Requirement 9.9）─────────────────────────────
    Mutation(
        id="M01", side="be", path=PS, kind="replace",
        anchor='    "65154146ed3b88a3c2908e064ceb29b6bc73e842559934cbaf2b6893421bd0b0"',
        new='    "65154146ed3b88a3c2908e064ceb29b6bc73e842559934cbaf2b6893421bd0b1"',
        want=f"{_TPL}::test_template_bytes_are_unchanged",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="模板字节哨兵改一位后仍绿 ⇒ 「backend/wp_templates 运行时只读」这条无人把守，"
            "而后面每个 definition digest 都会对着一份错模板算出来",
        tags=("template",),
    ),
    Mutation(
        id="M02", side="be", path=PS, kind="replace",
        anchor="    if digest != TEMPLATE_SHA256:",
        new="    if False and digest != TEMPLATE_SHA256:",
        want=f"{_TPL}::test_template_sentinel_rejects_a_mutated_workbook",
        why="哨兵比对被短路 ⇒ 模板被运行时改写不再抛，静默按新字节继续发布"
            "（fail-open 掩盖接线错误的形态）",
        tags=("template",),
    ),
    # ── ② 选型必要条件（AC 12.1 / Property 49）───────────────────────
    Mutation(
        id="M03", side="be", path=PS, kind="replace",
        anchor='    assessment = assess_pilot_classes(manifest=payload)[PilotClass.simple_checklist]',
        new='    assessment = assess_pilot_classes(manifest=payload)[PilotClass.d2_large_json]',
        want=f"{_SEL}::test_entry_is_frozen_from_the_source_backed_manifest",
        why="pilot 类边界改成 d2 后 entry 不在候选里却仍绿 ⇒ 「类边界由 harness 判定」"
            "退化成本模块自己声明（Property 49 的分母失守）",
        tags=("selection",),
    ),
    Mutation(
        id="M04", side="be", path=PS, kind="replace",
        anchor='    if not entry.get("independent_entry"):',
        new='    if False and not entry.get("independent_entry"):',
        want=f"{_SEL}::test_selection_fails_closed_on_parent_duplicate",
        why="parent_duplicate 不再被拒 ⇒ 44 条重复入口都能拿到自己的 adapter，"
            "同一 OO room 会被两个 adapter 各写一遍（AC 12.1「每个独立 entry」）",
        tags=("selection",),
    ),
    Mutation(
        id="M05", side="be", path=PS, kind="replace",
        anchor="    if codes != set(PILOT_WP_CODES):",
        new="    if False and codes != set(PILOT_WP_CODES):",
        want=f"{_SEL}::test_selection_fails_closed_on_wp_code_drift",
        why="matcher 域与 entry 的 wp_code 不再双向锁死 ⇒ 宿主新增/删掉一个 wp_code 后"
            "matcher 会漏匹配或越界匹配，而 registry 的重叠判据看不出来",
        tags=("selection",),
    ),
    Mutation(
        id="M06", side="be", path=PS, kind="replace",
        anchor="    if not zero_fallback:",
        new="    if False and not zero_fallback:",
        want=f"{_SEL}::test_selection_fails_closed_when_no_template_wp_code_matches",
        why="零回退判据被短路 ⇒ 允许给一个只能回退到父级程序表的 entry 发契约，"
            "source_ref 会指向另一份底稿的单元格（本 spec 已付两次学费的形态）",
        tags=("selection",),
    ),
    # ── ③ 契约 ↔ 源侧双向锁 ─────────────────────────────────────────
    Mutation(
        id="M07", side="be", path=PS, kind="replace",
        anchor='        "semantic_version": "1.0.0",',
        scope="        \"contract_id\": PILOT_ADAPTER_ID,",
        offset=1,
        new='        "semantic_version": "1.0.1",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="源侧 payload 变了而磁盘契约没跟着变仍绿 ⇒ 双向锁失效，"
            "契约里的 digest 可以与真实 definition payload 悄悄脱钩",
        tags=("contract",),
    ),
    Mutation(
        id="M08", side="be", path=CONTRACT, kind="replace",
        anchor='              "source_ref": "源xlsx!B60-1工时预算与控制表!A7",',
        new='              "source_ref": "源xlsx!B60-1工时预算与控制表!A9",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="磁盘契约的 source_ref 被改到别的单元格仍绿 ⇒ 「逐字段有来源」可被事后篡改",
        scope_check=_rows_field("grade", "source_ref", "源xlsx!B60-1工时预算与控制表!A9"),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M09", side="be", path=CONTRACT, kind="replace",
        anchor='              "header_source_ref": "源xlsx!B60-1工时预算与控制表!A5",',
        new='              "header_source_ref": "源xlsx!B60-1工时预算与控制表!A6",',
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="表头依据被改到空格（A6）仍绿 ⇒ 表头比对不是对着权威模板真读，"
            "而是自证式同义反复",
        scope_check=_rows_field(
            "grade", "header_source_ref", "源xlsx!B60-1工时预算与控制表!A6"
        ),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M10", side="be", path=CONTRACT, kind="replace",
        anchor='  "semantic_version": "1.0.0",',
        new='  "semantic_version": "9.9.9",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        why="顶层 semantic_version 被改仍绿 ⇒ 磁盘契约与源侧脱钩（另一侧的同一条锁）",
        scope_check=_semantic_version_is("9.9.9"),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M11", side="be", path=PS, kind="replace",
        anchor='    ("grade", "A", "editable", "text", "A5", "级别"),',
        new='    ("grade", "A", "editable", "text", "A5", "级 别"),',
        want=f"{_GROUND}::test_every_managed_header_matches_the_real_cell_text",
        why="登记的表头文本与权威模板实测不符仍绿 ⇒ 期望值不是从源侧推导的",
        tags=("contract",),
    ),
    Mutation(
        id="M12", side="be", path=PS, kind="replace",
        anchor='    ("budget_cost", "F", "formula", "amount", "F5", "费用预算"),',
        new='    ("budget_cost", "F", "editable", "amount", "F5", "费用预算"),',
        want=f"{_GROUND}::test_formula_column_is_really_a_formula_in_the_template",
        wants=(
            f"{_GROUND}::test_field_counts_are_the_real_template_facts",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="把真公式列声明成 editable 仍绿 ⇒ 受保护格篡改分类（Property 24）在这个 entry 上"
            "整条不生效，OO 侧改 F 列会覆盖公式结果而无人报冲突",
        tags=("contract",),
    ),
    Mutation(
        id="M13", side="be", path=PS, kind="replace",
        anchor='FOOTER_MARKER: Final[str] = "合计"',
        new='FOOTER_MARKER: Final[str] = "总计"',
        want=f"{_GROUND}::test_footer_marker_is_the_real_cell_text",
        wants=(f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",),
        why="footer 标记与权威模板 A24 实测文本不符仍绿 ⇒ footer 定位会找不到锚点，"
            "而 contract 层的形态校验（只查非空）看不出来",
        tags=("contract",),
    ),
    Mutation(
        id="M14", side="be", path=PS, kind="replace",
        anchor='UUID_COL: Final[str] = "J"',
        new='UUID_COL: Final[str] = "H"',
        # 🔴 首轮实测这条写成了 `_TPL::…` = WRONG-TEST：该测试住在
        #    `TestContractIsGroundedInTheTemplate` 而不是 `TestAuthoritativeTemplate`。
        #    `--list` 的 want 可定位性检查只比 nodeid **末段**（方法名），类名写错它查不出来。
        want=f"{_GROUND}::test_uuid_column_sits_right_of_the_managed_business_columns",
        why="隐藏 UUID 列落到受管业务列内仍绿 ⇒ 注入会覆盖可见业务单元格"
            "（Requirement 6.13）",
        tags=("instrumentation",),
    ),
    Mutation(
        id="M15", side="be", path=PS, kind="replace",
        anchor="LAST_DATA_ROW: Final[int] = 23",
        new="LAST_DATA_ROW: Final[int] = 22",
        want=f"{_GROUND}::test_uuid_column_sits_right_of_the_managed_business_columns",
        wants=(
            f"{_GROUND}::test_formula_column_is_really_a_formula_in_the_template",
            f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        ),
        why="数据区末行少一行仍绿 ⇒ 模板留的可增行（第 23 行）被排除在受管区域外，"
            "OO 在那里录入的值永远读不回来",
        tags=("instrumentation",),
    ),
    # ── ④ authority model / 发布 DAG ────────────────────────────────
    Mutation(
        id="M16", side="be", path=PS, kind="replace",
        anchor="AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract",
        new="AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.opaque_single_onlyoffice",
        want=f"{_DAG}::test_authority_model_is_projection_contract",
        wants=(f"{_PROP}::test_field_level_properties_are_not_substituted_away",),
        why="authority model 换成 opaque 后仍绿 ⇒ AC 12.12 的「字段级两场景替换」会被"
            "悄悄触发，Property 25/26 直接从 required set 里消失",
        tags=("authority",),
    ),
    Mutation(
        id="M17", side="be", path=PS, kind="replace",
        anchor='        "template_definition_sha256": canonical_digest(template_payload),',
        new='        "template_definition_sha256": "0" * 63 + "1",',
        want=f"{_GROUND}::test_disk_contract_matches_the_source_of_truth",
        wants=(f"{_DAG}::test_contract_payload_references_both_and_no_bundle",),
        why="契约里的 template digest 不再是真实 payload 的 canonical digest 仍绿 ⇒ "
            "`assert_contract_identity_frozen` 只是在比两个都错的值（单向引用断裂）",
        tags=("dag",),
    ),
    # ── ⑤ 顺序门：finalize 之前不得启用 capability ────────────────────
    Mutation(
        id="M18", side="be", path=PS, kind="replace",
        anchor="    if capability is not Capability.bidirectional:",
        new="    if False and capability is not Capability.bidirectional:",
        want=f"{_ORDER}::test_capability_is_not_enabled_before_finalize",
        why="capability 启用门被短路 ⇒ 可以在没有 published representation 时宣称双向可用，"
            "前端显示不可兑现的切换（Requirement 1.5）",
        tags=("ordering",),
    ),
    Mutation(
        # 🔴 Task 75 重指锚点：欠账 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 已结清，
        #    `raise PilotSelectionError(<欠账>)` 那一行不存在了（原锚点 0 命中 = ANCHOR-MISS）。
        #    判据强度**一字不放宽**：want 仍是同一条测试，变异仍精确构造「函数改成
        #    `return None`」这一**被 Task 75 正文逐字禁止**的中间形态②，只是构造手法从
        #    「把 raise 换成 return None」改为「在观测器调用前插一句 return None」。
        #    用 scope+offset 相对定位（import 行在本文件有 2 处同形），比绝对行号稳。
        id="M19", side="be", path=PS, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want=f"{_WIRE}::test_resolve_published_definitions_never_returns_none",
        why="观测器还没被调用就 `return None` ⇒ 上游把「观测失败」当成「这个 entry 没有身份」，"
            "一路静默走到注册一个没有 identity binding 的 adapter（本 spec 最贵的一类缺陷）",
        tags=("ordering",),
    ),
    Mutation(
        # 🔴 Task 75 补消歧：registry 的交付登记表加了 `provider_module` 键并已收满四条
        #    pilot 行 ⇒ `"adapter_registered": False,` 全文 4 命中，裸锚点必 ANCHOR-MISS。
        #    改 scope+offset 锁到 b60 那一行（scope 唯一 + anchor 逐字校验）。
        id="M20", side="be", path=RG, kind="replace",
        anchor='        "adapter_registered": False,',
        scope='        "contract_id": "b60.hour_budget",',
        offset=8,
        new='        "adapter_registered": True,',
        want=f"{_ORDER}::test_ledger_records_adapter_not_registered_yet",
        why="登记表声称 adapter 已注册而实际没有仍绿 ⇒ 交付登记与事实脱钩，"
            "「契约孤儿」这条可见欠账被账面抹平",
        tags=("ledger",),
    ),
    Mutation(
        id="M21", side="be", path=RG, kind="replace",
        anchor='        "contract_id": "b60.hour_budget",',
        new='        "contract_id": "b60.hour_budget_typo",',
        want=f"{_GROUND}::test_contract_is_registered_in_the_delivery_ledger",
        wants=(
            f"{T13}::TestTask13ScopeBoundary"
            "::test_contract_directory_matches_the_delivery_ledger",
        ),
        why="登记 id 与磁盘契约文件名不符仍绿 ⇒ 契约目录 ↔ 登记表的双向等值失效，"
            "未登记的生产契约可以溜进目录",
        tags=("ledger",),
    ),
    # ── ⑥ 生产接线（非 additive 死代码）────────────────────────────────
    Mutation(
        id="M22", side="be", path=ROUTER, kind="replace",
        anchor="    await _attach_pilot_adapters(svc)",
        new="    _ = _attach_pilot_adapters",
        want=f"{_WIRE}::test_registration_helper_awaits_the_attach",
        why="HTML→OO 的解析入口不再 await 接线 ⇒ pilot adapter 永远不进 registry，"
            "而「函数存在」的判据照样通过（additive 死代码）",
        tags=("wiring",),
    ),
    Mutation(
        id="M23", side="be", path=ROUTER, kind="replace",
        anchor="    await attach_pilot_adapters(registry, session=db)",
        new="    _ = attach_pilot_adapters",
        want=f"{_WIRE}::test_router_calls_attach_pilot_adapters_on_both_paths",
        why="callback 之后的 apply 入口不再接线 ⇒ 「能打开 OO、回写找不到 adapter」的半接线",
        tags=("wiring",),
    ),
    # ── ⑦ 真库侧：发布与 run 判据 ─────────────────────────────────────
    # 🔴 首轮这条写的是 `authority_model=AUTHORITY_MODEL,` →
    #    `AuthorityModel.custom_authoritative_ooxml`，实测 GREEN，而根因是**无效变异**：
    #    `build_bundle_canonical_payload()` 放进 payload 的是
    #    `authority_model: {type: definition, sha256: <authority definition 的 digest>}`，
    #    **不是**那个枚举；枚举只参与 `validate_bundle_slots()` 的分支选择，而
    #    `projection_contract` 与 `custom_authoritative_ooxml` 对「三个 slot 全是 approved
    #    definition」这一形态的判定完全相同 ⇒ 该改动在 digest 与库行上**都不可观测**，
    #    没有任何正确实现能把它抓出来。改成攻击真正进入 digest 的那一项：bundle 声称的
    #    authority 绑定与实际发布的 authority definition 脱钩。
    Mutation(
        id="M24", side="be", path=PS, kind="replace",
        anchor="        authority_model_definition_sha256=authority.sha256,",
        scope="    bundle = await publisher.publish_bundle(",
        offset=3,
        new='        authority_model_definition_sha256="0" * 63 + "1",',
        want=f"{T40PG}::test_bundle_digest_matches_the_canonical_recompute",
        wants=(f"{T40PG}::test_bundle_is_non_null_and_all_children_are_approved",),
        why="bundle canonical payload 里的 authority 绑定被换成别的 digest 仍绿 ⇒ bundle 与它"
            "实际指向的 authority definition 脱钩，历史 operation 的身份解析会取到另一个模型",
        tags=("publish",),
    ),
    Mutation(
        id="M25", side="be", path=PS, kind="replace",
        anchor="        semantic_version=contract.semantic_version,",
        new="        semantic_version=contract.semantic_version, approved=False,",
        want=f"{T40PG}::test_bundle_is_non_null_and_all_children_are_approved",
        wants=(
            f"{T40PG}::test_no_phase_crashed_during_collection",
            f"{T40PG}::test_four_definitions_and_one_bundle_are_published",
        ),
        why="contract child 以 candidate 状态进 bundle 仍绿 ⇒ 未经人工审核的候选契约可以"
            "被 representation 引用（AC 6.19 明令禁止）",
        tags=("publish",),
    ),
    Mutation(
        id="M26", side="be", path=PS, kind="replace",
        anchor="    contract = assert_contract_file_matches_source()",
        scope="async def publish_pilot_definitions(publisher: Any) -> PilotDefinitions:",
        offset=11,
        new="    contract = load_pilot_contract()",
        # 🔴 首轮 want 写的是 `test_disk_contract_matches_the_source_of_truth`，实测 GREEN：
        #    那条判据自己直接调锁，从不看生产路径调的是哪一个 ⇒ 判据与生产路径脱钩。
        #    补了 `test_both_production_paths_go_through_the_bidirectional_contract_lock`
        #    之后才有 oracle（这是**守卫缺陷**，不是生产代码问题）。
        want=f"{_WIRE}::test_both_production_paths_go_through_the_bidirectional_contract_lock",
        why="发布路径改成只读磁盘契约（不比对源侧）⇒ 一份被手改过的契约可以直接发布，"
            "而双向锁只在守卫里被调用（判据与生产路径脱钩）",
        tags=("publish",),
    ),
]

GUARD_FILES = {
    T40: "Task 40 新建（离线：冻结 entry 选型三条件、契约逐字段源侧比对、发布 DAG 单向、"
         "Property oracle 落点、顺序门、生产接线）",
    T40PG: "Task 40 新建（真库：四个 definition + non-null bundle 真发布、24 场景逐条落库、"
           "P25/P26 在本契约上真跑、无真实 OO ⇒ 不得 verified）",
    T13: "Task 13（契约目录 ↔ 交付登记表双向等值：本任务把它从「绝对空清册」翻转成登记锁）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 40 简单 checklist Excel pilot 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task40_simple_checklist_pilot.py",
                "backend/tests/workpaper_sync/test_task40_simple_checklist_pilot_pg.py",
                # 🔴 Task 13 只挑被翻转的那一个类：整文件跑会把并发会话在途的其它红
                #    拖进差集（Task 39 收口时的同一决定）。
                "backend/tests/workpaper_sync/test_task13_contract_registry.py"
                "::TestTask13ScopeBoundary",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=None,
        )
    )
