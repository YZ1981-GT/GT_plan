/**
 * G6 其他债权投资科目定位守卫。
 *
 * 🔴 **2026-08-01 重写**：本文件原先钉死的是**错值** `'1505'`（依据 `report_config`
 * 的 `BS-022 = TB('1505','期末余额')`），而 `account_chart` + `trial_balance.account_name`
 * 双向实证 **`1505` 实为「债权投资减值准备」**（G4 的备抵），其他债权投资真值是 **`1506`**。
 * 根因：`report_config` 的 BS-022/025/026 连续偏移一位。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/ Requirements 3
 */
import { describe, expect, it } from 'vitest'

import {
  G6_GROSS_FALLBACK_STANDARD,
  G6_REPORT_ROW_CODE,
  g6AccountCode,
  g6GrossQueryCodes,
  isG6AccountAbsent,
} from '../g6AccountScope'

/** 实证真值：其他债权投资 = 1506 */
const TRUE_CODE = '1506'

/** 禁止出现的科目码（旧准则 / 别循环 / 曾误用的错值） */
const FORBIDDEN = ['1501', '1502', '1503', '1504', '1505', '1507', '1519', '1531']

describe('G6 科目定位常量', () => {
  it('报表行是 BS-022（仅展示与溯源，不是定位依据）', () => {
    expect(G6_REPORT_ROW_CODE).toBe('BS-022')
  })

  it('🔴 兜底码是实证真值 1506，而不是 report_config 的 1505', () => {
    expect(G6_GROSS_FALLBACK_STANDARD).toBe(TRUE_CODE)
  })

  it('兜底码不得是任何别循环 / 旧准则科目', () => {
    expect(FORBIDDEN).not.toContain(G6_GROSS_FALLBACK_STANDARD)
  })
})

describe('g6GrossQueryCodes', () => {
  it('运行态优先：取 render 下发的 gross_standard', () => {
    expect(g6GrossQueryCodes({ gross_standard: ['1506'] })).toEqual(['1506'])
  })

  it('多科目码时全量返回', () => {
    expect(g6GrossQueryCodes({ gross_standard: ['1506', '1506.01'] })).toEqual([
      '1506',
      '1506.01',
    ])
  })

  it('语义解析形态（slots）同样可读', () => {
    const src = {
      slots: {
        gross: {
          key: 'gross',
          label: '其他债权投资',
          standard_codes: ['1506'],
          codes: ['1506.01'],
          resolved_from: 'account_chart_client' as const,
          found: true,
        },
      },
    }
    expect(g6GrossQueryCodes(src)).toEqual(['1506'])
  })

  it.each([
    ['空数组', { gross_standard: [] }],
    ['null', null],
    ['undefined', undefined],
    ['空对象', {}],
  ])('%s 时回退兜底码', (_label, src) => {
    expect(g6GrossQueryCodes(src as never)).toEqual([TRUE_CODE])
  })

  it('🔴 任何回退路径都不得返回 1505（债权投资减值准备）或 1503（可供出售金融资产）', () => {
    const inputs = [null, undefined, {}, { gross_standard: [] }, { gross_standard: [''] }]
    for (const src of inputs) {
      const codes = g6GrossQueryCodes(src as never)
      expect(codes).not.toContain('1505')
      expect(codes).not.toContain('1503')
    }
  })
})

describe('g6AccountCode', () => {
  it('有 render 数据时取首个', () => {
    expect(g6AccountCode({ gross_standard: ['1506'] })).toBe('1506')
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
  ])('%s 时回退兜底码', (_label, src) => {
    expect(g6AccountCode(src as never)).toBe(TRUE_CODE)
  })
})

describe('isG6AccountAbsent（区分「本项目无此科目」与「余额为 0」）', () => {
  it('后端明确 found=false → 判定为无此科目', () => {
    const src = {
      slots: {
        gross: { key: 'gross', label: '其他债权投资', found: false, resolved_from: 'none' as const },
      },
    }
    expect(isG6AccountAbsent(src)).toBe(true)
  })

  it('命中科目时不判无', () => {
    const src = {
      slots: {
        gross: {
          key: 'gross',
          label: '其他债权投资',
          standard_codes: ['1506'],
          found: true,
          resolved_from: 'account_chart_standard' as const,
        },
      },
    }
    expect(isG6AccountAbsent(src)).toBe(false)
  })

  it('🔴 render 未下发（null）时**不**判定为无此科目（那是未知，不是无）', () => {
    expect(isG6AccountAbsent(null)).toBe(false)
    expect(isG6AccountAbsent(undefined)).toBe(false)
  })
})
