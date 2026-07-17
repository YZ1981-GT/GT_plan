/**
 * useAlternativeK05Data.spec.ts — K0-5 其他应收款替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（2026-07-17 G4 confirmation-alternative-factory-convergence Task 1）：
 * alternative* 八套近重复 composable 中 K05 无测试。本文件锁定 K05 **收敛前的当前行为**
 * （characterization），作为后续收敛为工厂前的零回归安全网——收敛后同一套断言应对工厂
 * 产出的 K05 composable 全绿，证明行为不变。不得修改被测实现。
 *
 * K05 相对 D05/F05 的差异（本测试重点）：
 * - _format: alternative-k05-v1
 * - 默认 balance.item_name = '其他应收款'
 * - getCheckRatio('post_receipt') 用 block1 receipt_amount；('reconcile') 用 block4 self_balance
 * - 基数 = balance.closing_balance（非 sales/purchase）；基数 0/缺失 → null
 * - payload 比例字段 receipt_check_ratio / reconcile_check_ratio
 * - K05 独有：balanceSummary（closingBalance=opening+debit-credit）/ getReconcileDiff / 构造重载两形态
 */
import { describe, it, expect } from 'vitest'
import useAlternativeK05Data from '../useAlternativeK05Data'
import type { CheckRow } from '../../alternativeD05/alternativeD05Types'

/** 创建 composable 实例（props 形态） */
function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'alternative-k05-v1', companies: [] }
  return useAlternativeK05Data({
    wpId: 'wp-k05',
    projectId: 'proj-1',
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useAlternativeK05Data', () => {
  // ─── 1. init 格式门 ─────────────────────────────────────────────────────
  describe('初始化格式门', () => {
    it('空 htmlData → 空数组', () => {
      expect(createInstance(null).companies.value).toEqual([])
    })

    it('格式不匹配 → 空数组', () => {
      expect(createInstance({ _format: 'wrong-format' }).companies.value).toEqual([])
      expect(createInstance({ _format: 'alternative-d05-v1', companies: [{ entity_name: 'X' }] }).companies.value).toEqual([])
    })

    it('alternative-k05-v1 正确初始化并补 _company_id', () => {
      const data = createInstance({
        _format: 'alternative-k05-v1',
        companies: [{ entity_name: 'ABC公司', confirm_index: 'K0-1-001' }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0].entity_name).toBe('ABC公司')
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })

  // ─── 2. 公司 CRUD ───────────────────────────────────────────────────────
  describe('公司 CRUD + 默认 balance', () => {
    it('addCompany 默认 balance.item_name=其他应收款 + seq=1 + isDirty', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: '测试公司' })
      expect(c.balance?.item_name).toBe('其他应收款')
      expect(c.seq).toBe(1)
      expect(data.companies.value.length).toBe(1)
      expect(data.isDirty.value).toBe(true)
    })

    it('addCompany seq = max+1', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'A' })
      const c2 = data.addCompany({ entity_name: 'B' })
      expect(c2.seq).toBe(2)
    })

    it('deleteCompany 删除公司', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: '公司A' })
      data.addCompany({ entity_name: '公司B' })
      data.deleteCompany(c1._company_id!)
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0].entity_name).toBe('公司B')
    })

    it('updateCompany 更新字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: '旧名' })
      data.updateCompany(c._company_id!, 'entity_name', '新名')
      expect(data.companies.value[0].entity_name).toBe('新名')
    })

    it('importCompanies 按 confirm_index 去重 + 默认其他应收款 + _source=auto', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新公司', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].entity_name).toBe('新公司')
      expect(data.companies.value[1].balance?.item_name).toBe('其他应收款')
      expect(data.companies.value[1]._source).toBe('auto')
    })
  })

  // ─── 3. 区块行 CRUD ─────────────────────────────────────────────────────
  describe('区块行 CRUD', () => {
    it('addBlockRow 新增行（seq=1 / is_abnormal=否 / _source=manual）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block1')
      expect(row).toBeTruthy()
      expect(row!.seq).toBe(1)
      expect(row!.is_abnormal).toBe('否')
      expect(row!._source).toBe('manual')
      expect(data.companies.value[0].block1_rows!.length).toBe(1)
    })

    it('deleteBlockRow 删除行', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block2')!
      data.deleteBlockRow(c._company_id!, 'block2', row._row_id!)
      expect(data.companies.value[0].block2_rows!.length).toBe(0)
    })

    it('updateBlockField 更新行字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'voucher_amount', 1000)
      expect(data.companies.value[0].block3_rows![0].voucher_amount).toBe(1000)
    })
  })

  // ─── 4. getBlockTotal（SUM_FIELDS） ─────────────────────────────────────
  describe('getBlockTotal', () => {
    it('block1 合计 voucher_amount / receipt_amount（精确小数）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      const r2 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'voucher_amount', 100.55)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'voucher_amount', 200.45)
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'receipt_amount', 0.1)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'receipt_amount', 0.2)
      const totals = data.getBlockTotal(data.companies.value[0], 'block1')
      expect(totals.voucher_amount).toBe(301)
      expect(totals.receipt_amount).toBe(0.3)
    })

    it('block4 合计 voucher_amount / other_balance / self_balance', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const r1 = data.addBlockRow(c._company_id!, 'block4')!
      const r2 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r1._row_id!, 'voucher_amount', 300)
      data.updateBlockField(c._company_id!, 'block4', r2._row_id!, 'voucher_amount', 200)
      data.updateBlockField(c._company_id!, 'block4', r1._row_id!, 'other_balance', 150)
      data.updateBlockField(c._company_id!, 'block4', r2._row_id!, 'other_balance', 50)
      data.updateBlockField(c._company_id!, 'block4', r1._row_id!, 'self_balance', 120)
      data.updateBlockField(c._company_id!, 'block4', r2._row_id!, 'self_balance', 80)
      const totals = data.getBlockTotal(data.companies.value[0], 'block4')
      expect(totals.voucher_amount).toBe(500)
      expect(totals.other_balance).toBe(200)
      expect(totals.self_balance).toBe(200)
    })
  })

  // ─── 5. getCheckRatio ───────────────────────────────────────────────────
  describe('getCheckRatio（K05 语义）', () => {
    it('closing_balance 缺失 → null', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'X' })
      expect(data.getCheckRatio(data.companies.value[0], 'post_receipt')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'reconcile')).toBeNull()
    })

    it('closing_balance = 0 → null', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应收款', closing_balance: 0 })
      expect(data.getCheckRatio(data.companies.value[0], 'post_receipt')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'reconcile')).toBeNull()
    })

    it('post_receipt = block1 receipt_amount 合计 / closing_balance * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应收款', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'receipt_amount', 300)
      expect(data.getCheckRatio(data.companies.value[0], 'post_receipt')).toBe(30)
    })

    it('reconcile = block4 self_balance 合计 / closing_balance * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应收款', closing_balance: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'self_balance', 500)
      expect(data.getCheckRatio(data.companies.value[0], 'reconcile')).toBe(25)
    })
  })

  // ─── 6. getCompletionStatus ─────────────────────────────────────────────
  describe('getCompletionStatus', () => {
    it('4 区块均无行 → completed=0 / rate=0', () => {
      const data = createInstance()
      data.addCompany({ entity_name: 'X' })
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status.completed).toBe(0)
      expect(status.total).toBe(4)
      expect(status.rate).toBe(0)
    })

    it('4 区块均有行 → completed=4 / rate=100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c._company_id!, b))
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status.completed).toBe(4)
      expect(status.rate).toBe(100)
    })

    it('2 区块有行 → completed=2 / rate=50', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.addBlockRow(c._company_id!, 'block1')
      data.addBlockRow(c._company_id!, 'block3')
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status.completed).toBe(2)
      expect(status.rate).toBe(50)
    })
  })

  // ─── 7. hasAbnormal ─────────────────────────────────────────────────────
  describe('hasAbnormal', () => {
    it('无异常行 → false', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.addBlockRow(c._company_id!, 'block1')
      expect(data.hasAbnormal(data.companies.value[0])).toBe(false)
    })

    it('任一区块任一行 is_abnormal=是 → true', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'is_abnormal', '是')
      expect(data.hasAbnormal(data.companies.value[0])).toBe(true)
    })
  })

  // ─── 8. metrics ─────────────────────────────────────────────────────────
  describe('metrics', () => {
    it('空数据看板指标', () => {
      const data = createInstance()
      expect(data.metrics.value.total_companies).toBe(0)
      expect(data.metrics.value.completed_companies).toBe(0)
      expect(data.metrics.value.abnormal_companies).toBe(0)
      expect(data.metrics.value.completion_rate).toBe(0)
    })

    it('统计 total/completed/abnormal + receipt/shipment 比例映射', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c1._company_id!, 'balance', { item_name: '其他应收款', closing_balance: 1000 })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c1._company_id!, b))
      // c1 的 block1 receipt_amount 用于 receipt_ratio、block4 self_balance 用于 shipment_ratio
      const b1 = data.companies.value[0].block1_rows![0]
      data.updateBlockField(c1._company_id!, 'block1', b1._row_id!, 'receipt_amount', 400)
      const b4 = data.companies.value[0].block4_rows![0]
      data.updateBlockField(c1._company_id!, 'block4', b4._row_id!, 'self_balance', 250)

      const c2 = data.addCompany({ entity_name: 'B' })
      const row = data.addBlockRow(c2._company_id!, 'block1')!
      data.updateBlockField(c2._company_id!, 'block1', row._row_id!, 'is_abnormal', '是')

      expect(data.metrics.value.total_companies).toBe(2)
      expect(data.metrics.value.completed_companies).toBe(1)
      expect(data.metrics.value.abnormal_companies).toBe(1)
      // receipt_ratio ← post_receipt (block1 receipt_amount / closing)；shipment_ratio ← reconcile (block4 self_balance / closing)
      const distA = data.metrics.value.ratio_distribution.find((d) => d.entity_name === 'A')!
      expect(distA.receipt_ratio).toBe(40)
      expect(distA.shipment_ratio).toBe(25)
    })
  })

  // ─── 9. buildPayload ────────────────────────────────────────────────────
  describe('buildPayload', () => {
    it('_format=alternative-k05-v1 + 固化 receipt/reconcile 比例', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应收款', closing_balance: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'receipt_amount', 500)
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-k05-v1')
      expect(payload.companies.length).toBe(1)
      expect(payload.companies[0].balance?.receipt_check_ratio).toBe(50)
      expect(payload.companies[0].balance).toHaveProperty('reconcile_check_ratio')
    })
  })

  // ─── 10. K05 独有面 ─────────────────────────────────────────────────────
  describe('balanceSummary（K05 独有）', () => {
    it('closingBalance = opening + debit - credit；currentAmount = debit + credit', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', {
        item_name: '其他应收款',
        opening_balance: 1000,
        debit_amount: 500,
        credit_amount: 300,
      })
      expect(data.balanceSummary.value.investmentType).toBe('其他应收款')
      expect(data.balanceSummary.value.openingBalance).toBe(1000)
      expect(data.balanceSummary.value.debitAmount).toBe(500)
      expect(data.balanceSummary.value.creditAmount).toBe(300)
      expect(data.balanceSummary.value.closingBalance).toBe(1200)
      expect(data.balanceSummary.value.currentAmount).toBe(800)
    })

    it('postCheckRatio / reconcileRatio 基于计算的 closingBalance', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', {
        item_name: '其他应收款',
        opening_balance: 1000,
        debit_amount: 500,
        credit_amount: 300,
      })
      // closingBalance = 1200
      const b1 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', b1._row_id!, 'receipt_amount', 600)
      const b4 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', b4._row_id!, 'self_balance', 300)
      expect(data.balanceSummary.value.postCheckRatio).toBe(50)
      expect(data.balanceSummary.value.reconcileRatio).toBe(25)
    })

    it('closingBalance <= 0 → 比例返回 0（非 null）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', {
        item_name: '其他应收款',
        opening_balance: 0,
        debit_amount: 0,
        credit_amount: 0,
      })
      expect(data.balanceSummary.value.closingBalance).toBe(0)
      expect(data.balanceSummary.value.postCheckRatio).toBe(0)
      expect(data.balanceSummary.value.reconcileRatio).toBe(0)
    })
  })

  describe('getReconcileDiff（K05 独有）', () => {
    it('= self_balance - other_balance', () => {
      const data = createInstance()
      const row: CheckRow = { self_balance: 1000, other_balance: 800 }
      expect(data.getReconcileDiff(row)).toBe(200)
    })

    it('缺失字段按 0 处理', () => {
      const data = createInstance()
      expect(data.getReconcileDiff({ self_balance: 500 })).toBe(500)
      expect(data.getReconcileDiff({})).toBe(0)
    })
  })

  describe('构造重载两形态', () => {
    it('(wpId, projectId) 形态可用（htmlData 默认 null → 空数组）', () => {
      const data = useAlternativeK05Data('wp-1', 'proj-1')
      expect(data.companies.value).toEqual([])
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('其他应收款')
      expect(data.companies.value.length).toBe(1)
    })

    it('({wpId,projectId,htmlData,readonly}) 形态可用', () => {
      const data = useAlternativeK05Data({
        wpId: 'wp-1',
        projectId: 'proj-1',
        htmlData: () => ({ _format: 'alternative-k05-v1', companies: [{ entity_name: 'ABC' }] }),
        readonly: false,
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0].entity_name).toBe('ABC')
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })
})
