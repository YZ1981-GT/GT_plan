# Design Document

## Overview

本设计把 G7 复盘剩余缺口落在**四条既有机制之上**，不新造第二套口径：

| 缺口 | 落地方式 | 复用的既有资产 |
| --- | --- | --- |
| G7 侧发起合并联动（R1） | Main_Group 新增入口组件，直接调既有两个端点 | `previewG7Linkage` / `importG7Linkage`（`consolWorksheetDataApi.ts`）、`g7_consol_linkage_service` |
| G7-2 逐户取数（R2） | 新增后端 aux 归集端点 + 前端纯函数映射 | `_f1_import_export.py` 的 `pick_aux_type` / `get_active_filter` 范式 |
| G7-1 分类核对（R3） | render 注入叶子分类合计 + 审定表核对卡片 | G7 main render 的 `tb_values` 注入点、`calcGroupSubtotal` |
| G7-14 → 审定（R4） | 带入目标改写 **G7-2 权益法行**，G7-1 只显示对照差异 | Cross_Book_Pull（`g7EquityMethodPushG73.ts` 同款）、`g7:detail-updated`、`calcClosingReconVariance` |
| 抽凭铺开（R5） | 三个组件各挂 `GtVoucherSamplingEngine` | `G7TabVoucherCheck.vue` 的 proven props 写法 |
| stale 常驻（R6） | 新增只读薄端点 + 两侧横幅 | `load_linkage_stale_state`（已实现，仅 preview 内被调用） |
| 合并范围 → G7-4（R7） | 新增 `sourcesFromConsolScope` 纯函数 | `syncG7BasicInfoFromSources`（已含 Persist_First + ratioScale） |

### 关键设计决策（含对 requirements 的两处落点纠偏）

**Decision 1（纠偏 R3.1：G7-1 不新增「从 G7-2 带入」按钮）**
读码实证：`G7TabAdjudication.vue` 的 `applyG7DetailRows()` 在 hydrate 时（读 `G7-2-rows`）与收到 `g7:detail-updated` 时**整体重建四个分组的 rows**，AJE/RJE 亦由 `detailAdjRow()` 从 G7-2 的调整字段派生，仅 `varianceNote` 经 `previous` 保留。即 **G7-1 已经是 G7-2 的自动投影**。再加「带入按钮」会：①与投影语义重复；②任何写入 G7-1 的未审/AJE 值在下一次 G7-2 更新时被覆盖，形成"填了又没了"的假象。
→ 本设计不做该按钮。R3.1 的用户意图（审定表未审数与账套一致）由 **R2（G7-2 取数）+ 既有投影**达成；R3 落地为 **Leaf_Category_Source 分类合计核对卡片** + 审定表顶部一行说明「本表行由 G7-2 明细自动投影，请在 G7-2 修改」。

**Decision 2（纠偏 R4 落点：G7-14 带入目标是 G7-2 而非 G7-1）**
同 Decision 1 的原因，带入 G7-1 会被投影覆盖。故 `G7-14 期末余额` 带入目标为 **G7-2 权益法行**（`G7EquityRow`）；写入 G7-2 后由既有 `g7:detail-updated` 事件自动传导到 G7-1（零额外接线）。G7-1 侧只做**逐户对照与差异展示**（口径复用 `calcClosingReconVariance`），不写值。R4.2 的"逐户对照确认"与 R4.3 的 Persist_First 在 G7-2 侧实现。

**Decision 3（G7-2 取数走后端端点，不在前端拼 SQL）**
新增 `POST /api/workpapers/{wp_id}/g7/import-aux-balance`，放在既有 `_g7_long_term_equity_main_import_export.py`。严格照 F1 版实现（`get_active_filter` 取 active dataset、先按 `aux_type` 分组定维度再归集、使用 tb_aux_balance **真实列** `opening_balance/debit_amount/credit_amount/closing_balance`、科目用 `LIKE '1511%'` 前缀）。
🔴 禁止照 D3/D5/D6/D7 的历史 aux 实现（memory 已记录其 SQL 引用不存在的列 `period_type`/`balance`，运行必 500）。

**Decision 4（分类核对数据由 render 注入，不在前端逐科目查 TB）**
G7 main render 策略已向 `html_data` 注入 `tb_values`；本设计 **additive** 增加 `tb_leaf_categories`（1511/1512 叶子子科目按 Category_Map 归并后的合计）。前端只消费，不新增 HTTP 往返，也不产生第二套分类口径。

**Decision 5（G7-4 反向补录复用既有 sync 函数）**
`g7BasicInfoModel.ts` 已有 `syncG7BasicInfoFromSources(rows, sources)`：缺失单位新增、已有单位只补空字段、**不删除** G7-4 独有单位、序列化时打 `ratioScale:'percent'`。R7 的全部 Persist_First / 口径要求由它保证，本设计只新增纯函数 `sourcesFromConsolScope(scopeRows)` 把 `consol_scope` 行转成 `G7BasicInfoSyncSource[]`。

**Decision 6（stale 状态用只读薄端点）**
R1.2 禁止为 preview/import 新建端点；R6 的常驻提示若复用 `preview` 会付全量候选构建成本。故新增只读薄端点 `GET /api/consol-worksheet-data/g7-linkage/{project_id}/{year}/stale`，**函数体只委托既有 `load_linkage_stale_state`**，不含任何映射/计算逻辑，权限 `readonly`。

**Decision 7（灰度只覆盖取数，不覆盖联动入口与提示）**
`G7_FOUR_TABLE_EXTRACTION_ENABLED`（默认 `False`，对齐 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 命名与默认）只门控 R2/R3 的取数与注入；R1/R5/R6/R7 是纯 UI 接线与只读展示，不受该开关约束（各自独立可回退）。

## Architecture

```
                          ┌──────────────────────────────────────┐
四表库                     │ tb_aux_balance (aux_type='客户',1511%) │
                          └──────────────┬───────────────────────┘
                                         │ get_active_filter + pick_aux_type
                       POST /workpapers/{wp}/g7/import-aux-balance
                                         ▼
     ┌───────────────┐  build_g7_detail_rows_from_aux (纯函数)  ┌──────────────┐
     │  G7-2 明细表   │◄──────────────────────────────────────── │  Main_Group  │
     │ (G7-2-rows)   │                                          │   后端 IE     │
     └───────┬───────┘                                          └──────────────┘
             │ g7:detail-updated（既有 window 事件）
             ▼
     ┌───────────────┐   tb_leaf_categories（render 注入，additive）
     │  G7-1 审定表   │◄────────────────────────────────────────── tb_balance 叶子
     │ 投影自 G7-2    │   → 分类合计核对卡片（差异>0.01 告警）
     └───────┬───────┘
             │ 既有 substantive:adjudicated（writebackTb 才回写 1511/1512）
             ▼  试算表

     Method_Group G7-14 ──Cross_Book_Pull(ACNR resolve-instance)──► G7-2 权益法行（对照后带入）
     consol_scope ──sourcesFromConsolScope + syncG7BasicInfoFromSources──► Method_Group G7-4

     Main_Group（G7-1 / 目录）──preview/import（既有端点）──► 合并工作底稿四表 + g7_suggestions
             ▲                                                        │
             └────── GET .../g7-linkage/{pid}/{year}/stale ◄───────────┘（两侧常驻提示）
```

## Components and Interfaces

### 后端

**1. `backend/app/routers/wp_render_strategies/_g7_long_term_equity_main_import_export.py`（追加）**

```python
_G7_AUX_ACCOUNT_PREFIX = "1511"

def build_g7_detail_rows_from_aux(
    aux_entries: Iterable[Sequence],   # (aux_name, opening, debit, credit, closing)
    *, row_limit: int = ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
    source_note: str = "",
) -> list[dict]:
    """纯函数：aux 归集结果 → G7-2 成本法行（section='cost'）。

    - 期末优先取账套 closing，缺失回退 opening+debit-credit；
    - relationship 不臆造：aux 无控制类型信息，一律落 cost 段，由审计师按 G7-4 判断改段；
    - 每行 remark 写入来源溯源串（科目 + aux_type + 取数时间）。
    """

async def aggregate_g7_detail_rows_from_aux(
    db, project_id: str, year: int, *, aux_type: str | None = None, ...
) -> tuple[list[dict], str | None, int, list[str]]:
    """(rows, 选定 aux_type, 归集单位数, 候选 aux_type 列表)。
    先按 aux_type 分组定维度（pick_aux_type，可由入参显式指定），再按 aux_name 归集。"""

@router.post("/api/workpapers/{wp_id}/g7/import-aux-balance")
async def g7_import_aux_balance(wp_id, overwrite: bool = False, aux_type: str | None = None, ...):
    """灰度关闭 → 返回 {ok: True, enabled: False, imported_count: 0}（不触库不写入）。
    merge 语义：按 investeeName 去重，已存在单位不覆盖；overwrite=True 时按名覆盖金额并回报影响行数。"""
```

**2. `backend/app/routers/wp_render_strategies/_g7_long_term_equity_main.py`（render 注入，additive）**

```python
_G7_CATEGORY_MAP = {          # 由 postgres 实证的子科目 → G7-2 列语义
    "1511.01": "cost",        # 对子公司的投资
    "1511.02": "cost",        # 联营/合营投资成本
    "1511.03": "profit_loss", # 损益调整
    "1511.04.01": "oci",      # 其他权益变动-其他综合收益
    "1511.04.02": "other_equity",
    "1512": "impairment",
}

async def _build_g7_leaf_categories(ctx) -> dict | None:
    """tb_balance 1511%/1512% 叶子科目 → 分类合计。
    叶子判定：某 code 不是任何其它 code 的前缀（防父子双算）。
    灰度关闭返回 None；查询异常 fail-open 返回 None（不阻断 render）。"""
```
输出形如 `html_data.tb_leaf_categories = {"cost": …, "profit_loss": …, "oci": …, "other_equity": …, "impairment": …, "unmapped": [{"code","name","amount"}], "source": "tb_balance"}`。

**3. `backend/app/routers/consol_worksheet_data.py`（追加只读薄端点）**

```python
@router.get("/g7-linkage/{project_id}/{year}/stale")
async def g7_linkage_stale(project_id, year, user=Depends(require_project_access("readonly")), db=...):
    return await load_linkage_stale_state(db, project_id, year)   # 仅委托，无新逻辑
```

**4. `backend/app/core/config.py`**：`G7_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`。

### 前端

**1. `composables/g7ConsolLinkageEntry.ts`（新建，Main_Group 侧联动入口逻辑）**

```ts
export interface G7LinkageEntryState { preview: G7LinkagePreview | null; loading: boolean; stale: boolean; staleSheets: string[] }
export function useG7ConsolLinkageEntry(projectId: Ref<string>, year: Ref<number>) {
  // openPreview() → previewG7Linkage；confirmImport() → importG7Linkage(expected_versions 透传)
  // 409 → ElMessage.warning + 自动重新 openPreview()；422 → 显示后端 detail 原文
  // refreshStale() → GET .../stale（失败静默）
  // gotoConsolidation() → router.push 合并工作底稿
}
```
挂载点：`G7TabAdjudication.vue` 头部与 `G7TabDirectory.vue`，弹窗组件 `G7ConsolLinkageEntryDialog.vue`（预览摘要 + 未匹配主体 + 建议草稿条数 + stale 提示 + 确认导入按钮，`:disabled="isReadonly || !canEdit"`）。

**2. `composables/g7AuxExtraction.ts`（新建纯函数 + 调用封装）**

```ts
export interface G7AuxExtractionResult { rows: Partial<G7CostRow>[]; auxType: string | null; totalUnits: number; truncated: boolean; message: string }
export function mergeAuxRowsIntoDetail(
  state: G7DetailState, incoming: Partial<G7CostRow>[], opts: { overwrite: boolean },
): { state: G7DetailState; added: number; filled: number; skipped: number }
// 按 investeeName 规范化（去空白/全角括号）匹配；overwrite=false 时只填空字段，已有值不动
```
挂载点：`G7TabDetail.vue` 工具栏「从四表取数」（灰度关闭时按钮隐藏）。

**3. `composables/g7EquityMethodPullToDetail.ts`（新建，Cross_Book_Pull）**

```ts
export interface G7EquityClosingRow { investeeName: string; closingAmount: number }
export function extractG7_14ClosingRows(payload: unknown): G7EquityClosingRow[]           // 纯函数
export function buildEquityPullDiff(detail: G7DetailState, src: G7EquityClosingRow[]): Array<{ investeeName: string; current: number; incoming: number; diff: number; matched: boolean }>
export async function pullG7_14ForDetail(projectId: string, wpCodeParent: 'G7-4'): Promise<G7EquityClosingRow[]>  // ACNR resolve-instance → checklist-responses
```
挂载点：`G7TabDetail.vue`「从 G7-14 带入期末余额」→ 对照弹窗 → 确认后按 Persist_First 写入 `G7EquityRow`；G7-1 侧新增只读「G7-14 对照差异」行（`calcClosingReconVariance`）。

**4. 抽凭铺开**：`G7TabSubsequentMeasurement.vue`(G7-10)、`G7TabDisposalSingle.vue`(G7-11)、`G7TabDisposalPackage.vue`(G7-12) 各加

```vue
<GtVoucherSamplingEngine v-if="!isReadonly && wpId && projectId"
  :project-id="projectId" :workpaper-id="wpId"
  account-code="1511" phase="final" :year="auditYear" @filled="onSampleFilled" />
```
`onSampleFilled(payload)` 解构 `payload.samples`，按各表既有行模型映射（凭证号/日期/借贷金额/对方科目），按 `voucherNo` 去重。

**5. stale 常驻提示**：`ConsolWorksheetTabs.vue` 主界面顶部横幅（消费 `/stale`，列出 `stale_sheets`；成功导入后 `refreshStale()` 清除）；`GtG7LongTermEquityMain.vue` 顶部同款提示（文案「合并侧联动结果已过期，请重新联动」）。

**6. G7-4 反向补录**：`g7BasicInfoModel.ts` 追加

```ts
export function sourcesFromConsolScope(scopeRows: Array<Record<string, unknown>>): G7BasicInfoSyncSource[]
// company_name → investeeName；ownership_ratio → directHoldingRatio（percent 口径，>1 视为已是百分数）
// company_type/inclusion_reason 映射到 acquisitionMethod/备注类字段；is_included=false 的行跳过
```
`G7TabBasicInfo.vue` 新增「从合并范围带入」→ `GET /api/consolidation/scope?project_id&year` → `sourcesFromConsolScope` → 既有 `syncG7BasicInfoFromSources` → 提示 `added/filled`。

## Data Models

### Aux_Investee_Source → G7-2 成本法行

| 来源 | 目标字段 | 说明 |
| --- | --- | --- |
| `aux_name`（`aux_dimensions_raw` 的单位名） | `investeeName` | 空名跳过 |
| `opening_balance` | `openingAmount` | |
| `debit_amount` | `increaseAmount` | 资产借方增加 |
| `credit_amount` | `decreaseAmount` | |
| `closing_balance` | 校验用 | 期末由 `recalcG7CostRow` 派生；账套 closing 与滚存不一致时取 closing 并在 remark 记差异 |
| — | `section` | 恒 `'cost'`（aux 无控制类型，不臆造 relationship） |
| — | `remark` | `由辅助余额表(1511·{aux_type})导入 @{timestamp}` |

比例列（`investmentRatio` / `openingRatio` 等）**不取数**（aux 无持股信息），保持 0 由审计师从 G7-4 带入。

### Leaf_Category_Source → 审定表核对

| 分类 | 叶子科目 | 对应审定表口径 |
| --- | --- | --- |
| `cost` | `1511.01` + `1511.02`（及其叶子） | 投资合计行 `closingUnadjusted` 中的成本部分 |
| `profit_loss` | `1511.03` | 权益法两组的损益调整（经 G7-2 汇总） |
| `oci` / `other_equity` | `1511.04.01` / `1511.04.02` | 其他权益变动 |
| `impairment` | `1512` | 减值组小计 |
| 合计核对 | `cost+profit_loss+oci+other_equity` vs 投资合计 `closingUnadjusted`；`impairment` vs 减值组小计 | 差异 > 0.01 → 告警（提示分类归属 / 未纳入范围 / 账套未标准化） |

未落入 Category_Map 的叶子进 `unmapped`，在核对卡片列出（**不并入任何分类**，避免臆造归属）。

### consol_scope → G7BasicInfoSyncSource

| 来源列 | 目标 | 说明 |
| --- | --- | --- |
| `company_name` | `investeeName` | 空名跳过 |
| `company_code` | 备注/编码字段 | 仅补空 |
| `ownership_ratio` | `directHoldingRatio` | 百分数口径；`0<v<=1` 且全部 ≤1 时按小数换算（复用 `looksLikeFractionRatio`） |
| `company_type` | `groupType` 建议值 | 仅新增行使用；已有行**不改**分类（G7-4 手工判断优先） |
| `inclusion_reason` | 取得方式/备注 | 仅补空 |
| `is_included=false` | — | 跳过 |

## Correctness Properties

### Property 1: 叶子过滤无双算
对任意科目集合（含父子层级），`_build_g7_leaf_categories` 的各分类合计等于仅叶子科目金额之和；任一被其它 code 作为前缀的 code 不参与求和。
**Validates: Requirements 3.4, 10.1**

### Property 2: Persist_First 不改已填值
对任意 `G7DetailState` 与任意取数结果，`mergeAuxRowsIntoDetail(..., {overwrite:false})` 后，原本非零/非空的字段值逐字不变；仅空值被填充。
**Validates: Requirements 2.3, 4.3, 10.2**

### Property 3: 单一 aux_type 不跨维相加
当同一科目存在多个 `aux_type` 时，归集结果等于**选定单一 aux_type** 子集的合计，且总额不超过任一维度的合计。
**Validates: Requirements 2.2, 10.3**

### Property 4: 按名归并幂等
同一取数结果连续应用两次，`state` 的行数与各字段值不变（不产生重名重复行）。
**Validates: Requirements 2.1, 10.4**

### Property 5: 灰度关闭零写入
`G7_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，取数端点返回 `imported_count=0` 且不执行任何 `INSERT/UPDATE`；render 不注入 `tb_leaf_categories`。
**Validates: Requirements 2.6, 9.1, 10.5**

### Property 6: 无数据不臆造
Aux_Investee_Source 为空时返回空行集合与提示文案，**不**用科目合计生成任何逐户行。
**Validates: Requirements 2.5**

### Property 7: 取数可溯源
每个由取数产生的行都带非空来源串（科目 + aux_type + 时间）。
**Validates: Requirements 2.4**

### Property 8: G7-1 投影语义不变
应用本 spec 后，`applyG7DetailRows` 仍整体重建四组行且保留 `varianceNote`；核对卡片只读不写 rows。
**Validates: Requirements 3.5, 9.4**

### Property 9: 差异阈值一致
分类核对与既有 TB 核对使用同一阈值 0.01 与同一四舍五入口径（分位）。
**Validates: Requirements 3.2, 3.3**

### Property 10: 跨册缺源安全
Method_Group 未实例化或 G7-14 无数据时，`pullG7_14ForDetail` 返回空集合，G7-2/G7-1 状态不变且无异常抛出。
**Validates: Requirements 4.4**

### Property 11: 联动冲突自愈
`import` 返回 409 时前端不重试写入，而是重新 `preview` 并提示；`expected_versions` 始终取自最近一次 preview。
**Validates: Requirements 1.3**

### Property 12: stale 提示与导入一致
成功 `import` 后 `/stale` 返回 `linkage_stale=false`，两侧提示消失；`/stale` 请求失败时不显示提示且不抛错。
**Validates: Requirements 6.3, 6.4**

### Property 13: 反向补录不删不覆盖
`sourcesFromConsolScope` + `syncG7BasicInfoFromSources` 后，G7-4 原有行不减少、原有非空字段不变、序列化带 `ratioScale='percent'`。
**Validates: Requirements 7.2, 7.3**

### Property 14: 抽凭回填去重
同一 `voucherNo` 重复回填只产生一行；缺 `wpId`/`projectId`/只读态时抽凭入口不渲染。
**Validates: Requirements 5.3, 5.4**

### Property 15: 合并服务语义不变
`g7_consol_linkage_service` 的字段映射、比例口径、只填空合并与「不自动生成抵消分录」在本 spec 前后逐字节等价（契约测试锁定函数签名与关键常量）。
**Validates: Requirements 9.2**

## Error Handling

| 场景 | 处理 |
| --- | --- |
| aux 查询异常 | 端点 `rollback()` + 返回 `ok:True, imported_count:0` + message 说明取数失败（不 500，不阻断底稿） |
| `tb_leaf_categories` 查询异常 | render fail-open 返回 `None`，核对卡片显示「账套分类合计不可用」 |
| `preview` 422（多实例/未生成/年度不一致） | 弹窗显示后端 `detail` 原文，禁用确认导入 |
| `import` 409 | 提示「G7 源数据已变更」+ 自动重新 preview，**不**自动重试导入 |
| `/stale` 失败 | 静默降级（不显示提示、不打断页面） |
| ACNR `resolve-instance` 未命中 | 视为来源缺失（Property 10） |
| `consol_scope` 空 | 提示「合并范围未维护」，G7-4 不变 |
| 抽凭 `payload.samples` 缺失/非数组 | 忽略并提示「未获取到样本」 |

## Testing Strategy

**后端**
- `tests/g7_extraction/test_g7_aux_extraction.py`：`build_g7_detail_rows_from_aux` 纯函数（映射、空名跳过、closing 优先、来源串）+ `aggregate_*` 的 aux_type 选定（monkeypatch db）。
- `tests/g7_extraction/test_g7_leaf_categories.py`：叶子过滤（Property 1）、Category_Map、unmapped、灰度关闭返回 None（Property 5）。
- `tests/g7_extraction/test_g7_linkage_endpoints.py`（R8.1/R8.2）：`preview`/`import` 成功路径、409（`assert_expected_versions`）、422、readonly 不可导入；import 的 DB 写入（四表只填空、`consol_scope` 不覆盖 `is_included`、`g7_suggestions` 写入、stale 置位/清零）。
- `tests/g7_extraction/test_g7_pbt.py`：hypothesis 覆盖 Property 1/2/3/4/5（`max_examples` 走全局 fast profile）。
- 契约测试：`load_linkage_stale_state` 被新端点直接委托（源码断言无额外逻辑）+ `g7_consol_linkage_service` 关键函数签名与常量（Property 15）。

**前端**
- `g7AuxExtraction.spec.ts`：`mergeAuxRowsIntoDetail` Persist_First / overwrite / 幂等 / 名称规范化匹配（Property 2/4）。
- `g7EquityMethodPullToDetail.spec.ts`：`extractG7_14ClosingRows` / `buildEquityPullDiff` / 缺源返回空（Property 10）。
- `g7BasicInfoModel.spec.ts`（追加）：`sourcesFromConsolScope` + 既有 sync 的不删不覆盖与 ratioScale（Property 13）。
- `g7ConsolLinkageEntry.spec.ts`：409 → 重新 preview 不重试写入（Property 11）、422 文案、readonly 禁用、`/stale` 失败静默（Property 12）。
- 抽凭：三组件各断言 props 齐备 + 只读隐藏 + `voucherNo` 去重（Property 14）。
- 零回归：`G7TabAdjudication.spec.ts` 保留既有投影断言（Property 8）；`ConsolWorksheetTabs` 既有 74 测试全绿。

**验证门（每波必跑）**
`get_diagnostics` 全清 + 改动 `.vue`/`.ts` 经 `curl.exe` 查 Vite transform 200 + 相关 vitest/pytest 全绿；pre-existing 失败用 `git stash` 区分。Playwright 端到端标记为可选（需实例化 G7 三册 + 有 1511 辅助余额的项目）。
