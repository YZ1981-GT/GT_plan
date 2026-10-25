/**
 * useL5Detail.rowIdentity.spec.ts — L5-2 明细表稳定行身份 + 受管列模型 + 三区段测试
 *
 * Task: l5-true-bidirectional-2026-10-01 · T2
 *
 * 验证 L5-2 明细表（受管表 明细表L5-2，三区同键 store `L5-L5-2-rows`，行身份字段 `key`）：
 * 1. `newRowIdentity('l52det')` 生成 l52det 前缀且连续生成互不相同（铸号器不撞）。
 * 2. 新增行 key 唯一、带 section=saleLeaseback、带全部受管字段默认值（0）。
 * 3. 删中间行其余行 key 不变（位置化缺陷反例）。
 * 4. hydrate：缺 key 的历史行补铸、已有 key 优先保留；缺 section 的落默认区（售后租回）。
 * 5. html_only 字段键清单稳定（后端 provider 的 html_only_keys 必须与此逐值一致）。
 * 6. 新增字段默认值全 0（roll-forward 受管列 F~S + 账龄 T~X）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const promptMock = vi.fn().mockResolvedValue({ value: '测试款项' })
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: (...args: any[]) => promptMock(...args) },
}))

import {
  useL5Detail,
  createL5DetailRow,
  L5_HTML_ONLY_KEYS,
  L5_SECTION_SALE_LEASEBACK,
  type L5DetailRow,
} from '../useL5Detail'
import { newRowIdentity } from '../shared/rowIdentity'

function makeFormDataStub() {
  return {
    allResponses: ref(new Map<string, any>()),
    debouncedSave: vi.fn(),
  } as any
}

describe('L5-2 明细表稳定行身份 + 受管列模型 + 三区段', () => {
  beforeEach(() => {
    promptMock.mockClear()
  })

  it('newRowIdentity(l52det) 生成 l52det 前缀且连续生成互不相同', () => {
    const ids = new Set<string>()
    for (let i = 0; i < 50; i++) {
      const id = newRowIdentity('l52det')
      expect(id.startsWith('l52det-')).toBe(true)
      ids.add(id)
    }
    expect(ids.size).toBe(50)
  })

  it('createL5DetailRow 带 section=saleLeaseback 且全部受管字段默认 0', () => {
    const row = createL5DetailRow('某融资租赁')
    expect(row.key.startsWith('l52det-')).toBe(true)
    expect(row.section).toBe(L5_SECTION_SALE_LEASEBACK)
    expect(row.payableName).toBe('某融资租赁')
    // roll-forward 受管列 + 账龄桶默认 0
    const managedZeroKeys: (keyof L5DetailRow)[] = [
      'beginning', 'periodRepayment', 'periodIncrease', 'endBalance',
      'priorAdjustment', 'priorReclass', 'ajeDebit', 'ajeCredit', 'rjeDebit', 'rjeCredit',
      'auditedBeginning', 'auditedDebit', 'auditedCredit', 'auditedEnding',
      'minusPriorDue', 'minusEndDue', 'disclosureBeginning', 'disclosureEnding',
      'agingWithin6m', 'aging6to12m', 'aging1to2y', 'aging2to3y', 'agingOver3y',
    ]
    for (const k of managedZeroKeys) expect(row[k]).toBe(0)
    // 新增行不再使用旧随机前缀
    expect(row.key.startsWith('l5-detail-')).toBe(false)
  })

  it('新增两行 key 唯一且是 l52det 稳定身份', async () => {
    const detailRows = ref<L5DetailRow[]>([])
    const { addRow } = useL5Detail(makeFormDataStub(), detailRows)
    await addRow()
    await addRow()
    expect(detailRows.value).toHaveLength(2)
    const [r1, r2] = detailRows.value
    expect(r1.key).not.toBe(r2.key)
    expect(r1.key.startsWith('l52det-')).toBe(true)
    expect(r2.section).toBe(L5_SECTION_SALE_LEASEBACK)
  })

  it('删中间行其余行 key 不变（位置化缺陷反例）', () => {
    const detailRows = ref<L5DetailRow[]>([
      createL5DetailRow('甲'), createL5DetailRow('乙'), createL5DetailRow('丙'),
    ])
    detailRows.value[0].key = 'l52det-aaa'
    detailRows.value[1].key = 'l52det-bbb'
    detailRows.value[2].key = 'l52det-ccc'
    const { removeRow } = useL5Detail(makeFormDataStub(), detailRows)
    removeRow(1)
    expect(detailRows.value).toHaveLength(2)
    expect(detailRows.value[0].key).toBe('l52det-aaa')
    expect(detailRows.value[1].key).toBe('l52det-ccc')
    expect(detailRows.value[1].payableName).toBe('丙')
  })

  it('hydrate：缺 key 补铸、已有 key 保留、缺 section 落默认区', () => {
    const formData = makeFormDataStub()
    const legacy = [
      { payableName: '无身份历史行', beginning: 100 },            // 缺 key 缺 section
      { key: 'l5-detail-999-xyz', payableName: '旧身份行', section: 'installment' }, // 有 key 有 section
    ]
    formData.allResponses.value.set('L5-L5-2-rows', { remark: JSON.stringify(legacy) })
    const detailRows = ref<L5DetailRow[]>([])
    useL5Detail(formData, detailRows) // 构造即 hydrate
    expect(detailRows.value).toHaveLength(2)
    // 缺 key → 补铸稳定身份；缺 section → 落默认区
    expect(detailRows.value[0].key.startsWith('l52det-')).toBe(true)
    expect(detailRows.value[0].section).toBe(L5_SECTION_SALE_LEASEBACK)
    expect(detailRows.value[0].beginning).toBe(100)
    // 有 key 优先保留（旧 key 不重铸）；section 原样
    expect(detailRows.value[1].key).toBe('l5-detail-999-xyz')
    expect(detailRows.value[1].section).toBe('installment')
  })

  it('html_only 字段键清单稳定（与后端 provider html_only_keys 对齐的真源）', () => {
    expect([...L5_HTML_ONLY_KEYS].sort()).toEqual([
      'aje', 'audited', 'category', 'creditor', 'currency', 'discountRate',
      'guaranteeType', 'maturityDate', 'nominalAmount', 'presentValue',
      'rje', 'startDate', 'unadjusted',
    ])
  })
})
