/**
 * createAlternativeConfirmationData.spec.ts — Shared_Core 工厂通用单测
 *
 * 用最小 fake config 验证 design.md Correctness Properties：
 * - P1  buildPayload._format === config.format
 * - P3  getBlockTotal === precise(sum)（每 sumField）
 * - P4  completion 计数 / rate
 * - P5  hasAbnormal
 * - P6  addCompany seq=max+1+isDirty；importCompanies 去重+seq 续接；deleteCompany 后 selectedCompanyId 回退首个
 * - P7  metrics 聚合 + ratio 映射
 * - P8  init 格式门（匹配载入 / 不匹配空 / 不传 htmlData 不 init）
 * - P9  buildPayload 每公司 balance 写 payloadKey=getRatio
 * - P10 emptyBase：'null' 组 base 无效返回 null；'zero' 组返回 0；per-rule calcRatio 覆盖；字段回退优先级
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  createAlternativeConfirmationData,
  type AltConfig,
} from '../createAlternativeConfirmationData'
import type { AlternativeCompany } from '../../alternativeD05/alternativeD05Types'

// ─── 最小 fake config ────────────────────────────────────────────────────────

/**
 * fake sumFields：
 * - block3 → ['recv_a', 'recv_b']（用于验证字段回退优先级）
 * - block4 → ['ship_amt']
 * - block1/block2 → []
 */
function fakeSumFields(blockType: string): string[] {
  if (blockType === 'block3') return ['recv_a', 'recv_b']
  if (blockType === 'block4') return ['ship_amt']
  return []
}

function makeConfig(overrides: Partial<AltConfig> = {}): AltConfig {
  return {
    format: 'alternative-fake-v1',
    getSumFields: fakeSumFields,
    defaultBalance: () => ({ item_name: '测试科目' }),
    baseAmount: (c) => Number(c.balance?.base_amount ?? 0),
    ratios: [
      { key: 'receipt', block: 'block3', fields: ['recv_a', 'recv_b'], payloadKey: 'receipt_check_ratio' },
      { key: 'shipment', block: 'block4', fields: ['ship_amt'], payloadKey: 'shipment_check_ratio' },
    ],
    metricRatioKeys: { receipt: 'receipt', shipment: 'shipment' },
    ...overrides,
  }
}

// 便捷：造一个含 4 区块行的公司
function seedCompanyWithRows(core: ReturnType<typeof createAlternativeConfirmationData>): AlternativeCompany {
  const c = core.addCompany({ entity_name: 'Alpha', balance: { base_amount: 1000 } })
  const id = c._company_id!
  core.addBlockRow(id, 'block1')
  core.addBlockRow(id, 'block2')
  core.addBlockRow(id, 'block3')
  core.addBlockRow(id, 'block4')
  return core.companies.value.find((x) => x._company_id === id)!
}

// ─── P1：format 恒等 ────────────────────────────────────────────────────────

describe('P1 format 恒等', () => {
  it('buildPayload._format === config.format', () => {
    const core = createAlternativeConfirmationData(makeConfig({ format: 'alternative-xyz-v1' }))
    expect(core.buildPayload()._format).toBe('alternative-xyz-v1')
  })
})

// ─── P3：区块合计 = precise(sum) ────────────────────────────────────────────

describe('P3 区块合计', () => {
  it('getBlockTotal 对每个 sumField = precise(sum)', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r1 = core.addBlockRow(id, 'block3')!
    const r2 = core.addBlockRow(id, 'block3')!
    core.updateBlockField(id, 'block3', r1._row_id!, 'recv_a', 10.111)
    core.updateBlockField(id, 'block3', r2._row_id!, 'recv_a', 20.222)
    core.updateBlockField(id, 'block3', r1._row_id!, 'recv_b', 5)
    const company = core.companies.value.find((x) => x._company_id === id)!
    const totals = core.getBlockTotal(company, 'block3')
    // recv_a = precise(10.111 + 20.222) = 30.33
    expect(totals.recv_a).toBe(30.33)
    // recv_b = precise(5 + 0) = 5
    expect(totals.recv_b).toBe(5)
  })

  it('非数值字段按 0 计入（NaN→0）', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r1 = core.addBlockRow(id, 'block4')!
    core.updateBlockField(id, 'block4', r1._row_id!, 'ship_amt', 'not-a-number')
    const company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.getBlockTotal(company, 'block4').ship_amt).toBe(0)
  })
})

// ─── P4：完成度 ─────────────────────────────────────────────────────────────

describe('P4 完成度', () => {
  it('completed = 非空区块数；rate=round(completed/4*100)', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    // 0 块
    let company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.getCompletionStatus(company)).toEqual({ completed: 0, total: 4, rate: 0 })
    // 1 块
    core.addBlockRow(id, 'block1')
    company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.getCompletionStatus(company)).toEqual({ completed: 1, total: 4, rate: 25 })
    // 3 块
    core.addBlockRow(id, 'block2')
    core.addBlockRow(id, 'block3')
    company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.getCompletionStatus(company)).toEqual({ completed: 3, total: 4, rate: 75 })
    // 4 块
    core.addBlockRow(id, 'block4')
    company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.getCompletionStatus(company)).toEqual({ completed: 4, total: 4, rate: 100 })
  })
})

// ─── P5：异常检测 ───────────────────────────────────────────────────────────

describe('P5 异常检测', () => {
  it('hasAbnormal ⟺ 任一块任一行 is_abnormal===是', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r = core.addBlockRow(id, 'block2')!
    let company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.hasAbnormal(company)).toBe(false)
    core.updateBlockField(id, 'block2', r._row_id!, 'is_abnormal', '是')
    company = core.companies.value.find((x) => x._company_id === id)!
    expect(core.hasAbnormal(company)).toBe(true)
  })
})

// ─── P6：CRUD 不变式 ────────────────────────────────────────────────────────

describe('P6 CRUD 不变式', () => {
  it('addCompany seq=max+1 且 isDirty=true，返回新公司', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    expect(core.isDirty.value).toBe(false)
    const a = core.addCompany()
    expect(a.seq).toBe(1)
    expect(core.isDirty.value).toBe(true)
    const b = core.addCompany()
    expect(b.seq).toBe(2)
    // 默认 balance 用 config.defaultBalance()
    expect(a.balance).toEqual({ item_name: '测试科目' })
  })

  it('addCompany 兜底生成 _company_id（partial 传空 _company_id 时）', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ _company_id: '' })
    expect(c._company_id).toBeTruthy()
  })

  it('importCompanies 按 confirm_index 去重且 seq 续接', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    core.addCompany({ confirm_index: 'D0-1-001' }) // seq=1
    core.importCompanies([
      { entity_name: 'X', confirm_index: 'D0-1-001' }, // 重复→跳过
      { entity_name: 'Y', confirm_index: 'D0-1-002' }, // seq 续接
      { entity_name: 'Z', confirm_index: 'D0-1-003' },
    ])
    const names = core.companies.value.map((c) => c.entity_name)
    expect(names).toEqual(['', 'Y', 'Z'])
    const seqs = core.companies.value.map((c) => c.seq)
    expect(seqs).toEqual([1, 2, 3])
    // _source 默认 'auto'
    expect(core.companies.value[1]._source).toBe('auto')
    // 默认 balance 合并
    expect(core.companies.value[1].balance).toEqual({ item_name: '测试科目' })
  })

  it('importCompanies 合并 item.balance 覆盖默认', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    core.importCompanies([{ entity_name: 'Y', confirm_index: 'i1', balance: { base_amount: 500 } }])
    expect(core.companies.value[0].balance).toEqual({ item_name: '测试科目', base_amount: 500 })
  })

  it('deleteCompany 后 selectedCompanyId 回退首个', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const a = core.addCompany()
    const b = core.addCompany()
    core.selectedCompanyId.value = b._company_id!
    core.deleteCompany(b._company_id!)
    // 回退到首个 (a)
    expect(core.selectedCompanyId.value).toBe(a._company_id)
    // 删除最后一个 → null
    core.deleteCompany(a._company_id!)
    expect(core.selectedCompanyId.value).toBeNull()
  })
})

// ─── P7：metrics 聚合 + ratio 映射 ──────────────────────────────────────────

describe('P7 metrics 聚合', () => {
  it('total/completed/abnormal/completion_rate + ratio_distribution 映射', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    // 公司 1：4 块全非空 + 有异常 + base=1000
    const c1 = seedCompanyWithRows(core)
    const id1 = c1._company_id!
    const b3row = core.companies.value.find((x) => x._company_id === id1)!.block3_rows![0]
    core.updateBlockField(id1, 'block3', b3row._row_id!, 'recv_a', 200)
    core.updateBlockField(id1, 'block3', b3row._row_id!, 'is_abnormal', '是')
    const b4row = core.companies.value.find((x) => x._company_id === id1)!.block4_rows![0]
    core.updateBlockField(id1, 'block4', b4row._row_id!, 'ship_amt', 100)
    // 公司 2：仅 1 块 + 无异常
    const c2 = core.addCompany({ entity_name: 'Beta', balance: { base_amount: 0 } })
    core.addBlockRow(c2._company_id!, 'block1')

    const m = core.metrics.value
    expect(m.total_companies).toBe(2)
    expect(m.completed_companies).toBe(1) // 只有公司1 4块全非空
    expect(m.abnormal_companies).toBe(1)
    expect(m.completion_rate).toBe(50) // round(1/2*100)
    // ratio_distribution 映射 metricRatioKeys
    expect(m.ratio_distribution).toHaveLength(2)
    // 公司1 receipt = precise(200/1000*100)=20；shipment=precise(100/1000*100)=10
    expect(m.ratio_distribution[0]).toEqual({ entity_name: 'Alpha', receipt_ratio: 20, shipment_ratio: 10 })
    // 公司2 base=0 → null（emptyBase 默认 'null'）
    expect(m.ratio_distribution[1]).toEqual({ entity_name: 'Beta', receipt_ratio: null, shipment_ratio: null })
  })

  it('entity_name 空 → 未命名', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    core.addCompany({ balance: { base_amount: 1000 } })
    expect(core.metrics.value.ratio_distribution[0].entity_name).toBe('未命名')
  })
})

// ─── P8：init 格式门 ────────────────────────────────────────────────────────

describe('P8 init 格式门', () => {
  it('格式匹配 → 载入 companies（ensure ids）+ isDirty=false', () => {
    const htmlData = ref<any>({
      _format: 'alternative-fake-v1',
      companies: [
        { entity_name: 'FromHtml', block1_rows: [{ recv_a: 1 }] },
      ],
    })
    const core = createAlternativeConfirmationData(makeConfig({ htmlData: () => htmlData.value }))
    expect(core.companies.value).toHaveLength(1)
    expect(core.companies.value[0].entity_name).toBe('FromHtml')
    // ensureCompanyId 补 _company_id
    expect(core.companies.value[0]._company_id).toBeTruthy()
    // ensureRowId 补 _row_id
    expect(core.companies.value[0].block1_rows![0]._row_id).toBeTruthy()
    expect(core.isDirty.value).toBe(false)
  })

  it('格式不匹配 → companies 置空', () => {
    const htmlData = ref<any>({ _format: 'other-format', companies: [{ entity_name: 'X' }] })
    const core = createAlternativeConfirmationData(makeConfig({ htmlData: () => htmlData.value }))
    expect(core.companies.value).toEqual([])
  })

  it('不传 htmlData → 不 init（companies 空，_initFromHtmlData 手动可调）', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    expect(core.companies.value).toEqual([])
    // 手动调 _initFromHtmlData 格式匹配可载入
    core._initFromHtmlData({ _format: 'alternative-fake-v1', companies: [{ entity_name: 'Manual' }] })
    expect(core.companies.value).toHaveLength(1)
    expect(core.companies.value[0].entity_name).toBe('Manual')
  })

  it('watch：htmlData 变化后重建 companies', async () => {
    const htmlData = ref<any>({ _format: 'alternative-fake-v1', companies: [{ entity_name: 'A' }] })
    const core = createAlternativeConfirmationData(makeConfig({ htmlData: () => htmlData.value }))
    expect(core.companies.value).toHaveLength(1)
    htmlData.value = { _format: 'alternative-fake-v1', companies: [{ entity_name: 'B' }, { entity_name: 'C' }] }
    await Promise.resolve()
    await new Promise((r) => setTimeout(r, 0))
    expect(core.companies.value).toHaveLength(2)
  })
})

// ─── P9：payload 比例固化 ───────────────────────────────────────────────────

describe('P9 payload 比例固化', () => {
  it('buildPayload 每公司 balance 写 payloadKey=getRatio', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ entity_name: 'Alpha', balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r3 = core.addBlockRow(id, 'block3')!
    core.updateBlockField(id, 'block3', r3._row_id!, 'recv_a', 250)
    const r4 = core.addBlockRow(id, 'block4')!
    core.updateBlockField(id, 'block4', r4._row_id!, 'ship_amt', 300)

    const payload = core.buildPayload()
    const comp = payload.companies[0]
    // receipt = 250/1000*100 = 25；shipment = 300/1000*100 = 30
    expect(comp.balance!.receipt_check_ratio).toBe(25)
    expect(comp.balance!.shipment_check_ratio).toBe(30)
    // 原 balance 字段保留
    expect((comp.balance as any).base_amount).toBe(1000)
  })

  it('payloadKey 使用 config.ratios 声明的键名', () => {
    const core = createAlternativeConfirmationData(
      makeConfig({
        ratios: [
          { key: 'receipt', block: 'block3', fields: ['recv_a'], payloadKey: 'custom_ratio_key' },
          { key: 'shipment', block: 'block4', fields: ['ship_amt'], payloadKey: 'other_key' },
        ],
      })
    )
    core.addCompany({ balance: { base_amount: 1000 } })
    const comp = core.buildPayload().companies[0]
    expect(comp.balance).toHaveProperty('custom_ratio_key')
    expect(comp.balance).toHaveProperty('other_key')
    expect(comp.balance).not.toHaveProperty('receipt_check_ratio')
  })
})

// ─── P10：emptyBase 语义 + per-rule calcRatio + 字段回退 ────────────────────

describe('P10 emptyBase / calcRatio 覆盖 / 字段回退', () => {
  it("emptyBase 默认 'null'：base 无效返回 null", () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 0 } })
    const company = core.companies.value.find((x) => x._company_id === c._company_id)!
    expect(core.getRatio(company, 'receipt')).toBeNull()
  })

  it("emptyBase 'zero'（L05 语义）：base 无效返回 0", () => {
    const core = createAlternativeConfirmationData(makeConfig({ emptyBase: 'zero' }))
    const c = core.addCompany({ balance: { base_amount: 0 } })
    const company = core.companies.value.find((x) => x._company_id === c._company_id)!
    expect(core.getRatio(company, 'receipt')).toBe(0)
  })

  it('per-rule calcRatio 覆盖 config.calcRatio 与默认', () => {
    // rule 覆盖：返回固定 2（→ precise(2*100)=200）
    const core = createAlternativeConfirmationData(
      makeConfig({
        calcRatio: () => 99, // config 级
        ratios: [
          { key: 'receipt', block: 'block3', fields: ['recv_a'], payloadKey: 'receipt_check_ratio', calcRatio: () => 2 },
          { key: 'shipment', block: 'block4', fields: ['ship_amt'], payloadKey: 'shipment_check_ratio' },
        ],
      })
    )
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r3 = core.addBlockRow(id, 'block3')!
    core.updateBlockField(id, 'block3', r3._row_id!, 'recv_a', 1)
    const r4 = core.addBlockRow(id, 'block4')!
    core.updateBlockField(id, 'block4', r4._row_id!, 'ship_amt', 1)
    const company = core.companies.value.find((x) => x._company_id === id)!
    // receipt：per-rule calcRatio ()=>2 → precise(2*100)=200
    expect(core.getRatio(company, 'receipt')).toBe(200)
    // shipment：config.calcRatio ()=>99 → precise(99*100)=9900
    expect(core.getRatio(company, 'shipment')).toBe(9900)
  })

  it('字段回退优先级：取 fields 中第一个 total 有值的', () => {
    // receipt fields = ['recv_a','recv_b']；recv_a 有行值时用 recv_a，否则回退 recv_b
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r3 = core.addBlockRow(id, 'block3')!
    // recv_a=0（行存在→total.recv_a=0，非 undefined），recv_b=50
    core.updateBlockField(id, 'block3', r3._row_id!, 'recv_a', 0)
    core.updateBlockField(id, 'block3', r3._row_id!, 'recv_b', 50)
    const company = core.companies.value.find((x) => x._company_id === id)!
    // recv_a total=0（非 undefined）→ 命中第一个 → sum=0 → ratio=0
    expect(core.getRatio(company, 'receipt')).toBe(0)
  })

  it('字段回退：第一个字段不在 sumFields 时回退第二个', () => {
    // getSumFields(block3)=['recv_a','recv_b']，但 rule.fields 首个用不在 total 的键
    const core = createAlternativeConfirmationData(
      makeConfig({
        ratios: [
          // 'missing' 不在 getSumFields(block3) → total 无该键(undefined) → 回退 recv_b
          { key: 'receipt', block: 'block3', fields: ['missing', 'recv_b'], payloadKey: 'receipt_check_ratio' },
          { key: 'shipment', block: 'block4', fields: ['ship_amt'], payloadKey: 'shipment_check_ratio' },
        ],
      })
    )
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const id = c._company_id!
    const r3 = core.addBlockRow(id, 'block3')!
    core.updateBlockField(id, 'block3', r3._row_id!, 'recv_b', 400)
    const company = core.companies.value.find((x) => x._company_id === id)!
    // missing 未计算(undefined) → 回退 recv_b=400 → 400/1000*100=40
    expect(core.getRatio(company, 'receipt')).toBe(40)
  })

  it('getRatio 未知 key → null', () => {
    const core = createAlternativeConfirmationData(makeConfig())
    const c = core.addCompany({ balance: { base_amount: 1000 } })
    const company = core.companies.value.find((x) => x._company_id === c._company_id)!
    expect(core.getRatio(company, 'nonexistent')).toBeNull()
  })
})
