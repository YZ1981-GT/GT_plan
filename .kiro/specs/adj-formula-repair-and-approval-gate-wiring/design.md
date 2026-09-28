# 设计文档：ADJ 取数修复与调整分录确认门接线

> 关联需求：#[[file:.kiro/specs/adj-formula-repair-and-approval-gate-wiring/requirements.md]]
> 工作流：Design-First。类型 bugfix + 口径统一。
> 前置：本 spec 不依赖其他 active spec；与 `disclosure-payload-authority-source` 并行无冲突
> （二者改动文件零交集，见 §九）。

## §一 现状全景：链条已通，断在「调整分录」一段

调研实证的既有事件链（**本 spec 不重建**）：

```
LEDGER_DATASET_ACTIVATED（四表库激活）
  ├→ _auto_map_on_dataset_activated（自动科目映射）→ MAPPING_CHANGED
  ├→ on_data_imported → full_recalc（未审数 → 调整列 → 审定数）
  ├→ _mark_workpapers_stale_all / _invalidate_addr_all / _invalidate_formula_cache_all
  └→ TRIAL_BALANCE_UPDATED（after_commit 自动发）
        └→ ReportEngine.on_trial_balance_updated → REPORTS_UPDATED
              ├→ DisclosureEngine.on_reports_updated
              └→ AuditReportService.on_reports_updated

ADJUSTMENT_CREATED / UPDATED / DELETED / BATCH_COMMITTED
  ├→ TrialBalanceService.on_adjustment_changed（recalc_adjustments + recalc_audited）
  ├→ _mark_workpapers_stale_by_account / _mark_reports_stale_on_adjustment
  ├→ _notify_adjustment_event_sse（分录大厅）
  └→ on_event_adjustment_approved（← 名实不符，见 §二.4）
```

**结论**：上行与下行的**管道都在**，缺陷集中在三处：

| # | 缺陷 | 后果 |
|---|---|---|
| 1 | `ADJ()` 每次求值抛 `ImportError` | 审定表调整列恒空 |
| 2 | `ADJ()` 第二参字面量不匹配 | 即使修 1，AJE/RJE 返回同值 |
| 3 | 三套取数口径不一致 | 底稿数 ≠ 试算表数 ≠ 核对数 |
| 4 | 确认动作不发事件 + handler 名实不符 | 「确认后推送」语义不存在 |
| 5 | 调整列不按确认态过滤 | 草稿分录已进审定数 |

**为什么上行第一段不走公式管理**：四表库 → 试算表未审数走
`tb_balance → account_mapping` 的**映射聚合**（叶子节点去重 + 借贷方向归一 +
未映射叶子继承最近已映射祖先），其代码注释各对应一个已修的会计事故
（父子双计致试算表翻倍 / 漏映射叶子被静默丢弃致资产≠负债+权益 / 无符号存储致负债虚增）。
该段是聚合而非公式，**维持现状**，不纳入公式管理（ADR-ADJ-001 附注）。

---

## §二 缺陷解剖

### 二.1 `ImportError`（L1，探针实测）

`prefill_engine._resolve_adj_formula` 函数体内 lazy import：

```python
from app.models.phase10_models import Adjustment, AdjustmentEntry
```

`phase10_models.py` 顶部只 import `uuid` / `datetime` / `sqlalchemy` / `Base`，
**既无 `Adjustment` 定义也无 re-export**。探针实测：

```
🔴 ImportError: cannot import name 'Adjustment' from 'app.models.phase10_models'
```

**变异证明**（排除探针自身问题）：同一探针内
`app.models.audit_platform_models.Adjustment`（`table=adjustments`）与
`.TrialBalance` 均导入成功。

真实模型位置与列（探针现读 `__table__.columns`）：

| 模型 | 表 | 本 spec 关心的列 |
|---|---|---|
| `audit_platform_models.Adjustment` | `adjustments` | `account_code` · `adjustment_type` · `review_status` · `origin` · `source_ref` · `is_deleted` |
| `audit_platform_models.AdjustmentEntry` | `adjustment_entries` | `standard_account_code` · `detail_account_code` · `report_line_code` · `debit_amount` · `credit_amount` |

🔴 **`origin` 与 `review_status` 只在主表 `adjustments`**，entry 表没有 ⇒
任何按 entry 表取数的实现要过滤这两个维度**必须 JOIN 主表**。

**异常传播路径**（现读）：
`resolve_formula_value` → `_FORMULA_RESOLVERS.get(ft)` → resolver 抛 →
`prefill_workpaper_real` 单元格循环 `except Exception as e: errors.append({...})`
⇒ 该格**不计入 `filled`、值不写、错误进 `errors` 数组随返回值上报**。

即：不是完全静默（有 errors 上报），但用户侧表现为**空白格**，
错误文案是技术性 ImportError 而非业务提示。

### 二.2 第二参字面量不匹配（L2）

实现只认（现读）：

```python
if adj_type.upper() in ("AJE", "审计调整"): ...
elif adj_type.upper() in ("RJE", "重分类"): ...
```

预设实际使用 `aje_net` / `rje_net`。`'aje_net'.upper() == 'AJE_NET'`
⇒ **两个分支皆不命中** ⇒ 不加 `adjustment_type` 过滤 ⇒ **AJE 与 RJE 返回同一合计值**。

**对照组**：`wp_cross_check_service._get_adj_value` 用
`adj_type_filter = "aje" if adj_type == "aje_net" else "rje"`，**匹配预设字面量** ⇒
cross_check 侧对、prefill 侧错。这是同一语义两处实现、一处对一处错的典型。

### 二.3 三套口径对账表（L3，现算）

| 维度 | `recalc_adjustments`（写 TB 列） | `_resolve_adj_formula`（ADJ 公式） | `_get_adj_value`（交叉核对） |
|---|---|---|---|
| 科目列 | `adjustments.account_code` | `adjustment_entries.standard_account_code` + JOIN | `adjustment_entries.standard_account_code` + JOIN |
| `review_status` | **无过滤**（文件内出现 0 次） | **无过滤**（0 次） | `!= 'rejected'`（1 次） |
| `origin` | **排除 `workpaper`**（过滤命中 5 次） | **无**（0 次） | **无**（0 次） |
| 类型字面量 | 按 `adjustment_type` 分组 | `AJE`/`审计调整`/`RJE`/`重分类` | `aje_net`/`rje_net` |
| 符号归一 | `resolve_account_direction`，贷方取反 | 同 | 同 |

🔴 **三处 docstring 都声称与 `trial_balance.aje_adjustment` 口径一致**，
实际三样。注释互相引用形成「看起来已对齐」的假象 —— 这是本 spec 要根治的模式，
不只是修数值。

### 二.4 确认门断点（现读）

`AdjustmentService._change_review_status` 的完整尾部：

```python
for row in adj_rows:
    row.review_status = target
    if target == ReviewStatus.approved:
        row.reviewer_id = reviewer_id
        row.reviewed_at = now
    ...
await self.db.flush()
# ← 函数结束，无任何 _publish_adjustment_event
```

`EventType` 枚举（全量已读）**无 `ADJUSTMENT_APPROVED` 成员**。
状态机 `_VALID_TRANSITIONS`：`draft → pending_review → approved/rejected → draft`，
`approved: set()`（不可再转）。

**名实不符**（`event_handlers/_impl.py`）：

```python
async def on_event_adjustment_approved(payload) -> None:
    """ADJUSTMENT_BATCH_COMMITTED → 全部 DisclosureNote.is_stale=True (R2.1)."""
    ...
event_bus.subscribe(EventType.ADJUSTMENT_BATCH_COMMITTED, on_event_adjustment_approved)
```

同组另两个 handler 名实相符（`on_event_ledger_activated` → `LEDGER_DATASET_ACTIVATED`，
`on_event_workpaper_reviewed` → `WORKPAPER_REVIEW_PASSED`），**只有 approved 这条被降级**。
根因推定：实现时 `ADJUSTMENT_APPROVED` 不存在，遂用最接近的 `BATCH_COMMITTED` 顶替，
函数名保留原意图。归档 spec 标完成 ⇒ 假绿（勘误见 §八）。

### 二.5 测试盲区（本 spec 最强立项依据）

含 ADJ 字面量的测试文件现算 12 个，**真正执行 ADJ 求值的为 0**。
两处 grep 命中 `_resolve_adj_formula` 经现读均为**误报**：
一处是字符串清单元素（resolver 注册完整性检查），一处是注释。

⇒ 全是「预设纯度」静态检查（断言 JSON 里公式字符串的科目码正确），
从不执行求值 ⇒ `ImportError` 长期无人发现。

**教训固化**：静态预设检查与求值端到端检查是两类守卫，
前者绿不代表后者通。需求 7.4 据此要求 `_FORMULA_RESOLVERS` 每个成员都有真实调用用例。

---

## §三 方案：单一取数函数 + 三处改调用

### 组件 1：共享取数模块（新建）

**位置**：`backend/app/services/adjustment_amount_source.py`
（与 `formula_management/four_table_source.py` 同构——后者已是「四表库取数单一入口」的先例）。

**对外 API**：

```python
async def adj_net(
    db: AsyncSession, *, project_id: UUID, year: int,
    account_code: str, adj_type: str,            # 归一前的原始字面量
    include_statuses: frozenset[str] | None = None,   # None = 用默认口径
    exclude_origins: frozenset[str] = frozenset(),    # recalc 侧传 {"workpaper"}
) -> Decimal: ...

def normalize_adj_type(raw: str) -> str:   # -> "aje" | "rje"，无法归一则 raise
```

**设计要点**：

1. **类型归一表**为模块级常量，同时容纳 `aje_net`/`AJE`/`审计调整` 与
   `rje_net`/`RJE`/`重分类`；无法归一 **raise** 而非静默省略过滤（需求 2.3）。
2. **符号归一**复用 `ledger_import.direction_resolver.resolve_account_direction`
   （三处现已共用，不变）。
3. **科目列**统一走 `adjustment_entries.standard_account_code` + JOIN `adjustments`
   （理由见 ADR-ADJ-001）。
4. `origin` / `review_status` 作**显式参数**而非硬编码，使「TB 列排除 workpaper」
   与「公式取数口径」的差异**写在调用点、可被读到**，而不是藏在注释里。
5. 本模块**只 flush 不 commit**（service 铁律），实际它只读不写。

### 组件 2：三处改调用

| 调用点 | 传参 | 说明 |
|---|---|---|
| `recalc_adjustments` | `exclude_origins={"workpaper"}` | 保 V124 防双计约定 |
| `_resolve_adj_formula` | 按 ADR-ADJ-002 裁定 | 修 import + 类型归一 |
| `_get_adj_value` | 同公式口径 | 与底稿显示一致 |

`recalc_adjustments` 当前是**按科目分组的批量聚合**（一次 SQL 出全表），
改为逐科目调 `adj_net` 会退化成 N+1。故本组件对它**只替换口径判定逻辑**
（`review_status` / `origin` / 类型归一 / 符号），保留批量 SQL 形态，
并由属性 **P5** 的对账测试锁死「批量路径与单点路径逐值相同」。

### 组件 3：确认门事件（照搬 ELIMINATION_APPROVED 三件套）

| 部位 | 本 spec 落点 | 样板 |
|---|---|---|
| 枚举 | `EventType.ADJUSTMENT_APPROVED = "adjustment.approved"` | `ELIMINATION_APPROVED = "elimination.approved"` |
| publish | 分录复核 router，`await db.commit()` **之后** | `routers/consolidation.py` |
| handler | 独立文件 `adjustment_approved_recalc_handler.py` | `consol_elimination_recalc_handler.py` |
| 注册 | `main.py` 的 `_register_phase_handlers` | 同处 |

**handler 约定**（逐条照搬样板文件头）：
重算与审批解耦（审批已落库）· 失败记 error **不抛**（不阻断审批）·
幂等（按科目覆盖写，重复触发结果不变）。

---

## §四 事件语义裁定

### 四.1 订阅关系目标态

| 事件 | 订阅者 | 动作 | 现状 |
|---|---|---|---|
| `ADJUSTMENT_APPROVED` | `TrialBalanceService.on_adjustment_changed` | 按科目重算调整列 + 审定数 | 🆕 |
| `ADJUSTMENT_APPROVED` | `on_event_adjustment_approved` | 附注章节标 stale | 改订阅源 |
| `ADJUSTMENT_APPROVED` | `_notify_adjustment_event_sse` | 分录大厅 SSE | 🆕 扩订 |
| `ADJUSTMENT_APPROVED` | `_mark_workpapers_stale_by_account` | 底稿标 stale | 🆕 扩订 |
| `ADJUSTMENT_APPROVED` | `_mark_reports_stale_on_adjustment` | 报表标 stale | 🆕 扩订 |
| `ADJUSTMENT_BATCH_COMMITTED` | 保留既有订阅者 | 不变 | 见 四.3 |

### 四.2 撤回语义（ADR-ADJ-005 覆盖，需求 4.4）

`approved` 不可再转出（`_VALID_TRANSITIONS` 中 `approved: set()`），
但 `pending_review → rejected` 与 `rejected → draft` 会发生。若纳入口径是
「仅 approved」，则这两个转换**不改变**已纳入集合，无需事件；
若纳入口径含 `pending_review`，则 `pending_review → rejected` **会**使金额退出口径，
必须发事件否则下游不回退。

⇒ **事件设计依赖 ADR-ADJ-003 的口径裁定**，两者必须同时定。
本设计采用「仅 approved」（ADR-ADJ-003），故：
新增 `ADJUSTMENT_APPROVED` 一个事件即足够，`rejected`/`draft` 回退无需新事件。
**但** `approved` 之后若分录被**软删除**（`soft_delete`）仍需回退 ——
既有 `ADJUSTMENT_DELETED` 已覆盖该路径，无需新增。

### 四.3 `ADJUSTMENT_BATCH_COMMITTED` 是否保留标附注 stale

**保留**。理由：批量提交意味着一批草稿进入复核流程，附注编制者需要知道
「上游有在途变更」。但**必须换 handler 名**（如 `on_event_adjustment_batch_committed`），
使名实相符（需求 5.3）。即结果是**两个 handler 各订各的事件**，行为都保留。

---

## §五 现算数据（交付时须重算，禁写死）

以下数字为本 spec 编写时的现算值，**tasks 的判据一律写「现算 + 禁写死」**。
复算脚本：`backend/scripts/analyze/` 下临时探针（交付后删，见 tasks 收尾任务）。

| 指标 | 编写时现算值 |
|---|---|
| `prefill_formula_mapping.json` 中 `ADJ()` 出现次数 | 165 |
| 涉及不同科目码数 | 78 |
| JSON 内 block 总数 | 306 |
| 第二参取值分布 | `aje_net` 83 / `rje_net` 81 / `类型` 1 |
| 全仓含 `ADJ(` 的文件数 | 27（tests 11 / scripts 7 / app 6 / data 2 / frontend 1）|
| 含 ADJ 字面量的测试文件数 | 12 |
| **真正执行 ADJ 求值的测试数** | **0** |
| `recalc_adjustments` 文件内 `review_status` 出现次数 | 0 |
| `FormulaContext` 数据源字段数 | 6（无 `adj_data`）|

**受影响下游（消费 `aje_adjustment`/`rje_adjustment`，现算清单）**：
`wp_formula_eval_service`（列名映射 `"AJE调整"→aje_adjustment`）·
`wp_mapping_service` · `wp_fill/_note_draft` ·
`wp_data_rules`（审定表通用规则「期末调整数 = aje + rje」）·
`wp_cross_check_service` · `wp_audit_sheet_tb_service`（`sys_aje` 系统汇总参考值）·
`triple_format_adapter` · `trial_balance_service` · `trial_balance_full_view_service`。

🔴 **关键缓冲**：`trial_balance_full_view_service` 已有
`other_adjustment = audited - unadjusted - aje - rje` 差额列 ⇒
口径收紧后未纳入部分**可观测、不静默**（需求 6.4 据此成立）。

---

## §六 属性（Properties，供 PBT / 守卫锁死）

> `hypothesis` PBT 一律 `max_examples=5`（用户明确要求，禁默认 100）。

- **P1 import 可解析**：`_resolve_adj_formula` 所需模型可导入；对 `_FORMULA_RESOLVERS`
  全部成员做同样断言（防同类 lazy-import 缺陷）。
- **P2 类型归一双向**：`normalize_adj_type` 对 `aje_net`/`AJE`/`审计调整` 均得 `"aje"`，
  对 `rje_net`/`RJE`/`重分类` 均得 `"rje"`；且**对同一输入集，AJE 组与 RJE 组结果必不相等**。
- **P3 非法第二参不静默**：任意不可归一字符串 → raise，**不得**退化为「不加过滤」。
- **P4 单一取数函数**：全仓除 `adjustment_amount_source` 外，
  不得再出现「JOIN adjustments 求 debit-credit 净额」的第二份实现（AST/正则守卫）。
- **P5 三处返回逐值相同**：同 `(project_id, year, account_code, adj_type)`，
  批量路径（`recalc_adjustments` 写入的列值）与单点路径（`adj_net`）逐值相等。
- **P6 origin 维度可参数化**：`exclude_origins` 生效——传 `{"workpaper"}` 与传空集
  在存在 workpaper 来源分录时结果**必不相等**（变异证明）。
- **P7 确认门事件存在且落库后发**：状态转 `approved` → 恰发 1 次
  `ADJUSTMENT_APPROVED`；事件发布**晚于** commit。
- **P8 重复触发幂等**：同一 `entry_group_id` 连续触发 2 次，试算表结果不变。
- **P9 端到端整链贯通**：draft 建分录 → 调整列**未**变 → approved → 调整列与审定数已变
  → `TRIAL_BALANCE_UPDATED` 已发布。
- **P10 名实相符**：`event_handlers` 中 handler 函数名与其订阅的 `EventType`
  语义一致（守卫：函数名含 `approved` 者必订阅 `ADJUSTMENT_APPROVED`）。
- **P11 差额可观测**：未纳入口径的分录金额必出现在 `other_adjustment` 列，不为 0 吞掉。
- **P12 双向变异守卫**：每条「结构性零」断言都配正样本非零断言。

---

## §七 架构决策记录（ADR）

### ADR-ADJ-001：取数收敛到 `adjustment_amount_source`，科目列统一用 `standard_account_code`

**状态**：已接受

**背景**：三套实现里两套用 `adjustment_entries.standard_account_code` + JOIN，
一套用 `adjustments.account_code`。

**决策**：统一用 `adjustment_entries.standard_account_code` + JOIN 主表。

**理由**：`adjustment_entries` 是分录**行**级载体（一张分录多行、每行一个科目），
`adjustments.account_code` 是冗余的行级投影（该表每行也带 `account_code`，
由 `AdjustmentService.create` 写入）。按 entry 表取数语义更准确，
且 `detail_account_code` / `report_line_code` 两个细化维度只在 entry 表，
未来扩展（按报表行取数）不必再改结构。

**代价**：`recalc_adjustments` 需从「单表分组」改为「JOIN 后分组」，
须验证性能（真实 PG 上 `adjustments` 规模见 tasks 实测任务）。

**附注**：四表库 → 试算表未审数的映射聚合**不纳入**本次收敛，
它不是公式而是聚合，且其现有实现承载三个已修会计事故的修复。

### ADR-ADJ-002：`ADJ()` 公式取数**不排除** `origin='workpaper'`

**状态**：已接受

**背景**：`recalc_adjustments` 排除 workpaper 来源（V124，防与审定表 writeback 双计）；
公式侧两套实现都不排除。

**决策**：公式取数口径**保持不排除**，但改为**显式传 `exclude_origins=frozenset()`**
并在调用点注释说明差异原因。

**理由**：`ADJ()` 的语义是「该科目的调整分录净额」，是**信息呈现**，
审计师在底稿上要看到全部调整（含底稿汇聚来源）；而 TB 的 `aje_adjustment` 列参与
`audited = unadjusted + rje + aje` 的**计算**，底稿来源已由审定表 writeback 计入
`audited_amount`，再计一次会双计。两者差异是**语义差异而非缺陷**。

**关键改进**：把这个差异从「注释声称一致、实际不同」改成
「参数显式不同、注释解释为什么」。

### ADR-ADJ-003：试算表调整列只纳入 `review_status == approved`

**状态**：已接受

**背景**：`recalc_adjustments` 当前无 `review_status` 过滤，草稿分录已进
`aje_adjustment`/`rje_adjustment`，并经 `recalc_audited` 进入 `audited_amount`。

**决策**：只纳入 `approved`。

**理由**：① 审定数是对外报表与附注的取数源，未经复核的草稿进正式口径违审计复核流程；
② 与合并模块 **ADR-CONSOL-102** 的既有裁定一致（"统一只认 APPROVED，draft 不进合并数…
未审批的 draft 抵销进合并数会让未定稿的抵销影响正式合并报表，违审计复核流程"）——
主链路与合并链路应同口径，否则同一平台两套审慎标准；
③ 用户明确要求「项目组确认调整分录后」才推送，这正是 approved 的语义。

**代价**：现有项目若大量分录停在 `draft`，升级后试算表调整列会**变小**、
审定数**变化**。差额在 `other_adjustment` 列可观测（P11）。
须在 tasks 中实测真实 PG 的 `review_status` 分布并评估影响量级。

**不选「排除 rejected」**：那等于纳入 draft 与 pending_review，
与 ② 的审慎原则冲突；`_get_adj_value` 现用此口径，本 ADR 令其向 approved 对齐
（但 ADJ() 呈现口径见 ADR-ADJ-002，两者是不同用途，须分别裁定不可混淆）。

🔴 **口径矩阵（消除歧义，三者不同是刻意的）**：

| 用途 | review_status | origin | 依据 |
|---|---|---|---|
| TB 调整列（参与审定数计算） | 仅 approved | 排除 workpaper | ADR-003 + V124 |
| `ADJ()` 底稿呈现 | 仅 approved | 不排除 | ADR-003 + ADR-002 |
| 交叉核对 | 与 `ADJ()` 一致 | 不排除 | 与底稿显示一致才能核对 |

### ADR-ADJ-004：`ADJ()` 暂不进 L1 内核（收口路径留待）

**状态**：已接受（本 spec 范围外，登记路径）

**背景**：`formula_engine._REGISTRY` 已有 `TB`/`SUM_TB`/`PREV`/`AUX`/`NOTE`/`WP`/
`ROW`/`SUM_ROW`/`REPORT` + `IF`/`ABS`/`ROUND`/`MAX`/`MIN`；`ADJ` 不在其中，
`preset_acnr_migration.PENDING_FUNCTION_ALLOWLIST` 把 `ADJ`/`LEDGER`/
`LEDGER_DETAIL`/`COUNT_LEDGER` 标 `pending`。归档 spec 明载
「`ADJ()` 属 prefill 引擎专属函数（未注册进 `formula_engine._REGISTRY`），
按 prefill 词汇表放行并配反向自检防豁免长挂」。

**决策**：本 spec **不**注册 `ADJ` 进 L1。

**理由**：L1 内核是**纯同步函数**（"不依赖 async/DB，由 L2 编排层预载后注入"），
`ADJ` 需 DB 查询。技术上可行的路径是给 `FormulaContext` 加 `adj_data` 字段
（与现有 6 个数据源字段同构）+ L2 预载 + L1 写 `_handle_adj` 纯查 ctx。
但那会牵动 ACNR `grammar_v1`、三处 pending 白名单、drift guard CI 与 306 个预设块的
校验口径，**风险面远超本 spec 的 bugfix 定位**。

**收口路径（留待独立 spec）**：① `FormulaContext` 加 `adj_data: dict[str, dict[str, Decimal]]`
② L2 编排层经 `adjustment_amount_source.adj_net` 批量预载
③ 注册 `_handle_adj` 到 `_REGISTRY` ④ 从 `PENDING_FUNCTION_ALLOWLIST` 移除 `ADJ`
⑤ 同步 `test_h_prefill_extension.VALID_FORMULA_TYPES` 与各 preset purity 守卫。
本 spec 的组件 1 是该路径的**前置**（先有单一取数函数，再谈进内核）。

### ADR-ADJ-005：撤回不新增事件，靠既有 `ADJUSTMENT_DELETED`

**状态**：已接受

**决策**：因 ADR-ADJ-003 取「仅 approved」，且 `approved` 不可转出，
`rejected`/`draft` 转换不改变纳入集合 ⇒ 无需新事件；
approved 后软删除由既有 `ADJUSTMENT_DELETED` 覆盖。

**风险**：若未来放宽口径到含 `pending_review`，本 ADR 失效，须补撤回事件。
已在 tasks 中登记为守卫：口径常量与事件集合的一致性断言。

---

## §八 归档 spec 勘误登记（append-only，不回填归档）

历史档案是审计轨迹，**不修改归档 spec 内容**。以下勘误登记在本 spec：

| 归档 spec | 标记状态 | 实际情况 | 本 spec 处置 |
|---|---|---|---|
| `_archive/08-disclosure-notes/disclosure-note-full-revamp` Task 2.5 | 标完成 | 规划的 `ADJUSTMENT_APPROVED` 订阅**未实现**，实际订阅 `ADJUSTMENT_BATCH_COMMITTED`，函数名保留 approved ⇒ 名实不符假绿 | 需求 5 修正 |
| 同上（`requirements.md` R2.1 事件表） | 列出 `ADJUSTMENT_APPROVED` 为「🆕 本 spec 新增订阅」 | 该事件枚举成员从未创建 | 需求 4 创建 |
| `_archive/05-business-features/trial-balance-version-timemachine` | trigger 枚举含 `adjustment_approved` | 字面量存在但无对应事件驱动 | 需求 4 后可真实触发 |
| 多份 `08-disclosure-notes/*` 循环 spec | 大量 `ADJ('code','aje_net')` 预设标完成 | 预设字符串正确，但求值必抛 `ImportError` ⇒ 值从未落格 | 需求 1/2 修复；**不回填归档 tasks** |

**教训固化**：归档 spec 的「预设已写对」与「预设能求出值」是两件事，
前者由静态纯度守卫保证，后者需求值端到端守卫（需求 7）。

---

## §九 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 修 import 后 165 处预设**首次真正求出值**，可能暴露科目码错配等下游问题 | 分两步：先只修 import + 类型归一，跑真实项目比对 `errors` 数组归零；再动口径 |
| R2 | ADR-ADJ-003 收紧口径使既有项目审定数变化 | tasks 先实测真实 PG `review_status` 分布，量级不可接受则回到设计重议 |
| R3 | `recalc_adjustments` 改 JOIN 后性能退化 | 实测真实 PG 行数 + `explain_query`；必要时加索引（`adjustment_entries.standard_account_code`）|
| R4 | 既有测试固化了错口径，改口径后大面积红 | 逐条判定「测试错」还是「实现错」，禁改断言凑绿 |
| R5 | 与 `disclosure-payload-authority-source` 并行冲突 | 改动文件零交集：本 spec 动 `prefill_engine`/`trial_balance_service`/`wp_cross_check_service`/`adjustment_service`/`event_handlers`/`EventType`；对方动前端载荷层 + `disclosure_stale_marker`。唯一接触面是 `event_handlers/_impl.py`（本 spec 改 approved 订阅源，对方不动该段）|
| R6 | 扩订 SSE / stale handler 造成事件风暴 | 按科目增量（`account_codes`）而非全量；幂等覆盖写（P8）|

---

## §十 交付前自查清单

- [ ] 每条需求至少被某个 task 引用（判据引用闭合性，非仅编号连续）
- [ ] 每条属性 P1~P12 至少被某个 task 引用
- [ ] 每条 ADR-ADJ-001~005 至少被某个 task 引用
- [ ] 所有计数类判据标「现算 + 禁写死」，无写死行号
- [ ] 所有「结构性零」断言配双向变异证明（P12）
- [ ] 探针文件已删（`backend/scripts/analyze/_adj*`）
- [ ] `router_registry` 无需改动（本 spec 不新建 router）—— 若新建须登记
- [ ] service 只 flush、router 层 commit（事件在 commit 后 publish）
- [ ] 真实环境未实测项如实标 `[ ]*` + 「代码已改但未实测」措辞
