/**
 * M 循环权益类「变动表」披露子表契约（M4 资本公积 / M5 盈余公积 / M7 专项储备）
 *
 * 复用共享 helper 的 P1~P6（子表名逐字 / 章节存在 / group·flat 表态 / 纯文本 /
 * 标签列头对齐 headers[0] / 模板 headers 纯文本），另加本循环专属断言：
 * - 三循环共用标准变动表结构（项目|期初|本期增加|本期减少|期末），国企 M7 多「备注」列
 * - 期末余额读时派生 = 期初 + 本期增加 − 本期减少（权益类贷方），显式传 end 时以 end 为准
 * - 合计行去空白判定后重算，原有合计行不重复计入
 * - M7 组件富列（Listed reason / SOE 费用化·资本化·计提依据）投影为附注标准列
 * - 不适用变体返回 null（跳过同步，不写错章节）
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 5（M 循环批 4）
 */
import { describe, expect, it } from 'vitest'

import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M_EQUITY_CONFIG,
  M_EQUITY_DISCLOSURE_SHEET_NAME,
  M_EQUITY_TOTAL_LABEL,
  buildMEquityRows,
  buildMEquitySyncPayload,
  isMEquityApplicable,
  mEquityColumnsFor,
  mEquityEndAmount,
  type MEquityCycle,
} from '../mEquityChangeNoteSectionMap'
import { M4_NOTE_SECTION, M4_DISCLOSURE_SHEET_NAME } from '../m4NoteSectionMap'
import { M5_NOTE_SECTION, M5_DISCLOSURE_SHEET_NAME } from '../m5NoteSectionMap'
import { M7_NOTE_SECTION, M7_DISCLOSURE_SHEET_NAME } from '../m7NoteSectionMap'

// ─── P1~P6 共享契约（三循环 × 两变体） ───────────────────────────────────────

const CYCLES: MEquityCycle[] = ['M4', 'M5', 'M7']

for (const cycle of CYCLES) {
  const cfg = M_EQUITY_CONFIG[cycle]
  runDisclosureSubtableContract({
    cycle,
    variants: [
      {
        variant: 'listed',
        section: cfg.section.listed,
        subtables: { main: cfg.table.listed },
        columns: mEquityColumnsFor(cycle, 'listed'),
      },
      {
        variant: 'soe',
        section: cfg.section.soe,
        subtables: { main: cfg.table.soe },
        columns: mEquityColumnsFor(cycle, 'soe'),
      },
    ],
  })
}

// ─── 共享映射专属 ────────────────────────────────────────────────────────────

describe('M 循环权益变动表 披露映射', () => {
  it('sheet 名两版全角括号（实测源 xlsx tab 名）', () => {
    expect(M_EQUITY_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(M_EQUITY_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国有企业）')
  })

  it('三循环列结构：标准 5 列；国企 M7 多「备注」列（源模板八、61）', () => {
    for (const cycle of CYCLES) {
      const listed = mEquityColumnsFor(cycle, 'listed')[M_EQUITY_CONFIG[cycle].table.listed]
      expect(listed.map((c) => c.label)).toEqual(['项目', '期初余额', '本期增加', '本期减少', '期末余额'])
    }
    // M4/M5 国企无备注列
    for (const cycle of ['M4', 'M5'] as const) {
      const soe = mEquityColumnsFor(cycle, 'soe')[M_EQUITY_CONFIG[cycle].table.soe]
      expect(soe.map((c) => c.label)).not.toContain('备注')
    }
    // M7 国企含备注列
    const m7soe = mEquityColumnsFor('M7', 'soe')[M_EQUITY_CONFIG.M7.table.soe]
    expect(m7soe.map((c) => c.label)).toEqual(['项目', '期初余额', '本期增加', '本期减少', '期末余额', '备注'])
  })

  it('单级表头必须显式 flat（抑制后端前缀推断凭空造「本期」父表头）', () => {
    for (const cycle of CYCLES) {
      for (const variant of ['listed', 'soe'] as const) {
        const cols = mEquityColumnsFor(cycle, variant)[M_EQUITY_CONFIG[cycle].table[variant]]
        expect(cols.some((c) => c.flat), `${cycle}/${variant} 未表态 flat`).toBe(true)
        expect(cols.some((c) => c.group), `${cycle}/${variant} 不应有 group`).toBe(false)
      }
    }
  })

  it('期末余额读时派生 = 期初 + 本期增加 − 本期减少；显式传 end 时以 end 为准', () => {
    expect(mEquityEndAmount({ label: 'x', begin: 100, increase: 50, decrease: 30 })).toBe(120)
    expect(mEquityEndAmount({ label: 'x', begin: 100, increase: 50, decrease: 30, end: 999 })).toBe(999)
  })

  it('合计行去空白判定后重算，原有合计行不重复计入', () => {
    const rows = buildMEquityRows(
      [
        { label: '法定盈余公积', begin: 100, increase: 20, decrease: 5 },
        { label: '任意盈余公积', begin: 50, increase: 10, decrease: 0 },
        // 上游误传合计行（带空格）→ 必须被剔除后重算
        { label: '合  计', begin: 999, increase: 999, decrease: 999 },
      ],
      'listed',
      false,
    )
    expect(rows).toHaveLength(3) // 2 数据行 + 1 合计
    const total = rows[rows.length - 1]
    expect(total.label).toBe(M_EQUITY_TOTAL_LABEL)
    expect(total.is_total).toBe(true)
    expect(total.begin_amount).toBe(150)
    expect(total.increase).toBe(30)
    expect(total.decrease).toBe(5)
    expect(total.end_amount).toBe(175) // 150 + 30 − 5
  })

  it('国企 M7 载荷含备注列，上市 M7 无备注列（宁缺勿造，reason 列不进附注）', () => {
    const soeRows = buildMEquityRows(
      [{ label: '安全生产费', begin: 100, increase: 50, decrease: 20, end: 130, remark: '安全生产费管理办法' }],
      'soe',
      true,
    )
    expect(soeRows[0]).toHaveProperty('remark', '安全生产费管理办法')
    const listedRows = buildMEquityRows(
      [{ label: '安全生产费', begin: 100, increase: 50, decrease: 20, end: 130 }],
      'listed',
      false,
    )
    expect(listedRows[0]).not.toHaveProperty('remark')
  })

  it('buildMEquitySyncPayload 落章节号 / sheet 名 / current_standard', () => {
    const p = buildMEquitySyncPayload('wp-1', {
      cycle: 'M5',
      variant: 'soe',
      rows: [{ label: '法定盈余公积', begin: 100, increase: 20, decrease: 0 }],
    })
    expect(p).not.toBeNull()
    expect(p!.section_id).toBe('八、62')
    expect(p!.sheet_name).toBe('附注披露信息（国有企业）')
    expect(p!.current_standard).toBe('soe_standalone')
    expect(Object.keys(p!.sub_table_data)).toContain('盈余公积')
  })

  it('带说明文本时挂 _note_texts 且 title 为中文（缺 title 会渲染出英文 section 键）', () => {
    const p = buildMEquitySyncPayload('wp-1', {
      cycle: 'M4',
      variant: 'listed',
      rows: [{ label: '资本溢价（股本溢价）', begin: 1, increase: 1, decrease: 0 }],
      note: '资本溢价本期因增资增加',
    })
    const texts = (p!.sub_table_data as any)._note_texts as Array<Record<string, string>>
    expect(texts[0].title).toBe('资本公积变动说明')
    expect(texts[0].title).not.toMatch(/^[a-z0-9-]+$/i)
  })

  it('per-wp 薄壳常量与共享映射逐字一致（防 registry/守卫 与共享映射两处漂移）', () => {
    // 章节号
    expect(M4_NOTE_SECTION).toEqual(M_EQUITY_CONFIG.M4.section)
    expect(M5_NOTE_SECTION).toEqual(M_EQUITY_CONFIG.M5.section)
    expect(M7_NOTE_SECTION).toEqual(M_EQUITY_CONFIG.M7.section)
    // sheet 名
    for (const shim of [M4_DISCLOSURE_SHEET_NAME, M5_DISCLOSURE_SHEET_NAME, M7_DISCLOSURE_SHEET_NAME]) {
      expect(shim.listed).toBe(M_EQUITY_DISCLOSURE_SHEET_NAME.listed)
      expect(shim.soe).toBe(M_EQUITY_DISCLOSURE_SHEET_NAME.soe)
    }
  })

  it('不适用变体返回 null（跳过同步，不写错章节）；空准则列表放行', () => {
    expect(
      buildMEquitySyncPayload('wp-1', { cycle: 'M4', variant: 'listed', rows: [] }, ['soe_standalone']),
    ).toBeNull()
    expect(
      buildMEquitySyncPayload('wp-1', { cycle: 'M4', variant: 'soe', rows: [] }, ['soe_standalone']),
    ).not.toBeNull()
    expect(isMEquityApplicable('listed', [])).toBe(true)
    expect(isMEquityApplicable('soe', [])).toBe(true)
  })
})
