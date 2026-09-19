/**
 * useAlternativeH05Data.spec.ts — H0-5 固定资产循环替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（2026-07-17 G4）：alternative* 八套近重复中 H05 无测试。锁定 H05 **当前行为**，
 * 作为收敛为工厂前的回归安全网。不覆盖 importFromSummary（依赖 http，另测）。
 *
 * H05 差异（本测试重点）：
 * - _format: alternative-h05-v1；默认 balance.item_name = '固定资产'
 * - 基数 = balance.closing_balance ?? ending_balance（非销售/采购额）
 * - getCheckRatio('ownership') 用 block2 contract_amount；('acceptance') 用 block1 voucher_amount
 * - payload 比例字段 ownership_check_ratio / post_acceptance_ratio
 */
import { describe, it, expect } from 'vitest'
import { useAlternativeH05Data } from '../useAlternativeH05Data'

function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'alternative-h05-v1', companies: [] }
  return useAlternativeH05Data({
    wpId: 'wp-test',
    projectId: 'proj-test',
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useAlternativeH05Data', () => {
  describe('初始化', () => {
    it('空 / 格式不匹配 → 空数组', () => {
      expect(createInstance(null).companies.value).toEqual([])
      expect(createInstance({ _format: 'alternative-f05-v1' }).companies.value).toEqual([])
    })

    it('alternative-h05-v1 正确初始化', () => {
      const data = createInstance({
        _format: 'alternative-h05-v1',
        companies: [{ entity_name: '设备供应商' }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })

  describe('CRUD + 默认 balance', () => {
    it('addCompany 默认 balance.item_name=固定资产', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('固定资产')
    })

    it('importCompanies 去重 + 默认固定资产', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].balance?.item_name).toBe('固定资产')
    })
  })

  describe('检查比例（H05 语义：基数=期末余额）', () => {
    it('ownership 比例 = block2 contract_amount / closing_balance * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '固定资产', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block2')!
      data.updateBlockField(c._company_id!, 'block2', row._row_id!, 'contract_amount', 400)
      expect(data.getCheckRatio(data.companies.value[0], 'ownership')).toBe(40)
    })

    it('acceptance 比例 = block1 voucher_amount / closing_balance * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '固定资产', closing_balance: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'voucher_amount', 500)
      expect(data.getCheckRatio(data.companies.value[0], 'acceptance')).toBe(25)
    })

    it('无期末余额 → null', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(data.getCheckRatio(data.companies.value[0], 'ownership')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'acceptance')).toBeNull()
    })
  })

  describe('metrics / buildPayload / persistAll', () => {
    it('metrics 统计正确', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c1._company_id!, b))
      expect(data.metrics.value.total_companies).toBe(1)
      expect(data.metrics.value.completed_companies).toBe(1)
    })

    it('buildPayload _format=alternative-h05-v1 + 固化比例字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '固定资产', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block2')!
      data.updateBlockField(c._company_id!, 'block2', row._row_id!, 'contract_amount', 600)
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-h05-v1')
      expect(payload.companies[0].balance?.ownership_check_ratio).toBe(60)
      expect(payload.companies[0].balance).toHaveProperty('post_acceptance_ratio')
    })

    it('persistAll 等价于 buildPayload', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'X' })
      expect(data.persistAll()._format).toBe('alternative-h05-v1')
    })
  })
})
