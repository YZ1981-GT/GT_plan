# Requirements — workpaper-sync 注册隔离 + 通用对齐守卫 + D2 sibling 发布

**spec**：`workpaper-sync-registration-isolation-and-d2-republish`
**创建**：2026-09-26
**起因**：D2 灰度开关（`_INCLUDE_D203_BAD_DEBT` / `_INCLUDE_D201_ADJUDICATION`）在
`04a90f386` / `915d2d5d2` 打开后**只改了契约**（新增 d23-managed / d21-managed 两张受管
sheet），但 D2 父模块 instrumentation 仍是单数（只锚 d22），已发布 representation 也未
重发布 ⇒ attach 时观测器对 d21/d23 报 `sync_contract_structure_drift`；而注册路径是
**全有或全无**，一个 entry 抛错整批中断、缓存不写 ⇒ **全部** entry（D4/G7/D2 …）的 sync
端点都 422。已先止血（两开关回退 False，契约回到冻结 digest），本 spec 做结构性修复。

## 术语

| 术语 | 含义 |
|------|------|
| 注册路径 | `wp_sync_router._attach_pilot_adapters` → 4 条 pilot attach + `registry.register_from_manifest`，两个生产接线点（`_registration` HTML→OO 解析入口 / `_apply_durable_incoming` OO 回调 apply 入口）都走它 |
| 供给不足 reason | entry 尚无 approved bundle / published representation 等**静态或数据**原因（`ManifestRegistrationOutcome.reasons`），不是故障 |
| 注册失败 failure | entry 的 provider/register 抛 `SyncDomainError`（如 `ContractDriftError`）—— 是**真故障**，AC 5.12 要求与「供给不足」可分辨 |
| blast radius | 一个 entry 出错波及多少其它 entry。现状 = 全部；目标 = 仅该 entry 自己 |
| 对齐守卫 | 「provider 的 `instrumentation_specs()` 张数 == 契约 `sheets[]` 受管 sheet 张数」的 fail-closed 校验，D4-35 事故后 D1/D3 各写一份，D4/D2 无 |
| 重物化（rematerialize / 重投影） | 对**已有 current published representation** 的 entry，契约/instrumentation 变更后按 `template → instrumentation → contract → bundle → representation` 发布新一代 definitions（推进 content_revision） |

---

## Requirement 1：注册按 entry 隔离（blast radius 收敛到单 entry）

**User Story**：作为审计师，当某一张底稿的契约与已发布结构漂移时，我只应看到**那一张**底稿
不可在线编辑，其余底稿的在线编辑照常可用。

### Acceptance Criteria

1.1. WHEN 注册计划中某个 entry 的 provider attach 或 `register()` 抛 `SyncDomainError`（含
`ContractDriftError` / `ObservedIdentityDriftError` / `RegistrationError` 等所有子类）
THEN 该异常 SHALL 被记录为一条 **typed failure**（含 `entry_id` / `error_code` /
`message` / 异常类名），且**不得**中断其余 entry 的注册。

1.2. WHEN 一次注册完成 THEN 成功注册的 entry SHALL 照常进 ROI-0 缓存
（`_REGISTRATION_CACHE`），后续请求命中缓存不再重跑；失败 entry **不进**成功集合。

1.3. WHEN 请求解析到一个**注册失败**的 entry（`assert_bidirectional_ready` /
`resolve_for_entry` 找不到 adapter）THEN 端点 SHALL 返回 **422** 且 `error_code` /
`message` **原样透传**该 entry 记录的 failure（不得替换成泛化的 `adapter_not_ready`，
否则丢失中文根因）。

1.4. 「注册失败 failure」与「供给不足 reason」SHALL 是**两个独立集合**（AC 5.12：不得把
故障降级成「本项目无数据」）。`ManifestRegistrationOutcome` 的记账等式扩展为
`len(registered_entry_ids) + len(reasons) + len(failures) == len(planned_entry_ids)`，
三者两两不相交。

1.5. `register_from_manifest` 的**注册准入判据一条不放宽**：真正的 `register()`（RG-1~RG-19
全部）与 provider 的 published-identity 观测器仍照跑；隔离只改「一个 entry 抛错不连累
别的 entry」，不改「这个 entry 到底能不能注册」。

1.6. `_apply_durable_incoming`（OO 回调 apply 入口）SHALL 走**与请求路径同一条**隔离后的
注册（复用 `_attach_pilot_adapters` 的缓存与隔离），不得各自再冷跑一遍全量注册
（现状：它内联 4 条 attach + `register_from_manifest`，无缓存、不隔离 ⇒ 每次 OO 回调冷注册
25~30s 且某 entry 漂移即 500）。

1.7. 启动预热（`startup_prewarm`）与启动日志（`main._warm_workpaper_sync_registry`）
SHALL 把 failures 数**单独报出**（与 reasons 分开），生产 `log_level=WARNING` 下失败数
非零 SHALL 以 WARNING 可见。

---

## Requirement 2：通用「instrumentation spec ↔ 契约 sheet」对齐守卫

**User Story**：作为维护者，当我给某个 entry 的契约加一张受管 sheet 却漏了对应的
instrumentation spec（D4-35 事故形态）时，我应在**接入时**就看到精确差集，而不是上线后
整册 500。

### Acceptance Criteria

2.1. 系统 SHALL 提供**一个**通用守卫 `assert_provider_specs_align_with_contract(provider, contract)`，
校验 provider 的 `instrumentation_specs()`（或单数 `instrumentation_spec()`）覆盖的受管
sheet 集合 == 契约 `sheets[]` 的受管 sheet 集合；不一致即 fail-closed 并**精确报差集**
（契约有而 spec 缺 / spec 有而契约缺）。

2.2. 该守卫 SHALL 兼容三类 provider：单数 `instrumentation_spec()`（B60/D1/D3 父/D5/D6/D7）、
复数 `instrumentation_specs()`（D4/D2 改造后）、以及带 `static_sheets` / `transposed_sheets`
寄生声明的形态（静态区 sheet_key 也要计入受管 sheet 集合）。

2.3. 既有的 `phase5_d1_expansion.assert_specs_align_with_contract_sheets` /
`phase5_d3_expansion` 同名函数 SHALL 收敛到通用守卫（薄转发或直接调用），**不保留两份实现**
（两份必然漂移）。

2.4. 系统 SHALL 有**一条**测试遍历 golden digest `PROVIDERS` 登记的全部 provider，对每个
跑通用守卫，证明现状全部对齐（含 D4 —— 它此前没有任何对齐守卫）。

---

## Requirement 3：D2 父模块补齐多 sheet 发布能力（照 D4 已验证范式）

**User Story**：作为维护者，我要能重新打开 D2-3 / D2-1 的灰度开关，让 D2 的三张受管 sheet
走同一条已验证的多 sheet 发布/attach 路径，而不是给单绑定 bridge 打补丁。

### Acceptance Criteria

3.1. `pilot_d2_large_json` SHALL 提供 `instrumentation_specs()`（复数）：d22 主动态 spec +
（`_INCLUDE_D203_BAD_DEBT` 开时）D2-3 双区两 spec + （`_INCLUDE_D201_ADJUDICATION` 开时）
D2-1 静态区寄生在主 spec 的 `static_sheets` 上。

3.2. WHEN 两个开关**都关**（止血态）THEN `instrumentation_specs()` == `(instrumentation_spec(),)`，
且 `instrumentation_definition_payload()` / `template_definition_payload()` / 契约 canonical
digest **逐字节等价**于改造前（已实证 `build_instrumentation_payload_for_sheets([单spec])`
== `build_instrumentation_payload(单spec)`），冻结 bundle 仍匹配、golden digest 零回归。

3.3. D2-1 静态受管区 SHALL 照 D4-13 范式声明：`sheet_payload_d21` 的 locator 改
`defined_name_ref` + `region_boundary_locator`（`region_kind=static`，range 覆盖 6 个
editable 金额格所跨最小矩形），并提供 `static_sheet_payload_d21()` 挂到主 spec 的
`static_sheets`；instrumentation 注入只写 workbook-scope definedName。

3.4. `attach_pilot_adapters` SHALL 传 `sibling_bindings=attach_sibling_bindings(provider=本模块, ...)`
（框架层 `phase5_row_table_sheet.attach_sibling_bindings`，与 publish 侧共享
`_align_specs_to_sibling_tables`），使 d23 双区 + d21 静态区在 attach 期获得各自 binding。

3.5. 契约生成器 `generate_pilot_d2_large_json_contract.py` 与 golden digest 门 SHALL 在开关
打开后重取基线；开关关闭态的 d22-managed sheet digest **逐字节不变**（additive 语义，非回归）。

---

## Requirement 4：D2 双向 store（HTML→OO / OO→HTML 两方向都生效）

**User Story**：作为审计师，D2-3 坏账准备与 D2-1 审定表切在线编辑后，我在 OO 里改的值要能
回写到结构化视图，反之亦然，且不串到 D2-2 明细。

### Acceptance Criteria

4.1. HTML→OO：`pilot_d2_large_json` SHALL 在开关打开时暴露 `STORE_ITEM_IDS`（D2-2 一条 +
D2-3 三键 + D2-1 六键）、`all_store_item_ids()`、`build_combined_store_projection(payloads, *, contract)`
（合并 D2-2 `build_store_projection` + D2-3 `build_d23_store_projection` + D2-1 新
`build_d21_store_projection`，并复制 D2-3 的 `_d23_combined_category` 信号）。
`store_projection_response` 现有的「`len(STORE_ITEM_IDS)>1` 且有 `build_combined_store_projection`
⇒ 走多 store」分派对 D2 自动生效。

4.2. OO→HTML：`d2_bidirectional_bridge.merge_projection_into_store_rows` SHALL 加 **table
前缀过滤**（只处理 `{ROWS_TABLE_KEY}/` 开头的键），使 D2-3/D2-1 的键不会串进 D2-2 建幽灵行。

4.3. OO→HTML：D2 SHALL 支持多 store 回写。做法二选一，在 design 裁决：① 把
`oo_to_html._mirror_d4_dual_stores` 写死的 `merge_projection_into_all_d4_stores` /
fixed-text 块**泛化**为 `StoreMergePlan` 声明驱动（`merge_all_fn` / `fixed_text_blocks`，
对 D4 零行为变化）；② `d2_bidirectional_bridge` 导出同名 `merge_projection_into_all_d2_stores`
+ D2-1 纯文本写回门面。`store_item_registry` 的 `d2.receivable_detail` plan 相应加
`dual_store_fn` / dedicated 声明。

4.4. D2-1 per-cell 静态审定格 SHALL 有投影+写回：投影把 6 个 store 键值（amount 文本）映射到
契约静态字段 `adjudication_cells/{row_key}_{col}`（None/空串→None，数字串→Decimal）；写回把
projection 值格式化回纯文本 remark（None→""，整数值输出整数文本，按数值比较避免
"100"/"100.0" 误判变化）。

4.5. golden digest 的 D2 projection 段 SHALL 保持可算（脚本 `_digests_for` 现只调
`build_store_projection` 投 D2-2；若纳入多 store 投影需同步改脚本 + 基线）。

---

## Requirement 5：D2 重新发布（真栈闭环）与真栈边界

**User Story**：作为维护者，开关打开后我要能对已发布的 D2 entry 发布新一代 definitions，且
确认发布链零漂移。

### Acceptance Criteria

5.1. 系统 SHALL 提供 D2 的重物化宿主（参数化 `d43_rematerialize_dual_sheet.py` 或新建 D2 版），
支持 `--check`（`would_rematerialize` / `already_on_desired_bundle`）与 `--apply`（推进
content_revision，产出新 generation）。

5.2. 发布顺序 SHALL 为：`generate_pilot_d2_large_json_contract.py --apply` →
`fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d2-accounts-receivable`
→ D2 重物化宿主 `--apply`；每步 `--check` 无 drift；最终 `store-projection` 三张受管 sheet
均 200 且字段数非零。

5.3. 🔴 **D2-3 行插入真栈边界**（实测确认，照 D3-4 裁决 F5 诚实登记，不代为修复引擎）：D2-3
模板小计行在数据**上方**（`B12=SUM(B13:B16)` 段① / `E17=SUM(E18:E21)` 段②），引擎结构性
插行固定插在 `last_data_row+1`（段①=17、段②=22），只对契约声明 `carries_total_formula`
的 **footer 行**做区间扩张 —— 段内小计的 `SUM(数据区)` 区间**不会**随插行扩张（普查实测
16 处）。因此 D2-3 首版发布 SHALL 明确其真栈行增长边界：要么限定为模板固定行集（OO 侧不
增行，`delete_policy` 相应裁决），要么在 design 登记「段内小计漏算」为已知引擎边界并给出
判据可复现的位移链纯函数验证（真栈整册 materialize 的行增长受此约束）。

5.4. 组合区 OO 新增行且三条 category 线索全缺时 `_combined_target` 已 fail-closed 抛
`StorePayloadError`；但它继承 `ValueError` 非 `SyncDomainError` ⇒ 在 apply 路径会成 opaque
500。SHALL 在 design 裁决：让 `StorePayloadError` 同时携带 `error_code`（继承或适配到
`SyncDomainError`），或在 D2 写回门面预剔除并记录，使它成 fail-visible 而非 500。

---

## Requirement 6：前端开关同步（避免「后端关、前端可切 → 422」）

6.1. 前端 D2 受管 sheet 集合（`D2_MANAGED_SHEET_KEYS`）SHALL 与后端灰度开关状态一致：开关
关时不得让 D2-3/D2-1 显示「在线编辑」可选（否则切了就 422）。做法：后端 render-config /
capability 驱动，或前端映射跟随开关（design 裁决，优先后端驱动避免两个真源）。

6.2. 非受管 sheet SHALL 保持现状「直接禁用 + 显式中文原因」，不得静默无反应或落 legacy 假双向。

---

## 非目标（本 spec 明确不做）

- 不改 `excel_materialize` 的结构性插行内核去支持「段内小计（数据上方）随插行扩张」——
  那是 D3-4 已登记的引擎边界，规模超出本 spec（Requirement 5.3 只做诚实登记 + 边界约束）。
- 不接入 E1（registry 白名单 `DELIVERED_PER_ENTRY_CONTRACTS` 无 e1 行，adapter 未在注册计划
  内，属平台级供给缺口）。
- 不重发布 b60 / d3（磁盘契约 digest 与冻结不符但二者非 bidirectional，attach 返回空不炸；
  d3 有并发会话未提交改动，不动）。
- 不改 LLM / 6000 并发 / 钉集成等既有外部依赖待办。
