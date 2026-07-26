# Design Document

## Overview

H2 在建工程 P1 增强——4 个独立功能块（披露同步 / 审定带入 / 明细 prefill / H4 勾稽），全程 additive 不改共享服务。后端仅改 render 策略加 `detail_prefill`；前端新建 2 个纯函数模块 + 改 3 个组件。无 DB 迁移。

## Data Models

### SyncFromWorkpaperPayload（复用既有，不新增）

```typescript
interface SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string  // 五、23 | 八、23
  current_standard: string
  sub_table_data: Record<string, SubTableRow[]>
  columns?: Record<string, ColumnDef[]>
  _note_texts?: Array<{ section: string; title: string; text: string }>
  year?: number
}
```

### H2DetailPrefillRow（后端 render 输出）

```python
class H2DetailPrefillRow(TypedDict):
    name: str          # 子科目名（去除 1604 前缀）
    cipBegin: float    # abs(opening_balance)
    cipEnd: float      # abs(closing_balance)
    category: str      # '自动种子'
```

### H4PullResult

```typescript
interface H4PullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h4WpId: string | null
  h4AuditedTotal: number | null
}
```

## Architecture

本 spec 纯前端+后端 render 策略改动，不新增 DB 迁移/不改共享服务。

**改动范围**：
- 前端新建 `composables/h2DisclosureSyncPayload.ts`（纯函数 buildH2SyncPayload）
- 前端改 `h2/core/H2TabDisclosureListed.vue` + `H2TabDisclosureSoe.vue`（接同步+反向跳转按钮）
- 前端改 `h2/core/H2TabAdjudication.vue`（接 useAdjudicationBringIn 双实例）
- 前端新建 `composables/h2H4MaterialPull.ts`（跨底稿勾稽纯函数+拉取）
- 后端改 `_h2_construction_in_progress.py` render 策略（加 detail_prefill）
- 前端改 `GtH2ConstructionInProgress.vue`（prefill 种子逻辑）

**不改**：附注模块 / sync-from-workpaper 后端 / trial_balance_service / 公式管理 / 导入导出 / 其它循环。

## Components and Interfaces

### Component: h2DisclosureSyncPayload.ts

纯函数模块，从 H2 allResponses snapshot 构建 sync payload。

```typescript
export function buildH2SyncPayload(
  variant: 'listed' | 'soe',
  snapshot: { allResponses: Map<string, any>; crossSheet: H2CrossSheetData },
  ctx: { wpId: string; projectId: string; year: number; currentStandard: string }
): SyncFromWorkpaperPayload
```

**数据映射（上市 6 张子表，逐字对齐模板 tables[].name + headers）**：
| 子表键（= 模板 tables[].name） | 数据源 | 列（模板 headers 逐字） |
|---|---|---|
| 在建工程 | H2-1 审定表各行 begin/end audited | 项目/期末余额/上年年末余额 |
| 在建工程明细 | H2-2 明细行 endAudited/beginAudited | 项目/期末余额/上年年末余额 |
| 重要在建工程项目变动情况 | H2-2 明细行 movement | 工程名称/期初余额/本期增加/转入固定资产/其他减少/利息资本化累计金额/其中：本期利息资本化金额/本期利息资本化率%/期末余额 |
| 重要在建工程项目变动情况（续）： | H2-2 预算/进度/资金来源 | 工程名称/预算数/工程累计投入占预算比例%/工程进度/资金来源 |
| 在建工程减值准备情况 | H2-1 减值段 | 项目/期初余额/本期计提/本期减少/期末余额 |
| 项  目 | H2-1 工程物资段审定 | 项目/期末余额/上年年末余额 |

> 注：「所有权受限」在模板为 text_sections 文本段（非独立子表），通过 `_note_texts` 推送。

**数据映射（国企 4 张子表）**：
| 子表键 | 数据源 | 列 |
|---|---|---|
| 在建工程 | H2-1 原值段+减值段审定 | 项目/期末余额/期初余额 |
| （1）在建工程情况 | H2-2 明细 | 项目/预算/期初余额/本期增加/转入固定资产/其他减少/期末余额/完工率/累计利息资本化 |
| （2）重要在建工程项目本期变动情况 | H2-2 大额行 movement | 项目/预算/期初/增加/转固/减少/期末/超支情况/资本化利率/本期资本化/累计资本化/资金来源 |
| （3）本期计提在建工程减值准备情况 | H2-1 减值段有变动行 | 项目/本期计提/计提原因 |

### Component: useAdjudicationBringIn（复用，H2 双实例适配）

H2-1 审定表创建两个独立 helper 实例：
- `adjPull1604`：subjectPrefix='1604', direction='debit', rows=原值段行
- `adjPull1605`：subjectPrefix='1605', direction='debit', rows=工程物资段行

`updateCell` 桥接 H2 审定表行模型的 `endAdjustment` 字段（累加）。

### Component: _build_h2_detail_prefill（后端 render）

```python
async def _build_h2_detail_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 1604% 叶子科目构建明细行种子。"""
```

输出结构对齐 `H2DetailRow`：`{name, cipBegin, cipEnd, category:'自动种子'}`。

### Component: h2H4MaterialPull.ts

```typescript
export async function pullH4AuditedForH2(projectId: string): Promise<H4PullResult>
export function buildH2H4MaterialReconcile(h2Total: number, h4Total: number): ReconcileResult
```

复用 `resolveWpId` + `loadResponseItem` 范式（同 h1CipH2Pull/h2L1LoanPull）。

## Correctness Properties

### Property 1: 上市子表键完整性
`buildH2SyncPayload('listed', snapshot, ctx)` 产出的 `sub_table_data` 键集合严格等于模板五、23 `tables[].name` 集合（6 张）。

**Validates: Requirements 1**

### Property 2: 国企子表键完整性
`buildH2SyncPayload('soe', snapshot, ctx)` 产出的 `sub_table_data` 键集合严格等于模板八、23 `tables[].name` 集合（4 张）。

**Validates: Requirements 1**

### Property 3: 列数一致性
每张子表 `rows[i].values.length === columns[key].length`（不多不少）。

**Validates: Requirements 1**

### Property 4: 空文本不传
`_note_texts` 内容全空时 payload 无 `_note_texts` 键。

**Validates: Requirements 1**

### Property 5: 跳转双向一致
`noteDisclosureJump(五、23)` 返回 wpCode='H2' ∧ `noteDisclosureReverseJump.H2.listed === '五、23'`。

**Validates: Requirements 2**

### Property 6: 净额符号正确
bring-in 1604 对 credit>debit 行返回负值净额（=借−贷，资产减少语义）。

**Validates: Requirements 3**

### Property 7: 累加非替换
apply 后 endAdjustment = 旧值 + net。

**Validates: Requirements 3**

### Property 8: 叶子防双算
`_build_h2_detail_prefill` 对 1604/1604.01/1604.02 同时存在时只取 .01/.02（非1604父级）。

**Validates: Requirements 4**

### Property 9: abs 正数
prefill 行 cipBegin/cipEnd 均 ≥ 0（资产借方不产出负数种子）。

**Validates: Requirements 4**

### Property 10: H4 缺失不崩
`pullH4AuditedForH2` 对 H4 底稿不存在时返回 status='wp_missing' + h4Total=null 不抛异常。

**Validates: Requirements 5**

### Property 11: 空载荷保护
sync 空 sub_table_data 后附注 _tables 不变（平台层 no-op）。

**Validates: Requirements 6**

### Property 12: Persist_First 不覆盖
H2-2 已有 ≥1 行明细时 prefill 不种子不追加。

**Validates: Requirements 4, 6**

## Error Handling

- `buildH2SyncPayload`：数据源某 key 缺失时对应子表行填 null 值（不跳过该表以免丢表结构）
- `pullH4AuditedForH2`：网络/解析失败返回 `{status:'error', message}`，UI 友好提示
- `_build_h2_detail_prefill`：tb_balance 查询失败返回空数组（fail-open，前端无种子即手工）
- 双模式 OO config 预拉失败已在 P0 修复中处理（回退 html）


## Testing Strategy

- **纯函数单测**：`h2DisclosureSyncPayload.spec.ts`（Property 1-4）+ `h2H4MaterialPull.spec.ts`（Property 10）+ 后端 `test_h2_detail_prefill.py`（Property 8/9/12）
- **组件验证**：get_diagnostics 全清 + Vite transform 200（全 21 sheet）
- **集成/契约**：覆盖率守卫 `--strict` + noteDisclosureJump vitest 含 H2 case
- **端到端（可选）**：live HTTP round-trip 对真实项目 sync→GET 附注→断言→恢复
- **零回归**：1.2 基线对照，改动前后 H2 全套测试数不减
