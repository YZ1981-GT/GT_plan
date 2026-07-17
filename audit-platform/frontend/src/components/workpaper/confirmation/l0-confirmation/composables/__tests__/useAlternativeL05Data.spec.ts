/**
 * useAlternativeL05Data.spec.ts — L0-5 债务循环替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（confirmation-alternative-factory-convergence Task 3）：alternative* 八套近重复中
 * L05 位于 l0-confirmation 目录，收敛为工厂前需锁定其**当前行为**作为零回归安全网。
 * 测试针对现有实现编写并全部通过，不改被测实现。
 *
 * L05 差异（本测试重点，与 D/F/H/K 不同处）：
 * - _format: alternative-l05-v1；默认 balance.item_name = '长期应付款/借款'
 * - 比例是**命名方法**：getRepaymentRatio(c) / getMortgageRatio(c)（非 getCheckRatio(c,type)）
 * - getRepaymentRatio = calcRepaymentRatio(block1.repayment_principal ?? voucher_amount, closing_balance) * 100
 * - getMortgageRatio = closing_balance>0 ? (block4.mortgage_amount ?? voucher_amount)/closing_balance*100 : 0
 * - 🔴 **空基数返回 0 而非 null**（与 D/F/H/K 相反，务必锁定）
 * - 独有面：balanceSummary（currentLoan=block3.voucher_amount 合计、avg repayment/mortgage）
 * - payload 比例字段：receipt_check_ratio / shipment_check_ratio
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mock http（importFromSummary 依赖）──────────────────────────────────────
vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import http from '@/utils/http'
import { useAlternativeL05Data, FORMAT_VERSION } from '../useAlternativeL05Data'

function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'alternative-l05-v1', companies: [] }
  return useAlternativeL05Data({
    wpId: 'wp-test',
    projectId: 'proj-test',
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useAlternativeL05Data', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ─── 1. init 格式门 ────────────────────────────────────────────────────────
  describe('初始化格式门', () => {
    it('FORMAT_VERSION 常量 = alternative-l05-v1', () => {
      expect(FORMAT_VERSION).toBe('alternative-l05-v1')
    })

    it('null / 格式不匹配 → 空数组', () => {
      expect(createInstance(null).companies.value).toEqual([])
      expect(createInstance({ _format: 'alternative-h05-v1' }).companies.value).toEqual([])
      expect(createInstance({ companies: [{ entity_name: 'X' }] }).companies.value).toEqual([])
    })

    it('alternative-l05-v1 正确载入并补 _company_id / block rows', () => {
      const data = createInstance({
        _format: 'alternative-l05-v1',
        companies: [{ entity_name: '工商银行', block1_rows: [{ voucher_amount: 100 }] }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0]._company_id).toBeTruthy()
      // block1 行被补 _row_id
      expect(data.companies.value[0].block1_rows![0]._row_id).toBeTruthy()
    })
  })

  // ─── 2. 公司 CRUD + 默认 balance + 去重 ─────────────────────────────────────
  describe('公司 CRUD', () => {
    it('addCompany 默认 balance.item_name = 长期应付款/借款', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('长期应付款/借款')
      expect(c._source).toBe('manual')
      expect(c.seq).toBe(1)
      expect(data.companies.value.length).toBe(1)
    })

    it('addCompany 递增 seq', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'A' })
      const c2 = data.addCompany({ entity_name: 'B' })
      expect(c2.seq).toBe(2)
    })

    it('updateCompany 修改字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'entity_name', '改名后')
      expect(data.companies.value[0].entity_name).toBe('改名后')
    })

    it('deleteCompany 移除公司', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.deleteCompany(c._company_id!)
      expect(data.companies.value.length).toBe(0)
    })

    it('importCompanies 按 confirm_index 去重 + 默认 长期应付款/借款', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].balance?.item_name).toBe('长期应付款/借款')
      expect(data.companies.value[1]._source).toBe('auto')
    })
  })

  // ─── 3. 区块行 CRUD ─────────────────────────────────────────────────────────
  describe('区块行 CRUD', () => {
    it('addBlockRow / getBlockRows / deleteBlockRow', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      expect(row).toBeDefined()
      expect(row.is_abnormal).toBe('否')
      expect(data.getBlockRows(data.companies.value[0], 'block1').length).toBe(1)
      data.deleteBlockRow(c._company_id!, 'block1', row._row_id!)
      expect(data.getBlockRows(data.companies.value[0], 'block1').length).toBe(0)
    })

    it('updateBlockField 修改行字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'voucher_amount', 888)
      expect(data.getBlockRows(data.companies.value[0], 'block1')[0].voucher_amount).toBe(888)
    })
  })

  // ─── 4. getBlockTotal（SUM_FIELDS）─────────────────────────────────────────
  describe('getBlockTotal', () => {
    it('block1 合计 voucher_amount / repayment_principal / repayment_interest', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      const r2 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'voucher_amount', 1000)
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'repayment_principal', 600)
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'repayment_interest', 50)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'voucher_amount', 2000)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'repayment_principal', 400)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'repayment_interest', 25)
      const total = data.getBlockTotal(data.companies.value[0], 'block1')
      expect(total.voucher_amount).toBe(3000)
      expect(total.repayment_principal).toBe(1000)
      expect(total.repayment_interest).toBe(75)
    })

    it('block4 合计 voucher_amount / mortgage_amount / guarantee_amount', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r._row_id!, 'voucher_amount', 500)
      data.updateBlockField(c._company_id!, 'block4', r._row_id!, 'mortgage_amount', 300)
      data.updateBlockField(c._company_id!, 'block4', r._row_id!, 'guarantee_amount', 200)
      const total = data.getBlockTotal(data.companies.value[0], 'block4')
      expect(total.voucher_amount).toBe(500)
      expect(total.mortgage_amount).toBe(300)
      expect(total.guarantee_amount).toBe(200)
    })

    it('空区块合计为 0', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      expect(data.getBlockTotal(data.companies.value[0], 'block1').voucher_amount).toBe(0)
    })
  })

  // ─── 5. 命名比例 getRepaymentRatio / getMortgageRatio ──────────────────────
  describe('getRepaymentRatio（block1.repayment_principal / closing_balance * 100）', () => {
    it('repayment_principal 优先作为分子', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      // voucher_amount=800 但 repayment_principal=300 → 用 repayment_principal
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'voucher_amount', 800)
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'repayment_principal', 300)
      expect(data.getRepaymentRatio(data.companies.value[0])).toBe(30)
    })

    it('仅 voucher_amount（repayment_principal 缺失=0）→ 分子为 0 → 比例 0', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'voucher_amount', 800)
      expect(data.getRepaymentRatio(data.companies.value[0])).toBe(0)
    })

    it('🔴 空基数（closing_balance=0）→ 返回 0（非 null）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 0 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'repayment_principal', 500)
      const ratio = data.getRepaymentRatio(data.companies.value[0])
      expect(ratio).toBe(0)
      expect(ratio).not.toBeNull()
    })

    it('🔴 空基数（closing_balance 缺失）→ 返回 0（非 null）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'repayment_principal', 500)
      const ratio = data.getRepaymentRatio(data.companies.value[0])
      expect(ratio).toBe(0)
      expect(ratio).not.toBeNull()
    })
  })

  describe('getMortgageRatio（block4.mortgage_amount / closing_balance * 100）', () => {
    it('mortgage_amount 优先作为分子', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'voucher_amount', 900)
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'mortgage_amount', 500)
      expect(data.getMortgageRatio(data.companies.value[0])).toBe(25)
    })

    it('🔴 空基数（closing_balance=0）→ 返回 0（非 null）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 0 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'mortgage_amount', 500)
      const ratio = data.getMortgageRatio(data.companies.value[0])
      expect(ratio).toBe(0)
      expect(ratio).not.toBeNull()
    })

    it('🔴 空基数（closing_balance 缺失）→ 返回 0（非 null）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'mortgage_amount', 500)
      expect(data.getMortgageRatio(data.companies.value[0])).toBe(0)
    })
  })

  // ─── 6. getCompletionStatus / hasAbnormal ──────────────────────────────────
  describe('getCompletionStatus / hasAbnormal', () => {
    it('getCompletionStatus 按 4 区块是否有行计数', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      expect(data.getCompletionStatus(data.companies.value[0])).toEqual({ completed: 0, total: 4, rate: 0 })
      data.addBlockRow(c._company_id!, 'block1')
      data.addBlockRow(c._company_id!, 'block2')
      expect(data.getCompletionStatus(data.companies.value[0])).toEqual({ completed: 2, total: 4, rate: 50 })
    })

    it('getCompletionStatus 4 区块全有行 → rate 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c._company_id!, b))
      expect(data.getCompletionStatus(data.companies.value[0]).rate).toBe(100)
    })

    it('hasAbnormal 任一区块行 is_abnormal=是 → true', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      expect(data.hasAbnormal(data.companies.value[0])).toBe(false)
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'is_abnormal', '是')
      expect(data.hasAbnormal(data.companies.value[0])).toBe(true)
    })
  })

  // ─── 7. metrics ─────────────────────────────────────────────────────────────
  describe('metrics', () => {
    it('receipt_ratio←getRepaymentRatio、shipment_ratio←getMortgageRatio', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 1000 })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'repayment_principal', 300)
      const r4 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r4._row_id!, 'mortgage_amount', 400)
      const dist = data.metrics.value.ratio_distribution
      expect(dist.length).toBe(1)
      expect(dist[0].receipt_ratio).toBe(30)
      expect(dist[0].shipment_ratio).toBe(40)
    })

    it('metrics 统计 total / completed / abnormal / completion_rate', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c._company_id!, b))
      expect(data.metrics.value.total_companies).toBe(1)
      expect(data.metrics.value.completed_companies).toBe(1)
      expect(data.metrics.value.completion_rate).toBe(100)
      expect(data.metrics.value.abnormal_companies).toBe(0)
    })
  })

  // ─── 8. buildPayload / persistAll ──────────────────────────────────────────
  describe('buildPayload / persistAll', () => {
    it('buildPayload _format=alternative-l05-v1 + balance 写 receipt_check_ratio/shipment_check_ratio', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 1000 })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'repayment_principal', 250)
      const r4 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r4._row_id!, 'mortgage_amount', 600)
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-l05-v1')
      expect(payload.companies[0].balance?.receipt_check_ratio).toBe(25)
      expect(payload.companies[0].balance?.shipment_check_ratio).toBe(60)
    })

    it('persistAll 返回等价 payload 且清 isDirty', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'A' })
      expect(data.isDirty.value).toBe(true)
      const payload = data.persistAll()
      expect(payload._format).toBe('alternative-l05-v1')
      expect(data.isDirty.value).toBe(false)
    })
  })

  // ─── 9. 独有面：balanceSummary / getClosingBalance / importFromSummary ──────
  describe('balanceSummary（L05 独有）', () => {
    it('currentLoan = 各公司 block3.voucher_amount 合计', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      const c2 = data.addCompany({ entity_name: 'B' })
      const r1 = data.addBlockRow(c1._company_id!, 'block3')!
      data.updateBlockField(c1._company_id!, 'block3', r1._row_id!, 'voucher_amount', 1000)
      const r2 = data.addBlockRow(c2._company_id!, 'block3')!
      data.updateBlockField(c2._company_id!, 'block3', r2._row_id!, 'voucher_amount', 2500)
      expect(data.balanceSummary.value.currentLoan).toBe(3500)
      expect(data.balanceSummary.value.investmentType).toBe('长期应付款/借款')
    })

    it('balanceSummary 汇总 opening/debit/credit/closing + 平均比例', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', {
        item_name: '长期应付款/借款',
        opening_balance: 100,
        debit_amount: 20,
        credit_amount: 30,
        closing_balance: 1000,
      })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'repayment_principal', 300)
      const r4 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r4._row_id!, 'mortgage_amount', 400)
      const s = data.balanceSummary.value
      expect(s.openingBalance).toBe(100)
      expect(s.debitAmount).toBe(20)
      expect(s.creditAmount).toBe(30)
      expect(s.closingBalance).toBe(1000)
      // 单公司平均 = 该公司比例
      expect(s.repaymentCheckRatio).toBe(30)
      expect(s.mortgageCheckRatio).toBe(40)
    })

    it('getClosingBalance 读取 balance.closing_balance（缺失=0）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      expect(data.getClosingBalance(data.companies.value[0])).toBe(0)
      data.updateCompany(c._company_id!, 'balance', { item_name: '长期应付款/借款', closing_balance: 777 })
      expect(data.getClosingBalance(data.companies.value[0])).toBe(777)
    })
  })

  describe('importFromSummary（mock http，sheet=L0-5，内部调 importCompanies）', () => {
    it('拉取未回函实体并带入公司列表，返回实体总数', async () => {
      vi.mocked(http.get).mockResolvedValue({
        data: {
          data: [
            { entity_name: 'A银行', confirm_index: 'L-1', confirm_amount: 5000 },
            { entity_name: 'B银行', confirm_index: 'L-2', confirm_amount: 8000 },
          ],
        },
      })
      const data = createInstance()
      const n = await data.importFromSummary()
      expect(n).toBe(2)
      expect(http.get).toHaveBeenCalledWith(
        expect.stringContaining('/l0/unreplied-entities'),
        { params: { sheet: 'L0-5' } },
      )
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[0].entity_name).toBe('A银行')
      expect(data.companies.value[0]._source).toBe('auto')
      expect(data.companies.value[0].balance?.closing_balance).toBe(5000)
      expect(data.companies.value[0].balance?.item_name).toBe('长期应付款/借款')
      expect(data.loading.value).toBe(false)
    })

    it('去重后仍返回实体总数（返回值=拉取数非新增数）', async () => {
      vi.mocked(http.get).mockResolvedValue({
        data: {
          data: [
            { entity_name: '重复', confirm_index: 'L-1', confirm_amount: 100 },
            { entity_name: '新', confirm_index: 'L-2', confirm_amount: 200 },
          ],
        },
      })
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'L-1' })
      const n = await data.importFromSummary()
      expect(n).toBe(2)
      // 已有 1 + 仅新增 L-2 = 2
      expect(data.companies.value.length).toBe(2)
    })

    it('空结果 → 返回 0', async () => {
      vi.mocked(http.get).mockResolvedValue({ data: { data: [] } })
      const data = createInstance()
      expect(await data.importFromSummary()).toBe(0)
      expect(data.companies.value.length).toBe(0)
    })

    it('http 异常 → 返回 0（catch 兜底）', async () => {
      vi.mocked(http.get).mockRejectedValue(new Error('network'))
      const data = createInstance()
      expect(await data.importFromSummary()).toBe(0)
      expect(data.companies.value.length).toBe(0)
      expect(data.loading.value).toBe(false)
    })
  })
})
