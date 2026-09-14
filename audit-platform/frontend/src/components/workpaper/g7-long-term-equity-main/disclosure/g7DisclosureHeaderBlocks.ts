/**
 * G7 披露表**两级表头分块**（上市 / 国企两个 Tab 共用的单一真源）。
 *
 * 背景（2026-08-12 浏览器实测）：两个披露 Tab 原先都是扁平
 * `v-for="column in effectiveColumns(table)"`，模板只读 `column.label / width / type`，
 * **`column.group` 一次都没读**。于是模型里的分组（`groupedCols()` 产出，三向守卫拿它
 * 跟源 xlsx 合并单元格逐一对齐）成了 additive 死代码：
 *
 * - 源模板 `is_two_level=true` 的表：上市 11/15 张、国企 13/23 张（共 24 张）
 * - 浏览器实测：两个 Tab 共 38 张表，两级表头 **0 张**（`headRows` 直方图 `{1: 38}`）
 *
 * 用户可见后果：像国企「重要非全资子公司 / 主要财务信息」这种 5 家公司 × (期末数/期初数)
 * 的表，DOM 里就是 5 组一模一样的 `期末数|期初数`，**没有公司名父行** —— 审计师无法
 * 分辨哪一对属于哪家被投资单位。
 *
 * 判据真源是**源模板的合并单元格**（如 B10:C10），与平台共享组件
 * `shared/disclosure/WpDisclosureSegmentTable.vue` 的 `headerBlocks` 同一套语义：
 * **相邻**且同 `group` 的列合并到一个父表头下。
 *
 * 🔴 只按「相邻」合并，不做全表按 group 归并 —— 源模板里同名父表头若被别的列隔开，
 *    那是两段独立的合并单元格（跨列合并不可能跳格），归并会凭空造出错误跨度。
 * 🔴 `group` 为空/缺省即单级列（`G7DisclosureColumn.group` 的类型注释：只支持单级；
 *    源模板本就单行表头的表由 `flat: true` 显式表态，禁前缀推断凭空造父表头）。
 */

import type { G7DisclosureColumn } from './g7SoeDisclosureModel'

/** 一个表头块：`group` 有值 = 两级（父表头 + 子列）；无值 = 单级（仅一列）。 */
export interface G7HeaderBlock {
  /** 父表头名；`undefined` 表示该块是单级列。 */
  group?: string
  /** 该块下的列（单级块恒为 1 列）。 */
  columns: G7DisclosureColumn[]
}

/**
 * 把列清单切成表头块：相邻同 `group` 的列合并为一个两级块，其余各自成单级块。
 *
 * @param columns `resolveG7{Soe,Listed}TableColumns()` 的产出（已含 `group`）。
 */
export function buildG7HeaderBlocks(
  columns: readonly G7DisclosureColumn[] | undefined | null,
): G7HeaderBlock[] {
  const blocks: G7HeaderBlock[] = []
  for (const column of columns ?? []) {
    const group = column.group || undefined
    const last = blocks[blocks.length - 1]
    if (group && last && last.group === group) {
      last.columns.push(column)
    } else {
      blocks.push({ group, columns: [column] })
    }
  }
  return blocks
}

/**
 * 该表是否应渲染两级表头（= 至少一个块有父表头）。
 *
 * 供守卫与调试用：它与 `g7_column_source_facts.json` 的 `is_two_level` 应当一致，
 * 不一致说明模型侧的 `group` 声明与源模板脱节（三向守卫会打红）。
 */
export function hasG7TwoLevelHeader(
  columns: readonly G7DisclosureColumn[] | undefined | null,
): boolean {
  return buildG7HeaderBlocks(columns).some(b => !!b.group)
}
