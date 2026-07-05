/**
 * H0 固定资产循环函证 — 前端集成测试
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import { calcCheckRatio } from '../confirmation/alternativeH05/composables/useH0FormulaEngine'
import { useAlternativeH05Data } from '../confirmation/alternativeH05/composables/useAlternativeH05Data'
import { BLOCK_COLUMN_CONFIGS_H05 } from '../confirmation/alternativeH05/blockColumnConfigsH05'
import { getRendererEntry } from '../htmlRendererRegistry'

describe('H0 集成: wp_code_overrides 9 条映射', () => {
  const overridesPath = path.resolve(
    __dirname,
    '../../../../../../backend/app/data/wp_code_overrides.json',
  )
  const overrides: Record<string, string> = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))

  const expected: [string, string][] = [
    ['H0', 'confirmation-hub'],
    ['H0A', 'a-program-console'],
    ['H0-1', 'confirmation-summary'],
    ['H0-2', 'confirmation-entity-verify'],
    ['H0-3', 'confirmation-followup'],
    ['H0-4', 'confirmation-diff-reconcile'],
    ['H0-5', 'confirmation-alternative-h05'],
    ['H0-6', 'confirmation-reliability'],
    ['H0-7', 'confirmation-fraud-risk'],
  ]

  it.each(expected)('wp_code "%s" → componentType "%s"', (code, ct) => {
    expect(overrides[code]).toBe(ct)
  })
})

describe('H0 集成: H0-5 替代程序', () => {
  it('htmlRendererRegistry 注册 confirmation-alternative-h05', () => {
    const entry = getRendererEntry('confirmation-alternative-h05')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-alternative-h05')
  })

  it('四区块列配置完整', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_H05).sort()).toEqual(
      ['block1', 'block2', 'block3', 'block4'].sort(),
    )
    for (const cfg of Object.values(BLOCK_COLUMN_CONFIGS_H05)) {
      expect(cfg.columns.length).toBeGreaterThan(5)
    }
  })

  it('权属/验收检查比例基于期末余额', () => {
    const { getCheckRatio, addCompany, updateCompany, addBlockRow, updateBlockField } =
      useAlternativeH05Data({
        htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
        readonly: false,
      })

    const company = addCompany({ entity_name: '测试单位' })
    updateCompany(company._company_id!, 'balance', {
      item_name: '固定资产',
      closing_balance: 1000,
    })

    const row = addBlockRow(company._company_id!, 'block2')!
    updateBlockField(company._company_id!, 'block2', row._row_id!, 'contract_amount', 500)

    expect(getCheckRatio(company, 'ownership')).toBe(50)
    expect(calcCheckRatio(500, 1000)).toBe(0.5)
  })

  it('buildPayload 输出 alternative-h05-v1', () => {
    const { buildPayload, addCompany } = useAlternativeH05Data({
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    })
    addCompany({ entity_name: 'A公司' })
    const payload = buildPayload()
    expect(payload._format).toBe('alternative-h05-v1')
    expect(payload.companies).toHaveLength(1)
  })
})

describe('H0 集成: H0-1 → H0-5 反向联动', () => {
  function filterUnreplied(rows: any[]) {
    return rows.filter(
      (r) => r.match_status === '未回函' || (r.is_replied === false && r.match_status !== '相符'),
    )
  }

  function mapToCompanies(unreplied: any[]) {
    return unreplied.map((r) => ({
      entity_name: r.entity_name || '',
      confirm_index: r.confirm_index,
      _source: 'auto',
      balance: {
        item_name: r.account_type || '固定资产',
        closing_balance: Number(r.amount) || 0,
      },
    }))
  }

  const h01Rows = [
    { entity_name: '甲公司', match_status: '相符', is_replied: true, confirm_index: 'H0-001', amount: 1000000 },
    { entity_name: '乙公司', match_status: '未回函', is_replied: false, confirm_index: 'H0-002', amount: 500000, account_type: '在建工程' },
  ]

  it('只带入未回函项目', () => {
    expect(filterUnreplied(h01Rows).map((r) => r.entity_name)).toEqual(['乙公司'])
  })

  it('映射为 H0-5 公司清单并 importCompanies 去重', () => {
    const d = useAlternativeH05Data({
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    })
    const companies = mapToCompanies(filterUnreplied(h01Rows))
    d.importCompanies(companies)
    expect(d.companies.value).toHaveLength(1)
    expect(d.companies.value[0].balance?.item_name).toBe('在建工程')
    d.importCompanies(companies)
    expect(d.companies.value).toHaveLength(1)
  })
})

describe('H0 集成: useH0ImportExport API 前缀', () => {
  it('cycleImportExportRegistry 含 h0/H0-5', async () => {
    const { CYCLE_IMPORT_EXPORT } = await import('../shared/cycleImportExportRegistry')
    expect(CYCLE_IMPORT_EXPORT.h0?.apiPrefix).toBe('h0')
    expect(CYCLE_IMPORT_EXPORT.h0?.sheets).toContain('H0-5')
  })
})
