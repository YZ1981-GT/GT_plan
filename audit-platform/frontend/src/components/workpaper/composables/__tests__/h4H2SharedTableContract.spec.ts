/**
 * H2 ↔ H4 共享子表契约守卫。
 *
 * 背景：H4 工程物资**没有独立附注章节**，它推的是 H2 在建工程章节
 * （上市 §五、23 / 国企 §八、23）里的子表 —— H2 负责「在建工程」行、
 * H4 负责「工程物资」行，两者写**同一张**表。而 `_sub_table_columns` 与
 * `sub_table_data[表名]` 都由最后一次同步整体覆盖 → 两侧任何定义分叉都会让
 * 附注列头 / 合计行字面「随最后同步方跳变」，且两边单测各自都是绿的。
 *
 * 实测分叉（已修）：
 * - H4 soe 自造列定义缺 `format:'amount'`（H2 侧有）
 * - H4 soe 合计行推 `合  计`（两空格，源模板底稿字面），H2 与附注模板是 `合计`
 *
 * spec: h3-investment-property-disclosure-alignment 之后的 H4 收口
 */
import { describe, expect, it } from 'vitest'
import {
  H2_LISTED_SUBTABLE,
  H2_SOE_SUBTABLE,
} from '../h2NoteSectionMap'
import { buildH2ListedColumns, buildH2SoeColumns } from '../h2DisclosureSyncPayload'
import { buildH4SoeColumns, buildH4SoeSyncPayloads } from '../h4SoeDisclosureSyncPayload'
import { buildH4ListedSyncPayloads } from '../h4DisclosureSyncPayload'

describe('H2 ↔ H4 共享子表列定义单一真源', () => {
  it('H4 soe 汇总表列定义 === H2 soe 同名表（含 format/group，逐字段相等）', () => {
    const key = H2_SOE_SUBTABLE.summary
    expect(buildH4SoeColumns()[key]).toEqual(buildH2SoeColumns()[key])
  })

  it('H4 soe 只声明它实际推送的那一张表（不越界带上 H2 的明细表）', () => {
    expect(Object.keys(buildH4SoeColumns())).toEqual([H2_SOE_SUBTABLE.summary])
  })

  it('H4 listed 列定义取自 H2（工程物资表键已随 H2 改名同步）', () => {
    const payloads = buildH4ListedSyncPayloads('wp1', ['listed_standalone'], {
      materials: [{ label: '专用材料', endBalance: 100, priorBalance: 80 }] as never,
    } as never)
    expect(payloads).toHaveLength(1)
    const cols = payloads[0].columns || {}
    const matKey = H2_LISTED_SUBTABLE.materials
    expect(matKey).toBe('工程物资')
    expect(Object.keys(cols)).toContain(matKey)
    expect(cols[matKey]).toEqual(buildH2ListedColumns()[matKey])
    // 旧泄漏名不得复活
    expect(Object.keys(cols)).not.toContain('项  目')
  })
})

describe('H2 ↔ H4 合计行字面一致（附注侧统一「合计」）', () => {
  it('H4 soe 汇总表合计行推「合计」而非源模板底稿字面「合  计」', () => {
    const payloads = buildH4SoeSyncPayloads('wp1', ['soe_standalone'], {
      summary: [
        { label: '在建工程', endBook: 100, endImpairment: 10, beginBook: 90, beginImpairment: 5 },
        { label: '工程物资', endBook: 50, endImpairment: 0, beginBook: 40, beginImpairment: 0 },
      ] as never,
    } as never)
    expect(payloads).toHaveLength(1)
    const rows = payloads[0].sub_table_data[H2_SOE_SUBTABLE.summary]
    const total = rows.find((r) => r.is_total)!
    expect(total.label).toBe('合计')
    expect(rows.map((r) => r.label)).not.toContain('合  计')
    // 账面价值 = 账面余额 − 减值准备（逐期）
    expect(total.end_carrying).toBe(150 - 10)
    expect(total.begin_carrying).toBe(130 - 5)
  })
})
