/**
 * useAlternativeK06Data.spec.ts — K0-6 其他应付款替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（2026-07-17 G4）：alternative* 八套近重复中 K06 无测试。锁定 K06 **收敛前当前实现**，
 * 作为收敛为工厂前的零回归安全网。断言全部匹配真实当前行为，不改被测源码。
 *
 * K06 是异质最大的一套（相对 D05/F05/F06/H05 的差异，本测试重点）：
 * - default export 仅 `(wpId, projectId)` positional 构造
 * - 构造末尾自动调 loadAll()：从 http `render-config` 提取 sheet_name 含 'K0-6' 且
 *   html_data._format==='alternative-k06-v1' 的 sheet 才载入 companies，否则空
 * - persistAll 逐块 POST `checklist-responses`，item_id 形如 `K0-6-alt-{entityKey}-block{N}-rows`
 * - 比例是命名方法 getPostPaymentRatio(c) / getReconcileRatio(c)（不是 getCheckRatio）
 * - _format = alternative-k06-v1；默认 balance.item_name = '其他应付款'
 * - base = balance.closing_balance ?? balance.credit_amount；base 无效 → null
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ─── Mock http（loadAll 在构造时即触发 http.get，需在实例化前配置好 mock） ──────────
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mocks.get(...args),
    post: (...args: any[]) => mocks.post(...args),
  },
}))

import useAlternativeK06Data, {
  BLOCK_TITLES_K06,
  getSumFieldsK06,
} from '../useAlternativeK06Data'

// 可变响应，测试可在实例化 / 调用前覆盖
let renderConfigResponse: any
let unrepliedResponse: any

beforeEach(() => {
  renderConfigResponse = { data: { data: { sheets: [] } } }
  unrepliedResponse = { data: [] }
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.get.mockImplementation((url: string) => {
    const u = String(url)
    if (u.includes('render-config')) return Promise.resolve(renderConfigResponse)
    if (u.includes('unreplied-entities')) return Promise.resolve(unrepliedResponse)
    return Promise.resolve({ data: {} })
  })
  mocks.post.mockResolvedValue({ data: {} })
})

/** 构造实例并等待构造时 loadAll() 的 promise 链完成 */
async function createInstance() {
  const data = useAlternativeK06Data('wp-1', 'proj-1')
  await flushPromises()
  return data
}

describe('useAlternativeK06Data', () => {
  // ── 1. loadAll（构造时触发） ───────────────────────────────────────────────
  describe('loadAll（构造时自动触发，从 render-config 提取 K0-6 sheet）', () => {
    it('render-config 含 K0-6 sheet 且 _format 匹配 → companies 载入', async () => {
      renderConfigResponse = {
        data: {
          data: {
            sheets: [
              {
                sheet_name: 'K0-6 其他应付款替代程序',
                html_data: {
                  _format: 'alternative-k06-v1',
                  companies: [{ entity_name: '债权人甲' }, { entity_name: '债权人乙' }],
                },
              },
            ],
          },
        },
      }
      const data = await createInstance()
      expect(data.companies.value.length).toBe(2)
      // ensureCompanyId 补齐 _company_id
      expect(data.companies.value[0]._company_id).toBeTruthy()
      expect(data.companies.value[0].entity_name).toBe('债权人甲')
      expect(data.loading.value).toBe(false)
      expect(data.isDirty.value).toBe(false)
    })

    it('sheet 存在但 _format 不匹配 → 空数组', async () => {
      renderConfigResponse = {
        data: {
          data: {
            sheets: [
              {
                sheet_name: 'K0-6 其他应付款',
                html_data: { _format: 'alternative-k05-v1', companies: [{ entity_name: 'X' }] },
              },
            ],
          },
        },
      }
      const data = await createInstance()
      expect(data.companies.value).toEqual([])
    })

    it('无匹配 sheet → 空数组', async () => {
      renderConfigResponse = {
        data: { data: { sheets: [{ sheet_name: 'D0-5 别的表', html_data: {} }] } },
      }
      const data = await createInstance()
      expect(data.companies.value).toEqual([])
    })

    it('render-config 请求失败 → 空数组（catch 兜底）', async () => {
      mocks.get.mockImplementation((url: string) => {
        if (String(url).includes('render-config')) return Promise.reject(new Error('boom'))
        return Promise.resolve({ data: {} })
      })
      const data = await createInstance()
      expect(data.companies.value).toEqual([])
    })
  })

  // ── 2. 公司 CRUD ───────────────────────────────────────────────────────────
  describe('公司 CRUD', () => {
    it('addCompany 默认 balance.item_name=其他应付款', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('其他应付款')
      expect(c._company_id).toBeTruthy()
      expect(c.seq).toBe(1)
      expect(data.isDirty.value).toBe(true)
    })

    it('addCompany seq 自增', async () => {
      const data = await createInstance()
      data.addCompany({ entity_name: 'A' })
      const c2 = data.addCompany({ entity_name: 'B' })
      expect(c2.seq).toBe(2)
    })

    it('deleteCompany 删除并重置 selectedCompanyId', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.selectedCompanyId.value = c._company_id!
      data.deleteCompany(c._company_id!)
      expect(data.companies.value.length).toBe(0)
      expect(data.selectedCompanyId.value).toBeNull()
    })

    it('updateCompany 更新字段', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'entity_name', '改名')
      expect(data.companies.value[0].entity_name).toBe('改名')
    })

    it('importCompanies 按 confirm_index 去重 + 默认其他应付款', async () => {
      const data = await createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].balance?.item_name).toBe('其他应付款')
    })
  })

  // ── 3. 区块行 CRUD ─────────────────────────────────────────────────────────
  describe('区块行 CRUD', () => {
    it('addBlockRow 新增行并返回，默认 is_abnormal=否', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block1')
      expect(row).toBeTruthy()
      expect(row!._row_id).toBeTruthy()
      expect(row!.seq).toBe(1)
      expect(row!.is_abnormal).toBe('否')
      expect(data.companies.value[0].block1_rows!.length).toBe(1)
    })

    it('addBlockRow 公司不存在 → undefined', async () => {
      const data = await createInstance()
      expect(data.addBlockRow('nope', 'block1')).toBeUndefined()
    })

    it('updateBlockField 更新行字段', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block2')!
      data.updateBlockField(c._company_id!, 'block2', row._row_id!, 'amount', 123)
      expect(data.companies.value[0].block2_rows![0].amount).toBe(123)
    })

    it('deleteBlockRow 删除行', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.deleteBlockRow(c._company_id!, 'block3', row._row_id!)
      expect(data.companies.value[0].block3_rows!.length).toBe(0)
    })
  })

  // ── 4. getBlockTotal（SUM_FIELDS） ─────────────────────────────────────────
  describe('getBlockTotal（block1: amount/paymentAmount；block2/3/4: amount）', () => {
    it('block1 同时合计 amount 与 paymentAmount', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      const r2 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'amount', 10)
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'paymentAmount', 5)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'amount', 20)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'paymentAmount', 15)
      const totals = data.getBlockTotal(data.companies.value[0], 'block1')
      expect(totals).toEqual({ amount: 30, paymentAmount: 20 })
    })

    it('block2 仅合计 amount', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r = data.addBlockRow(c._company_id!, 'block2')!
      data.updateBlockField(c._company_id!, 'block2', r._row_id!, 'amount', 42)
      data.updateBlockField(c._company_id!, 'block2', r._row_id!, 'paymentAmount', 999)
      const totals = data.getBlockTotal(data.companies.value[0], 'block2')
      expect(totals).toEqual({ amount: 42 })
    })
  })

  // ── 5. 命名比例 ────────────────────────────────────────────────────────────
  describe('命名比例 getPostPaymentRatio / getReconcileRatio', () => {
    it('getPostPaymentRatio = block1.paymentAmount 合计 / closing_balance * 100', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应付款', closing_balance: 1000 })
      const r = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r._row_id!, 'paymentAmount', 200)
      expect(data.getPostPaymentRatio(data.companies.value[0])).toBe(20)
    })

    it('getReconcileRatio = block4.amount 合计 / closing_balance * 100', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应付款', closing_balance: 1000 })
      const r = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', r._row_id!, 'amount', 400)
      expect(data.getReconcileRatio(data.companies.value[0])).toBe(40)
    })

    it('base 取 credit_amount 兜底（无 closing_balance 时）', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应付款', credit_amount: 500 })
      const r = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r._row_id!, 'paymentAmount', 100)
      expect(data.getPostPaymentRatio(data.companies.value[0])).toBe(20)
    })

    it('base 无效（无 closing_balance / credit_amount）→ null', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      expect(data.getPostPaymentRatio(data.companies.value[0])).toBeNull()
      expect(data.getReconcileRatio(data.companies.value[0])).toBeNull()
    })
  })

  // ── 6. getCompletionStatus / hasAbnormal ──────────────────────────────────
  describe('getCompletionStatus / hasAbnormal', () => {
    it('getCompletionStatus 统计有行的区块数', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.addBlockRow(c._company_id!, 'block1')
      data.addBlockRow(c._company_id!, 'block2')
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status).toEqual({ completed: 2, total: 4, rate: 50 })
    })

    it('getCompletionStatus 4 区块全有行 → rate 100', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) =>
        data.addBlockRow(c._company_id!, b),
      )
      expect(data.getCompletionStatus(data.companies.value[0]).rate).toBe(100)
    })

    it('hasAbnormal：任一区块存在 is_abnormal=是 → true', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r = data.addBlockRow(c._company_id!, 'block3')!
      expect(data.hasAbnormal(data.companies.value[0])).toBe(false)
      data.updateBlockField(c._company_id!, 'block3', r._row_id!, 'is_abnormal', '是')
      expect(data.hasAbnormal(data.companies.value[0])).toBe(true)
    })
  })

  // ── 7. metrics ─────────────────────────────────────────────────────────────
  describe('metrics（receipt_ratio←getPostPaymentRatio、shipment_ratio←getReconcileRatio）', () => {
    it('metrics 统计 + 比例映射', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应付款', closing_balance: 1000 })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) =>
        data.addBlockRow(c._company_id!, b),
      )
      // block1 paymentAmount=200 → post 20；block4 amount=400 → reconcile 40
      const b1 = data.companies.value[0].block1_rows![0]
      const b4 = data.companies.value[0].block4_rows![0]
      data.updateBlockField(c._company_id!, 'block1', b1._row_id!, 'paymentAmount', 200)
      data.updateBlockField(c._company_id!, 'block4', b4._row_id!, 'amount', 400)

      const m = data.metrics.value
      expect(m.total_companies).toBe(1)
      expect(m.completed_companies).toBe(1)
      expect(m.completion_rate).toBe(100)
      expect(m.ratio_distribution[0].receipt_ratio).toBe(20)
      expect(m.ratio_distribution[0].shipment_ratio).toBe(40)
    })

    it('metrics 异常公司计数', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r._row_id!, 'is_abnormal', '是')
      expect(data.metrics.value.abnormal_companies).toBe(1)
    })
  })

  // ── 8. buildPayload ────────────────────────────────────────────────────────
  describe('buildPayload', () => {
    it('_format=alternative-k06-v1 + balance 写 receipt/shipment_check_ratio', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '其他应付款', closing_balance: 1000 })
      const b1 = data.addBlockRow(c._company_id!, 'block1')!
      const b4 = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block1', b1._row_id!, 'paymentAmount', 300)
      data.updateBlockField(c._company_id!, 'block4', b4._row_id!, 'amount', 500)

      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-k06-v1')
      expect(payload.companies[0].balance?.receipt_check_ratio).toBe(30)
      expect(payload.companies[0].balance?.shipment_check_ratio).toBe(50)
    })
  })

  // ── 9. persistAll ──────────────────────────────────────────────────────────
  describe('persistAll（逐块 POST checklist-responses）', () => {
    it('每公司每块 POST 一次，item_id 形如 K0-6-alt-{entityKey}-block{N}-rows', async () => {
      const data = await createInstance()
      const c = data.addCompany({ entity_name: 'A' })
      const r = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r._row_id!, 'amount', 10)

      mocks.post.mockClear()
      const payload = data.persistAll()

      // 1 公司 × 4 区块 = 4 次 POST
      expect(mocks.post).toHaveBeenCalledTimes(4)

      const entityKey = c._company_id
      const urls = mocks.post.mock.calls.map((call) => call[0])
      const bodies = mocks.post.mock.calls.map((call) => call[1])

      urls.forEach((u) => expect(u).toBe('/api/workpapers/wp-1/checklist-responses'))
      expect(bodies.map((b) => b.item_id)).toEqual([
        `K0-6-alt-${entityKey}-block1-rows`,
        `K0-6-alt-${entityKey}-block2-rows`,
        `K0-6-alt-${entityKey}-block3-rows`,
        `K0-6-alt-${entityKey}-block4-rows`,
      ])
      // block1 remark 为 rows 的 JSON
      const block1Body = bodies.find((b) => b.item_id === `K0-6-alt-${entityKey}-block1-rows`)
      expect(block1Body.remark).toBe(JSON.stringify(data.companies.value[0].block1_rows))

      // 返回 payload + isDirty 复位
      expect(payload._format).toBe('alternative-k06-v1')
      expect(data.isDirty.value).toBe(false)
    })
  })

  // ── 10. importFromSummary ──────────────────────────────────────────────────
  describe('importFromSummary（从 K0-1 未回函列表带入，按 confirm_index 去重）', () => {
    it('带入未回函公司并去重', async () => {
      const data = await createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'C-1' })

      unrepliedResponse = {
        data: [
          { entity_name: '重复', confirm_index: 'C-1', confirm_amount: 100 },
          { entity_name: '新公司', confirm_index: 'C-2', confirm_amount: 888 },
        ],
      }
      const added = await data.importFromSummary()
      expect(added).toBe(1)
      expect(data.companies.value.length).toBe(2)
      const imported = data.companies.value[1]
      expect(imported.entity_name).toBe('新公司')
      expect(imported._source).toBe('auto')
      expect(imported.balance?.item_name).toBe('其他应付款')
      expect(imported.balance?.closing_balance).toBe(888)
    })

    it('unreplied-entities 请求带 sheet=K0-6 参数', async () => {
      const data = await createInstance()
      unrepliedResponse = { data: [] }
      await data.importFromSummary()
      const call = mocks.get.mock.calls.find((c) => String(c[0]).includes('unreplied-entities'))
      expect(call).toBeTruthy()
      expect(call![1]).toEqual({ params: { sheet: 'K0-6' } })
    })

    it('空列表 → 返回 0', async () => {
      const data = await createInstance()
      unrepliedResponse = { data: [] }
      expect(await data.importFromSummary()).toBe(0)
    })
  })

  // ── 11. 导出常量 / helper ───────────────────────────────────────────────────
  describe('导出 BLOCK_TITLES_K06 / getSumFieldsK06', () => {
    it('BLOCK_TITLES_K06 四区块标题', () => {
      expect(BLOCK_TITLES_K06).toEqual({
        block1: '①期后付款检查',
        block2: '②期末余额支持性证据',
        block3: '③本期发生额检查',
        block4: '④往来对账/协议证据',
      })
    })

    it('getSumFieldsK06 各区块字段', () => {
      expect(getSumFieldsK06('block1')).toEqual(['amount', 'paymentAmount'])
      expect(getSumFieldsK06('block2')).toEqual(['amount'])
      expect(getSumFieldsK06('block3')).toEqual(['amount'])
      expect(getSumFieldsK06('block4')).toEqual(['amount'])
      expect(getSumFieldsK06('unknown')).toEqual([])
    })
  })
})
