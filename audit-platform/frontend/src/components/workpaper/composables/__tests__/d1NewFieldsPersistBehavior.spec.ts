/**
 * 新补的 8 个字段**真的会落库并读得回来** —— 行为判据（不是源码扫描）。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · 裁决「补 8 个字段」
 *
 * ═══ 为什么源码守卫不够 ═══
 *
 * 后端那条 `test_new_field_is_wired_in_all_four_places` 是**文本匹配**：
 * 断言字段名出现在 interface / 持久化白名单 / 空行工厂 / 宿主 .vue 四处。
 * 它能防「忘了改某一处」，但**不能证明字段真的进了 `remark` 的 JSON**
 * —— 例如白名单里有名字而 `serialize*` 换了实现、或 `updateXxx` 把该字段
 * 路由到了别的分支，文本匹配全绿而值照样丢。
 *
 * 本文件走 composable 的**公开 API**：真调 update → 真 flush → 从 `allResponses`
 * 的 `remark` 里把 JSON parse 回来逐字段对值。
 */
import { ref, type Ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useD1SamplingVouching } from '../useD1SamplingVouching'
import { useD1InventoryCount } from '../useD1InventoryCount'
import type { ChecklistResponse } from '../useD1FormData'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

const VOUCHING_KEY = 'D1-sampling-vouching-rows'
const INVENTORY_KEY = 'D1-inventory-rows'

/** D1-13 本轮新增的 7 个字段：字段名 → 写入值 */
const NEW_VOUCHING_FIELDS: Array<[string, string | number]> = [
  ['voucherDate', '2026-03-31'],
  ['counterDetail', '应收票据-银行承兑'],
  ['creditAmount', 12345.67],
  ['supportDoc', '银行承兑汇票原件 + 贴现凭证'],
  ['check4', '已核对背书连续性'],
  ['check5', '已核对到期日'],
  ['isAbnormal', '否'],
]

function mkOptions() {
  const allResponses = ref(new Map<string, ChecklistResponse>()) as Ref<
    Map<string, ChecklistResponse>
  >
  return {
    allResponses,
    opts: {
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      saveImmediate: vi.fn(),
      saveDebouncedText: vi.fn(),
      isReadonly: ref(false),
    },
  }
}

/**
 * 两个 composable **都不导出 flush** —— 落库走 2s debounce。
 *
 * 🔴 本文件第一版写的是 `api.flushPendingSaves?.()`，那个名字根本不存在，
 *    可选链把它**静默空转**掉 ⇒ 5 条写侧判据全报「remark 为空」。
 *    这本身就是个小号假绿模式：`?.()` 会把「方法名写错」变成「什么都没发生」。
 *    正解是推进真实 debounce（顺带把 2s 这个行为也覆盖住），而不是找个 flush 捷径。
 */
function flushDebounce(): void {
  vi.advanceTimersByTime(2100)
}

function parseRows(allResponses: Ref<Map<string, ChecklistResponse>>, key: string): any[] {
  const raw = allResponses.value.get(key)?.remark
  expect(raw, `${key} 没有落库（remark 为空）`).toBeTruthy()
  const parsed = JSON.parse(String(raw))
  expect(Array.isArray(parsed)).toBe(true)
  return parsed
}

describe('D1-13 抽凭：新增 7 个字段真的落库', () => {
  it('🔴 逐字段 update → flush → 从 remark 的 JSON 读回等值', () => {
    const { allResponses, opts } = mkOptions()
    const api = useD1SamplingVouching(opts as never)

    api.addVouchingRow()
    const rowId = (api.vouchingRows.value[0] as any).id
    expect(rowId, '新增行没有 id').toBeTruthy()

    for (const [field, value] of NEW_VOUCHING_FIELDS) {
      api.updateVouchingRow(rowId, field as never, value)
    }
    flushDebounce()

    const rows = parseRows(allResponses, VOUCHING_KEY)
    const row = rows.find((r) => r.id === rowId)
    expect(row, '落库的数组里找不到刚写的行').toBeTruthy()
    for (const [field, value] of NEW_VOUCHING_FIELDS) {
      expect(row[field], `${field} 没落进 remark（或值不对）`).toBe(value)
    }
  })

  it('creditAmount 是数值字段（走 parseNum，不是字符串直塞）', () => {
    const { allResponses, opts } = mkOptions()
    const api = useD1SamplingVouching(opts as never)
    api.addVouchingRow()
    const rowId = (api.vouchingRows.value[0] as any).id
    // 传字符串应被归一成 number
    api.updateVouchingRow(rowId, 'creditAmount' as never, '888.5' as never)
    flushDebounce()
    const row = parseRows(allResponses, VOUCHING_KEY).find((r) => r.id === rowId)
    expect(typeof row.creditAmount).toBe('number')
    expect(row.creditAmount).toBe(888.5)
  })

  it('借方/贷方两个金额互不覆盖（成对字段最容易写串）', () => {
    const { allResponses, opts } = mkOptions()
    const api = useD1SamplingVouching(opts as never)
    api.addVouchingRow()
    const rowId = (api.vouchingRows.value[0] as any).id
    api.updateVouchingRow(rowId, 'amount' as never, 100 as never)
    api.updateVouchingRow(rowId, 'creditAmount' as never, 200 as never)
    flushDebounce()
    const row = parseRows(allResponses, VOUCHING_KEY).find((r) => r.id === rowId)
    expect(row.amount).toBe(100)
    expect(row.creditAmount).toBe(200)
  })

  it('新增字段能从 remark 反序列化回来（读侧对称）', () => {
    const { allResponses, opts } = mkOptions()
    const seeded = [
      {
        id: 'row-seeded',
        seq: 1,
        voucherDate: '2026-01-01',
        counterDetail: 'X 科目',
        creditAmount: 7.5,
        supportDoc: '凭证影像',
        check4: 'c4',
        check5: 'c5',
        isAbnormal: '是',
      },
    ]
    allResponses.value.set(VOUCHING_KEY, {
      item_id: VOUCHING_KEY,
      conclusion: null,
      remark: JSON.stringify(seeded),
    } as never)

    const api = useD1SamplingVouching(opts as never)
    const row = api.vouchingRows.value.find((r: any) => r.id === 'row-seeded') as any
    expect(row, '反序列化没把行读出来').toBeTruthy()
    expect(row.voucherDate).toBe('2026-01-01')
    expect(row.counterDetail).toBe('X 科目')
    expect(row.creditAmount).toBe(7.5)
    expect(row.supportDoc).toBe('凭证影像')
    expect(row.check4).toBe('c4')
    expect(row.check5).toBe('c5')
    expect(row.isAbnormal).toBe('是')
  })
})

describe('D1-10 监盘：新增 payer 真的落库', () => {
  it('🔴 payer（Excel K 付款人名称）update → flush → 读回等值', () => {
    const { allResponses, opts } = mkOptions()
    const api = useD1InventoryCount(opts as never)

    api.addRow()
    const rowId = (api.rows.value[0] as any).id
    api.updateRow(rowId, 'payer' as never, '某某商贸有限公司' as never)
    flushDebounce()

    const row = parseRows(allResponses, INVENTORY_KEY).find((r) => r.id === rowId)
    expect(row, '落库的数组里找不到刚写的行').toBeTruthy()
    expect(row.payer).toBe('某某商贸有限公司')
  })

  it('payer 与相邻的 endorsee / endorseDate 不串（三者语义不同）', () => {
    const { allResponses, opts } = mkOptions()
    const api = useD1InventoryCount(opts as never)
    api.addRow()
    const rowId = (api.rows.value[0] as any).id
    api.updateRow(rowId, 'endorsee' as never, '被背书人A' as never)
    api.updateRow(rowId, 'payer' as never, '付款人B' as never)
    api.updateRow(rowId, 'endorseDate' as never, '2026-02-02' as never)
    flushDebounce()
    const row = parseRows(allResponses, INVENTORY_KEY).find((r) => r.id === rowId)
    expect(row.endorsee).toBe('被背书人A')
    expect(row.payer).toBe('付款人B')
    expect(row.endorseDate).toBe('2026-02-02')
  })

  it('payer 能从 remark 反序列化回来（读侧对称）', () => {
    const { allResponses, opts } = mkOptions()
    allResponses.value.set(INVENTORY_KEY, {
      item_id: INVENTORY_KEY,
      conclusion: null,
      remark: JSON.stringify([{ id: 'r1', payer: '读回来的付款人' }]),
    } as never)
    const api = useD1InventoryCount(opts as never)
    const row = api.rows.value.find((r: any) => r.id === 'r1') as any
    expect(row).toBeTruthy()
    expect(row.payer).toBe('读回来的付款人')
  })
})
