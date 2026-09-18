# Design Document: TB 回写显式发布门（tb-writeback-explicit-publish-gate）

## Overview

`d4-dual-mode-formula-governance` 的 Requirement 4.2 确立了原则：审定表向试算表（`trial_balance.audited_amount`）的回写，**必须**经过显式用户确认 + 服务端权限校验 + 幂等 + durable ack；普通保存 / 双模式切换绝不得触发 TB 回写。D4-1 已按此范式改造完成（二次确认 → `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` → 带 `publish_confirmed=True` 的 `WORKPAPER_SAVED` → 幂等 handler）。

但 D4-1 之外，**全平台仍有大量组件绕过该门**，直接调用旧端点 `PUT /api/projects/{project_id}/trial-balance/writeback`（另有 1 处 G6 变体端点 `POST /api/projects/{pid}/trial_balance`）。该旧端点仅 `require_project_access("edit")`、直写 `audited_amount` 后立即 commit 并 publish `TRIAL_BALANCE_UPDATED`，**无二次确认、无 `publish_confirmed` 信号、无幂等 ack**。这意味着：任意审定/保存路径都可能静默改写报表底数、触发报表与错报评价重算，且重复提交会重复写、重复级联。

> **重要修正（census 只读盘点 `census_writeback_call_sites.md`，权威）**：早期估算"100 个前端源文件 + 共享工厂"高估了工作量。按"组件的 TB 回写能力"去重逐点实证后，**真正需完整改造的活路径约 48 处；死代码约 40+ 处（零消费的 FormData 重复定义 / J2 孤儿模块 / 零调用的共享工厂 / D4 残留监听器 / G6 变体端点 / H8 断链）——只需删除+收口，不需二次确认/端点改造/端到端测试；另有 2 处假回写（K5/K7 只 emit 不写 TB）需先做产品决策**。详见 §现状确认。

本设计采用用户拍板的**方案 B（逐组件改造）**：把其余 D~N 审定表组件逐一改走 `publish-to-tb` 显式发布端点（复刻 D4-1 范式），而**不是**在旧端点侧统一加门。方案 B 更彻底——它把"回写"从一个随手可调的写端点，收敛为"必须显式发布"的用户动作，同时消除隐式回写路径。为支撑多科目、损益类发生额、无审定表子码等 D4-1 未覆盖的形态，`publish-to-tb` 端点需要做**向后兼容的入参扩展**（这是本 spec 的关键设计点，也是首个前置任务）。

改造后，旧端点在全部前端调用迁移完毕、CI 守卫就位后，收口为"禁止新增前端直调"，并评估删除或降级为内部调用。

## 关键术语

- **审定数（audited_amount）**：报表 / 审定表取数的权威字段，一般口径 = 未审数 + 账项调整(AJE) + 重分类调整(RJE)；损益类发生额形态为直接给定的最终发生额。
- **绕过端点**：`PUT /api/projects/{project_id}/trial-balance/writeback`（`backend/app/routers/trial_balance.py::writeback_audited_amount`）。
- **显式发布端点**：`POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（`backend/app/routers/wp_html_save.py::publish_determination_to_tb`）。
- **回写 handler**：`_on_d_audit_determination_saved`（`backend/app/services/event_handlers_cycle_linkage.py`），唯一有下游事件级联的 handler。
- **发布确认信号**：`WORKPAPER_SAVED` 事件 `extra` 中的 `publish_confirmed=True` + `confirmed_by` + `publish_token`。

## 现状确认（grep 实证，2026 本 spec 设计阶段）

> 本章节所有条目均由 `Select-String` / grep 全仓实证，非估算。命中口径：`audit-platform/frontend/src/**/*.{ts,vue}`，排除 `__tests__`。

### 1. 绕过端点直调总量与活/死分布（census 权威）

- **`trial-balance/writeback` 字面量命中：116 行**（其中 107 行真实 HTTP 调用，9 行为 D 循环 M1 已迁移的注释）。另有 **1 处变体端点** `useG6MainFormData` 用 `POST /api/projects/{pid}/trial_balance`（非 `trial-balance/writeback`，不在 107 行内，同属回写旁路——死代码）。
- 端点定义：`writeback_audited_amount`，body `{account_code, audited_amount, year?}`；仅 `require_project_access("edit")`；先精确 `standard_account_code` 匹配、失败回退 `LIKE {code}%` 取最新年度首行；`row.audited_amount = Decimal(...)` → `flush()` → **`commit()`** → 失效 TB 缓存 → **`publish TRIAL_BALANCE_UPDATED`**。无 `publish_confirmed`、无 `publish_token`、无 `tb_publish_ack`、无二次确认。
- **按"组件的 TB 回写能力"去重后的活/死分布（D 循环 M1 已处置不计入本次盘点口径）**：

| 维度 | 数量 | 说明 |
|---|---|---|
| **活路径（真实被消费，需完整改造）** | **约 48 处** | E1 / F1–F5 / G1–G3,G5,G7–G14 / H1–H7,H9,H10 / I1–I6（adjudication inline）/ K1–K4,K6,K8–K13 / L1–L8 / M1–M10 / N1–N5 |
| **死代码（零消费，只需删除+收口）** | **约 40+ 处** | 各 `useXFormData.writebackTB/writebackTrialBalance` 中被 adjudication/inline 取代的重复定义 + H8 全链 + K5/K7 无回写 + J2 全模块 + `createChecklistFormData` 工厂 + D4FormData（M1 残留）+ G6 变体端点 |
| **多科目（≥2 科目）** | **8 处** | H1(1601/1602/1603) / H5(1631/1632) / H8(死) / H9(租赁负债+未确认融资费用) / I1(1701/1702/1703) / K1(1221+坏账准备) / K6(资产+负债,动态) / G7(权益+减值,动态) |
| **发生额口径（occurrence）** | **≥14 处** | G10–G14 / H7 / H10 / K8(6601) / K9(6602) / K11(6701) / K12(6301) / K13(6711) / I6(6602) / N5(6801) 等 |
| **sheet 名不可解/存疑（R1 风险）** | **≥20 处（待改造时实证）** | 所有 form-B / 内联 .vue / adjudication-inline 路径当前用旧端点（仅 account_code、无 sheet_name），迁移到 `publish-to-tb` 时须实证审定表真实 sheet 名能否解出 `[D-N]\d+-1`；损益类发生额审定表尤其存疑 |
| **经共享工厂 createChecklistFormData** | **0 处（工厂本身零调用）** | 🔴 工厂 `createChecklistFormData(` 全仓无调用点——含其 `writebackTB` 是死代码 |

- **工作量修正结论**：真实改造约 48（活路径）+ 死代码清理约 40+（删+收口）+ 产品决策 2（K5/K7）。高度同构可批量：M1–M10 / L2–L8 / N2–N5 / G8–G14。

### 1b. 四项意外发现（census 实证，直接影响本 spec 约束）

1. **🔴 J2 整个 composable 模块是孤儿链**：`composables/workpaper/j2/`（含 `useJ2FormData.writebackTB` 2221、`useJ2Integration.onAdjudicationComplete`）**无任何渲染宿主 import**；J2 真实宿主 `J2TabAdjudication.vue` 根本无 TB 回写（既存测试 `ieOrphanBaseline.spec.ts` 已固化此判定）。⟹ 原设计 §3 "J2 特例：保留 events/publish + actuarial 联动" **针对的是死代码，已从本设计删除该约束**（见 §3）。
2. **🔴 共享工厂 `createChecklistFormData` 零调用**：全仓 0 个调用点。⟹ "供大批 checklist 底稿复用、一改受益多个"不成立——它一个底稿都没接，是纯死代码。
3. **🟡 K5/K7 假回写**：K5 `handleTbWriteback` 弹「已回写TB(2701)」成功提示，但只 `emit('save')` + `publishAdjudicated()`（发事件），**从不写 `trial_balance`**；K7 同理只 emit save。⟹ 两循环当前**无真实 TB 回写**，改造前须做产品决策（补真回写 or 维持"仅审定不落 TB"）。
4. **🟡 D 循环 M1 残留死代码**：D4-1 已从 `useD4Adjudication.publishAdjudicated` 移除 `dispatch('d4:writeback-trial-balance')`，但 `GtD4OperatingRevenue.vue` 仍注册 `handleD4Writeback` 监听器 + `useD4FormData.writebackTrialBalance` 仍在——**监听器无 dispatcher = 孤儿死代码**（M1 漏处置这一处，本 spec 补清理）。

### 2. 两种触发形态（改造时都要覆盖）

- **形态 A — composable 直调**：`useXFormData` / `useXAdjudication` 定义 `writebackTB(...)`，内部 `api.put('/api/projects/{pid}/trial-balance/writeback', ...)`。多数 D/F/K/L/M/N composable 属此形态。共享工厂 `createChecklistFormData.ts::writebackTB(amounts: Record<code, amount>)` 供大批 checklist 型底稿复用（逐科目 put + emit `substantive:adjudicated`）。
- **形态 B — 组件监听 window CustomEvent**：宿主组件 `window.addEventListener('{cycle}:writeback-trial-balance', handler)`，handler 内联 `http.put(...)`。已确认命中：`d2:writeback-trial-balance`(GtD2)、`d4:writeback-trial-balance`(GtD4，**D4-1 已改造移除**)、`f1:writeback-trial-balance`(GtF1)、`f5:writeback-trial-balance`(GtF5)、`g10~g14:writeback-trial-balance`(GtG10~G14)。改造时须移除该 dispatch 链，但保留同组件监听的其他事件（如 `d2:save-items`、`f5:save-items`）。

### 3. 下游联动事件（改造时严禁一并删除）

- **`substantive:adjudicated`**：绝大多数 `writebackTB` 成功后 `eventBus.emit('substantive:adjudicated', {accountCode, auditedAmount, wpCode, timestamp})`。该事件经 `crossWpEventBridge`（`main.ts::installCrossWpEventBridge`）在 mitt EventBus ⇄ window CustomEvent 间**双向桥接 + payload 归一**（`auditedAmount`/`adjudicatedAmount`/`auditedTotal` 三别名互填）。下游消费方（必须继续收到）：`services/acnr/useDisclosureSection.ts`（附注 auto-refresh）、`useL1DisclosureData.ts`、`GtF5CostOfSales.vue` 的 F5-7 校验区。
- **~~J2 特例（原约束已删除）~~**：早期设计约束「改造 J2 时保留 `useJ2Integration.ts`/`useJ2FormData.ts` 的 `POST /events/publish` + `actuarial:assumption-changed → B51` 联动」**基于误判——census 实证整个 `composables/workpaper/j2/` 是无渲染宿主 import 的孤儿链，这些联动全部在死代码内，且 J2 真实宿主 `J2TabAdjudication.vue` 无 TB 回写**（`ieOrphanBaseline.spec.ts` 交叉印证）。故本 spec 对 J2 按**死代码清理**处理（grep 0 消费后连带整个 j2 孤儿模块登记删除），不再有"保留 J2 events/publish + actuarial"约束。J1（`J1TabAdjudication` 2211 按钮）是**活路径**，正常真实改造。
- **I6→I2 联动（真实，须保留）**：`useI6Adjudication.writeback`（活）成功后 emit `research:expense-updated`（I6→I2）+ `i6:adjustment-writeback`，改造 I6 时须保留。
- **处置联动**：`disposal:completed` / `h1:disposal-completed`（H1 处置 → H6 自动建清理明细）属独立事件，与 TB 回写正交，不在本 spec 触碰。

### 4. 各形态审定数口径与 sheet_name 可解码性

`publish-to-tb` 端点靠 `extract_determination_wp_code(sheet_name)`（正则 `([D-N]\d+-1)\b`）把 sheet 名解析为 `[D-N]{n}-1` 子码，handler 靠 `wp_code ~ ^[D-N]\d+-1$` 匹配。据此逐组件评估：

| 组件/形态 | 科目数 | account_code 来源 | 审定数口径 | sheet_name 可解 [D-N]{n}-1？ | 触发形态 | 端点扩展需求 |
|---|---|---|---|---|---|---|
| D1~D7、F1~F5、L1~L8、M1~M10、N1~N5（多数） | 单科目 | 硬编码或参数 | 未审+AJE+RJE | 是（审定表 D2-1/F1-1/L1-1…） | A（部分 B） | 无（复用 audit_rows 三分量） |
| D4-1（已改造，参照系） | 双科目 6001+6051 | 常量 | 未审+AJE+RJE | 是（审定表D4-1） | A | 已支持（多 audit_rows） |
| K1 | 双科目 1221+坏账准备 | 派生 | 未审+AJE+RJE | 是（K1-1） | A | 无（多 audit_rows） |
| K6（GtK6HeldForSale） | 双科目 资产+负债 | `tb_source_codes`（动态/项目相关） | 前端已算最终 audited | 需确认 sheet 名 | A（组件内 writebackTB） | 直传预算 audited 行 + 动态多科目 |
| K12（K12TabAdjudication） | 单科目 6301 | 常量 | **发生额（occurrence_amount，前端已算最终值，非三分量分解）** | 需确认（"6711/6301"类损益审定表子码） | B/直调 | **直传预算 audited_amount** |
| K13（K13TabAdjudication） | 单科目 6711 | 常量 | 前端已算 | 需确认 | 直调 | 直传预算 audited_amount |
| G 系列（useG*FormData、GtG10~G14） | 多为单科目 | 硬编码/schema | 前端已算 | 部分 G 底稿**非标准审定表**，sheet 名可能不含 `[D-N]{n}-1` | A+B | 需确认子码；不可解者需端点放宽 or 专门处理 |
| H1~H10（GtH*TabAdjudication） | 单/双科目 | 硬编码或 scope 单一真源 | 前端已算 | 需逐一确认（如 H9 双科目租赁负债+未确认融资费用） | A+B | 双科目直传 |

> **关键观察**：`extract_determination_wp_code` 与 handler 正则都锚定 `[D-N]{n}-1`。对于 sheet 名天然不含该子码的底稿（部分 G 系列、损益类发生额审定），必须在设计阶段逐一确认真实 sheet 名——**不能假设一个端点直接通吃**。这是本 spec 最大设计风险（见 §设计风险）。

### 5. 后端 handler 与 S 类隔离确认

- **`_on_d_audit_determination_saved` 本身已通用**：它消费 `payload.extra.parsed_data.rows[{account_code, audited_amount}]`（直接读 `audited_amount`，不强制三分量），门控 = `wp_code ~ ^[D-N]\d+-1$` **且** `extra.publish_confirmed is True`；用 `tb_publish_ack`（`publish_token` 唯一，`ON CONFLICT DO NOTHING`）做 durable 幂等；服务端用 `confirmed_by` 二次校验 `WORKPAPER_WRITE` 权限；成功后 publish `TRIAL_BALANCE_UPDATED`。
  - **含义**：多科目 = 多个 rows；发生额 = row 里直接给最终 `audited_amount`。handler 无需改动，**扩展集中在端点侧**（把前端预算好的 audited 行透传，而非强制从 `audit_rows` 三分量重算）。
- **旧端点当前口径**：`publish-to-tb` 目前只从 `body.html_data.audit_rows[]` 用 `current_unadjusted + adj_amount(或sys_aje) + reclass_amount(或sys_rje)` 重算 audited。发生额/预算形态无法用此路径，需扩展。
- **S 类独立回写服务**：`SEstimateTBWritebackService` / `STransactionTBWritebackService`（`s_estimate_tb_writeback_service.py` / `s_transaction_tb_writeback_service.py`）仅被 `s_estimate_calculation.py` / `s_transaction_calculation.py` router 调用，**与本 spec 正交，严禁触碰**（非目标）。
- **旧端点合法非审定表调用方**：grep 未发现前端以外的服务内部调用 `writeback_audited_amount`；`n1_deferred_tax_assets_service.py` 已有 DEPRECATED 裸 SQL 旁路（无调用方）。旧端点前端迁移完毕后可安全收口。

### 6. 特例与产品决策（census 发现，改造前须先定）

- **I2 已部分现代化**：`I2TabAdjudication.vue` 的 `writebackTb`（`onAfterSave`）已用**新 per-wp 端点** `POST /api/workpapers/{wpId}/writeback-trial-balance`（非旧 project 端点）。改造 I 循环时须**先评估 I2 是否已合规 / 可直接并入 `publish-to-tb`**，不能当普通旧端点直调改（避免误改已现代化路径）。
- **N1 debounce watcher 自动写 TB**：`useN1Adjudication` 有 debounce watcher 自动调 `formData.writebackTB`（1811 期末），**直接违反 Req 1**（数据变化/普通保存不写 TB）。改造 N1 时须把该自动 watcher 写改为**显式确认发布**（watcher 只保留 emit `substantive:adjudicated`，不写 TB）。
- **K5/K7 假回写——产品决策前置**：K5(2701)/K7(2401) 的「回写TB」按钮当前只 emit save/发事件，**从不写 `trial_balance`**（假回写）。改造 K 循环前须由产品决定：**(a) 补真回写**（走 `publish-to-tb`，与其他循环一致）或 **(b) 维持"仅审定不落 TB"**（保留现状、仅清死代码 `useK5/K7FormData.writebackTB`、去掉误导性成功提示）。默认不假设它们有活回写路径。

## Architecture

### 目标态数据流（方案 B）

```mermaid
graph TD
    U[审计人员] -->|点击"发布到试算表"| C[审定表组件/composable]
    C -->|ElMessageBox 二次确认| CONF{确认?}
    CONF -->|取消| STOP[无副作用返回]
    CONF -->|确认| EP[POST /workpapers/wpId/audit-determination/publish-to-tb]
    EP -->|authorize_wp_edit + check_consol_lock| GATE[权限门/合并锁]
    GATE -->|extract_determination_wp_code| DEC{解出 D-N n-1?}
    DEC -->|否| ERR[400 非审定表]
    DEC -->|是| CALC[计算/透传审定数行]
    CALC -->|publish_confirmed=True + confirmed_by + publish_token| BUS[WORKPAPER_SAVED]
    BUS --> H[_on_d_audit_determination_saved]
    H -->|confirmed_by 权限二校 + tb_publish_ack 幂等| DB[(trial_balance.audited_amount)]
    H -->|publish| TBU[TRIAL_BALANCE_UPDATED → 报表/A13 重算]
    C -.保留.-> EV[emit substantive:adjudicated → 附注刷新]
```

### 普通保存态（改造后不变的保证）

普通保存 / 双模式切换发出的 `WORKPAPER_SAVED` **不带** `publish_confirmed`，handler 在 `extra.get("publish_confirmed") is not True` 处直接 return，对 TB 是 no-op。这是 R4.2 已建立的保证，本 spec 只是把更多组件纳入"只有显式发布才写 TB"的范式。

## Components and Interfaces

### 接口 1：`publish-to-tb` 端点入参契约演进（关键设计点）

**现状契约（D4-1 已用，必须向后兼容）**：

```python
class PublishToTbRequest(BaseModel):
    sheet_name: str                       # 须能解出 [D-N]{n}-1
    html_data: dict                       # {"audit_rows": [{id, account_code,
                                          #   current_unadjusted, adj_amount, reclass_amount}]}
    publish_token: str | None = None      # 缺省则端点合成
```

**扩展契约（新增，二选一路径，向后兼容）**：

```python
class PublishToTbRequest(BaseModel):
    sheet_name: str
    html_data: dict | None = None         # 路径①：审定表三分量重算（原样保留）
    # 路径②：前端预算好的审定行（发生额 / 多科目 / 无三分量分解）
    writeback_rows: list[WritebackRow] | None = None
    publish_token: str | None = None

class WritebackRow(BaseModel):
    account_code: str
    audited_amount: float                 # 前端已算最终审定数
    amount_kind: Literal["balance", "occurrence"] = "balance"  # 语义标注，供审计/日志
```

**端点行为**：
- 若 `writeback_rows` 存在 → 直接构造 `parsed_data.rows`（不走 `fetch_audit_sheet_tb_values` 三分量重算）。
- 否则回退原 `audit_rows` 三分量路径（D4-1 零回归）。
- 二者最终都发相同结构的 `WORKPAPER_SAVED`（`publish_confirmed=True` + `confirmed_by` + `publish_token` + `parsed_data.rows`）。
- `sheet_name` 仍须 `extract_determination_wp_code` 解出 `[D-N]{n}-1`；解不出 → 400（对 §4 中不可解的组件，需在其改造任务中先修 sheet 名或专门评估）。
- 权限 / 合并锁 / 幂等 / handler 均复用既有实现，**不新造平台机制**。

### 接口 2：前端 composable/组件改造范式（复刻 D4-1）

每个组件的 `writebackTB(...)` / CustomEvent handler 改造为：

```typescript
async function publishAdjudicated(): Promise<void> {
  if (readonly.value || publishing.value) return
  // 1) 中文二次确认（危险操作提示）
  try {
    await ElMessageBox.confirm(
      '发布后将把审定数写入试算表（trial_balance），并触发报表/错报评价等下游重算。确认发布？',
      '发布到试算表确认',
      { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return } // 用户取消 → 无副作用
  // 2) 走显式发布端点（多科目/发生额用 writeback_rows）
  const resp = await api.post(`/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`, {
    sheet_name: sheetName.value,
    writeback_rows: [{ account_code, audited_amount, amount_kind: 'occurrence' }],
  })
  // 3) 保留下游联动（附注刷新等）
  eventBus.emit('substantive:adjudicated', { accountCode, auditedAmount, wpCode, timestamp: Date.now() })
}
```

**改造要点**：
- 移除 `api.put('/api/projects/{pid}/trial-balance/writeback', ...)` 直调。
- 移除形态 B 的 `{cycle}:writeback-trial-balance` dispatch/listener 链（但保留 `{cycle}:save-items` 等其他事件监听）。
- **保留** `substantive:adjudicated` emit（及活路径的跨模块联动，如 I6→I2 的 `research:expense-updated`）。J2 不适用——它是死代码（见 §1b/§3）。
- 普通保存路径不再触发任何 TB 写；自动 watcher 写（如 N1）须改为显式确认。

### 接口 3：旧端点收口

- 迁移完成后：`writeback_audited_amount` 加 deprecation 注释 + 服务端可选拒绝外部调用（保留供潜在内部 `publish_confirmed` 场景，或直接删除——由末任务据 grep 结果定）。
- CI 守卫：断言 `audit-platform/frontend/src/**` 中 `trial-balance/writeback` 字面量命中数 = 0（迁移完成后）。

## Data Models

- **`trial_balance`**：`audited_amount`（回写目标，v2 正数口径），按 `project_id + year + standard_account_code` 定位。
- **`tb_publish_ack`**（迁移 V162，已存在）：`publish_token` 唯一约束做 durable 幂等，`accounts_updated` 回填实际写行数供审计。本 spec **不新增表**。

## 分批策略（按审计循环分组，每组一个可验证 milestone）

改造顺序按"形态一致性 + 风险从低到高"排列。**M0（端点扩展）是所有逐组件任务的前置**。

| 批次 | 循环/组 | 组件清单（源文件） | 形态特点 | milestone 验证点 |
|---|---|---|---|---|
| M0 | 端点扩展 | `wp_html_save.py` + schema | `writeback_rows` 路径 + 向后兼容 | 后端集成测试：三分量路径零回归 + 发生额/多科目路径生效 |
| M1 | D 循环 | useD1~D7FormData、GtD2、（D4 已完成） | 单科目为主，标准审定表 | D 审定表发布落库 + 普通保存不写 |
| M2 | F 循环 | useF1~F5FormData、GtF1、GtF5 | 单科目 + 形态 B CustomEvent | 移除 f1/f5 dispatch 链、保留 save-items |
| M3 | L 循环 | useL1~L8FormData、useL1/L3Adjudication、useL1FormData(src/composables) | 单科目负债类 | L1 双路径（composable+adjudication）统一 |
| M4 | M 循环 | useM1~M10FormData | 单科目 | 权益类审定发布 |
| M5 | N 循环 | useN1~N5FormData | 单科目 + N1 已有 DEPRECATED 旁路 | 税费审定发布；确认 N1 旁路不复活 |
| M6 | K 循环 | 活：K1–K4,K6,K8–K13（adjudication/inline/btn）；决策：K5/K7 假回写；死：各 FormData duplicate | **多科目(K1/K6)、发生额(K8/K9/K11/K12/K13)** —— 端点扩展主战场 | 双科目 + 发生额端到端；K5/K7 先决策 |
| M7 | H 循环 | 活：H1–H7,H9,H10（inline .vue/watcher/FormData）；死：useH1/H3/H4/H6/H8/H9 FormData duplicate + H8 断链 | 单/双科目 + 形态 B | H9 双科目、H3 防跨循环污染、H8 死链清理 |
| M8 | G 循环 | 活：G1–G3,G5,G7–G14（form B）；死：G6 变体端点 | 部分非标准审定表，sheet 名可解性存疑（G8–G14 发生额最高） | 逐一确认子码；不可解者专门处理；G6 清理 |
| M9 | I + E + J1 | 活：I1–I6（adjudication inline）/ E1 / J1(2211)；I2 特例(已用 per-wp 新端点)；死：I1–I6 FormData duplicate(BP-5) | I 死代码 duplicate、I6→I2 联动、E1 多科目 | 只改真实载体、保留 I6→I2 联动；I2 先评估合规 |
| M9c | 死代码集中清理 | J2 全模块（孤儿链）+ createChecklistFormData 工厂 + D4 残留（GtD4 监听器+useD4FormData）+ G6 变体 + H8 断链 + 各 FormData duplicate | 零消费，只删+收口 | grep 0 调用后删除；不依赖 M0 端点扩展，可并行 |
| M10 | 收口 | 旧端点 + CI 守卫 | grep=0 断言（含 `trial_balance` 变体）+ 删除/降级决策 | 前端零直调 + CI 卡点 |

### 每组外部依赖 / 降级

- **真实 PG 数据约束**：真实 PG 仅 5 个 standalone 项目，多数循环无对应审定表真实数据。凡缺真实数据的循环，端到端 UAT 标 `data-blocked`，降级为**隔离项目/合成数据**（复用 `seed_consol_uat.py` 式最小合成集）跑 service 层 + 端点集成测试；真实项目补测点标 `[ ]*` 待 live PG。
- **G 系列 sheet 名不可解**：若某 G 底稿 sheet 名无 `[D-N]{n}-1`，降级方案 = 在该组件改造任务内先规整 sheet 名（走审定表命名）或对该单点评估是否纳入本 spec（可能保留旁路并单独登记）。切换点：端点 `extract_determination_wp_code` 返回 None 时的 400。

## Error Handling

- **用户取消二次确认**：`ElMessageBox.confirm` reject → 直接 return，**无任何副作用**（不写 TB、不 emit）。
- **sheet 名不可解**：端点 400「非审定表（无 [D-N]{n}-1 子码）」；前端提示用户，不静默吞。
- **无可回写行**：端点 400，避免空发布产生噪声 ack。
- **权限不足 / 合并锁**：`authorize_wp_edit` → 403；`check_consol_lock` → 423。
- **发布者权限二校失败**：handler `_publisher_can_publish` 拒绝，不写 TB（服务端最后防线）。
- **重复提交**：`tb_publish_ack` `ON CONFLICT DO NOTHING`，`rowcount==0` → 幂等跳过，不重复写、不重复级联。
- **回写失败（旧行为对比）**：旧端点前端 `catch` 仅 `ElMessage.warning`；新范式失败同样提示用户手动确认，不静默成功。

## Testing Strategy

### 单元测试（前端）

- 每个改造组件：`publishAdjudicated` 触发 `ElMessageBox.confirm`；确认 → `api.post` 命中 `publish-to-tb`（断言 body：sheet_name / writeback_rows / 科目码 / audited）；取消 → 无 post、无 emit。
- 断言**不再**调用 `trial-balance/writeback`。
- 断言 `substantive:adjudicated` 仍被 emit（下游附注刷新回归）。

### 后端集成测试

- 端点扩展：`writeback_rows` 路径生效；`html_data.audit_rows` 三分量路径零回归；两路径都发 `publish_confirmed=True` 的 `WORKPAPER_SAVED`。
- 幂等：同 `publish_token` 二次投递只写一次（`tb_publish_ack` 断言）。
- 门控：普通保存（无 `publish_confirmed`）→ TB 不变。
- 权限：`confirmed_by` 无 `WORKPAPER_WRITE` → 拒绝。

### 属性 / 端到端

- 每组至少 1 个端到端验证点（真实或隔离项目）：确认 → 落库 → 报表读到新 audited；重复确认不双写。
- hypothesis PBT（如涉及）`max_examples=5`。

## 安全考虑

- 回写是改写报表底数的高影响操作：服务端 `authorize_wp_edit`（review/edit 级）+ handler `confirmed_by` 二校是双重防线，前端二次确认是 UX 防线。三者缺一不可，本 spec 全部复用既有实现。

## 依赖

- 既有：`publish-to-tb` 端点、`_on_d_audit_determination_saved` handler、`tb_publish_ack`（V162）、`crossWpEventBridge`、`extract_determination_wp_code`。
- 无新表、无新平台机制、无新第三方依赖。

## Correctness Properties

以下正确性属性以断言/测试描述表达，覆盖全部**活路径**改造组件（死代码清理属性见 Property 9）。

### Property 1: 普通保存不写 TB

`∀` 活路径组件，普通保存 / 双模式切换 / 自动 watcher（如 N1）发出的 `WORKPAPER_SAVED` 不含 `publish_confirmed=True` `⟹` `trial_balance.audited_amount` 保持不变。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 显式确认才写 TB

`∀` 活路径组件，`trial_balance.audited_amount` 发生变化 `⟺` 用户经过二次确认且服务端 `publish_confirmed=True` 且 `confirmed_by` 具 `WORKPAPER_WRITE`。

**Validates: Requirements 2.1, 3.1, 3.3**

### Property 3: 幂等——重复确认不双写

`∀ publish_token t`，无论 `t` 被投递多少次，`tb_publish_ack` 对应行恰存在一条，且 TB 各科目最多被该次发布写一次。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 4: 下游联动事件保留

`∀` 活路径组件，改造后成功发布 `⟹` 仍 emit `substantive:adjudicated`（及活路径的跨模块联动，如 I6→I2 的 `research:expense-updated`），附注刷新等下游消费方行为不回归。（J2 不适用——其联动在死代码内，见 Property 9。）

**Validates: Requirements 8.1, 8.3, 8.4**

### Property 5: 迁移后绕过端点零新增调用

迁移完成后 `count(grep 'trial-balance/writeback' in audit-platform/frontend/src/**) == 0` 且 `count(grep 'projects/.*/trial_balance' 变体端点) == 0`（CI 守卫断言，覆盖 G6 变体）。

**Validates: Requirements 9.1, 9.2**

### Property 6: 端点向后兼容

`∀` 原 `audit_rows` 三分量请求，扩展后端点产出的 `parsed_data.rows` 与扩展前一致（D4-1 零回归）。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 7: 用户取消无副作用

用户取消二次确认 `⟹` 无 `api.post`、无 emit、TB 不变。

**Validates: Requirements 2.2**

### Property 8: S 类不受影响

`SEstimateTBWritebackService` / `STransactionTBWritebackService` 及其 router 行为在本 spec 全程不变。

**Validates: Requirements 3.1**

### Property 9: 死代码清理不改变运行时行为

`∀` 死代码（零消费的 `writebackTB`/`writebackTrialBalance` 重复定义、J2 孤儿模块、`createChecklistFormData` 工厂、D4 残留监听器、G6 变体、H8 断链），删除前 grep 确认 0 调用方 `⟹` 删除后无任何运行时行为变化（无活路径依赖它们），且现有测试（含 `ieOrphanBaseline.spec.ts`）不回归。

**Validates: Requirements 9.1, 9.3**

### Property 10: 假回写决策一致性

K5(2701)/K7(2401) 改造后 `⟹` 要么走 `publish-to-tb` 真回写（决策 a），要么不写 TB 且移除误导性「已回写TB」成功提示（决策 b）；二者都 `⟹` 不存在"提示成功但 TB 未变"的假回写状态。

**Validates: Requirements 2.1, 2.2**

## 设计风险（identified）

- **R1（最高）——G 系列/发生额审定表 sheet 名可能不含 `[D-N]{n}-1`**：`extract_determination_wp_code`（正则 `([D-N]\d+-1)\b`）与 handler 正则强锚定该子码。所有当前活路径都用旧端点（仅传 `account_code`、无 `sheet_name`），迁移到 `publish-to-tb` 时每个都要实证审定表真实 sheet 名。若不可解，直接改走端点会 400。**每个真实改造任务的第一步固定为：grep 组件 `sheetName` / render schema（`backend/data/ledger_adapters/wp_render_schema/`）/ `SheetLabels.ts` / `wp_code`，实证 sheet 名能否解出 `[D-N]\d+-1`；不可解则任务内规整命名或按本条降级登记。** 按风险分层（census 实证）：
  - **高风险（损益类发生额审定表，须运行时/render schema 实证）**：G8–G14 / K8(6601) / K9(6602) / K11(6701) / K12(6301) / K13(6711) / N5(6801) / I6(6602) / H7(1621) / H10。
  - **中风险（G 系列非标准审定表，命名多样）**：G1 / G2 / G3 / G5 / G7——须逐一 grep render schema / SheetLabels 实证是否含 `G{n}-1`。
  - **低风险（标准余额类审定表，子码大概率 `xxx-1`，仍需确认）**：E1 / F1–F5 / H1–H6,H9 / I1–I5 / J1 / K1–K4,K6 / L1–L8 / M1–M10 / N1–N4。
  - 切换点 = 端点 `extract_determination_wp_code` 返回 None → 400；处置：可解则直接改走；不可解则规整命名 or 放宽/旁路单独登记。sheet 可解性是运行时属性，静态盘点只能定"存疑/大概率"，本设计不猜。
- **R6（新增）——假回写决策未定则改造无从下手**：K5(2701)/K7(2401) 当前只 emit 不写 TB（假回写）。缓解：把 K5/K7 的产品决策（补真回写 or 维持仅审定）列为 K 循环真实改造的**前置任务**，未决策前不改 K5/K7。
- **R7（新增）——N1 自动 watcher 违反 Req 1**：`useN1Adjudication` debounce watcher 自动写 TB。缓解：N1 改造须把自动写改为显式确认，测试断言"数据变化只 emit 不写 TB"。
- **R8（新增）——误改已现代化的 I2**：I2 已用新 per-wp 端点 `/api/workpapers/{wpId}/writeback-trial-balance`。缓解：I 循环改造先评估 I2 是否已合规/可直接并入，不当普通旧端点直调改。
- **R2——多科目动态科目码（K6 `tb_source_codes`）**：科目码非常量、随项目变。缓解：`writeback_rows` 由前端按当前项目算好后透传，端点不硬编码科目。
- **R3——形态 B CustomEvent 链误删下游**：`{cycle}:writeback-trial-balance` 与 `{cycle}:save-items`、`substantive:adjudicated` 常在同一 `onMounted` 注册。缓解：改造只摘 writeback 那一条 listener，测试断言其余事件仍注册。
- **R4——真实数据缺失致 UAT 假绿**：多数循环无真实审定数据，端到端只能隔离验证。缓解：明确标 `data-blocked` + `[ ]*`，用"代码已改但真实项目未实测"措辞，不假绿。
- **R5——旧端点删除误伤**：删除前须 grep 确认前端零调用且无服务内部合法调用方。缓解：末任务先 grep 断言再决策删除/降级。

## 实施回填与复盘（2026）

> append-only 回填，不改上文原始设计推理（审计轨迹）；凡与上文冲突以本章为准。

### 修正 1 — H7(1621) 口径实证为 balance（非 design 猜的 occurrence）
Task 10 实证：1621 生产性生物资产是余额类资产（成本/公允模式均审定期末余额）→ amount_kind=balance。§4/R1 将其归入“高风险损益发生额”是错的。教训：口径按科目在 trial_balance 的实际取数实证，不按循环名臆断。

### 修正 2 — 假回写不止 K5/K7：H6(1606)/H10(6115) 亦是
Task 10 实证 H6/H10 原只 emit 不写 TB（TB 靠 mount/debounce/跨wp 自动路径写，本身违反 Req 1），按 Property 10 决策(a) 补真回写。Property 10 适用范围应为“全 D~N 中任何'提示成功但当前调用栈不写 TB'的路径”，非枚举 K5/K7。

### 修正 3 — I2 是第三类假回写（非“已现代化”）
Task 13 实证：I2 用的 per-wp 端点 /api/workpapers/{wpId}/writeback-trial-balance 后端无路由定义（grep backend 零命中）→ onAfterSave 每次保存 catch 吞 404 = 运行时 no-op 假回写，且自动写违反 Req 1。裁定=并入 publish-to-tb。教训：“已现代化”必须后端 grep 路由定义对账，不能只看前端调用串。

### 补强 4 — Testing Strategy 应强制“组件级 mount/运行时验证”
G7 return 孤儿 export（模块加载即 ReferenceError）+ G5 isReadonly 对 Ref 恒真（发布门失效）两 bug 纯 diff/ESLint/getDiagnostics 都测不出，全靠 gate 测试 @vue/test-utils mount 真实点击才暴露。因此每个改造组件必须有 gate 测试（确认→post/取消→无副作用/readonly→无post/不调旧端点/仍emit）；「getDiagnostics 0 + ESLint 0」不足以证明运行时正确。

### 补强 5 — 预存失败基线机制
实施中反复靠 git stash 甄别“52 failed 是他 spec 预存”。建议类似大范围逐组件 spec 实施前先落一份预存失败基线清单，实施中对照基线而非每次 stash。

### 未变的正确判断
方案 B、R1 最高风险+逐任务 grep 实证、Property 9 死代码铁律——复盘均确认前瞻性成立。

