# Design — workpaper-sync 注册隔离 + 通用对齐守卫 + D2 sibling 发布

**spec**：`workpaper-sync-registration-isolation-and-d2-republish`　**创建**：2026-09-26

## 一、现状与根因（实证）

止血前：`04a90f386` / `915d2d5d2` 打开 D2 两开关，只改契约不改 instrumentation、不重发布
representation。attach 时 `published_identity_observer.collect_workbook_structure` →
`assert_no_structure_drift` 对 d21/d23 报 `sync_contract_structure_drift`。

注册路径是**全有或全无**：`_attach_pilot_adapters` 顺序调 4 条 pilot attach +
`register_from_manifest`，任一抛 `SyncDomainError` 整批中断、`_REGISTRATION_CACHE` 不写 ⇒
**所有** entry 的 sync 端点都 422（实测 D4/G7/D2 全 422，逐 entry 隔离跑只有 D2 抛）。

止血已把两开关回退 False、契约 `--apply` 回到冻结 digest `f341ea68`，实测恢复。本 spec 做
两件结构性修复（注册隔离 + 通用对齐守卫）+ 一件补齐（D2 多 sheet 真做双向 + 重发布）。

## 二、Requirement 1：注册隔离 — 组件与判据

### 2.1 数据结构

`ManifestRegistrationOutcome` 增加 `failures` 字段（与 `reasons` 并列，两者不相交）：

```
@dataclass(frozen=True)
class ManifestRegistrationOutcome:
    registered_adapter_ids: tuple[str, ...]
    reasons: Mapping[str, str]          # 供给不足（静态/数据原因，非故障）
    failures: Mapping[str, "RegistrationFailure"]  # 🔴 新增：注册失败（真故障）
    planned_entry_ids: tuple[str, ...]
    registered_entry_ids: tuple[str, ...]

@dataclass(frozen=True)
class RegistrationFailure:
    entry_id: str
    error_code: str
    message: str
    exc_type: str
```

记账等式（守卫钉）：
`len(registered_entry_ids) + len(reasons) + len(failures) == len(planned_entry_ids)`，
三集合 entry_id 两两不相交。

### 2.2 隔离发生在哪一层

隔离放在 `register_from_manifest` 内的**逐 entry 循环**里：对已通过供给门（`_describe_entry_supply`
返回 None）的 entry，`provider(...)` / `register()` 抛 `SyncDomainError` 时 `try/except`
捕获、记入 `failures`、`continue` 到下一个 entry；非 `SyncDomainError`（如 DB 故障、
`AttributeError`）**仍上抛**（那是真 bug 不是「这个 entry 契约漂移」）。这一层是逐 entry
派发的唯一位置，改这里不动 `register()` 的任何准入判据（Requirement 1.5）。

🔴 现有 `test_task75::test_registrar_does_not_relax_any_admission_check` 断言
`register_from_manifest` body 里不含 `_by_adapter_id[` / `_by_entry_id[` /
`assert_bundle_usable` / `declared_capability=` —— 加 try/except 记 failures 不触碰这些
token，判据仍绿。

4 条 pilot attach（`_attach_pilot_adapters` 里 `attach_pilot_adapters` + `attach_d2/h1/g7`）
同样各自包 try：单条 attach 抛 `SyncDomainError` 记 failure 不中断其余。**调用名不变**
（`test_task40/41/42/43::test_router_calls_*_attach_on_both_paths` 的 AST 断言只看
`_attach_pilot_adapters` 里有没有 `attach_d2_pilot_adapters` 等 Call 节点，包进 try 后
Call 节点仍在）。

### 2.3 请求侧透传 failure（AC 1.3）

`_registration`（HTML→OO）现在 `_attach_pilot_adapters(svc)` + `assert_bidirectional_ready`
包在把 `SyncDomainError` 翻 422 的 try 里。隔离后 attach 不再抛（failure 被吞进 outcome），
所以要在 `assert_bidirectional_ready` 抛 `AdapterNotRegisteredError` 之后、翻 422 之前，
查该 entry 是否在 `failures` 里：命中则用 failure 的 `error_code`/`message` 抛 422（保留
中文根因），否则用原 `adapter_not_ready`。

实现：`_attach_pilot_adapters` 返回值扩展或把 outcome.failures 存到 svc/缓存快照上，供
`_registration` 读。`_RegistrationSnapshot` 增加 `failures` 字段一并缓存（失败态也可缓存，
指纹变了才重算 —— 与成功注册同一失效条件）。

### 2.4 `_apply_durable_incoming` 复用同一路径（AC 1.6）

现状它内联 4 attach + `register_from_manifest`（无缓存、不隔离）。改为构造
`_RegistrationWarmupContext`（或复用 `_attach_pilot_adapters` 的 svc 形态）走同一条隔离+缓存
路径，再 `assert_bidirectional_ready`。`test_task28::test_apply_durable_incoming_is_really_called`
/ `test_task40/41::test_router_calls_*` 的 AST 断言要保留 `_apply_durable_incoming` 里对
attach 的 Call 节点 —— 复用时仍经 `_attach_pilot_adapters`，其内部有 Call。

🔴 变异锚点同步（`mutate_task75` M23/M24 用 `text.count(anchor)==1`）：
- M23 anchor `    outcome = await svc.registry.register_from_manifest(session=svc.session)`
- M24 anchor `    await registry.register_from_manifest(session=db)`
若 `_apply_durable_incoming` 改为复用 `_attach_pilot_adapters`，M24 锚点行会消失 ⇒ 必须同步
改 `mutate_task75_published_identity_observer_guards.py` 的 M24（重指到复用后的等价行），
并跑 `--check-anchors` 确认。M39/M40（task41）、M55/M56（task42）、M72/M73（task43）同理核对。

### 2.5 启动日志口径（AC 1.7）

`startup_prewarm.prewarm_sync_registration_cache` 返回 adapter_ids 不变；新增把 outcome 的
failures 数透出。`main._warm_workpaper_sync_registry` 汇总行加「失败 N 个」，与既有「不适用
N 个」并列。`test_sync_registration_prewarm` 的相关判据同步。

## 三、Requirement 2：通用对齐守卫

新增 `assert_provider_specs_align_with_contract(provider, contract)`，放在
`phase5_row_table_sheet.py`（框架层，已是 sibling binding 的家）。逻辑：
- spec 集合 = provider 有 `instrumentation_specs()` 则取其 `resolved_sheet_key`，否则单数；
  再并入每个 spec 的 `static_sheets[].sheet_key` / `transposed_sheets[].sheet_key`。
- 契约集合 = `{s.sheet_key for s in contract.sheets}`。
- 不等即抛 `ProviderCapabilityError`（已存在，`SyncDomainError` 子类）并报差集。

`phase5_d1_expansion` / `phase5_d3_expansion` 的同名函数改薄转发到它（D3-2/D1-3 自身 sheet
并入的特殊处理保留在各自转发层，核心比较收敛）。测试遍历 golden `PROVIDERS` 跑一遍。

## 四、Requirement 3/4/5：D2 多 sheet 真做双向 + 重发布

### 4.1 instrumentation 复数（零回归前提已实证）

`build_instrumentation_payload_for_sheets([单spec])` 与单数逐字节等价（digest 46f3c617）。
D2 加 `instrumentation_specs()`：主 spec（挂 `static_sheets` D2-1）+ 开关控 D2-3 双区两 spec。
`instrumentation_definition_payload()` 改走 `build_instrumentation_payload_for_sheets`。
开关全关时三段 digest 不变、冻结 bundle 匹配。

### 4.2 D2-1 静态区（照 D4-13）

`GT_MANAGED_REGION_D21` + range `$B$10:$D$11`（6 个 editable 金额格所跨最小矩形）。
`sheet_payload_d21` locator 改 `defined_name_ref` + `region_boundary_locator(region_kind=static)`；
新增 `static_sheet_payload_d21()` 挂主 spec。

### 4.3 双向 store

HTML→OO：`STORE_ITEM_IDS`（开关控）+ `all_store_item_ids()` + `build_combined_store_projection`
（合并 D2-2 + D2-3 + 新 `build_d21_store_projection`；复制 `_d23_combined_category`）。
OO→HTML：**裁决①内核泛化**（对 D4 零行为变化，收益是 D2/未来 provider 复用）——
`StoreMergePlan` 加 `merge_all_fn`（默认 `merge_projection_into_all_d4_stores` 保 D4 不变）+
`fixed_text_blocks`；`_mirror_d4_dual_stores` 用 `plan.merge_all_fn` 取函数名。D2 的
`d2_bidirectional_bridge` 补 `merge_projection_into_all_d2_stores` + D2-1 纯文本写回门面 +
`merge_projection_into_store_rows` 加 table 前缀过滤。`store_item_registry` D2 plan 加
`dual_store_fn` + dedicated 声明。

⚠️ `d2_bidirectional_bridge` 现 954 行 / 白名单 1115，加多 store 会顶 1115×1.05=1170。
D2-1 写回门面若超，抽伴生模块（照 `d2_store_value_equivalence` 已有先例）。

### 4.4 D2-3 行插入边界（AC 5.3，诚实登记）

实测 16 处段内小计 `SUM(数据区)` 落在 last_data_row 且非 footer，插行不扩张（引擎边界，
同 D3-4 F5）。裁决：D2-3 首版发布**限定模板固定行集**（OO 侧不动态增行），位移链由纯函数
判据验证；真栈整册 materialize 的行增长受此边界约束，登记 evidence 不代修引擎。

### 4.5 `_combined_target` fail-visible（AC 5.4）

让 `phase5_d2_03_bad_debt.StorePayloadError` 携带 `error_code` 并被 apply 路径识别为
fail-visible（继承 `SyncDomainError` 或写回门面预剔除）。裁决：优先让它继承
`SyncDomainError`（`error_code="d23_combined_row_category_unresolved"`），最小改动、语义正确。

## 五、Requirement 6：前端开关同步

后端 render-config 已按 capability 驱动「能否切 OO」。D2 前端 `D2_MANAGED_SHEET_KEYS` 应由
后端受管 sheet 集合派生而非硬编码。裁决：本 spec 后端先补齐并重发布，前端映射跟随开关
（开关关时 D2-3/D2-1 不在集合内），最终态由后端 capability 驱动。

## 六、实施顺序（wave）

1. Wave A（结构修复，最高优先，可独立交付）：Requirement 1 注册隔离 + Requirement 2 通用
   对齐守卫。这两件与 D2 是否重发布无关，先落地并回归。
2. Wave B（D2 补齐）：Requirement 3/4 D2 instrumentation 复数 + 双向 store（开关仍关，纯代码
   就绪 + 判据）。
3. Wave C（D2 重发布）：Requirement 5 打开开关 + 重生成契约 + 发布链 + 真栈实测。
4. Wave D（前端）：Requirement 6。

每 wave 独立回归；Wave A 交付即消除「一个漂移拖垮全部」的类，Wave C 才真正打开 D2-3/D2-1。

## 七、风险与回滚

- Wave A 改注册路径：变异锚点必须同步（§2.4），否则 `mutate_task75 --check-anchors` 红。
- Wave C 打开开关前必须先跑通 Wave B 的对齐守卫（否则重发布期 `assert_no_structure_drift`
  会漂移）。
- 每步独立 commit；开关是单行回退点（Wave C 失败即回退开关 = 回到止血态）。
