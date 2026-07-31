/**
 * useF2DisclosureListed — 对齐 Excel 上市披露模板
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useF2DisclosureListed,
  safeRatio,
  F2_LISTED_DISCLOSURE_CATEGORIES,
} from '../composables/useF2DisclosureListed'
import { buildF2ListedSubTableData } from '../composables/f2DisclosureSyncPayload'
import type { ChecklistResponse } from '../composables/useF2FormData'

function setAdj(
  map: Map<string, ChecklistResponse>,
  block: 'gross' | 'impairment',
  rowKey: string,
  fields: Record<string, number>,
) {
  for (const [field, val] of Object.entries(fields)) {
    map.set(`F2-1-${block}-${rowKey}-${field}`, {
      item_id: `F2-1-${block}-${rowKey}-${field}`,
      conclusion: String(val),
      remark: null,
    })
  }
}

describe('safeRatio', () => {
  it('分母为 0 时返回 0（避免 #DIV/0!）', () => {
    expect(safeRatio(10, 0)).toBe(0)
    expect(safeRatio(0, 0)).toBe(0)
  })
  it('正常比例', () => {
    expect(safeRatio(25, 100)).toBe(0.25)
  })
})

describe('useF2DisclosureListed', () => {
  // Sprint 8：9 → 11 类，补源模板注要求的「开发成本」「开发产品」
  it('分类行对齐 Excel：含在产品/开发成本/开发产品/数据资源等 11 类', () => {
    expect(F2_LISTED_DISCLOSURE_CATEGORIES.map((c) => c.label)).toEqual([
      '原材料', '在产品', '开发成本', '委托加工物资', '库存商品', '开发产品',
      '发出商品', '周转材料', '合同履约成本', '消耗性生物资产', '数据资源',
    ])
  })

  it('（1）账面价值=账面余额−跌价；原材料合并在途', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'raw-materials', { opening: 100, increase: 20, decrease: 10, adjustment: 0 })
    setAdj(map, 'gross', 'material-in-transit', { opening: 50, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'raw-materials', { opening: 10, increase: 5, decrease: 2, adjustment: 0 })
    setAdj(map, 'impairment', 'material-in-transit', { opening: 5, increase: 0, decrease: 0, adjustment: 0 })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const raw = api.section1Rows.value.find((r) => r.rowKey === 'raw-materials')!
    expect(raw.priorGross).toBe(150)
    expect(raw.priorImpairment).toBe(15)
    expect(raw.priorNet).toBe(135)
    // endGross = 150 + 20 - 10 = 160; endI = 15 + 5 - 2 = 18
    expect(raw.endGross).toBe(160)
    expect(raw.endImpairment).toBe(18)
    expect(raw.endNet).toBe(142)
  })

  it('（2）期末=期初+计提+其他−转回−其他，并与（1）勾稽', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'finished-goods', { opening: 0, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'finished-goods', {
      opening: 100, increase: 30, decrease: 10, adjustment: 0,
    })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const row = api.section2Rows.value.find((r) => r.rowKey === 'finished-goods')!
    expect(row.opening).toBe(100)
    expect(row.incProvision).toBe(30)
    expect(row.decReversal).toBe(10)
    expect(row.ending).toBe(120)
    expect(Math.abs(row.tieDiff)).toBeLessThan(0.01)

    const cls = api.section1Rows.value.find((r) => r.rowKey === 'finished-goods')!
    expect(cls.endImpairment).toBe(120)
  })

  it('组合比例合计为 0 时显示 0 而非 Infinity', () => {
    const api = useF2DisclosureListed({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      applicableStandards: ref([]),
    })
    expect(api.s3EndTotal.value.balancePct).toBe(0)
    expect(api.s3EndTotal.value.impairmentPct).toBe(0)
  })

  // ── (3) 按组合计提：两列比例分母不同（源模板 C52=B52/B54 / F52=D52/B52）──
  describe('（3）按组合计提比例口径', () => {
    function mountWithS3(rows: Array<{ groupName: string; balance: number; impairment: number }>) {
      const map = new Map<string, ChecklistResponse>()
      const payload = rows.map((r, i) => ({
        rowId: `s3-fixed-${i}`,
        groupName: r.groupName,
        balance: r.balance,
        impairment: r.impairment,
        provisionStandard: '',
        netValue: 0,
        balancePct: 0,
        impairmentPct: 0,
      }))
      for (const key of ['F2-note-listed-s3-end', 'F2-note-listed-s3-prior']) {
        map.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(payload) })
      }
      return useF2DisclosureListed({
        allResponses: ref(map),
        isReadonly: ref(false),
        applicableStandards: ref(['listed_standalone']),
      })
    }

    it('R1.1 计提比例 = 本组合跌价 ÷ 本组合账面余额', () => {
      const api = mountWithS3([
        { groupName: '组合A', balance: 1000, impairment: 150 },
        { groupName: '组合B', balance: 4000, impairment: 250 },
      ])
      const a = api.s3EndRows.value.find((r) => r.groupName === '组合A')!
      expect(a.impairmentPct).toBeCloseTo(0.15, 10)
      const b = api.s3EndRows.value.find((r) => r.groupName === '组合B')!
      expect(b.impairmentPct).toBeCloseTo(0.0625, 10)
    })

    it('R1.2 合计行计提比例 = 跌价合计 ÷ 账面余额合计', () => {
      const api = mountWithS3([
        { groupName: '组合A', balance: 1000, impairment: 150 },
        { groupName: '组合B', balance: 4000, impairment: 250 },
      ])
      const total = api.s3EndTotal.value
      expect(total.balance).toBe(5000)
      expect(total.impairment).toBe(400)
      expect(total.impairmentPct).toBeCloseTo(0.08, 10)
    })

    it('R1.3 本组合账面余额为 0 时计提比例为 0（不产生 NaN/Infinity）', () => {
      const api = mountWithS3([
        { groupName: '零余额组合', balance: 0, impairment: 50 },
        { groupName: '组合B', balance: 4000, impairment: 250 },
      ])
      const z = api.s3EndRows.value.find((r) => r.groupName === '零余额组合')!
      expect(z.impairmentPct).toBe(0)
      expect(Number.isFinite(z.impairmentPct)).toBe(true)
    })

    it('R1.4 占比列口径不变：分母为合计账面余额，合计行 100%', () => {
      const api = mountWithS3([
        { groupName: '组合A', balance: 1000, impairment: 150 },
        { groupName: '组合B', balance: 4000, impairment: 250 },
      ])
      const a = api.s3EndRows.value.find((r) => r.groupName === '组合A')!
      expect(a.balancePct).toBeCloseTo(0.2, 10)
      expect(api.s3EndTotal.value.balancePct).toBe(1)
    })

    it('R1.5 期末表与上年年末表采用同一算法', () => {
      const api = mountWithS3([
        { groupName: '组合A', balance: 1000, impairment: 150 },
        { groupName: '组合B', balance: 4000, impairment: 250 },
      ])
      const endA = api.s3EndRows.value.find((r) => r.groupName === '组合A')!
      const priorA = api.s3PriorRows.value.find((r) => r.groupName === '组合A')!
      expect(priorA.impairmentPct).toBeCloseTo(endA.impairmentPct, 10)
      expect(priorA.balancePct).toBeCloseTo(endA.balancePct, 10)
      expect(api.s3PriorTotal.value.impairmentPct).toBeCloseTo(
        api.s3EndTotal.value.impairmentPct, 10,
      )
    })
  })

  it('getSyncSnapshot 可构建附注 sync payload', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'raw-materials', { opening: 100, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'raw-materials', { opening: 10, increase: 0, decrease: 0, adjustment: 0 })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const sub = buildF2ListedSubTableData(api.getSyncSnapshot())
    expect(sub['存货分类'].length).toBeGreaterThan(1)
    expect(sub['存货分类'][0].label).toBe('原材料')
    expect(sub['存货分类'][0].end_gross).toBe(100)
    expect(sub['存货跌价准备及合同履约成本减值准备'][0].ending).toBe(10)
  })

  it('R2.4 合同履约成本摊销说明随 _note_texts 以 listed-note-amort 推送', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-note-listed-note-amort', {
      item_id: 'F2-note-listed-note-amort',
      conclusion: null,
      remark: '本期摊销合同履约成本 1,200,000.00 元，计入主营业务成本。',
    })
    map.set('F2-note-listed-note-borrow', {
      item_id: 'F2-note-listed-note-borrow',
      conclusion: null,
      remark: '存货期末余额中含有借款费用资本化金额 300,000.00 元。',
    })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    expect(api.s4AmortText.value).toContain('1,200,000.00')

    const texts = buildF2ListedSubTableData(api.getSyncSnapshot())._note_texts as Array<{
      section: string
      title: string
      text: string
    }>
    const amort = texts.find((t) => t.section === 'listed-note-amort')
    expect(amort?.text).toContain('计入主营业务成本')
    // R20：title 必须是中文（缺省会让附注正文出现 `【listed-note-amort】`）
    expect(amort?.title).toBe('合同履约成本本期摊销金额的说明')
    // 借款费用资本化仍独立成段，未被摊销说明顶替
    expect(texts.some((t) => t.section === 'listed-note-borrow')).toBe(true)
    // R20：空文本域不入 _note_texts（本例未填分类说明）
    expect(texts.some((t) => t.section === 'listed-note-category')).toBe(false)
  })

  it('R20 每条 _note_texts 都带非空中文 title', () => {
    const map = new Map<string, ChecklistResponse>()
    for (const key of ['category', 'nrv', 'provision', 'borrow', 'amort', 're']) {
      map.set(`F2-note-listed-note-${key}`, {
        item_id: `F2-note-listed-note-${key}`,
        conclusion: null,
        remark: `说明-${key}`,
      })
    }
    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })
    const texts = buildF2ListedSubTableData(api.getSyncSnapshot())._note_texts as Array<{
      section: string
      title: string
      text: string
    }>
    expect(texts).toHaveLength(6)
    for (const t of texts) {
      expect(t.title.trim()).not.toBe('')
      // 禁止英文 section 键泄漏成标题
      expect(t.title).not.toBe(t.section)
      expect(/[a-z-]{6,}/.test(t.title)).toBe(false)
    }
  })

  it('R21 计提方式二选一：推送表名互斥 + 另一组进 _removed_table_keys', () => {
    const map = new Map<string, ChecklistResponse>()
    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const byPortfolio = buildF2ListedSubTableData(api.getSyncSnapshot())
    expect(byPortfolio['按组合计提存货跌价准备']).toBeDefined()
    expect(byPortfolio['按库龄组合计提存货跌价准备']).toBeUndefined()
    expect(byPortfolio._removed_table_keys).toEqual([
      '按库龄组合计提存货跌价准备',
      '按库龄组合计提存货跌价准备（续）',
    ])

    api.setS3Mode('aging')
    expect(api.s3Mode.value).toBe('aging')
    // 空组合名时用库龄段预填骨架
    expect(api.s3EndRows.value[0].groupName).toBe('1年以内')

    const byAging = buildF2ListedSubTableData(api.getSyncSnapshot())
    expect(byAging['按库龄组合计提存货跌价准备（续）']).toBeDefined()
    expect(byAging['按组合计提存货跌价准备']).toBeUndefined()
    expect(byAging._removed_table_keys).toEqual([
      '按组合计提存货跌价准备',
      '按组合计提存货跌价准备（续）',
    ])
    // 待删表名不得与本次推送表名相交（否则后端会被要求删刚推的表）
    const pushed = new Set(Object.keys(byAging).filter((k) => !k.startsWith('_')))
    for (const k of byAging._removed_table_keys as string[]) {
      expect(pushed.has(k)).toBe(false)
    }
  })
})
