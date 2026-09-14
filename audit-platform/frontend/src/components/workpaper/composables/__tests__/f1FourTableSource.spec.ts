/**
 * F1 四表库取数溯源归一守卫
 *
 * 后端 `tb_source_codes` 由 `list[str]`（旧，前端 0 消费）升级为
 * `ReportLineAccounts.as_dict()`（新）→ 归一函数必须兼容两种形态。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R1.7, R4.3
 */
import { describe, expect, it } from 'vitest'
import {
  describeResolvedFrom,
  normalizeF1CrossCycleSources,
  normalizeF1TbSource,
  tbAmountDivergence,
} from '../f1FourTableSource'

/** 实证 render 输出（项目 2aa00f57 / 0ec33ac9 两侧一致） */
const REAL_DICT = {
  gross: ['1123'],
  provision: ['1231'],
  gross_standard: ['1123'],
  provision_standard: ['1231-04'],
  extra: {},
  signed_codes: [['1123', 1]],
  formula: "TB('1123','期末余额')",
  row_code: 'BS-008',
  resolved_from: 'report_config',
  provision_resolved_from: 'fallback',
  provision_exact: false,
  use_provision_name_filter: true,
}

describe('normalizeF1TbSource', () => {
  it('新 dict 形态逐字段归一', () => {
    const s = normalizeF1TbSource(REAL_DICT)
    expect(s.rowCode).toBe('BS-008')
    expect(s.formula).toBe("TB('1123','期末余额')")
    expect(s.grossStandard).toEqual(['1123'])
    expect(s.gross).toEqual(['1123'])
    expect(s.provisionStandard).toEqual(['1231-04'])
    expect(s.provision).toEqual(['1231'])
    expect(s.resolvedFrom).toBe('report_config')
    expect(s.provisionResolvedFrom).toBe('fallback')
    expect(s.provisionExact).toBe(false)
    expect(s.useProvisionNameFilter).toBe(true)
  })

  it('旧 string[] 形态兼容（保守标为兜底 + 需名称过滤）', () => {
    const s = normalizeF1TbSource(['1123'])
    expect(s.gross).toEqual(['1123'])
    expect(s.grossStandard).toEqual(['1123'])
    expect(s.resolvedFrom).toBe('fallback')
    expect(s.useProvisionNameFilter).toBe(true)
  })

  it.each([null, undefined, 0, '', 'x'])('非法入参 %s → 安全默认', (raw) => {
    const s = normalizeF1TbSource(raw)
    expect(s.rowCode).toBe('BS-008')
    expect(s.gross).toEqual([])
    expect(s.resolvedFrom).toBe('fallback')
  })

  it('provision_exact=true 时不再叠名称过滤', () => {
    const s = normalizeF1TbSource({
      ...REAL_DICT,
      provision_exact: true,
      use_provision_name_filter: false,
    })
    expect(s.provisionExact).toBe(true)
    expect(s.useProvisionNameFilter).toBe(false)
  })

  it('缺 use_provision_name_filter 时由 provision_exact 反推', () => {
    const { use_provision_name_filter: _drop, ...rest } = REAL_DICT
    expect(normalizeF1TbSource(rest).useProvisionNameFilter).toBe(true)
    expect(normalizeF1TbSource({ ...rest, provision_exact: true }).useProvisionNameFilter).toBe(false)
  })
})

describe('normalizeF1CrossCycleSources', () => {
  it('实证形态：存货 BS-010 区间 / 应付账款 BS-045', () => {
    const c = normalizeF1CrossCycleSources({
      inventory: { row_code: 'BS-010', codes: ['1401~1499'] },
      payable: { row_code: 'BS-045', codes: ['2202'] },
    })
    expect(c.inventory).toEqual({ rowCode: 'BS-010', codes: ['1401~1499'] })
    expect(c.payable).toEqual({ rowCode: 'BS-045', codes: ['2202'] })
  })

  it('缺失时给兜底（存货区间 / 2202）', () => {
    const c = normalizeF1CrossCycleSources(undefined)
    expect(c.inventory.rowCode).toBe('BS-010')
    expect(c.inventory.codes).toEqual(['1401~1499'])
    expect(c.payable.codes).toEqual(['2202'])
  })
})

describe('describeResolvedFrom（UI 全中文化）', () => {
  it('report_config → 报表映射（绿）；fallback → 兜底科目（橙）', () => {
    expect(describeResolvedFrom('report_config')).toEqual({ text: '报表映射', type: 'success' })
    expect(describeResolvedFrom('fallback')).toEqual({ text: '兜底科目', type: 'warning' })
  })
})

describe('tbAmountDivergence（两口径差异）', () => {
  it('实证项目 2aa00f57：trial_balance 是叶子合计的 2 倍 → 报差异', () => {
    const d = tbAmountDivergence(2603836.86, 1301918.43)
    expect(d.hasDivergence).toBe(true)
    expect(d.diff).toBe(1301918.43)
  })

  it('实证项目 0ec33ac9：两口径一致 → 不报差异', () => {
    expect(tbAmountDivergence(13576792.21, 13576792.21).hasDivergence).toBe(false)
  })

  it('任一口径为 0（未取数）不报差异，避免「未取数」被误读为勾稽异常', () => {
    expect(tbAmountDivergence(0, 1301918.43).hasDivergence).toBe(false)
    expect(tbAmountDivergence(2603836.86, 0).hasDivergence).toBe(false)
    expect(tbAmountDivergence(null, undefined).hasDivergence).toBe(false)
  })

  it('容差 0.01 元内视为一致', () => {
    expect(tbAmountDivergence(100.005, 100).hasDivergence).toBe(false)
    expect(tbAmountDivergence(100.05, 100).hasDivergence).toBe(true)
  })
})
