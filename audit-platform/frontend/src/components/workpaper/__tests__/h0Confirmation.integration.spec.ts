/**
 * H0 固定资产循环函证 — 前端集成测试
 *
 * 覆盖：overrides 映射 / 四区块 CRUD / 导入导出 round-trip / importFromSummary
 */
import { describe, it, expect, vi } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import { calcCheckRatio, calcBlockTotal, calcRowVariance, isAbnormal } from '../confirmation/alternativeH05/composables/useH0FormulaEngine'
import { useAlternativeH05Data } from '../confirmation/alternativeH05/composables/useAlternativeH05Data'
import { BLOCK_COLUMN_CONFIGS_H05, getSumFieldsH05 } from '../confirmation/alternativeH05/blockColumnConfigsH05'
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

  it('四区块列配置完整且 sumFields 正确', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_H05).sort()).toEqual(
      ['block1', 'block2', 'block3', 'block4'].sort(),
    )
    for (const cfg of Object.values(BLOCK_COLUMN_CONFIGS_H05)) {
      expect(cfg.columns.length).toBeGreaterThan(5)
    }
    // block2 应含 contract_amount / invoice_amount / payment_amount 合计字段
    const b2Sum = getSumFieldsH05('block2')
    expect(b2Sum).toContain('contract_amount')
    expect(b2Sum).toContain('invoice_amount')
    expect(b2Sum).toContain('payment_amount')
    // block4 应含 mortgage_amount
    expect(getSumFieldsH05('block4')).toContain('mortgage_amount')
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

describe('H0 集成: 四区块 CRUD', () => {
  function makeData() {
    return useAlternativeH05Data({
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    })
  }

  it('addCompany / deleteCompany', () => {
    const d = makeData()
    const c1 = d.addCompany({ entity_name: '公司A' })
    const c2 = d.addCompany({ entity_name: '公司B' })
    expect(d.companies.value).toHaveLength(2)
    expect(c2.seq).toBe(2)

    d.deleteCompany(c1._company_id!)
    expect(d.companies.value).toHaveLength(1)
    expect(d.companies.value[0].entity_name).toBe('公司B')
  })

  it('addBlockRow / deleteBlockRow 四区块独立', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '测试' })
    const id = c._company_id!

    const r1 = d.addBlockRow(id, 'block1')!
    const r2 = d.addBlockRow(id, 'block1')!
    const r3 = d.addBlockRow(id, 'block3')!
    expect(r1._row_id).toBeDefined()
    expect(r2.seq).toBe(2)

    // block1 有 2 行，block3 有 1 行
    d.deleteBlockRow(id, 'block1', r1._row_id!)
    // block1 剩 1 行
    const company = d.companies.value[0]
    expect(company.block1_rows).toHaveLength(1)
    expect(company.block3_rows).toHaveLength(1)
  })

  it('updateBlockField 正确更新字段', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '字段测试' })
    const id = c._company_id!
    const row = d.addBlockRow(id, 'block4')!

    d.updateBlockField(id, 'block4', row._row_id!, 'mortgage_contract', 'DY-2024-001')
    d.updateBlockField(id, 'block4', row._row_id!, 'mortgage_amount', 2000000)

    const updated = d.companies.value[0].block4_rows![0]
    expect(updated.mortgage_contract).toBe('DY-2024-001')
    expect(updated.mortgage_amount).toBe(2000000)
  })

  it('getBlockTotal 多行合计正确', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '合计测试' })
    const id = c._company_id!

    const r1 = d.addBlockRow(id, 'block2')!
    const r2 = d.addBlockRow(id, 'block2')!
    d.updateBlockField(id, 'block2', r1._row_id!, 'contract_amount', 100)
    d.updateBlockField(id, 'block2', r1._row_id!, 'invoice_amount', 80)
    d.updateBlockField(id, 'block2', r2._row_id!, 'contract_amount', 200)
    d.updateBlockField(id, 'block2', r2._row_id!, 'invoice_amount', 170)

    const totals = d.getBlockTotal(d.companies.value[0], 'block2')
    expect(totals.contract_amount).toBe(300)
    expect(totals.invoice_amount).toBe(250)
  })

  it('getCheckRatio balance=0 → null', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '零余额' })
    // balance 默认无 closing_balance → 0
    expect(d.getCheckRatio(c, 'ownership')).toBeNull()
    expect(d.getCheckRatio(c, 'acceptance')).toBeNull()
  })

  it('hasAbnormal 检测异常行', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '异常测试' })
    const id = c._company_id!
    expect(d.hasAbnormal(d.companies.value[0])).toBe(false)

    const row = d.addBlockRow(id, 'block1')!
    d.updateBlockField(id, 'block1', row._row_id!, 'is_abnormal', '是')
    expect(d.hasAbnormal(d.companies.value[0])).toBe(true)
  })

  it('getCompletionStatus 按区块有行计算', () => {
    const d = makeData()
    const c = d.addCompany({ entity_name: '进度测试' })
    const id = c._company_id!

    expect(d.getCompletionStatus(d.companies.value[0])).toEqual({ completed: 0, total: 4, rate: 0 })

    d.addBlockRow(id, 'block1')
    d.addBlockRow(id, 'block3')
    expect(d.getCompletionStatus(d.companies.value[0])).toEqual({ completed: 2, total: 4, rate: 50 })
  })

  it('isDirty 标记变化', () => {
    const d = makeData()
    expect(d.isDirty.value).toBe(false)
    d.addCompany({ entity_name: '脏标记' })
    expect(d.isDirty.value).toBe(true)
  })
})

describe('H0 集成: 导入导出 round-trip', () => {
  it('buildPayload → loadAll 数据完整还原', () => {
    // Step 1: 构造带数据的 composable，生成 payload
    const d1 = useAlternativeH05Data({
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    })
    const c = d1.addCompany({ entity_name: '往返测试公司', confirm_index: 'H0-RT-001' })
    d1.updateCompany(c._company_id!, 'balance', {
      item_name: '在建工程',
      closing_balance: 5000000,
    })
    const row1 = d1.addBlockRow(c._company_id!, 'block1')!
    d1.updateBlockField(c._company_id!, 'block1', row1._row_id!, 'voucher_amount', 1200000)
    d1.updateBlockField(c._company_id!, 'block1', row1._row_id!, 'asset_name', '办公楼')
    const row2 = d1.addBlockRow(c._company_id!, 'block4')!
    d1.updateBlockField(c._company_id!, 'block4', row2._row_id!, 'mortgage_amount', 3000000)

    const payload = d1.buildPayload()
    expect(payload._format).toBe('alternative-h05-v1')

    // Step 2: 用 payload 初始化新 composable，验证数据还原
    const d2 = useAlternativeH05Data({
      htmlData: () => payload,
      readonly: false,
    })
    expect(d2.companies.value).toHaveLength(1)
    const restored = d2.companies.value[0]
    expect(restored.entity_name).toBe('往返测试公司')
    expect(restored.confirm_index).toBe('H0-RT-001')
    expect(restored.balance?.item_name).toBe('在建工程')
    expect(restored.block1_rows).toHaveLength(1)
    expect(restored.block1_rows![0].voucher_amount).toBe(1200000)
    expect(restored.block1_rows![0].asset_name).toBe('办公楼')
    expect(restored.block4_rows).toHaveLength(1)
    expect(restored.block4_rows![0].mortgage_amount).toBe(3000000)
  })

  it('payload 含 ownership/acceptance 比例字段', () => {
    const d = useAlternativeH05Data({
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    })
    const c = d.addCompany({ entity_name: '比例测试' })
    d.updateCompany(c._company_id!, 'balance', { item_name: '固定资产', closing_balance: 2000 })
    const row = d.addBlockRow(c._company_id!, 'block2')!
    d.updateBlockField(c._company_id!, 'block2', row._row_id!, 'contract_amount', 800)

    const payload = d.buildPayload()
    const payloadCompany = payload.companies[0]
    expect(payloadCompany.balance?.ownership_check_ratio).toBe(40)
  })

  it('空 payload 加载不崩溃', () => {
    const d = useAlternativeH05Data({
      htmlData: () => null,
      readonly: false,
    })
    expect(d.companies.value).toHaveLength(0)

    const d2 = useAlternativeH05Data({
      htmlData: () => ({ _format: 'wrong-format', companies: [{ entity_name: 'x' }] }),
      readonly: false,
    })
    expect(d2.companies.value).toHaveLength(0)
  })
})

describe('H0 集成: importFromSummary mock', () => {
  it('从 API 获取未回函实体并去重插入', async () => {
    const mockEntities = [
      { entity_name: '丙银行', confirm_index: 'H0-003', confirm_amount: 800000 },
      { entity_name: '丁租赁', confirm_index: 'H0-004', confirm_amount: 1200000 },
    ]

    // 直接mock http模块的get方法（已在顶部导入的composable中引用）
    const httpModule = await import('@/utils/http')
    const getSpy = vi.spyOn(httpModule.default, 'get').mockResolvedValue({
      data: { data: mockEntities },
    } as any)

    const d = useAlternativeH05Data({
      wpId: 'test-wp-001',
      projectId: 'test-proj-001',
      htmlData: () => ({ _format: 'alternative-h05-v1', companies: [] }),
      readonly: false,
    } as any)

    // 先手动添加一个已有 confirm_index 的公司
    d.importCompanies([{ entity_name: '丙银行', confirm_index: 'H0-003' }])
    expect(d.companies.value).toHaveLength(1)

    const added = await d.importFromSummary()
    // 丙银行已存在，只新增丁租赁
    expect(added).toBe(1)
    expect(d.companies.value).toHaveLength(2)
    expect(d.companies.value[1].entity_name).toBe('丁租赁')
    expect(d.companies.value[1].balance?.closing_balance).toBe(1200000)

    getSpy.mockRestore()
  })
})
