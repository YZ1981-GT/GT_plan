r"""Task 75 变异检验 —— published-identity 观测器与 manifest 驱动注册的守卫强度。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 75
被检验的守卫：``backend/tests/workpaper_sync/test_task75_published_identity_observer.py``
（另含四个 pilot 守卫里被本轮改写的那几条）

## 为什么每条变异都不是无效变异

本轮的两类最贵缺陷各自都有对应变异：

1. **fail-open / fail-closed 掩盖接线错误** —— 把观测器的某条 ERROR 判据改成 `return` /
   宽泛 `except` / 悄悄取空，守卫必须打红（M01~M09、M14~M16）；
2. **additive 死代码** —— 把新加的能力（binding 派生、注册计划、路由接线）短路成「加了但
   没人消费」，守卫必须打红（M10~M13、M17~M20）。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task75_published_identity_observer_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task75_published_identity_observer_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task75_published_identity_observer_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

OBS = "backend/app/services/workpaper_sync/published_identity_observer.py"
REG = "backend/app/services/workpaper_sync/adapters/registry.py"
ROUTER = "backend/app/routers/wp_sync_router.py"
P_B60 = "backend/app/services/workpaper_sync/pilot_simple_checklist.py"
P_G7 = "backend/app/services/workpaper_sync/pilot_g7_two_level_dynamic.py"
P_D2 = "backend/app/services/workpaper_sync/pilot_d2_large_json.py"
P_H1 = "backend/app/services/workpaper_sync/pilot_h1_grouped_dynamic.py"
GATE44 = "backend/scripts/check/check_task44_oo94_excel_pilot_gate.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 写成带
#: `backend/tests/...` 前缀的全路径会让「实际打红的正是预期那条」被判 WRONG-TEST
#: （首轮 M01/M02/M04 实测踩到）。
_T = "test_task75_published_identity_observer.py"
_SELF = f"{_T}::TestGuardSelfChecks"
_STRUCT = f"{_T}::TestObserverStructure"
_DEBT = f"{_T}::TestDebtRemovedWithRealImpl"
_REGT = f"{_T}::TestManifestRegistrar"
_RUN = f"{_T}::TestNonEmptyRunOnRealSupply"
_PROP = f"{_T}::TestProperties"

MUTATIONS: list[Mutation] = [
    # ═══ 观测器：ERROR 态不得降级（AC 5.12）═════════════════════════════════
    Mutation(
        id="M01", side="be", path=OBS, kind="replace",
        anchor='        if pointer != rep["id"]:',
        new='        if False:',
        want=f"{_RUN}::test_non_current_representation_is_refused",
        wants=(f"{_STRUCT}::test_every_stage_carries_a_reachable_error_path",),
        why="non-current published generation 被静默放行 ⇒ candidate/旧 generation 会成为运行态"
            "substrate（AC 6.18 / Property 67）。不能只删 if：删 if 会让 pointer 判据整段消失，"
            "而本条要测的是「判断成立却不抛」这一形态",
    ),
    Mutation(
        id="M02", side="be", path=OBS, kind="replace",
        anchor='        if observed["structure_hash"] != str(rep["structure_hash"]).strip():',
        new='        if False:',
        want=f"{_RUN}::test_drift_is_an_error_not_a_silent_empty",
        why="受管结构漂移后仍按旧坐标写格（Requirement 6.10 / Property 28）。这条是观测器"
            "唯一把「重算 vs 冻结」变成可 falsify 的判据，短路它 = 整个物理观测退化成装饰",
    ),
    Mutation(
        id="M03", side="be", path=OBS, kind="replace",
        anchor="        if observed != str(resolution.artifact_sha256).strip():",
        new="        if False:",
        want=f"{_RUN}::test_tampered_artifact_bytes_are_refused",
        wants=(f"{_RUN}::test_no_phase_crashed",),
        why="published artifact 字节被改写后仍按旧身份解析 ⇒ immutable representation 的内容"
            "身份失守；改 if 而不是删 raise，因为要测的是「不再比 digest」这一形态",
    ),
    Mutation(
        id="M04", side="be", path=OBS, kind="replace",
        anchor="        except OSError as exc:",
        new="        except Exception as exc:  # noqa: BLE001",
        want=f"{_STRUCT}::test_observer_has_no_broad_except_fail_open",
        why="宽泛 `except Exception` 会把「函数名/列名拼错、单参调用 async、传错客户端形态」"
            "全吞成一条 artifact 读取失败（AC 5.12 逐字禁止）",
    ),
    Mutation(
        id="M05", side="be", path=OBS, kind="replace",
        anchor="        if fingerprint.errors:",
        new="        if False:",
        want=f"{_RUN}::test_collection_errors_block_half_baked_facts",
        why="结构采集有错却按半份事实组装 adapter ⇒ 「本项目无此数据」式静默取空",
    ),
    Mutation(
        id="M07", side="be", path=OBS, kind="replace",
        anchor="        if pointer is None:",
        new="        if False:",
        want=f"{_RUN}::test_missing_entry_pointer_is_refused",
        why="🔴 首轮此编号打的是「bundle digest 重复比对」，实测 GREEN —— 那条判据已由 "
            "`CanonicalResolutionService.resolve` 第 ⑤ 步承担（抄一份必 GREEN），故生产侧"
            "删除了重复，本编号**重写**为「entry pointer 整行缺失」这条**独有**判据："
            "短路它 ⇒ 还没 finalize 的 entry 会被编出一份身份（AC 6.18 / Property 67）",
    ),
    Mutation(
        id="M08", side="be", path=OBS, kind="replace",
        anchor="        if bundle.authority_model is not AuthorityModel.projection_contract:",
        new="        if False:",
        # 🔴 want 重指：原先指向 `test_every_stage_carries_a_reachable_error_path`，
        #    那是**结构**判据（每个 stage 有可达 error path），短路 `if` 不会删掉 `raise`
        #    ⇒ 它照样绿，实测判 GREEN。而真实供给里 authority model 恒 projection_contract，
        #    这条分支一次都没被执行过。现改指对生产方法本体喂非 projection authority 的
        #    行为判据（判据强度是**加强**：从「有 raise 语句」变成「真抛且点名」）。
        want=f"{_STRUCT}::test_non_projection_authority_model_is_refused",
        why="custom/opaque authority model 混进标准 Excel 通道 ⇒ AC 3.3 的 authority 不匹配"
            "阻断被绕过",
    ),
    Mutation(
        id="M09", side="be", path=OBS, kind="replace",
        anchor="        if contract_child.state != DefinitionState.approved.value:",
        new="        if False:",
        # 🔴 want 重指（同 M08）：结构判据短路 `if` 也不会红；真实供给里 contract child 恒
        #    approved，库里又有 append-only CHECK 禁止 `approved→candidate`（实测），
        #    故行为判据只能对 `_load_frozen_children` 本体喂非 approved 的 child row。
        want=f"{_STRUCT}::test_unapproved_contract_child_is_refused",
        why="generator 候选 contract 被当已审核契约放行（AC 12.1 明令：projection-based entry "
            "缺 approved per-entry contract 不得进入 bidirectional 验收）",
    ),

    # ═══ 观测器：物理派生不得退化成抄声明（假绿第③源）════════════════════════
    Mutation(
        id="M10", side="be", path=OBS, kind="replace",
        anchor="                if row > max_row or _column_index(column) > max_col:",
        new="                if False:",
        # 🔴 want 重指：G7 权威模板**物理上覆盖了全部 107 项声明字段** ⇒ 在真实供给上短路
        #    外延过滤一个字都不变，`test_physical_structure_matches_the_declared_inventory`
        #    恒绿（实测 GREEN）。要证明「实测清册不是把声明抄一遍」，判据必须用**物理外延
        #    小于声明**的指纹，那条判据在 `TestObserverStructure` 里。
        want=f"{_STRUCT}::test_structure_inventory_is_filtered_by_physical_extent",
        why="不再核对物理外延 ⇒ 实测清册退化成「把契约声明抄一遍」，与 declared 恒相等 ⇒ "
            "结构漂移永远测不出来（假绿第③源：自我比对）",
    ),
    Mutation(
        id="M11", side="be", path=OBS, kind="replace",
        anchor="            keys = dynamic_column_stable_keys(slot=table.table_key, count=len(span))",
        new="            keys = tuple(f\"{table.table_key}_{label}\" for label in labels)",
        want=f"{_RUN}::test_identity_binding_is_produced_by_the_observer",
        wants=(f"{_RUN}::test_no_phase_crashed",),
        why="动态列 key 改成由**可改 label** 派生 ⇒ 公司改名就换 key、两家同名撞键"
            "（Property 22 / 平台 H7 已付学费）",
    ),
    Mutation(
        id="M12", side="be", path=OBS, kind="replace",
        anchor="        if len(row_tables) != 1:",
        new="        if False:",
        # 🔴 want 重指：真实契约恰好声明 1 张 row_identity 表 ⇒ 「不唯一」这条分支在真实供给
        #    上永不执行，实测 GREEN。行为判据改为对 `_build_identity_binding` 本体喂
        #    0 / 2 / 3 张的契约形态。
        want=f"{_STRUCT}::test_row_identity_table_must_be_unique",
        why="row_identity 表不唯一时随手挑第一张 ⇒ 隐藏 UUID 列绑到另一张表，受管格整体错位"
            "而没有任何报错（BP-17 同类：接线错误静默）",
    ),
    Mutation(
        id="M13", side="be", path=OBS, kind="replace",
        anchor="                spread[f\"{_letters(col)}{row}\"] = values[anchor]",
        new="                pass",
        # 🔴 want 重指：merge 铺开只影响 label 文本，真实供给里没有任何判据直接看它
        #    ⇒ 实测 GREEN。行为判据改为直接测这个纯函数（含「没 merge 时不铺」的反向自检）。
        want=f"{_STRUCT}::test_merged_header_values_are_spread_over_the_whole_range",
        why="不把 merge 左上角的值铺开 ⇒ 横向分组表头第 2..N 列的 label 全读成空，"
            "「改名不改 key」这条 Property 22 判据失去观测对象",
    ),

    # ═══ pilot：欠账真删 + 真实现真接（任务正文第二条的两种中间形态）═══════════
    Mutation(
        # 🔴 首版锚在 `attach_pilot_adapters` 里那句 **调用**上（`observation = await
        #    resolve_published_frozen_definitions(` ，4 空格缩进），`insert` 把 raise 塞进了
        #    调用的实参列表 ⇒ 产出的是 **SyntaxError**。它当时判 RED 纯属巧合：pytest 只跑一个
        #    文件时收集错误被摘成了逐条失败名，恰好含 want。扩到 6 个文件后 pytest 报
        #    「1 error in 2.03s」、失败名集合为空 ⇒ 立刻暴露成 GREEN。
        #    这是**脚本缺陷**（无效变异），不是守卫缺陷。改锚到
        #    `resolve_published_frozen_definitions` **函数体首行**，产出语法合法的中间形态①。
        id="M14", side="be", path=P_B60, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new='    raise PilotSelectionError("观测器仍未实现（合成中间形态①）")',
        want=f"{_DEBT}::test_no_pilot_still_raises_unconditionally",
        why="🔴 中间形态①：欠账登记已删而函数仍无条件 fail closed —— 任务正文明令要有一条"
            "打红判据",
    ),
    Mutation(
        id="M15", side="be", path=P_B60, kind="replace",
        anchor="    return observation",
        new="    return None  # type: ignore[return-value]",
        want=f"{_DEBT}::test_no_pilot_returns_none_or_empty_identity",
        why="🔴 中间形态②：欠账登记已删而函数改成 `return None` ⇒ 上游把「观测失败」表现成"
            "「这个 entry 没有身份」，一路静默走到「注册一个没有 identity binding 的 adapter」",
    ),
    Mutation(
        id="M16", side="be", path=P_G7, kind="replace",
        anchor="    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:",
        new="    if False:",
        want=f"{_DEBT}::test_pilot_consumes_the_contract_argument",
        why="`contract` 入参退化成摆设 ⇒ 观测器按冻结 adapter_id 读出的契约与本模块 "
            "source-locked 的那一份脱钩时无人拦（additive 死代码形态）",
    ),
    Mutation(
        id="M17", side="be", path=P_G7, kind="replace",
        anchor="            binding=observation.identity_binding,",
        new="            binding=definitions.identity_binding,",
        want=f"{_RUN}::test_registration_really_happens_when_both_links_are_in_place",
        wants=(f"{_RUN}::test_no_phase_crashed",),
        why="🔴 BP-17 的回归变异：`FrozenEntryDefinitions` 没有 `identity_binding` 字段 ⇒ "
            "退回原写法必 AttributeError。它当年没暴露只因为该行永不可达",
    ),

    # ═══ registry：注册计划不得是空壳、不得静默跳过 ═══════════════════════════
    Mutation(
        id="M18", side="be", path=REG, kind="replace",
        anchor="    registry.bind_registration_plan(",
        new="    return registry\n    registry.bind_registration_plan(",
        want=f"{_REGT}::test_build_production_registry_is_no_longer_an_empty_shell",
        why="退回 Task 75 之前的空壳形态（只 `return WorkpaperSyncAdapterRegistry()`，注册哪些"
            "entry 由每个调用方各拼一遍 attach）",
    ),
    Mutation(
        id="M19", side="be", path=REG, kind="replace",
        anchor="                reasons[item.entry_id] = supply",
        new="                pass",
        want=f"{_REGT}::test_registration_outcome_accounting_is_closed",
        wants=(
            f"{_RUN}::test_supply_alone_is_not_enough_and_the_reason_says_so",
            f"{_REGT}::test_every_unregisterable_entry_carries_an_explicit_reason",
        ),
        why="供给不足的 entry 被**静默跳过**（既不注册也不留原因）⇒ 「未满足供给的 entry 保持 "
            "null 加显式原因」这条正文要求失守，`registered + unregistered == planned` 不再成立",
    ),
    Mutation(
        id="M20", side="be", path=REG, kind="replace",
        anchor='                "尚无该 entry 自己的 approved per-entry 生产契约（不在 "',
        new='                "" ',
        want=f"{_REGT}::test_every_unregisterable_entry_carries_an_explicit_reason",
        why="不可注册原因被抹成空串 ⇒ 182 条 entry 的 `adapter_id=null` 又变回「没有原因的空」",
    ),
    Mutation(
        id="M21", side="be", path=REG, kind="replace",
        anchor="        if row is not None and blocked is None and not provider_module:",
        new="        if False:",
        # 🔴 want 重指：四条真实登记行都填了 `provider_module` ⇒ 这条分支在真实数据上永不
        #    执行，`test_registrar_delegates_to_each_entry_own_attach`（读的是真实登记表）
        #    恒绿，实测 GREEN。行为判据改为喂一份缺该键的登记行。
        want=f"{_REGT}::test_ledger_row_without_provider_module_is_refused",
        why="缺 provider_module 的 entry 静默复用**别人的** attach ⇒ 等于复用别人的 "
            "contract/bundle（Tasks 40~57 正文明令禁止）",
    ),
    Mutation(
        id="M22", side="be", path=REG, kind="replace",
        anchor="    if module_path not in _ALLOWED_PROVIDER_MODULES:",
        new="    if False:",
        want=f"{_REGT}::test_registrar_delegates_to_each_entry_own_attach",
        why="provider 白名单被短路 ⇒ 登记表变成任意 import 面（动态加载面）",
    ),

    # ═══ 路由：manifest 驱动注册必须真被 await（additive 死代码）══════════════
    Mutation(
        id="M23", side="be", path=ROUTER, kind="replace",
        anchor="    outcome = await svc.registry.register_from_manifest(session=svc.session)",
        new="    outcome = svc.registry.register_from_manifest",
        want=f"{_REGT}::test_registrar_is_wired_on_both_production_paths",
        why="HTML→OO 解析入口不再 await manifest 驱动注册 ⇒ 计划永不执行，Task 75 的注册器变成"
            "additive 死代码（假绿第①源）",
    ),
    Mutation(
        id="M24", side="be", path=ROUTER, kind="replace",
        anchor="    await registry.register_from_manifest(session=db)",
        new="    _ = registry.register_from_manifest",
        want=f"{_REGT}::test_registrar_is_wired_on_both_production_paths",
        why="callback 后 apply 这条路径丢掉注册 ⇒ 「HTML 侧能开 OO、OO 回写却找不到 adapter」"
            "的半接线",
    ),

    # ═══ 守卫自身的分母与工具（防整类空跑）═══════════════════════════════════
    Mutation(
        id="M25", side="be", path=OBS, kind="replace",
        anchor='STRUCTURE_HASH_SCHEMA_VERSION: Final[str] = "excel-entry-structure:v1"',
        new='STRUCTURE_HASH_SCHEMA_VERSION: Final[str] = "excel-entry-structure:v2"',
        want=f"{_STRUCT}::test_structure_hash_schema_is_locked_to_the_finalize_gate",
        wants=(f"{_RUN}::test_no_phase_crashed",),
        why="观测器重算公式与 finalize gate 脱钩 ⇒ 观测器在任何真实 entry 上都会误判漂移；"
            "双向锁必须从 gate 源码现取字面量比对，不是各写一份常量",
    ),
    Mutation(
        id="M26", side="be", path=OBS, kind="replace",
        anchor="            \"structure\": [list(item) for item in sorted(observed_structure)],",
        new="            \"structure\": [list(item) for item in observed_structure],",
        want=f"{_STRUCT}::test_recompute_structure_hash_is_order_insensitive_and_content_sensitive",
        why="去掉 sorted ⇒ 同一份结构因枚举顺序不同得到不同 hash，「重复观测逐字节相同」失守",
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # 覆盖面补口（M27~M31）：把 GUARD_FILES 里那 5 个**下游**守卫文件也反证一遍
    #
    # 🔴 为什么必须补：`GUARD_FILES` 声明了 6 个文件，而 M01~M26 的 want **全部**落在
    #    `test_task75_*` 一个文件里，`backend_args` 又只跑那一个文件 ⇒ 另 5 个文件
    #    **结构上不可能**被本 kit 打红。全量运行实测正是 1/6 + 5 条 [GAP]。
    #    「变异 25 条全 RED」按清单计数，「守卫都被反证过」按文件计数 —— 两回事。
    #    补口后 `backend_args` 一并扩到 6 个文件（单次基线 689 passed / 167s）。
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M27", side="be", path=P_B60, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        # 🔴 want 必须带**类段**：`matched()` 是「整串子串」或「末段前缀」两种匹配，
        #    写成 `file.py::test_x` 两者都不成立（实测判 WRONG-TEST 而非 RED）。
        want="test_task40_simple_checklist_pilot.py::TestProductionWiring"
             "::test_resolve_published_definitions_never_returns_none",
        why="Task 75 把 Task 40 的欠账判据改写成正向断言（观测器真被 await、返回非 None）。"
            "这里构造正文逐字禁止的中间形态②，证明改写后的那三条判据**真能**打红",
        tags=("coverage",),
    ),
    Mutation(
        id="M28", side="be", path=P_D2, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want="test_task41_d2_large_json_pilot.py::TestUpstreamDebtsAreVisibleFacts"
             "::test_resolve_published_definitions_never_returns_none",
        why="同 M27，对 Task 41 的改写判据做反证",
        tags=("coverage",),
    ),
    Mutation(
        id="M29", side="be", path=P_H1, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want="test_task42_h1_grouped_dynamic_pilot.py::TestUpstreamDebtsAreVisibleFacts"
             "::test_resolve_published_definitions_never_returns_none",
        why="同 M27，对 Task 42 的改写判据做反证",
        tags=("coverage",),
    ),
    Mutation(
        id="M30", side="be", path=P_G7, kind="insert",
        scope="    observation = await observe_published_frozen_definitions(",
        offset=-2,
        anchor="    from app.services.workpaper_sync.resolution import CanonicalResolutionService",
        new="    return None",
        want="test_task43_g7_two_level_dynamic_pilot.py::TestUpstreamDebtsAreVisibleFacts"
             "::test_resolve_published_definitions_never_returns_none",
        why="同 M27，对 Task 43 的改写判据做反证",
        tags=("coverage",),
    ),
    Mutation(
        id="M31", side="be", path=GATE44, kind="replace",
        anchor='        observer_state = "available" if implemented else "unavailable"',
        new='        observer_state = "available"',
        want="test_task44_oo94_excel_pilot_gate.py::TestFinalizeStateIsReadFromProduction"
             "::test_each_signal_flips_independently_under_substitution",
        why="Task 75 把 Task 44 的观测器探针从二态改成按异常类型分型的三态。抹掉分型后"
            "「观测器坏了」与「观测器已交付」不再可分辨 —— 证明那三条改写判据真能打红",
        tags=("coverage",),
    ),
]

GUARD_FILES = {
    "test_task75_published_identity_observer.py": "Task 75 新建（观测器 + manifest 驱动注册）",
    "test_task40_simple_checklist_pilot.py": "Task 75 改写其欠账三条判据",
    "test_task41_d2_large_json_pilot.py": "Task 75 改写其欠账三条判据",
    "test_task42_h1_grouped_dynamic_pilot.py": "Task 75 改写其欠账四条判据",
    "test_task43_g7_two_level_dynamic_pilot.py": "Task 75 改写其欠账五条判据",
    "test_task44_oo94_excel_pilot_gate.py": "Task 75 改写其观测器探针三条判据",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                # 🔴 六个文件全跑，与 `GUARD_FILES` 的分母**逐一对应**。原先只跑第一个，
                #    于是另 5 个登记文件结构上不可能被打红（实测 1/6 + 5 条 [GAP]）。
                #    代价：单次基线 167s（689 passed，含 2 条既存 fresh 红）。
                "backend/tests/workpaper_sync/test_task75_published_identity_observer.py",
                "backend/tests/workpaper_sync/test_task40_simple_checklist_pilot.py",
                "backend/tests/workpaper_sync/test_task41_d2_large_json_pilot.py",
                "backend/tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py",
                "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py",
                "backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=689,
            # 🔴 允许脏基线，理由逐条写明（本 kit 的判据是差集，不受既存失败影响）：
            #    基线里恒有 2 条 **既存**红，都在 `test_task44_oo94_excel_pilot_gate.py`：
            #      * `TestProbeRegistryIsLockedToTaskText::test_generated_registry_data_file_is_fresh`
            #      * `TestGateAddsNoProductionModule::test_writer_inventory_is_still_fresh`
            #    它们比对的是「evidence / 注册表数据文件是否与当前 source commit 同步」。
            #    Task 45 删除四个 pilot 宿主 legacy 后 evidence 立即 stale（那是 Task 45 正文
            #    写明的设计），刷新属 **Task 70**。Task 75 不碰这两个产物，也不得以自己的
            #    注册成功去刷新它们（正文：真实 OO required scenarios 未按 Task 70 刷新前
            #    evidence 保持 UNVERIFIABLE）。
            #    判定不受影响：verdict 只看 `added = current - baseline`，这两条在两侧都在
            #    ⇒ 永远不进 added。若哪天它们从基线**消失**，`baseline_backend_passed=689`
            #    会先对不上而报出来。
            allow_dirty_baseline=True,
        )
    )
