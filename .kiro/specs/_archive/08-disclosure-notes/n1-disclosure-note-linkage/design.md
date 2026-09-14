# Design Document

## Overview

把 N1（递延所得税资产，1811）两张披露 sheet 接入附注模块的三条链：**结构化推送（S）**、**正向跳转（J）**、**反向跳转 + 定向刷新（R）**。复用 `disclosure-table-sync-convergence` 已 proven 的范式（`buildXSyncPayload` + `columns` + `_note_texts` + `POST .../sync-from-workpaper`），**不新造后端能力**。

唯一非常规点：五、30 / 八、31 章节由 **N1 与 N3 共用**，且其中两张子表在同一张表内混合资产段与负债段行；`sync_from_workpaper` 对 `sub_table_data` 是「按键浅合并、同名键整体覆盖」，因此必须定义章节内**子表所有权**（见 Decision 1）。

## Architecture

```
┌─ N1 底稿（专属组件 GtN1DeferredTaxAssets） ───────────────────────────┐
│  N1-2 明细表 ─┐                                                      │
│  N1-5 亏损表 ─┼─► useN1DisclosureSource（真源键 + engine 重算）        │
│  N1-1 审定表 ─┘        │                                              │
│                        ▼                                              │
│   N1TabDisclosureListed / N1TabDisclosureSoe（表格 + 说明文本）        │
│                        │  ①「同步到附注」                              │
│                        │  ②「↩ 跳转回附注」                            │
└────────────────────────┼──────────────────────────────────────────────┘
                         │ buildN1SyncPayload(variant, snapshot, ctx)
                         ▼
   POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper
     body: { wp_id, sheet_name, section_id, sub_table_data, columns,
             current_standard, year }
                         │
                         ▼
┌─ 后端（既有，不改） ─────────────────────────────────────────────────┐
│  wp_disclosure_sync_service.sync_from_workpaper                      │
│   · _resolve_target_year（payload year > projects.audit_year）         │
│   · sub_table_data 浅合并（未推送子表保留；空载荷 no-op）               │
│   · _note_texts pop → text_content                                    │
│   · columns → table_data._sub_table_columns                           │
│  get_note_detail → note_sub_table_projector.project_sub_tables → _tables│
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌─ 附注模块 DisclosureEditor ──────────────────────────────────────────┐
│  · 渲染 _tables（列头来自 columns）+ text_content                     │
│  · ③「跳转至披露表」 ← resolveNoteDisclosureJumpTarget（新增 N1 分支） │
│  · ④ useNoteRefresh 定向刷新 ← disclosure:note-text-updated(1811)     │
└──────────────────────────────────────────────────────────────────────┘
```

## Decisions

### Decision 1（核心）：共用章节的子表所有权 — 采用方案 A（N1 单一 owner，无后端改动）

| 子表（模板 `tables[].name`） | 内容 | Owner | 说明 |
|---|---|---|---|
| 未经抵销的递延所得税资产和递延所得税负债 | 资产段 + 负债段行 | **N1** | N1 推完整行；负债段值取自 `N1-4-total-deferred-tax-liability`（`useN1CrossSheet.n1ToN3Correspondence`）或 N3 发布键；取不到 → 值为 `null` |
| 以抵销后净额列示的递延所得税资产或负债 | 资产行 + 负债行 | **N1** | 同上；互抵金额无独立来源时留 `null` |
| 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细（soe：未确认递延所得税资产明细） | 纯资产侧 | **N1** | 来自披露表 Section 3 |
| 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | 纯资产侧 | **N1** | 来自披露表 Section 4（N1-5 派生，按到期年度聚合） |

理由：①四张表里两张纯资产侧、两张以资产为主体（负债段只有小计级），N1 作为 owner 语义自然；②零后端改动，不动 `sync_from_workpaper` 浅合并语义（Req8.3）；③N3 后续 spec 落地时**不得推送**这两张共用表，只能发布跨底稿键供 N1 取用（若将来确需双向推送，再按方案 B 引入 `sub_table_merge_mode`，属独立变更）。

不选方案 B 的原因：行级合并语义是共享服务的行为改动，影响 43+ 现有调用点的回归面，且当前无第二个共用章节场景，属过早抽象。

### Decision 2：正向跳转默认落 N1

五、30 / 八、31 命中时统一返回 `wpCode='N1'`（资产为主体、且当前只有 N1 有披露 sheet 结构化推送）。N3 备选入口留扩展位（注释 + reverse map 预留 `N3` 条目），不在本 spec 实现。

### Decision 3：负债段/互抵缺失用 `null` 不用 0

审计呈现上 0 与"未取到"语义不同；附注模块对 `null` 显示空白，对 0 显示 0.00 会被误读为已核实为零。

### Decision 4：不改披露表现有区块结构

披露表 Section 1（已确认明细，含可抵扣差异/税率/确认/转回列）比附注模板表列更丰富，属底稿工作口径；推送时只投影模板要求的两列（期末余额 / 上年年末余额｜期初余额），不裁剪底稿显示。

## Components and Interfaces

### 1. 新建 `composables/n1NoteSectionMap.ts`（纯函数，单一真源）

```ts
export const N1_NOTE_SECTION = { listed: '五、30', soe: '八、31' } as const
export const N1_DISCLOSURE_SHEET = {
  listed: '附注披露信息（上市公司）',   // 实现时以 workpaper_sheet_classification 核实
  soe: '附注披露信息（国企）',
} as const

export type N1Variant = 'listed' | 'soe'

/** 子表键常量（逐字取自附注模板 tables[].name，按变体分别定义） */
export const N1_SUB_TABLE_KEYS: Record<N1Variant, {
  unoffset: string; netOffset: string; unrecognized: string; lossExpiry: string
}>

export interface N1DisclosureSnapshot {
  recognizedRows: Array<{ item: string; beginBalance: number; endBalance: number; isTotal?: boolean }>
  unrecognizedRows: Array<{ item: string; amount: number; unrecognizedAsset: number; reason: string }>
  lossExpiryRows: Array<{ expiryYear: string; unrecovered: number; priorUnrecovered?: number; remark?: string }>
  liability: { endBalance: number | null; priorBalance: number | null }
  offset: { assetOffsetEnd: number | null; assetNetEnd: number | null; assetOffsetPrior: number | null; assetNetPrior: number | null
            liabOffsetEnd: number | null; liabNetEnd: number | null; liabOffsetPrior: number | null; liabNetPrior: number | null }
  texts: Array<{ section: string; title: string; text: string }>
}

/** 纯函数：构造 sync 请求体（含 sub_table_data / columns / _note_texts） */
export function buildN1SyncPayload(
  variant: N1Variant,
  snapshot: N1DisclosureSnapshot,
  ctx: { wpId: string; year: number },
): {
  wp_id: string; sheet_name: string; section_id: string
  sub_table_data: Record<string, any[]>
  columns: Record<string, Array<{ key: string; label: string; is_label?: boolean; align?: string }>>
  current_standard: 'listed_standalone' | 'soe_standalone'
  year: number
}
```

约束：
- `sub_table_data` 与 `columns` 的键集合**必须相同**（Property 2）。
- 列头逐字取模板：listed = `['项目','期末余额','上年年末余额']`；soe = `['项目','期末余额','期初余额']`；亏损到期表 listed = `['年份','期末余额','上年年末余额','备注']`、soe 同构（期初余额）。
- `texts` 为空数组时不写入 `_note_texts`（Property 5）。

### 2. 披露组件改动（`N1TabDisclosureListed.vue` / `N1TabDisclosureSoe.vue`）

- 顶部工具栏新增：
  - `同步到附注`（success，`:loading="syncing"`）→ `buildN1SyncPayload` → `http.post`（读 `resp.data` 解包）→ 成功后 `eventBus.emit('disclosure:note-text-updated', {...accountCode:'1811', sectionIds:[章节]})`；`ERR_CANCELED` 静默。
  - `↩ 跳转回附注（五、30 / 八、31）`（split-button：主按钮当前变体，下拉可切另一变体）→ `buildNoteJumpRoute(projectId,'N1',variant)`。
- `year` 显式取 `props.year || useAuditContext().year`（Req2.4）。
- 说明/结论文本纳入 `snapshot.texts`。

### 3. 正向跳转 `views/composables/noteDisclosureJump.ts`

新增：
```ts
const N1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
const N1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'
export function isN1DeferredTaxNoteSection(section: string, variant?: string): boolean
```
判定：`section === '五、30'`（listed）或 `section === '八、31'`（soe）**精确相等**（Req1.4），或标题含「递延所得税资产和递延所得税负债」。解析块置于通用 `syncedSheet` 回退分支**之前**（多循环共用同名披露 sheet，须靠章节号优先命中，Req5.3）。`DisclosureEditor` 族标签映射加 `N1: '递延所得税资产'`。

### 4. 反向跳转 `views/composables/noteDisclosureReverseJump.ts`

`DISCLOSURE_NOTE_SECTION_MAP` 新增 `N1: { listed: '五、30', soe: '八、31' }`；契约测试与正向谓词交叉校验。

### 5. 定向刷新 `views/composables/useNoteRefresh.ts`

`matchesDisclosureFamily` 登记 N1：`accountCode === '1811'` 且当前节命中 `五、30`/`八、31`（或 payload `sectionIds` 命中，走既有 `matched(sectionIds)` 路径）。

### 6. 覆盖率守卫

`backend/scripts/check/check_disclosure_columns_coverage.py` 的 `COLUMN_BUILDERS` 登记 `buildN1SyncPayload`，保持 `--strict` 通过。

## Data Models

### 附注模板结构（权威，逐字核对自 `note_template_listed.json` / `note_template_soe.json`）

**listed 五、30**（section_id `chapter-05-...-di-yan-suo-de-shui-zi-chan-yu-di-yan-suo-de`）

| 表 | headers | rows（模板） |
|---|---|---|
| 未经抵销的递延所得税资产和递延所得税负债 | 项目 / 期末余额 / 上年年末余额 | 递延所得税资产：、资产减值准备、内部交易未实现利润、开办费、可抵扣亏损、租赁负债、小计、递延所得税负债：、…、小计 |
| 以抵销后净额列示的递延所得税资产或负债 | 项目 / 递延所得税资产和负债期末互抵金额 / 抵销后…期末余额 / …上年年末互抵金额 / 抵销后…上年年末余额 | 递延所得税资产、递延所得税负债 |
| 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细 | 项目 / 期末余额 / 上年年末余额 | 可抵扣暂时性差异、可抵扣亏损、合计 |
| 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | 年份 / 期末余额 / 上年年末余额 / 备注 | 2025年…2030年、合计 |

**soe 八、31**：同构，第二列组为「期末余额 / 期初余额」；表 3 名为「未确认递延所得税资产明细」；表 4 年份行更长且含「无使用期限」。

### 映射（披露表 → 附注子表）

| 附注子表 | 数据来源 | 行构造 |
|---|---|---|
| 未经抵销… | Section 1 已确认明细（`deriveDisclosureDetailRows`）+ 负债段（crossSheet） | 资产段逐项 `label=item, [endBalance, beginBalance]`；`小计` `is_total`；负债段小计（缺失 `null`） |
| 以抵销后净额… | crossSheet + 手工互抵录入 | 两行（资产/负债），4 数值列，缺失 `null` |
| 未确认…明细 | Section 3 | 可抵扣暂时性差异 / 可抵扣亏损 / 合计 |
| 未确认…亏损到期 | Section 4（`deriveDisclosureLossRows`，按 `expiryYear` 聚合 `unrecovered`） | 年份行 + 合计 + 备注（`reason`/说明） |

### `_note_texts`

```json
[{ "section": "n1-disclosure-conclusion", "title": "披露说明与结论", "text": "…" }]
```

## Correctness Properties

### Property 1: 章节号单一真源
`N1_NOTE_SECTION` 与权威矩阵 `di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de` 的 `listed_standalone` / `soe_standalone` 逐字相等；正向谓词、反向 map、payload `section_id` 三处取同一常量。
**Validates: Requirements 1.1, 1.2, 1.3, 1.5**

### Property 2: 子表键与列头键一致
对任意 variant 与 snapshot，`Object.keys(sub_table_data)` 与 `Object.keys(columns)` 相等；且每张表每行 `values` 长度 = 该表 `columns` 中非 label 列数。
**Validates: Requirements 2.2**

### Property 3: 列头逐字对齐模板
`columns[key].map(c => c.label)` 与模板该表 `headers` 逐字相等（按 variant）。
**Validates: Requirements 2.3**

### Property 4: 年度与准则显式传递
payload `year` 恒等于 `ctx.year`（不回退当前自然年）；`current_standard` 按 variant 为 `listed_standalone` / `soe_standalone`。
**Validates: Requirements 2.4, 2.5**

### Property 5: 空文本不写 `_note_texts`
`snapshot.texts` 为空（或全为空串）时，`sub_table_data` 不含 `_note_texts` 键。
**Validates: Requirements 4.1, 4.2**

### Property 6: 精确章节匹配
`isN1DeferredTaxNoteSection('五、3')`、`('五、31')`、`('八、3')`、`('八、32')` 均为 false；`('五、30')`（listed）/`('八、31')`（soe）为 true。
**Validates: Requirements 1.4, 5.1, 5.3**

### Property 7: 不抢占也不被抢占
携 `_last_sync_sheet='附注披露信息（上市公司）'` 的其他章节（如 五、4 应收票据）不解析为 N1；五、30 携任意 syncedSheet 仍解析为 N1。
**Validates: Requirements 5.3**

### Property 8: 正反向章节号一致
`DISCLOSURE_NOTE_SECTION_MAP.N1` 与正向谓词接受的章节号集合一致（交叉守卫）。
**Validates: Requirements 6.1, 6.4**

### Property 9: N3 所有权子表不被清空
payload 只含 Decision 1 表格中 owner=N1 的键；对既有附注（含假想 N3 键）执行浅合并后，非 N1 键仍在。
**Validates: Requirements 3.1, 3.3, 3.5**

### Property 10: 缺失不填 0
`snapshot.liability.endBalance === null` 时，负债段对应单元值为 `null`（不是 0、不是 `'0.00'`）。
**Validates: Requirements 3.2, 3.4, 3.5**

### Property 11: 载荷为纯函数
同一输入多次调用 `buildN1SyncPayload` 输出深相等；函数内不触发网络/时间依赖（`year` 由入参给定）。
**Validates: Requirements 9.1, 9.2**

### Property 12: 零回归
既有 `noteDisclosureJump` / `noteDisclosureReverseJump` / `useNoteRefresh` 测试与 N1 底稿 162 前端 + 45 后端测试全绿；覆盖率守卫 `--strict` 通过。
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

## Error Handling

| 场景 | 行为 |
|---|---|
| 推送 HTTP 失败（非取消） | `ElMessage.error` 明确失败原因，不谎报成功；不改本地数据 |
| 请求被取消（快速重复点击 → axios abort） | 静默忽略（`ERR_CANCELED` / `CanceledError` / `__CANCEL__`） |
| 后端 422（载荷校验） | 展示 detail，提示检查章节/子表键 |
| 负债段/互抵取不到 | 推送资产段，负债/互抵单元 `null`，UI 提示「负债段待 N3 编制后重新同步」 |
| 附注章节尚不存在 | 由服务端 upsert（`created=true`）；前端按 `created` 区分提示「已新建/已更新」 |
| 跳转目标 sheet 名与 DB 不一致 | 属实现期风险 → 任务内以 DB 核实为验收前置，且 `?sheet=` 传真实 tab 名 |
| `projectId` 缺失 | 反向跳转按钮 `disabled`；同步按钮提示缺少项目上下文 |

## Testing Strategy

1. **纯函数单测**（`n1NoteSectionMap.spec.ts`）：Property 1–5、9–11，含 listed/soe 两变体、负债缺失、空文本、键一致性。
2. **跳转契约测试**：`noteDisclosureJump.spec.ts` 增 N1 用例（Property 6、7）；`noteDisclosureReverseJump.spec.ts` 增 N1 条目 + 交叉守卫（Property 8）。
3. **零回归门**（Property 12）：N1 全量前端测试 + 两个跳转 spec + `check_disclosure_columns_coverage.py --strict` + 后端 `test_n1_*`。
4. **模板对齐守卫**：从 `note_template_{listed,soe}.json` 读该章节 `tables[].headers`，与 `columns` label 逐字比对（防模板改动漂移，Property 3）。
5. **live round-trip（可选）**：需 N1 已实例化项目；采用「备份 → sync → 断言 `_tables` 列头/行 → 恢复 + `RESTORED_IDENTICAL` 断言」范式，避免污染真实附注。无实例化项目时如实标注不执行（不假绿）。
