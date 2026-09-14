/**
 * Property-Based Tests — B23 业务层面控制（14 循环重做）
 *
 * Spec: .kiro/specs/b23-business-control-rework/
 * Task: 5.1
 *
 * Property 1: 持久化往返不变式 — load(save(x)) == x
 * Property 10: item_id 前缀完整 — generateItemId 恒返回非空 B23- 前缀键
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  generateItemId,
  type B23ControlPoint,
  type B23WalkthroughTest,
  type B23ControlTest,
  type B23Deficiency,
} from '../composables/useB23ProcessControl'
import { B23_CYCLES } from '../composables/b23CycleConfig'

// ─── Constants ───────────────────────────────────────────────────────────────

const ALL_CYCLE_CODES = B23_CYCLES.map((c) => c.code)

const CTRL_FIELDS = [
  'subProcess', 'ctrlNo', 'ctrlName', 'ctrlDesc', 'affectedItems',
  'assertion', 'wcgwRef', 'wcgwDetail', 'ctrlAttr', 'frequency',
  'itApp', 'preventDetect', 'designEffective', 'ctrlTypeL1', 'ctrlTypeL2',
  'executor', 'executorOrg', 'hasDoc', 'isKeyControl', 'doControlTest',
] as const

const WT_FIELDS = [
  'method', 'interviewee', 'procedure', 'evidence',
  'result', 'asDesigned', 'deficiencyFound',
] as const

const CT_FIELDS = [
  'riskJudgment', 'testNature', 'testTiming', 'testScope',
  'operatingEffective', 'deviation', 'substantiveImpact',
] as const

const DEF_FIELDS = [
  'subProcess', 'description', 'deficiencyType', 'severity', 'impact',
] as const

// Fields stored in conclusion column (enums)
const CTRL_CONCLUSION_FIELDS = new Set([
  'assertion', 'frequency', 'preventDetect', 'designEffective',
  'ctrlTypeL1', 'ctrlTypeL2', 'hasDoc', 'isKeyControl', 'doControlTest',
])
const WT_CONCLUSION_FIELDS = new Set(['asDesigned'])
const CT_CONCLUSION_FIELDS = new Set(['operatingEffective'])
const DEF_CONCLUSION_FIELDS = new Set(['deficiencyType', 'severity'])

// ─── Arbitraries ─────────────────────────────────────────────────────────────

const arbCycleCode = fc.constantFrom(...ALL_CYCLE_CODES)
const arbIndex = fc.integer({ min: 1, max: 10 })
const arbCtrlField = fc.constantFrom(...CTRL_FIELDS)
const arbWtField = fc.constantFrom(...WT_FIELDS)
const arbCtField = fc.constantFrom(...CT_FIELDS)
const arbDefField = fc.constantFrom(...DEF_FIELDS)

const arbYesNo = fc.constantFrom('是', '否', null)
const arbPreventDetect = fc.constantFrom('预防性', '检查性', null)
const arbFrequency = fc.constantFrom('每笔', '每日', '每周', '每月', '每季', '每年', '不定期', '定期', null)
const arbCtrlTypeL1 = fc.constantFrom('授权和审批', '监督控制', '信息处理', '实物控制', '职责分离', '绩效评价复核', null)
const arbOperatingEffective = fc.constantFrom('有效', '无效', null)
const arbDefType = fc.constantFrom('缺乏控制', '设计不合理', '未执行', null)
const arbSeverity = fc.constantFrom('重大缺陷', '重要缺陷', '一般缺陷', null)
const arbAssertions = fc.subarray(
  ['存在', '发生', '完整性', '准确性', '计价分摊', '权利义务', '列报'],
  { minLength: 0 },
)
const arbWtMethod = fc.subarray(
  ['询问', '观察', '检查文件', '穿行测试', '重新执行'],
  { minLength: 0 },
)

/** Arbitrary for B23ControlPoint */
const arbControlPoint: fc.Arbitrary<B23ControlPoint> = fc.record({
  index: fc.integer({ min: 1, max: 20 }),
  subProcess: fc.string({ minLength: 0, maxLength: 20 }),
  ctrlNo: fc.string({ minLength: 0, maxLength: 10 }),
  ctrlName: fc.string({ minLength: 0, maxLength: 30 }),
  ctrlDesc: fc.string({ minLength: 0, maxLength: 50 }),
  affectedItems: fc.string({ minLength: 0, maxLength: 30 }),
  assertion: arbAssertions,
  wcgwRef: fc.string({ minLength: 0, maxLength: 15 }),
  wcgwDetail: fc.string({ minLength: 0, maxLength: 30 }),
  ctrlAttr: fc.string({ minLength: 0, maxLength: 20 }),
  frequency: arbFrequency as fc.Arbitrary<B23ControlPoint['frequency']>,
  itApp: fc.string({ minLength: 0, maxLength: 15 }),
  preventDetect: arbPreventDetect as fc.Arbitrary<B23ControlPoint['preventDetect']>,
  designEffective: arbYesNo as fc.Arbitrary<B23ControlPoint['designEffective']>,
  ctrlTypeL1: arbCtrlTypeL1 as fc.Arbitrary<B23ControlPoint['ctrlTypeL1']>,
  ctrlTypeL2: fc.oneof(fc.constant(null), fc.string({ minLength: 1, maxLength: 10 })),
  executor: fc.string({ minLength: 0, maxLength: 10 }),
  executorOrg: fc.string({ minLength: 0, maxLength: 15 }),
  hasDoc: arbYesNo as fc.Arbitrary<B23ControlPoint['hasDoc']>,
  isKeyControl: arbYesNo as fc.Arbitrary<B23ControlPoint['isKeyControl']>,
  doControlTest: arbYesNo as fc.Arbitrary<B23ControlPoint['doControlTest']>,
})

/** Arbitrary for B23WalkthroughTest */
const arbWalkthroughTest: fc.Arbitrary<B23WalkthroughTest> = fc.record({
  ctrlIndex: fc.integer({ min: 1, max: 20 }),
  method: arbWtMethod,
  interviewee: fc.string({ minLength: 0, maxLength: 15 }),
  procedure: fc.string({ minLength: 0, maxLength: 30 }),
  evidence: fc.string({ minLength: 0, maxLength: 30 }),
  result: fc.string({ minLength: 0, maxLength: 30 }),
  asDesigned: arbYesNo as fc.Arbitrary<B23WalkthroughTest['asDesigned']>,
  deficiencyFound: fc.string({ minLength: 0, maxLength: 30 }),
})

/** Arbitrary for B23ControlTest */
const arbControlTest: fc.Arbitrary<B23ControlTest> = fc.record({
  ctrlIndex: fc.integer({ min: 1, max: 20 }),
  riskJudgment: fc.string({ minLength: 0, maxLength: 20 }),
  testNature: fc.string({ minLength: 0, maxLength: 20 }),
  testTiming: fc.string({ minLength: 0, maxLength: 15 }),
  testScope: fc.string({ minLength: 0, maxLength: 15 }),
  operatingEffective: arbOperatingEffective as fc.Arbitrary<B23ControlTest['operatingEffective']>,
  deviation: fc.string({ minLength: 0, maxLength: 20 }),
  substantiveImpact: fc.string({ minLength: 0, maxLength: 20 }),
})

/** Arbitrary for B23Deficiency */
const arbDeficiency: fc.Arbitrary<B23Deficiency> = fc.record({
  index: fc.integer({ min: 1, max: 10 }),
  subProcess: fc.string({ minLength: 0, maxLength: 15 }),
  description: fc.string({ minLength: 0, maxLength: 50 }),
  deficiencyType: arbDefType as fc.Arbitrary<B23Deficiency['deficiencyType']>,
  severity: arbSeverity as fc.Arbitrary<B23Deficiency['severity']>,
  impact: fc.string({ minLength: 0, maxLength: 30 }),
})

// ─── Serialization helpers (mirror composable save/load logic) ───────────────

interface StoredItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

function serializeControlPoint(code: string, idx: number, cp: B23ControlPoint): StoredItem[] {
  const items: StoredItem[] = []
  for (const field of CTRL_FIELDS) {
    const id = generateItemId(code, 'ctrl', idx, undefined, field)
    const val = cp[field as keyof B23ControlPoint]
    if (CTRL_CONCLUSION_FIELDS.has(field)) {
      // enum → conclusion; multi-select array → remark comma-joined
      if (field === 'assertion') {
        items.push({ item_id: id, conclusion: null, remark: (val as string[]).join(',') })
      } else {
        items.push({ item_id: id, conclusion: val as string | null, remark: null })
      }
    } else {
      items.push({ item_id: id, conclusion: null, remark: (val ?? '') as string })
    }
  }
  return items
}

function deserializeControlPoint(code: string, idx: number, store: Map<string, StoredItem>): B23ControlPoint {
  const get = (field: string) => {
    const id = generateItemId(code, 'ctrl', idx, undefined, field)
    return store.get(id)
  }
  return {
    index: idx,
    subProcess: get('subProcess')?.remark ?? '',
    ctrlNo: get('ctrlNo')?.remark ?? '',
    ctrlName: get('ctrlName')?.remark ?? '',
    ctrlDesc: get('ctrlDesc')?.remark ?? '',
    affectedItems: get('affectedItems')?.remark ?? '',
    assertion: (get('assertion')?.remark ?? '').split(',').filter(Boolean),
    wcgwRef: get('wcgwRef')?.remark ?? '',
    wcgwDetail: get('wcgwDetail')?.remark ?? '',
    ctrlAttr: get('ctrlAttr')?.remark ?? '',
    frequency: (get('frequency')?.conclusion as B23ControlPoint['frequency']) ?? null,
    itApp: get('itApp')?.remark ?? '',
    preventDetect: (get('preventDetect')?.conclusion as B23ControlPoint['preventDetect']) ?? null,
    designEffective: (get('designEffective')?.conclusion as B23ControlPoint['designEffective']) ?? null,
    ctrlTypeL1: (get('ctrlTypeL1')?.conclusion as B23ControlPoint['ctrlTypeL1']) ?? null,
    ctrlTypeL2: (get('ctrlTypeL2')?.conclusion as B23ControlPoint['ctrlTypeL2']) ?? null,
    executor: get('executor')?.remark ?? '',
    executorOrg: get('executorOrg')?.remark ?? '',
    hasDoc: (get('hasDoc')?.conclusion as B23ControlPoint['hasDoc']) ?? null,
    isKeyControl: (get('isKeyControl')?.conclusion as B23ControlPoint['isKeyControl']) ?? null,
    doControlTest: (get('doControlTest')?.conclusion as B23ControlPoint['doControlTest']) ?? null,
  }
}

function serializeWalkthrough(code: string, ctrlIdx: number, wt: B23WalkthroughTest): StoredItem[] {
  const items: StoredItem[] = []
  for (const field of WT_FIELDS) {
    const id = generateItemId(code, 'wt', ctrlIdx, undefined, field)
    const val = wt[field as keyof B23WalkthroughTest]
    if (field === 'method') {
      items.push({ item_id: id, conclusion: null, remark: (val as string[]).join(',') })
    } else if (WT_CONCLUSION_FIELDS.has(field)) {
      items.push({ item_id: id, conclusion: val as string | null, remark: null })
    } else {
      items.push({ item_id: id, conclusion: null, remark: (val ?? '') as string })
    }
  }
  return items
}

function deserializeWalkthrough(code: string, ctrlIdx: number, store: Map<string, StoredItem>): B23WalkthroughTest {
  const get = (field: string) => {
    const id = generateItemId(code, 'wt', ctrlIdx, undefined, field)
    return store.get(id)
  }
  return {
    ctrlIndex: ctrlIdx,
    method: (get('method')?.remark ?? '').split(',').filter(Boolean),
    interviewee: get('interviewee')?.remark ?? '',
    procedure: get('procedure')?.remark ?? '',
    evidence: get('evidence')?.remark ?? '',
    result: get('result')?.remark ?? '',
    asDesigned: (get('asDesigned')?.conclusion as B23WalkthroughTest['asDesigned']) ?? null,
    deficiencyFound: get('deficiencyFound')?.remark ?? '',
  }
}

function serializeControlTest(code: string, ctrlIdx: number, ct: B23ControlTest): StoredItem[] {
  const items: StoredItem[] = []
  for (const field of CT_FIELDS) {
    const id = generateItemId(code, 'ct', ctrlIdx, undefined, field)
    const val = ct[field as keyof B23ControlTest]
    if (CT_CONCLUSION_FIELDS.has(field)) {
      items.push({ item_id: id, conclusion: val as string | null, remark: null })
    } else {
      items.push({ item_id: id, conclusion: null, remark: (val ?? '') as string })
    }
  }
  return items
}

function deserializeControlTest(code: string, ctrlIdx: number, store: Map<string, StoredItem>): B23ControlTest {
  const get = (field: string) => {
    const id = generateItemId(code, 'ct', ctrlIdx, undefined, field)
    return store.get(id)
  }
  return {
    ctrlIndex: ctrlIdx,
    riskJudgment: get('riskJudgment')?.remark ?? '',
    testNature: get('testNature')?.remark ?? '',
    testTiming: get('testTiming')?.remark ?? '',
    testScope: get('testScope')?.remark ?? '',
    operatingEffective: (get('operatingEffective')?.conclusion as B23ControlTest['operatingEffective']) ?? null,
    deviation: get('deviation')?.remark ?? '',
    substantiveImpact: get('substantiveImpact')?.remark ?? '',
  }
}

function serializeDeficiency(code: string, idx: number, def: B23Deficiency): StoredItem[] {
  const items: StoredItem[] = []
  for (const field of DEF_FIELDS) {
    const id = generateItemId(code, 'def', idx, undefined, field)
    const val = def[field as keyof B23Deficiency]
    if (DEF_CONCLUSION_FIELDS.has(field)) {
      items.push({ item_id: id, conclusion: val as string | null, remark: null })
    } else {
      items.push({ item_id: id, conclusion: null, remark: (val ?? '') as string })
    }
  }
  return items
}

function deserializeDeficiency(code: string, idx: number, store: Map<string, StoredItem>): B23Deficiency {
  const get = (field: string) => {
    const id = generateItemId(code, 'def', idx, undefined, field)
    return store.get(id)
  }
  return {
    index: idx,
    subProcess: get('subProcess')?.remark ?? '',
    description: get('description')?.remark ?? '',
    deficiencyType: (get('deficiencyType')?.conclusion as B23Deficiency['deficiencyType']) ?? null,
    severity: (get('severity')?.conclusion as B23Deficiency['severity']) ?? null,
    impact: get('impact')?.remark ?? '',
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: item_id 前缀完整不变式
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Rework Property 10: item_id 前缀完整', () => {
  it('generateItemId 对简单类型恒返回非空 B23- 前缀字符串', () => {
    const simpleTypes = ['applicability', 'cycle-conclusion', 'conclusion-override', 'ctrl-count', 'def-count'] as const
    fc.assert(
      fc.property(arbCycleCode, fc.constantFrom(...simpleTypes), (code, type) => {
        const id = generateItemId(code, type)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('generateItemId 对 ctrl 类型恒返回非空 B23- 前缀、含 ctrl 段的唯一键', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbCtrlField, (code, idx, field) => {
        const id = generateItemId(code, 'ctrl', idx, undefined, field)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).toContain('-ctrl-')
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('generateItemId 对 wt 类型恒返回非空 B23- 前缀、含 wt 段的唯一键', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbWtField, (code, idx, field) => {
        const id = generateItemId(code, 'wt', idx, undefined, field)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).toContain('-wt-')
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('generateItemId 对 ct 类型恒返回非空 B23- 前缀、含 ct 段的唯一键', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbCtField, (code, idx, field) => {
        const id = generateItemId(code, 'ct', idx, undefined, field)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).toContain('-ct-')
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('generateItemId 对 def 类型恒返回非空 B23- 前缀、含 def 段的唯一键', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbDefField, (code, idx, field) => {
        const id = generateItemId(code, 'def', idx, undefined, field)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).toContain('-def-')
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('generateItemId 对 subproc 类型恒返回非空 B23- 前缀、含 subproc 段的唯一键', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, (code, idx) => {
        const id = generateItemId(code, 'subproc', idx)
        expect(id).toBeTruthy()
        expect(id.startsWith('B23-')).toBe(true)
        expect(id).toContain('-subproc-')
        expect(id).not.toContain('undefined')
        expect(id).not.toContain('null')
      }),
      { numRuns: 20 },
    )
  })

  it('16 cycles × all types × same index/field → 全部唯一（无碰撞）', () => {
    // Exhaustive uniqueness check across all cycles for representative IDs
    const ids = new Set<string>()
    const testFields = { ctrl: 'ctrlName', wt: 'procedure', ct: 'testScope', def: 'description' }
    for (const code of ALL_CYCLE_CODES) {
      ids.add(generateItemId(code, 'applicability'))
      ids.add(generateItemId(code, 'cycle-conclusion'))
      ids.add(generateItemId(code, 'conclusion-override'))
      ids.add(generateItemId(code, 'ctrl-count'))
      ids.add(generateItemId(code, 'def-count'))
      for (let idx = 1; idx <= 3; idx++) {
        ids.add(generateItemId(code, 'ctrl', idx, undefined, testFields.ctrl))
        ids.add(generateItemId(code, 'wt', idx, undefined, testFields.wt))
        ids.add(generateItemId(code, 'ct', idx, undefined, testFields.ct))
        ids.add(generateItemId(code, 'def', idx, undefined, testFields.def))
        ids.add(generateItemId(code, 'subproc', idx))
      }
    }
    // 16 codes × (5 simple + 3×5 indexed) = 16 × 20 = 320 unique IDs expected
    expect(ids.size).toBe(16 * (5 + 3 * 5))
  })

  it('wt-* 与 ct-* 命名空间不碰撞（同 code、同 index、同 field 名）', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, (code, idx) => {
        // Use a field name that exists in both WT and CT conceptually (like a generic name)
        const wtId = generateItemId(code, 'wt', idx, undefined, 'result')
        const ctId = generateItemId(code, 'ct', idx, undefined, 'deviation')
        expect(wtId).not.toBe(ctId)

        // Even with same hypothetical field name, type segment differs
        const wtX = generateItemId(code, 'wt', idx, undefined, 'x')
        const ctX = generateItemId(code, 'ct', idx, undefined, 'x')
        expect(wtX).not.toBe(ctX)
      }),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 持久化往返不变式 — load(save(x)) == x
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Rework Property 1: 持久化往返不变式', () => {
  it('ControlPoint: serialize→deserialize 等价', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbControlPoint, (code, idx, cp) => {
        const items = serializeControlPoint(code, idx, cp)
        const store = new Map<string, StoredItem>()
        for (const item of items) store.set(item.item_id, item)

        const restored = deserializeControlPoint(code, idx, store)

        // index comes from the deserialize parameter, not stored
        expect(restored.index).toBe(idx)
        expect(restored.subProcess).toBe(cp.subProcess)
        expect(restored.ctrlNo).toBe(cp.ctrlNo)
        expect(restored.ctrlName).toBe(cp.ctrlName)
        expect(restored.ctrlDesc).toBe(cp.ctrlDesc)
        expect(restored.affectedItems).toBe(cp.affectedItems)
        expect(restored.assertion).toEqual(cp.assertion)
        expect(restored.wcgwRef).toBe(cp.wcgwRef)
        expect(restored.wcgwDetail).toBe(cp.wcgwDetail)
        expect(restored.ctrlAttr).toBe(cp.ctrlAttr)
        expect(restored.frequency).toBe(cp.frequency)
        expect(restored.itApp).toBe(cp.itApp)
        expect(restored.preventDetect).toBe(cp.preventDetect)
        expect(restored.designEffective).toBe(cp.designEffective)
        expect(restored.ctrlTypeL1).toBe(cp.ctrlTypeL1)
        expect(restored.ctrlTypeL2).toBe(cp.ctrlTypeL2)
        expect(restored.executor).toBe(cp.executor)
        expect(restored.executorOrg).toBe(cp.executorOrg)
        expect(restored.hasDoc).toBe(cp.hasDoc)
        expect(restored.isKeyControl).toBe(cp.isKeyControl)
        expect(restored.doControlTest).toBe(cp.doControlTest)
      }),
      { numRuns: 20 },
    )
  })

  it('WalkthroughTest: serialize→deserialize 等价', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbWalkthroughTest, (code, idx, wt) => {
        const items = serializeWalkthrough(code, idx, wt)
        const store = new Map<string, StoredItem>()
        for (const item of items) store.set(item.item_id, item)

        const restored = deserializeWalkthrough(code, idx, store)

        expect(restored.ctrlIndex).toBe(idx)
        expect(restored.method).toEqual(wt.method)
        expect(restored.interviewee).toBe(wt.interviewee)
        expect(restored.procedure).toBe(wt.procedure)
        expect(restored.evidence).toBe(wt.evidence)
        expect(restored.result).toBe(wt.result)
        expect(restored.asDesigned).toBe(wt.asDesigned)
        expect(restored.deficiencyFound).toBe(wt.deficiencyFound)
      }),
      { numRuns: 20 },
    )
  })

  it('ControlTest: serialize→deserialize 等价', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbControlTest, (code, idx, ct) => {
        const items = serializeControlTest(code, idx, ct)
        const store = new Map<string, StoredItem>()
        for (const item of items) store.set(item.item_id, item)

        const restored = deserializeControlTest(code, idx, store)

        expect(restored.ctrlIndex).toBe(idx)
        expect(restored.riskJudgment).toBe(ct.riskJudgment)
        expect(restored.testNature).toBe(ct.testNature)
        expect(restored.testTiming).toBe(ct.testTiming)
        expect(restored.testScope).toBe(ct.testScope)
        expect(restored.operatingEffective).toBe(ct.operatingEffective)
        expect(restored.deviation).toBe(ct.deviation)
        expect(restored.substantiveImpact).toBe(ct.substantiveImpact)
      }),
      { numRuns: 20 },
    )
  })

  it('Deficiency: serialize→deserialize 等价', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbDeficiency, (code, idx, def) => {
        const items = serializeDeficiency(code, idx, def)
        const store = new Map<string, StoredItem>()
        for (const item of items) store.set(item.item_id, item)

        const restored = deserializeDeficiency(code, idx, store)

        expect(restored.index).toBe(idx)
        expect(restored.subProcess).toBe(def.subProcess)
        expect(restored.description).toBe(def.description)
        expect(restored.deficiencyType).toBe(def.deficiencyType)
        expect(restored.severity).toBe(def.severity)
        expect(restored.impact).toBe(def.impact)
      }),
      { numRuns: 20 },
    )
  })

  it('所有 item_id 在 serialize 后均以 B23- 为前缀（P1 × P10 交叉验证）', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbControlPoint, (code, idx, cp) => {
        const items = serializeControlPoint(code, idx, cp)
        for (const item of items) {
          expect(item.item_id.startsWith('B23-')).toBe(true)
          expect(item.item_id.length).toBeGreaterThan(4)
        }
      }),
      { numRuns: 20 },
    )
  })
})
