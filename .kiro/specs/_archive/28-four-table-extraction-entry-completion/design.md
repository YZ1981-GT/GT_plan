# Design Document

## Overview

两条主线并行：**横向补齐**（缺入口的明细表接上四表库取数）+ **纵向收敛**（把两套实现合成一套）。设计的核心约束是"不新造第 5 套归集逻辑"，所有取数走同一条管道。

```
报表行映射（report_config / ReportLineAccountSpec）
        │ 解析出科目原始码前缀（禁硬编码）
        ▼
four_table.aux_aggregation.aggregate_aux_by_name
        │ ① get_active_filter（只取 active dataset）
        │ ② pick_aux_type（先锁定单一维度）
        │ ③ account_code LIKE 前缀（非精确等值）
        ▼
AuxEntry[] (aux_name, opening, debit, credit, closing)
        │ 各循环的纯函数行构建器（只写录入列）
        ▼
checklist_responses[item_id].remark（merge 语义）
        │
        ▼
前端 reload → 明细 Tab → 审定表 → 附注（读同一 store）
```

## Architecture

### 现状分层（实扫）

| 层 | 正确范式（F1/G7/K1/D1） | 历史版本（D3/D5/D6/D7） |
|---|---|---|
| 数据集过滤 | `get_active_filter` | 裸 `is_deleted = false` ❌ |
| 维度锁定 | `pick_aux_type` 先定 `aux_type` | 直接 `GROUP BY aux_name` ❌ |
| 科目来源 | 报表映射解析（如 K1 走 BS-009，兜底注明） | 字面量 `'2203%'` 等 ❌ |
| 归集实现 | 共享件 `aux_aggregation` | 各自裸 SQL（D6 抽到 `detail_aggregation.py` 但仍裸 SQL）❌ |
| 账龄 | 应为**配置驱动空骨架**（键取 `get_effective_segments`，值留空）；🔴 **K1 现状仍全额塞首段** `_aging()`→`bucket[first_key]=amount`，属活体伪造待修 | 全额塞 `within1` ❌ 伪造（D3/D5/D6/D7 迁移已改留空） |

`aggregate_aux_by_name` 已是共享件且签名足够（`db, project_id, year, account_prefixes`），迁移主要是**替换调用 + 补 year 参数 + 科目码改解析**。

### 缺口分类（Requirement 1.3 的 gap 类型）

- **G-A**：后端端点有 + 前端按钮无（如 K1 只有 AutoSeed）→ 只补前端
- **G-B**：后端端点无 + 具备取数能力 → 端点 + 按钮都补，端点直接用共享件（不会产生历史债）
- **G-C**：两侧都有但实现违铁律（D3/D5/D6/D7）→ 迁移
- **G-D**：评估为不适合（源模板无列 / 数据只在序时账 / 无维度挂账）→ 只登记理由，不动代码

### 账龄骨架与账龄枚举联动（Requirement 7）

四表库**无账龄源**（`tb_aux_balance` 无 aging 列，`tb_ledger` 只有 `voucher_date` 但取数不做逐笔账龄核销）⇒ 账龄是审计师在明细表**手动录入**的判断。取数的职责只有两条：

1. **生成空账龄骨架**：账龄段键集来自 `aging_config_service.get_effective_segments(project_id, subject, db)`（与前端 `useAgingConfig` 同一真源 `wizard_state.aging_config`，subject-scoped）。3-period 科目（K1/D2/K3/G5/F1）生成 `agingPrior`/`agingCurrent`/`agingAudited` 三组，2-period 科目（D3/D5/D6/D7）生成 `agingPrior`/`agingAudited` 两组，每段值 = 0。**永不塞余额**。
2. **随枚举联动**：项目切三年段（4 段）↔五年段（6 段）↔自定义（2-10 段）时，骨架段键自动跟着 `effective_segments` 变；已录明细行经前端 `useAgingMigration.remapRowAgingData` 重映射到新段（不丢已录数据）。

实现要点：
- `build_k1_detail_rows_from_aux` 与各 D 循环行构建器接收的 `segments` 必须由**端点在后端** `await get_effective_segments(project_id, subject, db)` 取得后传入，删除 `["within1"]` 硬编码兜底（改为 subject 默认 preset 兜底）。
- K1 端点当前把余额喂给 `_aging()` 落首段 —— 改为 `_empty_aging(seg_keys)`（全 0），移除 `bucket[first_key]=amount`。
- 骨架键 ↔ UI 列（`useAgingConfig` bands）↔ 审定表/附注账龄汇总三处必须同键（同一 `effective_segments`），不得各写一套。

### fail-open 治理（Requirement 5.1）

`aggregate_aux_by_name` 现在 `except Exception: return [], None, 0`（连 `db.rollback()` 也吞）。这正是平台记过的"最贵一类"假绿：接线错误（列名拼错、传错客户端形态）会伪装成"本项目无此数据"。改法：**保留 fail-open 的返回契约**（调用方无需改），但异常必须 `logger.exception` 记 ERROR，并把原因码带回调用方：

```
AuxAggregationResult
  entries: list[AuxEntry]
  aux_type: str | None
  total_units: int
  reason: 'ok' | 'no_prefixes' | 'no_aux_type' | 'no_rows' | 'no_active_dataset' | 'error'
```

端点按 `reason` 产出不同中文提示（Requirement 4.4 / 5.2）。为不破坏既有 4 个消费者，新增 `aggregate_aux_by_name_ex()` 返回上述结构，旧函数改为其薄壳（保持返回三元组）。

## Components and Interfaces

### 后端

1. `backend/app/services/four_table/aux_aggregation.py`（改）
   - 新增 `aggregate_aux_by_name_ex(...) -> AuxAggregationResult`，异常记 ERROR
   - 旧 `aggregate_aux_by_name` 变薄壳，返回值逐字段不变（既有 4 消费者零改动）
   - 修正 docstring 里过期的「`period_type`/`balance` 必 500」表述
2. `_d3/_d5/_d6/_d7_import_export.py`（改）+ `d_cycle_extraction/detail_aggregation.py`（改）
   - 删裸 SQL，改调共享件；科目前缀由报表映射解析，兜底值保留但注明来源
   - 账龄字段留空（不再塞全额）
3. G-B 类新端点：`POST /api/workpapers/{wp_id}/{x}/import-aux-balance`，结构照 K1（最新、最薄的那份）

### 前端

1. 明细表 toolbar 补「从余额表导入」按钮（与 `+ 添加行` 同排，`:disabled="isReadonly"`，带 loading）
2. 宿主已有「导入导出 ▾」下拉的，作为下拉项接入
3. 有 AutoSeed 的底稿（F1/K1）保留 AutoSeed，手动入口按 merge 语义（Requirement 4.5）
4. 成功后走宿主既有 reload（保证审定表/附注级联刷新，Requirement 4.6）

### D4-6/D4-7 上下游数据联动（Phase 3）

#### D4-6 指标自动预填

后端 `_d4_operating_revenue.py` 的 render 函数在 `html_data` 中新增 `indicator_prefill` 字段：

```python
# 在 D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED 灰度下
indicator_prefill: dict[str, dict] = {}
# 从 trial_balance 取审定数 → 按公式计算每项指标
# 科目映射：1122=应收账款, 6001=主营业务收入, 4103=净利润, 1231=坏账准备, 资产总计=BS合计行
# 涉及非 TB 数据（员工总数等）的指标不预填
html_data["indicator_prefill"] = indicator_prefill
```

指标 key → 计算公式映射（纯函数 `build_d4_indicator_prefill`）：

| key | 公式 | 科目 / 来源 |
|---|---|---|
| `ar-to-assets` | 1122审定 / 资产总计审定 | `trial_balance` |
| `ar-turnover-days` | (期初1122+期末1122)/2 / (6001审定/365) | `trial_balance` + `tb_balance` |
| `ar-turnover-times` | 6001审定 / (期初1122+期末1122)/2 | 同上 |
| `net-profit-margin` | 4103审定 / 6001审定 | `trial_balance` |
| `bad-debt-ratio` | 1231审定 / 1122审定 | `trial_balance` |
| `revenue-per-employee` | — | 需 `project_info` 员工数，**不预填** |
| `profit-per-employee` | — | 同上，**不预填** |
| 其余 4 项 | 需折扣/折让/退货/末季月度/原材料，细粒度 > `trial_balance` 一级科目 | 视数据可用性，有则填无则空 |

前端 `D4TabIndicator.vue` 的 `loadIndicators()` 增加 prefill 消费：

```ts
// 注入 htmlData（或从 allResponses 获取 render-config 下发的 indicator_prefill）
const prefill = props.htmlData?.indicator_prefill ?? {}
indicators.value = DEFAULT_INDICATORS.map(d => {
  const p = prefill[d.key]
  return {
    ...d, current: p?.current ?? 0, prior: p?.prior ?? 0,
    diff1: null, analysis1: '', industryAvg: null, diff2: null, analysis2: '',
  }
})
```

只在 `D4-6-indicators-v2` 无持久化数据时预填；已有数据走正常加载路径。

#### D4-7 月度联动（从 D4-2 汇总）

前端 `D4TabMarginMonthly.vue` 的 `loadMonthly()` 增加 D4-2 种子逻辑：

```ts
function loadMonthly() {
  const resp = props.allResponses.get('D4-7-monthly')
  if (resp?.remark) { /* 已有持久化数据，照常加载 */ return }
  // 无持久化 → 尝试从 D4-2 汇总
  const d42Resp = props.allResponses.get('D4-2-rows')
  if (d42Resp?.remark) {
    const d42Rows = JSON.parse(d42Resp.remark) // StoredRevenueRow[]
    const revenue = new Array(12).fill(0)
    for (const row of d42Rows) {
      if (Array.isArray(row.months)) {
        row.months.forEach((v, i) => { revenue[i] += parseFloat(v) || 0 })
      }
    }
    monthly.value = { revenue, cost: new Array(12).fill(0), priorRevenue: 0, priorCost: 0 }
    // 成本需从 6401 侧取或手填；此处只种子收入
  }
}
```

注意：成本侧月度数据不在 D4-2（D4-2 只有收入明细），cost 留 0 由审计师手填或从成本明细表联动（超出本 phase 范围）。

#### D4-7 产品预填（从 segment_prefill）

前端 `D4TabMarginMonthly.vue` 的 `loadProducts()` 增加 segment_prefill 种子：

```ts
function loadProducts() {
  const resp = props.allResponses.get('D4-7-products')
  if (resp?.remark) { /* 已有持久化数据，照常加载 */ return }
  // 无持久化 → 从 render-config 的 segment_prefill 预填
  const segments = props.htmlData?.segment_prefill
  if (Array.isArray(segments) && segments.length > 0) {
    products.value = segments.map(s => ({
      name: s.label || '', curQty: 0,
      curRevenue: s.current_revenue ?? 0,
      curCost: s.current_cost ?? 0,
      priorQty: 0,
      priorRevenue: s.prior_revenue ?? 0,
      priorCost: s.prior_cost ?? 0,
      remark: '',
    }))
  }
}
```

需要在主入口向 D4-7 传递 `htmlData` prop（当前 D4-7 只收 4 个 prop，不收 htmlData）。

#### D4-7 月度数据导入导出

后端 `_d4_import_export.py` 新增 `D4-7-monthly` 子表支持：
- `_SHEET_HEADERS` 增加 `"D4-7-monthly"` 键：`["1月收入", "2月收入", ..., "12月收入", "1月成本", ..., "12月成本", "上期收入合计", "上期成本合计"]`
- `_SUPPORTED_SHEETS` 增加 `"D4-7-monthly"`
- 导入解析 `_parse_d4_7_monthly_row` 返回 `MonthlyData` 结构
- 导入写入 `D4-7-monthly` 的 remark
- 导出从 `D4-7-monthly` 读取并按列展开

#### D4-7 上期数量导入修复

`_parse_d4_7_row` 增加 `上期数量` 列解析：

```python
"priorQty": _safe_float(_col_val("上期数量")),
```

`_SHEET_HEADERS["D4-7"]` 在 `上期主营业务成本` 后面增加 `上期数量`。

## Data Models

不新增表。写入落既有 `checklist_responses(wp_id, item_id, remark)` JSON 数组，字段与各循环前端 `serializeRows` 的持久化子集逐字一致（派生列不写）。

来源可追溯（Requirement 5.4）：**实际交付采 DEC-4 的轻量方案** —— 不新增统一 `source_kind`/`source_dataset_id` 列（会动 5+ 循环的 store 形态与契约 digest，风险 > 收益），而是用行已有的 `remark` 字段携带中文来源标记（如 K1 写「由辅助余额表(1221·客户)导入」）区分取数行与手工录入；`source_dataset_id` 在端点响应上下文与 Task 9 证据中记录（不落入行）。统一来源列登记为 **deferred 增强**（不阻塞取数本身）。仅当某循环连取数行本身（store item 行结构）都无法承载时，该循环才标 blocked/deferred 并从最终完成数中排除（本 spec 所列宿主均满足行结构，无一因此阻塞）。

## Error Handling

所有面向用户的取数端点必须消费 `aggregate_aux_by_name_ex` 的结构化结果，不得用旧三元组兼容函数决定用户提示。（交付后实态：K1 / D2 / D3 / D5 / D6 / D7 **六个端点均已消费 `_ex` 并回传 `reason`**；D6 经 `aggregate_d_cycle_aux` 中转，K1 于收口阶段从旧薄壳迁至 `_ex`。）`AuxAggregationResult` 的 `reason` 枚举固定为 `ok`、`no_prefixes`、`no_aux_type`、`no_rows`、`no_active_dataset`、`error`；HTTP 响应必须同时返回 `reason`、`imported_count`、`message` 和可选的 `selected_aux_type`。异常路径必须先 rollback 当前事务，再以 ERROR 级别记录 `project_id`、`year`、`account_prefixes` 与异常类型；`no_rows` 等正常空结果不得记录 ERROR。响应经过 `ResponseWrapperMiddleware` 后，前端统一从 `response.data` 读取业务载荷，禁止各循环自行猜测包装层级。

科目来源采用严格优先级：`ReportLineAccountSpec` 成功解析的前缀才可自动取数；显式 fallback 必须在声明式 registry 中登记 `source_ref`、适用 wp_code 和有效期，并由守卫验证 source_ref 仍指向真实模板/报表行。无法证明来源时返回 `no_prefixes`，不得静默使用字面量。

## Correctness Properties

### Property 1: active dataset 过滤不变式
对任意 project/year/科目前缀，`aggregate_aux_by_name_ex` 的 SQL 必须包含 active dataset 谓词；移除该谓词时，存在至少一个真库样本使归集金额变为原值的整数倍（≥2×）。

**Validates: Requirements 2.3, 3.5**

### Property 2: 单一 aux_type 归集不变式

对任意挂了 ≥2 个 `aux_type` 的科目，归集结果必须只来自单一 `aux_type`；`sum(entries.closing)` 不得等于跨全部 `aux_type` 的合计。

**Validates: Requirements 3.5**

### Property 3: merge 持久化不覆盖不变式

对任意 merge 写入，已存在的业务键（客户名/合同名/单位名）行的所有字段逐字节不变，新增行只追加。

**Validates: Requirements 3.4**

### Property 4: 取数只写录入列不变式

端点返回的行 dict 的键集合必须是前端持久化子集的**子集**（不含任何派生列）。

**Validates: Requirements 3.3**

### Property 5: 无账龄来源不伪造不变式

四表侧无账龄来源 ⇒ 取数生成的账龄骨架每段值必须为 0/空，且**不存在**「某单段 == 期初/期末余额」（即不得整额落首段）；对任意非零余额行，`sum(agingAudited 各段) == 0`。含 K1 端点（现状 `_aging()` 落首段属违规，修复后此不变式成立）。

**Validates: Requirements 2.5, 5.3, 7.3**

### Property 6: reason 与异常日志分离不变式

对任意抛异常的内部调用，`aggregate_aux_by_name_ex` 返回 `reason='error'` 且日志含一条 ERROR；`reason='no_rows'` 时日志无 ERROR。二者不可混淆。

**Validates: Requirements 5.1, 5.2**

### Property 8: 账龄骨架与枚举联动不变式

对任意 project/subject，取数生成行的账龄段键集必须逐项等于 `get_effective_segments(project_id, subject, db)` 返回的 `[seg.key ...]`（顺序一致）；切换项目账龄枚举（三年/五年/自定义）后重取，骨架键集必须随之变化且与新枚举一致；已录明细行经 `useAgingMigration` 重映射后不丢已录账龄值。骨架键不得来自硬编码常量（改一处枚举不变则必红）。

**Validates: Requirements 7.1, 7.2, 7.4, 7.5**

### Property 7: 入口真实连通不变式

缺口清单中每条 G-A/G-B 条目，在交付后必须同时满足：组件由真实 renderer registry 挂载；按钮在非只读 DOM 中可见；点击后网络请求命中该循环的已注册路由；响应被该宿主唯一 handler 消费并触发 reload。静态 AST/import/route registry 检查只能作为辅助，不能替代 Vitest 与 Playwright 行为证据。

**Validates: Requirements 1.3, 6.3**

### Property 9: D4-6 指标预填与 TB 一致性不变式

对任意 D4-6 指标 key，如果后端能从 `trial_balance` / `tb_balance` 解析出所需科目余额（两个科目都有值），则 `indicator_prefill[key].current` 必须等于按公式计算的结果（如 `ar-to-assets` = 1122审定数 / 资产总计审定数），误差 ≤ 0.01；如果任一科目无数据，则该 key 不出现在 prefill 中（不伪造 0）。

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 10: D4-7 月度种子与 D4-2 数据一致性不变式

当 D4-7 月度从 D4-2 种子时，`seed.revenue[m]` 必须等于 `D4-2-rows` 中所有产品行的 `months[m]` 之和（m=0..11），不得遗漏行或月份；当 D4-2 无数据时 seed 为全零（不阻塞手填）。种子只在 `D4-7-monthly` 未持久化时执行，已有数据不覆盖。

**Validates: Requirements 8.4**

### Property 11: D4-7 产品预填与 segment_prefill 一致性不变式

当 D4-7 产品表从 `segment_prefill` 预填时，产品数 = `segment_prefill.length`，每行的 `name` / `curRevenue` / `curCost` / `priorRevenue` / `priorCost` 分别对应 `label` / `current_revenue` / `current_cost` / `prior_revenue` / `prior_cost`；`segment_prefill` 为空时产品表留空不伪造。预填只在 `D4-7-products` 未持久化时执行。

**Validates: Requirements 8.5**

## Testing Strategy

1. **共享件单测 + PBT**：`pick_aux_type` 已有守卫（`backend/tests/four_table/test_aux_aggregation.py`）；新增 `aggregate_aux_by_name_ex` 的 reason 分支与 ERROR 日志断言（Property 6）
2. **迁移前后金额对照**：对 D3/D5/D6/D7 在真库跑迁移前/后归集，落对照表；若下降为整数倍，写明是 ①或② 的双算修正（Requirement 6.5）
3. **变异检验**：`backend/scripts/diagnose/mutate_four_table_entry_guards.py`，锚点 ≥3（去 active filter · 去 `aux_type` 锁定 · merge→overwrite），四态判定
4. **前端 vitest**：按钮存在 + `isReadonly` 禁用 + 点击真调端点 URL（断言 URL 字面量，防接错循环）
5. **真栈实测**：Playwright 选一张 G-A/G-B 底稿，0 行 → 点按钮 → 行数 = 只读 SQL 查出的户数，抽 2 行金额逐字对齐
6. **反向自检**：所有守卫先写"故意接错"版本确认必红，再改回

## Open Decisions

- **DEC-1**：按钮摆法。倾向**沿用既有「从余额表导入」平铺按钮**（8 个宿主已如此，一致性优先），仅在宿主已有「导入导出 ▾」下拉时并入下拉。备选（全平台统一收进下拉）会改动 8 个既有宿主，超出本 spec 范围。
- **DEC-2**：D2 的 `importFromAuxBalance(projectId)` 签名与其余不同且 `wp_bound_entry_coverage.json` 中**无** `d2/import-aux-balance` 路由 ⇒ Task 1 必须核实它实际打哪个端点，据此归入 G-C 或 G-B。
- **DEC-3**：科目码解析源。K1 走报表行（BS-009）+ 兜底常量是当前最好范式；若某循环无干净的报表行映射，允许保留显式常量但必须注明 `source_ref`（哪张表/哪行），不得裸字面量。
- **DEC-4**：是否给取数行加统一 `source` 标记字段。倾向**本 spec 不加**（会动 5+ 循环的 store 形态与契约 digest），只在清册中登记为待增强；若 Task 1 发现多数循环已有等效字段则升级为本 spec 范围。
- **DEC-5**：G-B 类新端点的数量上限。若 Task 1 清册产出 > 6 个 G-B，建议按循环拆批次交付（每批 ≤3），避免一次动太多宿主导致 manifest/契约面失控。
