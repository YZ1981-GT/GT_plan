# Task 0 前置依赖核查（F5）

**执行**：2026-09-26　**基线**：工作树（HEAD `07eb3fb75` + 并发会话 WIP）

主证据见 `.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task0-prerequisites.md`
（F3/F4/F5 三 spec 共用）。本文件只记 F5 特有项。

## 补-1：🔴 框架层有**两份** json_path 实现，只有一份支持数组下标

> **🔴 本节结论在实施中修正过一次，保留修正轨迹**。初判写的是「引擎不支持数组下标 ⇒ 需新增能力」；
> 深入实测后发现真相是**多源**：`app/services/workpaper_sync/json_path.py` 早已是数组感知实现
> （docstring 自称「**本模块是唯一允许的数组段实现真源**」，已为 `months` 定
> `FIXED_ARRAY_LENGTHS = {"months": 12}`，D4 月度矩阵在用，判据
> `tests/workpaper_sync/test_d4_positional_array_roundtrip.py`），而 `phase5_row_table_sheet.py`
> 里存在**同名的第二份实现**且只认 `Mapping`。
>
> ⇒ 处置从「新增能力」改为「**收敛到真源**」（见下方 §处置）。
> ⇒ 裁决 F5-H5 写的「引擎 `resolve_json_path` 支持，D4-2 / D3 账龄组同机制」**半对**：
> D3/D7 账龄组是 nested **dict**（与数组无关），D4-2 月度矩阵确实走真源的数组段；
> spec 的疏漏在于没区分「哪一个 `resolve_json_path`」。

| 实现 | 数组下标 | 使用方 |
|---|---|---|
| `json_path.py`（真源，5 个错误码 fail closed） | ✅ 支持 + `months` 长度硬约束 12 | D4 月度矩阵 · D4-14 walkthrough |
| `phase5_row_table_sheet.py` 内同名函数 | 🔴 只认 `Mapping` | D1~D7 / E1 七家行表（`build_store_projection` / `merge_projection_into_store_rows`） |

F5-2 走的是后者（行表引擎）⇒「D4 已支持」并不能让 F5-2 直接用上。后者的实测行为：

```python
# phase5_row_table_sheet.py:328  resolve_json_path
cursor: object = row
for segment in json_path.split("/"):
    if not isinstance(cursor, Mapping):   # 🔴 list 不是 Mapping → 直接 return None
        return None
    cursor = cursor.get(segment)

# phase5_row_table_sheet.py:341  set_json_path
for seg in parts[:-1]:
    nxt = cursor.get(seg)
    if not isinstance(nxt, dict):         # 🔴 list 不是 dict
        nxt = {}
        cursor[seg] = nxt                 # 🔴 把 months 数组整个替换成 {} —— 数据破坏
    cursor = nxt
```

前端 `MonthlyDetailRow.months: number[]`（12 元素数组）⇒ 直接受管的真实后果：

| 方向 | 后果 |
|---|---|
| 投影（HTML→OO） | `resolve_json_path(row, "months/0")` 恒返 `None` ⇒ 12 个月列**投影恒空**，OO 里 B-M 全空 |
| 合并（OO→HTML） | `set_json_path(row, "months/0", v)` 把 `row["months"]`（list）**替换成 `{}`** ⇒ 12 个月数据全丢 |

对照真源 `json_path.py`：段是十进制非负整数（RFC 6901 风格，禁前导零）且游标是 list 时按下标寻址，
并带 5 个封闭错误码 —— `json_path_missing_segment` / `json_path_type_mismatch` /
`json_path_array_index_invalid` / `json_path_array_index_oob` / `json_path_array_length_invalid`。

### 处置（已实施）：收敛到真源，不新增第三份实现

`phase5_row_table_sheet.resolve_json_path` / `set_json_path` 改为**薄委托**真源。两处语义边界：

| 方向 | 处置 | 理由 |
|---|---|---|
| 读（`resolve_json_path`） | 捕获 `JsonPathMissingSegmentError` / `JsonPathTypeMismatchError` → 返 `None`；**数组越界 / 长度不符不吞** | 七家行表依赖「字段缺失 = None」（store 行常有用户没填的可选字段），直接透传真源的 fail closed 会让七家一接全崩；而数组越界是载荷真损坏，必须 fail |
| 写（`set_json_path`） | 不吞任何异常 | 写入失败必须可见 —— 静默跳过等于用户在 OO 里的改动凭空消失 |

被否决的方案：
- ❌ 在 `phase5_row_table_sheet` 里自己加 list 分支（= 造第三份实现，正是 FC 级多源问题；已写过又撤回）
- ❌ 前端改存 dict（spec F5-H5 已否决；会动 legacy 键 `F5-2-rows` 的历史载荷）
- ❌ 展平成 `month1`…`month12` 顶层键（要改 `updateMonth(id, monthIndex, value)` 与全部读方）
- ❌ F5-2 不受管（F5 主明细表，不接等于覆盖面丢一半）

零回归实测：dict 语义逐字保留（缺键/深层缺键/flat/建中间 dict/写同值返 False 全部同旧）；
`tests/workpaper_sync/` 下引擎与七家相关 **179 passed**（`test_phase5_row_table_sheet` /
`test_row_table_engine_equivalence` / `test_d4_positional_array_roundtrip` /
`test_d4_inspection_store_roundtrip` / `test_d4_14_walkthrough_roundtrip` /
`test_phase5_d1_sheet_specs` / `test_d1_sheet_specs` / `test_store_item_registry` /
`test_d3_expansion` / `test_d2_1_adjudication_mask` / `test_d2_3_bad_debt_contract` /
`test_multi_sheet_workbook_change_merge` / `test_store_payload_error_stays_domain_error`）。

新判据 `tests/workpaper_sync/test_f5_json_path_array_delegation.py`（**22 passed**）：
dict 语义零回归 8 条 · 数组读写 5 条 · 数组 fail-closed 4 条 · 单源委托 3 条（含 AST 判据
「引擎两个函数体内不得再出现 `json_path.split("/")`」）· F5-2 契约场景 2 条。
变异自检：把委托改成自己 split 遍历 + 吞掉全部 `JsonPathError` ⇒ 精准打红 2 条（已还原）。

🔴 该收敛是 F5 Task 16 的硬前置，已在 canary 链路之前完成。

## 补-2：锚行 footer（F5-7 / F5-8 两张依赖）✅ 已支持

`footer_carries_total_formula=False`（`phase5_row_table_sheet.py:152`）+ 生产先例 D3-4 段②
（磁盘契约 `d34-managed` / `analysis_credit_rows` / `carries_total_formula: False` / marker「差异合理性分析」）。

⇒ F5-8 `footer_row=30` + `footer_marker="三、审计说明"` + `carries_total_formula=False`
与 F5-7 `footer_row=32` 同款处置**可直接声明**，零框架层改动。
🔴 marker 逐字须核：spec 写「三、审计说明」（不含冒号），而 D3-6 的同类锚点原文是「三、审计说明：」（带全角冒号）
⇒ Task 2 须 openpyxl 逐格读 F5-8!A30 / F5-7!A32 的真实字符串，`footer_anchor.marker` 按实测值写
（`assert_footer_anchor_stable` 是逐字比对，差一个冒号即定位失败）。

## 补-3：模板覆盖层（F5-7!G31 修复依赖）✅ 已交付，默认方向①可用

- spec `excel-template-override-layer-and-onlyoffice-template-editor`：**25 done / 0 todo**
- 运行时 API 齐全（主证据 §6）；覆盖粒度 = 整文件副本 ⇒ 改 G31 的方式是「以权威模板为基底改该格公式、存覆盖文件」
- `assert_override_root_disjoint_from_authoritative:180` 保证不动 `backend/wp_templates/` 字节（符合 Task 17 红线）

⇒ **裁决 F5-H2 取默认①**（把 `G31` 修为 `=G24+G25+G26-G27-G28-G29-G30`），不退备选②。
Task 0 的 blocking「模板覆盖层未交付 ⇒ Task 17 只能走备选②」**解除**。

## 补-4：F3 spec 的 FC-11 工具链修复状态

同 F4 补-2：根因两处未修（主证据 §9）。本批把 F3 工具链根因修复排在 F5 数据迁移之前（todo #2 → #3）。

F5 侧现状实测：
- `prefill_formula_mapping.json` 块 `[226]`（wp_code=F5，sheet=`营业务成本审定表F5-1`）：`cells: []` + `items` **14 条**
- `convert_prefill_presets()` 现算：`workpaper:F0=2 / F1=33 / F2=78 / F3=18 / F4=18`，**`workpaper:F5` 键不存在**
  ⇒ F5-P21 的红基线锚点「预设数 == 0」属实，且 F5 是唯一能用「从 0 到有」证明 FC-11 修复生效的科目

## 补-5：F5 slice 逐元素实测（Task 1 前半）

`backend/data/workpaper_sync_f_cycle_manifest_slice.json` → `xlsx/gt-f5-cost-of-sales`：

```
wp_code_pattern             "F5C"
capability                  null
capability_verdict_stage    "pipeline_entry_pending_definition_delivery"
capability_target           "bidirectional"
capability_target_blocked_by ["BP-1","BP-2","BP-3","BP-4","BP-7"]   ← 🔴 含 BP-7，不含 BP-5（BP-5 是 F2 专属）
migration_state             "legacy_fake_bidirectional"
adapter_id / authority_model / definition_bundle
  / instrumentation_candidate / published_representation   全 null（五个 null 供给位）
template_ref                "F/F5 营业成本.xlsx"
mount_count                 2
scenario_profile_id         "xlsx.editable.shared.single.room_service_wired.v1"
html_counterpart_verdict    "exists"
manifest_mirror.capability  "single_onlyoffice" + divergence_from_slice 已登记（FC-12 属实）
ui_toolbar_gate             "class=\"f5-cost-of-sales-toolbar\""
ui_toolbar_gate_note        「本宿主的工具栏也没有 v-if 门控，模式切换器自己带 v-if="isHtmlSheet"」
```

⇒ 与 requirements「F5 当前状态实测」表逐项一致（含 `capability_target_blocked_by` 五元素、
宿主 `isHtmlSheet` 门控是 F 循环唯一），slice **未过期**。

## 补-6：F5 特有结论

| 项 | 判定 |
|---|---|
| BP-7 三处修复（Task 6） | ✅ 可做 —— `useF5MonthlyDetail.ts` / `useF5OtherCost.ts` / `useF5Comparison.ts` **均不在并发会话改动列表**（`git status` 已核），零冲突 |
| 锚行 footer（F5-7 / F5-8） | ✅ 可做，🔴 marker 须逐字实测（补-2） |
| F5-7!G31 覆盖层修复 | ✅ 可做（补-3），方向①ravel |
| F5-2 `months` 数组路径 | 🔴 需框架层新增（补-1），排 todo #5 |
| FC-11 数据侧（0→14） | ✅ 可做（依赖 F3 工具链先修） |
| FC-10 | 初判不命中（B6），须 Task 2 逐列取证（F5-2 V/W · F5-3 F/K/M · F5-5 K/L/M 是否全为公式列） |
| 真库零载荷 | 🔴 验收必须先 seed（F5-H7）；`seed_f5_publish_e2e.py` 待建（Task 11） |
| 发布链 ③④⑤ + 真栈 | 🔴 BP-61-1 外部阻塞，如实 `upstream_gap` |
| F5-1 主营区 HTML-only | ✅ 纯声明裁决，可做 |

## 补-7：BP-7 三处修复已落地（Task 6）

新增 `audit-platform/frontend/src/components/workpaper/composables/f5RowIdentity.ts`：
`resolveStableRowId(raw, prefix, stats)` / `mintStableRowId(prefix)` /
`isLegacyOrdinalRowId(value)` / `F5_ROW_ID_PREFIX`。

三处载入路径改为委托该 helper（裁决 F5-H6「一次修完，不分 spec」）：

| 键 | 文件 | 改造前 | 改造后 |
|---|---|---|---|
| `F5-2-monthly-rows` | `useF5MonthlyDetail.ts` | `String(r?.id ?? r?.rowId ?? \`m-${Date.now()}-${i}\`)` | `resolveStableRowId(r, 'f5m', stats)` |
| `F5-3-other-cost-rows` | `useF5OtherCost.ts` | `String(r?.id ?? r?.rowId ?? \`oc-migrated-${i}\`)` | `resolveStableRowId(r, 'f5oc', stats)` |
| `F5-5-comparison-rows` | `useF5Comparison.ts` | `String(r?.id ?? r?.rowId ?? \`cmp-migrated-${i}\`)` | `resolveStableRowId(r, 'f5cmp', stats)` |

三处 `migrate*` 的 `(r: any, i: number)` 已去掉 `i` 形参（下标不再参与身份派生，形态上就写不回去）。

**两条超出 spec 原文的处置**：
1. 不只在「缺 id」时铸，**id 命中旧下标形态时也重铸**（需求 3.3 的存量迁移判据）；
   判定正则 `^(m-\d+-\d+|oc-migrated-\d+|cmp-migrated-\d+)$` 逐字对应三处旧写法，不泛化猜测。
2. **立即回写**：`loadRows()` 拿 `RowIdentityMintStats.minted > 0` 时调 `persist()`。
   不回写的话 store 里仍无 id，下次载入又铸一个新的 ⇒ 身份每次都变，与下标派生同样破坏 roundtrip。
   `readonly` 态不回写（只读不得产生写操作）；`persist()` 的 `lastPersisted` 守卫使 watch 不成环。

判据 `audit-platform/frontend/src/components/workpaper/composables/__tests__/f5RowIdentityBp7.spec.ts`
（**17 passed**）：缺 id 铸造 ×3 · 存量下标型重铸 ×3 · 已是稳定 UUID 不重铸 ×3 ·
立即回写 ×3（含 legacy 键不被二次写入，对应需求 2.3）· readonly 不回写 ·
插删行后同一逻辑行 id 不变 · helper 语义 ×3。

变异自检：把 `resolveStableRowId` 的旧形态检查绕过（`if (candidate)`，模拟「只修缺 id、
不修存量下标型 id」的半修状态）⇒ 精准打红 **5 条**（已还原）。

零回归：F5 相关 11 个前端测试文件 **100 passed / 1 failed**，唯一 failed 是
`useF5Integration.spec.ts > F5-1 publishAdjudicated 触发 6401 事件` —— 已用
`git stash push` 精确验证为**预存红**（stash 掉我的三处改动后仍 failed），涉及
`useF5Adjudication` / `useF5CostRollforward` 两个我未触碰的文件。

## 补-8：全仓触类旁通 grep 结果（BP-7 同型第四处）

按 `?? \`prefix-${i}\`` / `${Date.now()}-${i}` / `-migrated-${` 三种模式全仓 grep：

- 绝大多数命中是**新建行**的 id 生成器（`createEmptyRow` / `generateId`），语义合法
  （新行只需唯一，不需要"从既有载荷恢复同一身份"）—— 不属 BP-7。
- 🔴 另有**两处同型载入回退**（`raw.id || ...-${seq}`，属 G7 循环，不在本批 spec 范围，登记移交）：
  - `components/workpaper/g7-long-term-equity-subsidiary/disposal/g7DisposalSingleModel.ts:118`
    `id: raw.id || \`g11-${Date.now()}-${seq}\``
  - `components/workpaper/g7-long-term-equity-method/calculation/g7InternalTransactionModel.ts:98`
    `id: raw.id || \`g15-${Date.now()}-${seq}\``
