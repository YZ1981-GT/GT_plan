# Design: 受限资产附注表行级合并接入

## Overview

复用平台已落地的行级合并（`disclosure-note-row-level-merge`），把「所有权或使用权
受到限制的资产」这张**受益面最大的共享表**从「零 pusher」接成「八循环各推自己那一段」。

三步走：
1. **修模板**（两处 `report_row_code` 错码/缺码 + columns/guidance + 假行 + 续表正名）
2. **补平台**（模板可显式声明 `row_type: "unowned"` → 段可写区排除它）
3. **逐 owner 接入**（每循环一个薄映射 + 披露 Tab 发第二个 payload）

**明确不做**：
- 不改该表的行集（除删 `header_label` 假行）—— 行是源模板固定科目列表
- 不做跨循环的「受限资产汇总底稿」—— 数据源就在各循环披露 Tab 里
- 不改 `SyncFromWorkpaperRequest` schema（`_row_scope` 随 `sub_table_data` 走）
- 不给「应收款项融资」段接 pusher（D5 披露 Tab 现无受限资产录入位置，属另一笔账）

## Architecture

```
各循环披露 Tab（已有受限资产录入）
  E1 ②表受限明细 ─┐
  D1 已质押票据   │
  D2 质押应收     ├─→ buildXRestrictedAssetPayload(variant, wpId, standards, snapshot)
  F2 抵押存货     │      └─ sub_table_data = { <表名>: [该段行...],
  H1 抵押固定资产 │                            _row_scope: { <表名>: { owner_row_code } } }
  H2 受限在建工程 │
  I1 受限无形资产 ┘
        │  POST /disclosure-notes/sync-from-workpaper（listed 侧发两次：主表 + 续表）
        ▼
wp_disclosure_sync_service.sync_from_workpaper
  → _extract_row_scope → _merge_rows_by_scope（窗口 = [start, data_end)）
        │
        ▼
disclosure_notes.table_data.sub_table_data
  listed 五、32：主表(期末) + 「…（续：上年年末）」
  soe   八、93：单表（期末账面价值 + 受限原因）
```

段归属（模板 `report_row_code` 实证，2026-08-02）：

| owner_row_code | 段标签 | 归属循环 | listed | soe |
|----------------|--------|---------|--------|-----|
| `BS-002` | 货币资金 | E1 | ✅ | ✅ |
| `BS-005` | 应收票据 | D1 | ✅ | ✅ |
| `BS-006` | 应收账款 | D2 | ✅ | ✅ |
| `BS-007` | 应收款项融资 | D5 | — | ✅（**本 spec 补码**） |
| `BS-010` | 存货 | F2 | ✅ | ✅（**本 spec 纠错码**，现为 `BS-008`） |
| `BS-028` | 固定资产 | H1 | ✅ | ✅ |
| `BS-029` | 在建工程 | H2 | — | ✅ |
| `BS-032` | 无形资产 | I1 | ✅ | ✅ |

## Components and Interfaces

### 1) 平台补强：`note_shared_table_segments.py`

```python
#: 无主行判据扩展（原只认表级合计行）
_UNOWNED_ROW_TYPES = frozenset({"unowned"})

def _is_unowned_row(row) -> bool:
    """模板显式声明不属于任何段的行（`row_type == "unowned"`）。"""

# split_segments 的可写区计算改为：
#   ① 段尾连续的表级合计行（既有逻辑，含「段级小计模式」豁免）
#   ② 段内**首个** `unowned` 行 → 可写区止于它之前（Requirement 2.5）
# 两者取更小的右界。
```

`stamp_baseline_rows` 已按 `[data_end, end)` 区间把 `_seg` 留空 —— `unowned` 行落进该区间
即自动不带戳，`find_stamped_window` 天然止于它之前，无需额外改动。

### 2) 模板修订脚本

```
backend/scripts/fix/fix_note_restricted_assets_structure.py  # --dry-run / --check
```

复用 `backend/scripts/fix/_note_structure_kit.py` 的 `flat_columns` / `rule` / `run_section` /
`build_cli`。改名走 `rule(aliases=...)`（**不能进 drops** —— `drop_tables` 在
`apply_plan` 之前执行会连行一起删掉）。

### 3) per-owner 映射（每循环一份薄文件）

```
composables/restrictedAssetsNoteSectionMap.ts        # 共享：章节号/表名/列/载荷构造
composables/e1RestrictedAssetsPayload.ts             # E1 owner 薄壳（BS-002）
composables/d1RestrictedAssetsPayload.ts             # …（按 owner 逐个加）
```

共享件对外接口：

```ts
export const RESTRICTED_ASSETS_NOTE_SECTION = { listed: '五、32', soe: '八、93' }
export const RESTRICTED_ASSETS_TABLE = {
  listed: '所有权或使用权受到限制的资产',
  listedPrior: '所有权或使用权受到限制的资产（续：上年年末）',
  soe: '所有权和使用权受到限制的资产',
}
export function buildRestrictedAssetsColumns(): Record<string, ColumnDef[]>   // 零入参
export function buildRestrictedAssetsPayloads(
  variant, wpId, applicableStandards, spec: { ownerRowCode: string; rows: RestrictedRowLike[] },
): RestrictedAssetsPayload[]     // listed → 2 个（主表 + 续表）；soe → 1 个
```

🔴 **文件名不匹配 `WP_CODE_RE`**（`^([a-z]+\d+)NoteSectionMap\.ts$`）是**故意的** ——
共享表一个章节有多个 owner，不该进 section→wp 的 1:1 反查 registry
（同 `e1FxNoteSectionMap.ts` 与 M 循环共享 map 的既有机制）。

### 4) 各循环接入点

每个 owner 循环在自己的披露 Tab 里加一个 `syncRestrictedAssetsToNote()`，
与主章节同步并列调用（K6 国企侧「一次发两个 payload」范式），并把驱动数据
加进自动同步的 `watch` 依赖数组（否则「改了受限资产不同步」）。

## Data Models

### 落库形态（soe `八、93`，3 列）

```jsonc
{
  "所有权和使用权受到限制的资产": [
    { "label": "货币资金", "_seg": "BS-002", "end_carrying": 1200000, "reason": "银行承兑汇票保证金" },
    { "label": "应收票据", "_seg": "BS-005", "end_carrying": null,    "reason": null },
    { "label": "应收账款", "_seg": "BS-006", "end_carrying": null,    "reason": null },
    { "label": "应收款项融资", "_seg": "BS-007", "end_carrying": null, "reason": null },
    { "label": "存货",     "_seg": "BS-010", "end_carrying": null,    "reason": null },
    { "label": "固定资产", "_seg": "BS-028", "end_carrying": null,    "reason": null },
    { "label": "无形资产", "_seg": "BS-032", "end_carrying": null,    "reason": null },
    { "label": "在建工程", "_seg": "BS-029", "end_carrying": null,    "reason": null },
    { "label": "其他",     "_seg": "",       "row_type": "unowned" }
  ]
}
```

### 列定义

| 变体 / 表 | 列（key → label） |
|-----------|-------------------|
| listed 主表 | `label`→项目（flat） / `end_amount`→期末 |
| listed 续表 | `label`→项目（flat） / `prior_amount`→上年年末 |
| soe | `label`→项目（flat） / `end_carrying`→期末账面价值 / `reason`→受限原因 |

## Correctness Properties

### Property 1: 段归属与真源一致

该表每个段的 `owner_row_code` 都能在 `report_config` 里查到同名报表行
（`BS-007` = 应收款项融资 / `BS-010` = 存货 / `BS-028` = 固定资产 …），
且 soe 的「存货」段**不再**是 `BS-008`（预付款项）。

**Validates: Requirements 1.1, 1.2**

### Property 2: `unowned` 行不被任何 owner 覆盖

对含 `row_type = "unowned"` 行的表，任意 owner 段推送后该行**逐字段不变**；
反向自检：把 `unowned` 判定去掉，相邻段推送必删掉该行。

**Validates: Requirements 2.1, 2.3, 3.2**

### Property 3: 无 `unowned` 行时逐字等价

对不含 `unowned` 行的全部共享表（含外币货币性项目），`split_segments` 的
`(start, end, data_end)` 三元组与引入该字段前**完全相同**。

**Validates: Requirements 2.4, 5.5**

### Property 4: `unowned` 在段中间时可写区止于其前

构造「段首 + 数据行 + unowned + 数据行」，可写区 SHALL 是 `[start, unowned_idx)`，
不得跨越保留（否则 owner 数据被劈成两段，顺序不可控）。

**Validates: Requirements 2.5**

### Property 5: 表级合计行存活

主表/续表/soe 表的合计行在任意 owner 推送后 SHALL 存活且值不被改写。

**Validates: Requirements 1.4, 3.2**

### Property 6: 列元数据齐备且单级

三张子表 SHALL 各有 `columns`，任一列标 `flat`，无列声明 `group`；
读时投影的 `_column_groups` SHALL 为 `[]`。

**Validates: Requirements 1.4, 1.5**

### Property 7: 续表正名且旧名可清理

「续：」SHALL 被重命名为带主表名前缀的形式；旧名进 legacy 种子，
使存量项目下一次同步时清掉孤儿表。

**Validates: Requirements 1.6**

### Property 8: listed 双期两次推送

listed 变体 SHALL 产出 2 个 payload（主表 = 期末列、续表 = 上年年末列），
两者 `_row_scope` 的 owner 相同、表名不同。

**Validates: Requirements 3.5**

### Property 9: 变体列差异

soe 载荷 SHALL 含 `reason` 列，listed 载荷 SHALL NOT 含（源模板 2 列）。

**Validates: Requirements 3.6**

### Property 10: 空数据不推空段

某 owner 无受限资产时 SHALL 返回空 payload 列表（不推），
不得推 `[]` 触发「段恢复模板骨架」。

**Validates: Requirements 3.3**

### Property 11: fail closed 可观测

owner 段解析失败时该表**完全未写**，`row_scope_unresolved` 含表名，
前端据此提示审计师。

**Validates: Requirements 3.4**

### Property 12: 合计勾稽

合计行 = 各段金额之和（容差 0.01）；未接入的段报 skip 而非 error。

**Validates: Requirements 4.1, 4.3**

### Property 13: 幂等与源 xlsx 三向比对

修订脚本 `--check` 0 欠账且重复 `--dry-run` 无变更；守卫以 openpyxl 直读源 xlsx
交叉比对表名/列头/行集，并含反向自检。

**Validates: Requirements 1.7, 5.1, 5.4**

### Property 14: 平台守卫覆盖新 owner

每个接入的 owner 都被 `disclosureSharedTableRowScope.spec.ts` 扫到且判为「已声明」；
`owner_row_code` ∈ 该表段集合。

**Validates: Requirements 5.2, 5.3**

## Error Handling

**总原则同平台 spec：宁可不同步，绝不覆盖他人数据。**

| 情形 | 处理 | 理由 |
|------|------|------|
| 模板查不到表 / owner code | 跳过该表写入 + `row_scope_unresolved` | fail closed（平台既有） |
| 某 owner 的段被 `unowned` 行截断到 0 长度 | 拒绝写入 + warning | 可写区为空说明模板声明有误 |
| listed 续表推送失败、主表成功 | 各自独立返回；前端分别提示 | 两张表是两条 section 写入，不做事务耦合 |
| 「其他」行需要填值 | 由审计师在附注模块直接编辑 | 它无 owner，不该被任何底稿驱动 |
| D5「应收款项融资」段无 pusher | 段保留模板骨架 + guidance 说明 | 宁缺勿造；D5 披露 Tab 现无受限录入位置 |

## Testing Strategy

1. **纯函数**：`split_segments` 的 `unowned` 语义（Property 2/3/4）+ PBT（随机插
   `unowned` → 可写区永不跨越它）
2. **模板结构**：`fix_note_restricted_assets_structure.py --check` + 后端守卫
   openpyxl 三向比对（Property 1/5/6/7/13）
3. **载荷契约**：`restrictedAssetsNoteSectionMap.spec.ts`（Property 8/9/10/14）
4. **服务层**：真实模板行集下逐 owner 推送 → 他段与 `unowned` 行逐字不变（Property 2/5/11）
5. **零回归**：`disclosure-note-row-level-merge` 的 characterization 全套不改断言跑绿
6. **实测**：真实 DB 直跑（`verify_row_level_merge_live.py` 参数化到本表）+
   浏览器录 E1 受限资产 → 附注 `八、93` 货币资金段出现数据、他段骨架完好、
   合计行存活；**先快照后改、按 md5 逐字节复原**
7. **CI**：新增 `note-restricted-assets-structure`（后端 + 脚本 drift）与
   `note-restricted-assets-frontend`（载荷契约 + 平台 row-scope 守卫回归）
