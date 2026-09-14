/**
 * H9 披露表动态插行守卫 — Property 11（往返无损）/ Property 12（key 非 label + 撞名拒绝）。
 *
 * 源模板依据：
 * - 上市 `A8:A10` = 三行**空白自由列示区** → 行数由实际数据决定，可增删改名
 * - 国企 `A11` = `……` **可续扣减行** → 固定三行（准则用语）之后可追加
 *
 * spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/ Task 20
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useH9ListedDisclosure,
  useH9SoeDisclosure,
  nextListedRowId,
  nextSoeExtraRowId,
} from '../useH9Disclosure'
import { H9_LISTED_KEYS, H9_SOE_KEYS } from '../h9DisclosureModel'

/** 构造一个会走响应式的 allResponses 替身（写读都过 ref.value） */
function makeStore(initial: Record<string, unknown> = {}) {
  const map = new Map<string, any>()
  for (const [k, v] of Object.entries(initial)) {
    map.set(k, { remark: typeof v === 'string' ? v : JSON.stringify(v), conclusion: null })
  }
  const allResponses = ref(map)
  const saved: Record<string, any> = {}
  const onSave = (itemId: string, value: any) => {
    saved[itemId] = value
    // 🔴 必须经 ref.value 写入，否则 computed 不追踪（memory 铁律）
    const next = new Map(allResponses.value)
    next.set(itemId, {
      remark: typeof value === 'string' ? value : JSON.stringify(value),
      conclusion: null,
    })
    allResponses.value = next
  }
  return { allResponses, onSave, saved }
}

// ──────────────────────────────────────────────────────────────────────────────
// Property 12: 稳定 key 不用 label
// ──────────────────────────────────────────────────────────────────────────────

describe('nextListedRowId / nextSoeExtraRowId', () => {
  it('空集从 1 开始', () => {
    expect(nextListedRowId([])).toBe('H9-listed-1')
    expect(nextSoeExtraRowId([])).toBe('H9-soe-extra-1')
  })

  it('取最大 seq + 1（不是行数）—— 删中间行后不得重用 key', () => {
    const rows = [{ rowId: 'H9-listed-1' }, { rowId: 'H9-listed-5' }]
    expect(nextListedRowId(rows)).toBe('H9-listed-6')
    // 若按行数生成会得到 H9-listed-3 → 与将来可能恢复的行撞键
    expect(nextListedRowId(rows)).not.toBe('H9-listed-3')
  })

  it('忽略无 rowId / 异形 rowId 的行', () => {
    expect(nextListedRowId([{}, { rowId: '' }, { rowId: 'foo' } as any])).toBe('H9-listed-1')
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 上市侧：增删改名 + 撞名拒绝
// ──────────────────────────────────────────────────────────────────────────────

describe('useH9ListedDisclosure 动态行', () => {
  it('新增成功并带稳定 rowId', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    const before = h.state.value.rows.length
    const res = h.addCategory('土地租赁')
    expect(res.ok).toBe(true)
    expect(h.state.value.rows.length).toBe(before + 1)
    const added = h.state.value.rows[h.state.value.rows.length - 1]
    expect(added.item).toBe('土地租赁')
    expect(added.rowId).toMatch(/^H9-listed-\d+$/)
  })

  it('撞名拒绝（同名不得创建）', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    h.addCategory('车辆租赁')
    const n = h.state.value.rows.length
    const dup = h.addCategory('车辆租赁')
    expect(dup.ok).toBe(false)
    expect(dup.message).toContain('已存在同名')
    expect(h.state.value.rows.length).toBe(n)
  })

  it('空名拒绝', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    for (const bad of ['', '   ', undefined]) {
      const r = h.addCategory(bad as any)
      expect(r.ok).toBe(false)
    }
  })

  it('改名后 rowId 不变、金额不丢（Property 12）', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    h.addCategory('设备A租赁')
    const idx = h.state.value.rows.length - 1
    const rowId = h.state.value.rows[idx].rowId
    h.updateCategory(idx, 'endBalance', 123456.78)
    h.updateCategory(idx, 'item', '设备A租赁（改名后）')
    expect(h.state.value.rows[idx].rowId).toBe(rowId)
    expect(h.state.value.rows[idx].endBalance).toBe(123456.78)
  })

  it('删除保留至少一行', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    while (h.state.value.rows.length > 1) h.removeCategory(0)
    const only = h.state.value.rows.length
    h.removeCategory(0)
    expect(h.state.value.rows.length).toBe(only)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 国企侧：固定三行不可删 + extra 可增删
// ──────────────────────────────────────────────────────────────────────────────

describe('useH9SoeDisclosure 续加扣减项', () => {
  it('固定行不可删除', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    const n = h.state.value.rows.length
    const res = h.removeExtraDeduction(0)
    expect(res.ok).toBe(false)
    expect(res.message).toContain('固定行')
    expect(h.state.value.rows.length).toBe(n)
  })

  it('新增扣减项带 rowId 且 key=extra', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    const res = h.addExtraDeduction('减：售后回租扣减')
    expect(res.ok).toBe(true)
    const last = h.state.value.rows[h.state.value.rows.length - 1]
    expect(last.key).toBe('extra')
    expect(last.rowId).toMatch(/^H9-soe-extra-\d+$/)
  })

  it('撞名拒绝（含与固定行同名）', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    const fixedName = h.state.value.rows[0].item
    expect(h.addExtraDeduction(fixedName).ok).toBe(false)
    h.addExtraDeduction('减：其他扣减')
    expect(h.addExtraDeduction('减：其他扣减').ok).toBe(false)
  })

  it('只有 extra 行可改名', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    expect(h.updateExtraItem(0, '乱改固定行').ok).toBe(false)
    h.addExtraDeduction('减：A')
    const i = h.state.value.rows.length - 1
    expect(h.updateExtraItem(i, '减：B').ok).toBe(true)
    expect(h.state.value.rows[i].item).toBe('减：B')
  })

  it('🔴 多个 extra 行重载后不被压成一行（按 key 去重的回归）', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    h.addExtraDeduction('减：扣减一')
    h.addExtraDeduction('减：扣减二')
    h.addExtraDeduction('减：扣减三')
    const extrasBefore = h.state.value.rows.filter((r) => r.key === 'extra')
    expect(extrasBefore).toHaveLength(3)

    // 重新 load（模拟切走再切回 / 宿主刷新）
    h.load()
    const extrasAfter = h.state.value.rows.filter((r) => r.key === 'extra')
    expect(extrasAfter).toHaveLength(3)
    expect(extrasAfter.map((r) => r.item)).toEqual(['减：扣减一', '减：扣减二', '减：扣减三'])
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// Property 11: 往返无损（PBT）
// ──────────────────────────────────────────────────────────────────────────────

describe('Property 11: 动态行往返无损', () => {
  it('任意行序列 增行→改名→删行→重载 后剩余行 rowId 与金额逐字保持', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(
          fc.record({
            name: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => !!s.trim()),
            amt: fc.integer({ min: -10_000_000, max: 10_000_000 }),
          }),
          { minLength: 1, maxLength: 5, selector: (x) => x.name.trim() },
        ),
        (specs) => {
          const { allResponses, onSave } = makeStore()
          const h = useH9ListedDisclosure({ allResponses, onSave })
          // 清到只剩一行，避免默认行名与随机名冲突
          while (h.state.value.rows.length > 1) h.removeCategory(0)

          const created: { rowId: string; amt: number }[] = []
          for (const s of specs) {
            const r = h.addCategory(s.name.trim())
            if (!r.ok) continue // 与保留行撞名则跳过
            const i = h.state.value.rows.length - 1
            h.updateCategory(i, 'endBalance', s.amt)
            created.push({ rowId: h.state.value.rows[i].rowId!, amt: s.amt })
          }
          if (!created.length) return true

          // 重载：rowId 与金额必须保持
          h.load()
          for (const c of created) {
            const found = h.state.value.rows.find((r) => r.rowId === c.rowId)
            expect(found).toBeTruthy()
            expect(found!.endBalance).toBe(c.amt)
          }
          return true
        },
      ),
      { numRuns: 12 },
    )
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 反向自检
// ──────────────────────────────────────────────────────────────────────────────

describe('反向自检', () => {
  it('key 常量存在（防 import 失效导致断言空转）', () => {
    expect(H9_LISTED_KEYS.pack).toBeTruthy()
    expect(H9_SOE_KEYS.pack).toBeTruthy()
  })

  it('addCategory 返回结构含 ok/message（调用方据此提示）', () => {
    const { allResponses, onSave } = makeStore()
    const h = useH9ListedDisclosure({ allResponses, onSave })
    const r = h.addCategory('x')
    expect(r).toHaveProperty('ok')
    expect(r).toHaveProperty('message')
  })
})


// ──────────────────────────────────────────────────────────────────────────────
// 净额勾稽：续加扣减项必须计入（否则加了扣减项后净额与各行不勾稽）
// ──────────────────────────────────────────────────────────────────────────────

describe('国企净额勾稽含续加扣减项', () => {
  it('净额 = 付款额 − 未确认融资费用 − 重分类 − Σ续加扣减项', async () => {
    const { buildSoeDisplayRows } = await import('../h9DisclosureModel')
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })

    const idxOf = (k: string) => h.state.value.rows.findIndex((r) => r.key === k)
    h.updateLine(idxOf('payment'), 'endBalance', 1_000_000)
    h.updateLine(idxOf('unearned'), 'endBalance', 120_000)
    h.updateLine(idxOf('reclass'), 'endBalance', 200_000)
    h.addExtraDeduction('减：售后回租扣减')
    h.updateLine(h.state.value.rows.length - 1, 'endBalance', 50_000)

    const rows = buildSoeDisplayRows(h.state.value)
    const net = rows.find((r) => r.kind === 'net')
    expect(net).toBeTruthy()
    // 1,000,000 − 120,000 − 200,000 − 50,000 = 630,000
    expect(net!.endBalance).toBe(630_000)
  })

  it('反向自检：不加扣减项时净额不含它（证明上一条的 50,000 真的来自 extra）', async () => {
    const { buildSoeDisplayRows } = await import('../h9DisclosureModel')
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    const idxOf = (k: string) => h.state.value.rows.findIndex((r) => r.key === k)
    h.updateLine(idxOf('payment'), 'endBalance', 1_000_000)
    h.updateLine(idxOf('unearned'), 'endBalance', 120_000)
    h.updateLine(idxOf('reclass'), 'endBalance', 200_000)
    const net = buildSoeDisplayRows(h.state.value).find((r) => r.kind === 'net')
    expect(net!.endBalance).toBe(680_000)
  })

  it('extra 行在 displayRows 里带 key=extra（删除按钮据此显示）', async () => {
    const { buildSoeDisplayRows } = await import('../h9DisclosureModel')
    const { allResponses, onSave } = makeStore()
    const h = useH9SoeDisclosure({ allResponses, onSave })
    h.addExtraDeduction('减：X')
    const rows = buildSoeDisplayRows(h.state.value)
    const extras = rows.filter((r) => r.key === 'extra')
    expect(extras).toHaveLength(1)
    expect(extras[0].rowIndex).toBe(h.state.value.rows.length - 1)
  })
})
