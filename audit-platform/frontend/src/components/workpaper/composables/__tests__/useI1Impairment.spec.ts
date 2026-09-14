/**
 * useI1Impairment — I1-12 减值准备测试公式/闸门/联动单测
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  resolveI1NeedTest,
  calcI1ImpairmentBookValue,
  calcI1ImpairmentRecoverable,
  calcI1RequiredImpairment,
  calcI1ImpairmentSupplement,
  calcI1ImpairmentOverProvision,
  suggestI1ImpairmentConclusion,
  recomputeI1ImpairmentRow,
  emptyI1ImpairmentRow,
  validateI1ImpairmentPrep,
  seedRowsFromI12Detail,
  useI1Impairment,
} from '../useI1Impairment'

describe('I1-12 减值闸门与公式', () => {
  it('寿命不确定 OR 有迹象 → 须测试', () => {
    expect(resolveI1NeedTest('Y', 'N')).toBe(true)
    expect(resolveI1NeedTest('N', 'Y')).toBe(true)
    expect(resolveI1NeedTest('Y', 'Y')).toBe(true)
    expect(resolveI1NeedTest('N', 'N')).toBe(false)
    expect(resolveI1NeedTest('', '')).toBe(false)
  })

  it('②账面价值 = 原值 − 累计摊销（不含减值）', () => {
    expect(calcI1ImpairmentBookValue(1000, 200)).toBe(800)
    expect(calcI1ImpairmentBookValue(100, 200)).toBe(0)
  })

  it('⑤可收回：须测试时 MAX(③,④)，否则 0', () => {
    expect(calcI1ImpairmentRecoverable(100, 200, true)).toBe(200)
    expect(calcI1ImpairmentRecoverable(300, 200, true)).toBe(300)
    expect(calcI1ImpairmentRecoverable(100, 200, false)).toBe(0)
  })

  it('⑥应计提 = MAX(②−⑤,0)；无须测试为 0', () => {
    expect(calcI1RequiredImpairment(1000, 600, true)).toBe(400)
    expect(calcI1RequiredImpairment(1000, 1200, true)).toBe(0)
    expect(calcI1RequiredImpairment(1000, 600, false)).toBe(0)
  })

  it('⑧应补提 / ⑨多提待查（CAS8 不得转回）', () => {
    expect(calcI1ImpairmentSupplement(500, 200)).toBe(300)
    expect(calcI1ImpairmentSupplement(200, 500)).toBe(0)
    expect(calcI1ImpairmentOverProvision(200, 500)).toBe(300)
    expect(calcI1ImpairmentOverProvision(500, 200)).toBe(0)
  })

  it('recompute：有迹象时走完整链路', () => {
    const row = recomputeI1ImpairmentRow(emptyI1ImpairmentRow({
      name: '软件A',
      hasIndication: 'Y',
      indicationDesc: '市价大幅下跌',
      cost: 1000,
      accAmort: 200,
      bookValue: 800,
      fairValueLessDisposal: 300,
      dcfValue: 400,
      alreadyProvided: 50,
      indexRef: 'I1-13',
    }))
    expect(row.needTest).toBe(true)
    expect(row.recoverableAmount).toBe(400)
    expect(row.shouldProvision).toBe(400)
    expect(row.supplement).toBe(350)
    expect(row.overProvision).toBe(0)
  })

  it('recompute：无迹象且寿命确定 → 不测试，可收回/应计提为 0', () => {
    const row = recomputeI1ImpairmentRow(emptyI1ImpairmentRow({
      name: '专利B',
      indefiniteLife: 'N',
      hasIndication: 'N',
      bookValue: 800,
      fairValueLessDisposal: 100,
      dcfValue: 200,
      alreadyProvided: 0,
    }))
    expect(row.needTest).toBe(false)
    expect(row.recoverableAmount).toBe(0)
    expect(row.shouldProvision).toBe(0)
    expect(suggestI1ImpairmentConclusion(row)).toBe('无需测试')
  })

  it('寿命不确定即使无迹象也须测试', () => {
    const row = recomputeI1ImpairmentRow(emptyI1ImpairmentRow({
      name: '商标C',
      indefiniteLife: 'Y',
      hasIndication: 'N',
      bookValue: 500,
      fairValueLessDisposal: 450,
      dcfValue: 400,
      alreadyProvided: 0,
      indexRef: 'I1-13',
    }))
    expect(row.needTest).toBe(true)
    expect(row.recoverableAmount).toBe(450)
    expect(row.shouldProvision).toBe(50)
    expect(suggestI1ImpairmentConclusion(row)).toBe('需补提')
  })

  it('编制校验：有迹象缺描述/索引/可收回', () => {
    const bad = emptyI1ImpairmentRow({
      name: '软件D',
      hasIndication: 'Y',
      bookValue: 100,
      indicationDesc: '',
      indexRef: '',
    })
    const v = validateI1ImpairmentPrep([bad])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('迹象描述'))).toBe(true)
    expect(v.messages.some((m) => m.includes('I1-13'))).toBe(true)
  })

  it('从 I1-2 明细推导：寿命 0 → 不确定，②=原值−摊销，⑦=减值期末', () => {
    const rows = seedRowsFromI12Detail([
      {
        rowId: 'd1',
        category: '软件',
        name: 'ERP',
        usefulLifeMonths: 0,
        costEnd: 1200,
        accAmortEnd: 200,
        impairmentEnd: 30,
      },
      {
        rowId: 'd2',
        category: '专利权',
        name: '专利X',
        usefulLifeMonths: 60,
        costEnd: 500,
        accAmortEnd: 100,
        impairmentEnd: 0,
      },
    ])
    expect(rows).toHaveLength(2)
    expect(rows[0].indefiniteLife).toBe('Y')
    expect(rows[0].bookValue).toBe(1000)
    expect(rows[0].alreadyProvided).toBe(30)
    expect(rows[1].indefiniteLife).toBe('N')
    expect(rows[1].bookValue).toBe(400)
  })

  it('兼容旧数据：仅有 recoverableAmount 时落入④', () => {
    const row = recomputeI1ImpairmentRow(emptyI1ImpairmentRow({
      name: '旧行',
      hasIndication: 'Y',
      indicationDesc: '闲置',
      bookValue: 1000,
      dcfValue: 700,
      alreadyProvided: 0,
      indexRef: 'I1-13',
    }))
    expect(row.recoverableAmount).toBe(700)
    expect(row.shouldProvision).toBe(300)
  })
})

describe('I1-12 跨表联动辅助（纯函数层）', () => {
  it('seedRowsFromI12Detail + recompute 可形成须测试行', () => {
    const [row] = seedRowsFromI12Detail([{
      name: '商标不确定',
      category: '商标权',
      usefulLifeMonths: 0,
      costEnd: 800,
      accAmortEnd: 0,
      impairmentEnd: 0,
    }])
    expect(row.indefiniteLife).toBe('Y')
    expect(recomputeI1ImpairmentRow(row).needTest).toBe(true)
  })
})

describe('useI1Impairment 联动动作', () => {
  const saved: Array<{ id: string; value: any }> = []
  let events: CustomEvent[] = []

  beforeEach(() => {
    saved.length = 0
    events = []
    vi.stubGlobal('window', {
      dispatchEvent: (e: Event) => {
        events.push(e as CustomEvent)
        return true
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function makeApi(seed?: Record<string, any>) {
    const map = new Map<string, any>()
    for (const [k, v] of Object.entries(seed || {})) {
      map.set(k, { remark: typeof v === 'string' ? v : JSON.stringify(v) })
    }
    const wpId = ref('wp-i1')
    const allResponses = ref(map)
    return useI1Impairment(wpId, allResponses as any, {
      onSave: (id, value) => saved.push({ id, value }),
    })
  }

  it('syncFromUsefulLife：从 I1-7-rows 同步寿命不确定', () => {
    const api = makeApi({
      'I1-7-rows': [
        { name: '软件A', usefulLifeMonths: 0, isIndefinite: 'Y', netBookValue: 100 },
        { name: '专利B', usefulLifeMonths: 60, isIndefinite: 'N', netBookValue: 200 },
      ],
      'I1-12-rows': [
        { name: '软件A', bookValue: 100, hasIndication: 'N' },
        { name: '专利B', bookValue: 200, hasIndication: 'N', indefiniteLife: 'Y' },
      ],
    })
    const r = api.syncFromUsefulLife()
    expect(r.ok).toBe(true)
    const a = api.impairmentRows.value.find((x) => x.name === '软件A')!
    const b = api.impairmentRows.value.find((x) => x.name === '专利B')!
    expect(a.indefiniteLife).toBe('Y')
    expect(a.needTest).toBe(true)
    expect(b.indefiniteLife).toBe('N')
    expect(b.needTest).toBe(false)
  })

  it('persist 推送 impairment:calculated 至 K11（wpCode=I1）', () => {
    const api = makeApi()
    api.addImpairmentRow({
      name: '需补提项',
      bookValue: 1000,
      hasIndication: 'Y' as any,
    })
    // 手动补可收回与迹象后重算
    api.updateImpairmentField(0, 'hasIndication', 'Y')
    api.updateImpairmentField(0, 'indicationDesc', '市价下跌')
    api.updateImpairmentField(0, 'indexRef', 'I1-13')
    api.updateImpairmentField(0, 'dcfValue', 600)
    api.updateImpairmentField(0, 'alreadyProvided', 0)

    expect(api.impairmentSummary.value.totalSupplement).toBe(400)
    expect(saved.some((s) => s.id === 'I1-12-supplement-total')).toBe(true)
    const ev = [...events].reverse().find((e) => e.type === 'impairment:calculated')
    expect(ev?.detail?.wpCode).toBe('I1')
    expect(ev?.detail?.totalRequiredProvision).toBe(400)
  })

  it('pushToAmortWithImpair 切换 I1-amort-branch=withImpair', () => {
    const api = makeApi({
      'I1-11-rows': [{ name: '软件A', impairment: 0 }],
    })
    api.addImpairmentRow({ name: '软件A', bookValue: 500 })
    api.updateImpairmentField(0, 'hasIndication', 'Y')
    api.updateImpairmentField(0, 'indicationDesc', '闲置')
    api.updateImpairmentField(0, 'indexRef', 'I1-13')
    api.updateImpairmentField(0, 'dcfValue', 200)
    api.updateImpairmentField(0, 'alreadyProvided', 50)

    const r = api.pushToAmortWithImpair({ createMissing: true })
    expect(r.ok).toBe(true)
    expect(saved.some((s) => s.id === 'I1-amort-branch' && s.value === 'withImpair')).toBe(true)
    expect(saved.some((s) => s.id === 'I1-11-rows')).toBe(true)
  })

  it('extractK11IntangibleAmount 读取 K11-source-I1-amount', async () => {
    const { extractK11IntangibleAmount } = await import('../useI1Impairment')
    const r = extractK11IntangibleAmount([
      { item_id: 'K11-source-I1-amount', remark: '12345.5' },
    ])
    expect(r.amount).toBe(12345.5)
    expect(r.source).toContain('I1')
  })

  it('assertCanConclude：须测试缺 I1-13 时硬闸门失败', () => {
    const api = makeApi()
    api.addImpairmentRow({ name: '商标权', bookValue: 800, cost: 1000, accAmort: 200 })
    api.updateImpairmentField(0, 'indefiniteLife', 'Y')
    expect(api.needTestGatePending.value).toBe(true)
    const gate = api.assertCanConclude()
    expect(gate.ok).toBe(false)
    expect(gate.message).toMatch(/I1-13|闸门/)
  })

  it('I1-13 回写后 assertCanConclude 可通过', () => {
    const api = makeApi()
    api.addImpairmentRow({ name: '软件X', bookValue: 500, cost: 600, accAmort: 100 })
    api.updateImpairmentField(0, 'hasIndication', 'Y')
    api.updateImpairmentField(0, 'indicationDesc', '技术淘汰')
    api.updateImpairmentField(0, 'indexRef', 'I1-13')
    const seed = api.seedFromImpairment()
    expect(seed.ok).toBe(true)
    const idx = api.recoverableRows.value.findIndex((r) => r.name === '软件X')
    expect(idx).toBeGreaterThanOrEqual(0)
    api.updateRecoverableField(idx, 'fairValueLessDisposal', 400)
    api.linkRecoverableToImpairment()
    expect(api.impairmentRows.value[0].recoverableAmount).toBeGreaterThan(0)
    const gate = api.assertCanConclude()
    expect(gate.ok).toBe(true)
  })
})
