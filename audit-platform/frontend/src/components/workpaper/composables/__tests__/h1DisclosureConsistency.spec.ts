/**
 * H1 披露表内部勾稽校验（上市 / 国企）
 *
 * 覆盖源模板要求的联动点：汇总↔①表、政府补助↔「其他减少」、
 * ②③④⑥ 子集约束、国企五层公式与土地不提折旧。
 */
import { describe, expect, it } from 'vitest'
import {
  H1_AMOUNT_TOLERANCE,
  checkH1ListedConsistency,
  checkH1SoeConsistency,
  checkSoeLayerCategorySum,
  listedMovementTotal,
  soeLandDepreciation,
  soeLandImpairment,
  type H1ListedConsistencyInput,
} from '../h1DisclosureConsistency'
import {
  H1_LISTED_DEFAULT_CATEGORIES,
  createDefaultGovSubsidy,
  createDefaultSummary,
  setCell,
  type MovementCellMap,
} from '../h1ListedDisclosureModel'
import {
  createH1SoeDisclosureState,
  recomputeSoeLayers,
  type H1SoeDisclosureState,
  type H1SoeLayer,
} from '../h1SoeDisclosureModel'

const CATS = H1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ ...c }))

function pick(checks: ReturnType<typeof checkH1ListedConsistency>['checks'], id: string) {
  const hit = checks.find((c) => c.id === id)
  if (!hit) throw new Error(`缺校验项 ${id}`)
  return hit
}

/** 单类别（房屋及建筑物）一套自洽数据：原值 1000 增 200 减 100、折旧 300/50/20、减值 0 */
function buildMovement(): MovementCellMap {
  let m: MovementCellMap = {}
  const k = 'buildings'
  m = setCell(m, 'cost_begin', k, 1000)
  m = setCell(m, 'cost_inc_purchase', k, 200)
  m = setCell(m, 'cost_dec_dispose', k, 60)
  m = setCell(m, 'cost_dec_other', k, 40)
  m = setCell(m, 'dep_begin', k, 300)
  m = setCell(m, 'dep_inc_provision', k, 50)
  m = setCell(m, 'dep_dec_dispose', k, 20)
  return m
}

function listedInput(over: Partial<H1ListedConsistencyInput> = {}): H1ListedConsistencyInput {
  const movement = over.movement ?? buildMovement()
  const bookEnd = listedMovementTotal(movement, CATS, 'book_end')
  const bookBegin = listedMovementTotal(movement, CATS, 'book_begin')
  const summary = createDefaultSummary()
  summary[0].endBalance = bookEnd
  summary[0].priorBalance = bookBegin
  return {
    summary,
    categories: CATS,
    movement,
    idle: [],
    leaseOut: [],
    titleCert: [],
    clearing: [],
    fullyDep: [],
    govSubsidyAmount: createDefaultGovSubsidy().amount,
    ...over,
  }
}

describe('listedMovementTotal', () => {
  it('期末原值 = 期初 + 增 − 减；账面价值 = 原值 − 折旧 − 减值', () => {
    const m = buildMovement()
    expect(listedMovementTotal(m, CATS, 'cost_end')).toBe(1000 + 200 - 100)
    expect(listedMovementTotal(m, CATS, 'dep_end')).toBe(300 + 50 - 20)
    expect(listedMovementTotal(m, CATS, 'book_end')).toBe(1100 - 330)
    expect(listedMovementTotal(m, CATS, 'book_begin')).toBe(1000 - 300)
  })
})

describe('checkH1ListedConsistency — 汇总表勾稽', () => {
  it('汇总表与①表一致时全部通过', () => {
    const r = checkH1ListedConsistency(listedInput())
    expect(r.errorCount).toBe(0)
    expect(r.warnCount).toBe(0)
    expect(r.allPass).toBe(true)
  })

  it('汇总表期末余额偏离①表账面价值 → error 并给出差额', () => {
    const input = listedInput()
    input.summary[0].endBalance += 50
    const c = pick(checkH1ListedConsistency(input).checks, 'listed-summary-fa-end')
    expect(c.level).toBe('error')
    expect(c.diff).toBe(50)
    expect(c.detail).toContain('50.00')
  })

  it('容差内（1 分）视为一致', () => {
    const input = listedInput()
    input.summary[0].endBalance += H1_AMOUNT_TOLERANCE
    expect(pick(checkH1ListedConsistency(input).checks, 'listed-summary-fa-end').level).toBe('ok')
  })

  it('清理行必须等于（2）清理表合计', () => {
    const input = listedInput({
      clearing: [{ rowId: 'c1', name: '待处理设备', endBalance: 120, priorBalance: 80, reason: '报废' }],
    })
    let checks = checkH1ListedConsistency(input).checks
    expect(pick(checks, 'listed-summary-clearing-end').level).toBe('error')

    input.summary[1].endBalance = 120
    input.summary[1].priorBalance = 80
    checks = checkH1ListedConsistency(input).checks
    expect(pick(checks, 'listed-summary-clearing-end').level).toBe('ok')
    expect(pick(checks, 'listed-summary-clearing-begin').level).toBe('ok')
  })
})

describe('checkH1ListedConsistency — 源模板 R56 政府补助联动', () => {
  it('政府补助金额 ≤ ①表原值「（2）其他减少」合计 → ok', () => {
    const c = pick(checkH1ListedConsistency(listedInput({ govSubsidyAmount: 40 })).checks,
      'listed-gov-subsidy-in-other-dec')
    expect(c.level).toBe('ok')
    expect(c.right).toBe(40)
  })

  it('超出「其他减少」→ error（未在①表列示）', () => {
    const c = pick(checkH1ListedConsistency(listedInput({ govSubsidyAmount: 60 })).checks,
      'listed-gov-subsidy-in-other-dec')
    expect(c.level).toBe('error')
    expect(c.diff).toBe(20)
    expect(c.rule).toContain('其他减少')
  })
})

describe('checkH1ListedConsistency — ②③④⑥ 子集约束', () => {
  const bookEnd = 770 // 1100 − 330

  it('闲置账面价值超过①表期末账面价值 → error', () => {
    const input = listedInput({
      idle: [{ rowId: 'i1', name: '闲置厂房', cost: bookEnd + 100, dep: 0, impairment: 0, bookValue: 0, remark: '' }],
    })
    const c = pick(checkH1ListedConsistency(input).checks, 'listed-idle-within-book')
    expect(c.level).toBe('error')
  })

  it('①表尚未取数但子表已填 → warn 提示先做①表', () => {
    const input = listedInput({
      movement: {},
      leaseOut: [{ rowId: 'l1', name: '租出设备', bookValue: 10 }],
    })
    input.summary[0].endBalance = 0
    input.summary[0].priorBalance = 0
    const c = pick(checkH1ListedConsistency(input).checks, 'listed-lease-within-book')
    expect(c.level).toBe('warn')
    expect(c.detail).toContain('①情况表')
  })

  it('未办证 / 已提足折旧在上限内 → ok', () => {
    const input = listedInput({
      titleCert: [{ rowId: 't1', name: '无证房屋', bookValue: 100, reason: '在办' }],
      fullyDep: [{ rowId: 'f1', name: '机器设备', cost: 200, remark: '' }],
    })
    const checks = checkH1ListedConsistency(input).checks
    expect(pick(checks, 'listed-title-within-book').level).toBe('ok')
    expect(pick(checks, 'listed-fullydep-within-cost').level).toBe('ok')
  })

  it('已提足折旧原值超过①表原值期末合计 → error', () => {
    const input = listedInput({ fullyDep: [{ rowId: 'f1', name: '机器设备', cost: 1200, remark: '' }] })
    const c = pick(checkH1ListedConsistency(input).checks, 'listed-fullydep-within-cost')
    expect(c.level).toBe('error')
    expect(c.right).toBe(1100)
  })
})

// ─── 国企 ────────────────────────────────────────────────────────────────────

function soeState(): H1SoeDisclosureState {
  const st = createH1SoeDisclosureState()
  const set = (layer: H1SoeLayer, key: string, v: { begin: number; increase: number; decrease: number }) => {
    const block = st.layers.find((l) => l.layer === layer)!
    const cat = block.categories.find((c) => c.key === key)!
    Object.assign(cat, v)
  }
  set('cost', 'building', { begin: 5000, increase: 500, decrease: 200 })
  set('cost', 'machinery', { begin: 3000, increase: 0, decrease: 100 })
  set('dep', 'building', { begin: 1000, increase: 250, decrease: 60 })
  set('dep', 'machinery', { begin: 900, increase: 150, decrease: 40 })
  set('impair', 'machinery', { begin: 100, increase: 50, decrease: 0 })
  recomputeSoeLayers(st.layers)
  return st
}

describe('checkH1SoeConsistency — 五层公式与结转', () => {
  it('recompute 后五层公式与结转全部成立', () => {
    const r = checkH1SoeConsistency({ state: soeState(), fullyDep: [] })
    const failed = r.checks.filter((c) => c.level !== 'ok').map((c) => `${c.id}:${c.detail}`)
    expect(failed, failed.join(' / ')).toHaveLength(0)
  })

  it('账面净值层被手工改坏 → error（净值 ≠ 原值 − 折旧）', () => {
    const st = soeState()
    st.layers.find((l) => l.layer === 'net')!.categories.find((c) => c.key === 'building')!.end += 999
    const c = pick(checkH1SoeConsistency({ state: st, fullyDep: [] }).checks, 'soe-net-formula-end')
    expect(c.level).toBe('error')
    expect(c.diff).toBe(999)
  })

  it('土地资产计提了折旧 → error（源模板 R24 整行「—」）', () => {
    const st = soeState()
    st.layers.find((l) => l.layer === 'dep')!.categories.find((c) => c.key === 'land')!.increase = 10
    expect(soeLandDepreciation(st)).toBe(10)
    const c = pick(checkH1SoeConsistency({ state: st, fullyDep: [] }).checks, 'soe-land-no-depreciation')
    expect(c.level).toBe('error')
    expect(c.rule).toContain('土地资产不计提折旧')
  })

  it('土地资产计提了减值准备 → error（源模板 R42 整行「--」）', () => {
    const st = soeState()
    st.layers.find((l) => l.layer === 'impair')!.categories.find((c) => c.key === 'land')!.begin = 5
    expect(soeLandImpairment(st)).toBe(5)
    const c = pick(checkH1SoeConsistency({ state: st, fullyDep: [] }).checks, 'soe-land-no-impairment')
    expect(c.level).toBe('error')
    expect(c.rule).toContain('不单独计提减值准备')
  })

  it('清理汇总行与（2）清理表不一致 → error，改平后 ok', () => {
    const st = soeState()
    st.clearingRows = [{ rowId: 'c1', name: '待清理机器', endCarrying: 300, beginCarrying: 150, reason: '报废' }]
    let checks = checkH1SoeConsistency({ state: st, fullyDep: [] }).checks
    expect(pick(checks, 'soe-summary-clearing-end').level).toBe('error')

    st.summary.clearingEnd = 300
    st.summary.clearingBegin = 150
    checks = checkH1SoeConsistency({ state: st, fullyDep: [] }).checks
    expect(pick(checks, 'soe-summary-clearing-end').level).toBe('ok')
    expect(pick(checks, 'soe-summary-clearing-begin').level).toBe('ok')
  })

  it('闲置 / 未办证 / 已提足折旧超出上限 → error', () => {
    const st = soeState()
    const carryingEnd = st.layers.find((l) => l.layer === 'carrying')!
      .categories.reduce((s, c) => s + c.end, 0)
    st.idleRows = [{
      rowId: 'i1', name: '闲置车间', originalCost: 0, accumDep: 0,
      impairment: 0, carrying: carryingEnd + 1, remark: '',
    }]
    st.titleRows = [{ rowId: 't1', name: '无证房', carrying: carryingEnd + 1, reason: '在办' }]
    const checks = checkH1SoeConsistency({
      state: st,
      fullyDep: [{ rowId: 'f1', name: '机器设备', cost: 99_999, remark: '' }],
    }).checks
    expect(pick(checks, 'soe-idle-within-carrying').level).toBe('error')
    expect(pick(checks, 'soe-title-within-carrying').level).toBe('error')
    expect(pick(checks, 'soe-fullydep-within-cost').level).toBe('error')
  })
})

describe('checkSoeLayerCategorySum', () => {
  it('五层各自的分类求和 = 合计行', () => {
    const checks = checkSoeLayerCategorySum(soeState())
    expect(checks).toHaveLength(5)
    expect(checks.every((c) => c.level === 'ok')).toBe(true)
  })
})
