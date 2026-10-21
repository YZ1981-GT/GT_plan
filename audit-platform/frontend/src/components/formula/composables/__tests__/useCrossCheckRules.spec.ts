/**
 * useCrossCheckRules —— 表间审核规则 composable（spec formula-global-settings-sync S2）
 *
 * 守护：persist 后调 askApplyScope（changed_slot_keys）、applyRulesData 保留 layer/pending、
 * onAdd/onSave/onRemove 经 persist、执行结果解析。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCrossCheckRules, type CrossCheckDeps } from '../useCrossCheckRules'

const KEYS = {
  report_note: 'cross_report_note',
  report_wp: 'cross_report_wp',
  note_wp: 'cross_note_wp',
  consol: 'cross_consol',
} as any

function makeDeps(overrides: Partial<CrossCheckDeps> = {}): CrossCheckDeps {
  return {
    projectId: ref('p1'),
    year: ref(2025 as number | string | undefined),
    selectedNodeKey: ref('cross_report_note'),
    currentProjectCacheKey: ref('p1:v1:2025'),
    cacheKeyMatches: (a, b) => a === b,
    shouldApplyResponse: () => true,
    api: { get: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) },
    projectFormula: {
      reportCrossCheck: (pid: string) => `/api/projects/${pid}/formula/report-cross-check`,
      crossCheckRules: (pid: string) => `/api/projects/${pid}/formula/cross-check-rules`,
    },
    P_rc: { executeFormulasBatch: '/api/report-config/execute-formulas-batch' },
    guardFormulaMutation: vi.fn(() => true),
    showFormulaError: vi.fn(),
    askApplyScope: vi.fn(),
    CROSS_CHECK_NODE_KEYS: KEYS,
    ...overrides,
  }
}

describe('applyRulesData', () => {
  it('保留后端下发的 layer 和 pending', () => {
    const deps = makeDeps()
    const cc = useCrossCheckRules(deps)
    cc.applyRulesData({
      rules: { cross_report_note: [{ rule_id: 'r1', label: '规则A', left_ref: '1', operator: '=', right_ref: '2', layer: 'global', pending: true }] },
      loaded: { 'cross_report_note#r1': 'G1' },
    })
    const rule = cc.rulesMap.value.cross_report_note[0]
    expect(rule.layer).toBe('global')
    expect(rule.pending).toBe(true)
    expect(cc.tokens.value).toEqual({ 'cross_report_note#r1': 'G1' })
  })
})

describe('persist', () => {
  it('成功后调 askApplyScope 传 changed_slot_keys', async () => {
    const deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {}, changed_slot_keys: ['cross_report_note#r1'] })
    const cc = useCrossCheckRules(deps)
    await cc.persist()
    expect(deps.askApplyScope).toHaveBeenCalledWith('cross_check', ['cross_report_note#r1'])
  })

  it('guardFormulaMutation 拒绝时不发请求', async () => {
    const deps = makeDeps({ guardFormulaMutation: vi.fn(() => false) as any })
    const cc = useCrossCheckRules(deps)
    await cc.persist()
    expect(deps.api.put).not.toHaveBeenCalled()
  })
})

describe('CRUD delegates to persist', () => {
  let deps: CrossCheckDeps
  let cc: ReturnType<typeof useCrossCheckRules>

  beforeEach(() => {
    deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {} })
    cc = useCrossCheckRules(deps)
  })

  it('onAdd → onSave 新增规则并落库', () => {
    cc.onAdd()
    expect(cc.showDialog.value).toBe(true)
    cc.form.value = { label: '新规则', left_ref: '1', operator: '=', right_ref: '2', description: '' }
    cc.onSave()
    expect(cc.showDialog.value).toBe(false)
    expect(cc.rulesForCurrent.value.some(r => r.label === '新规则')).toBe(true)
    expect(deps.api.put).toHaveBeenCalled()
  })

  it('onRemove 删除规则并落库', () => {
    cc.rulesMap.value.cross_report_note = [{ label: 'A' }, { label: 'B' }]
    cc.onRemove(0)
    expect(cc.rulesMap.value.cross_report_note.map(r => r.label)).toEqual(['B'])
    expect(deps.api.put).toHaveBeenCalled()
  })
})

describe('resetCache', () => {
  it('清空执行结果缓存', () => {
    const cc = useCrossCheckRules(makeDeps())
    cc.execLoaded.value = true
    cc.resetCache()
    expect(cc.execLoaded.value).toBe(false)
    expect(cc.execEmpty.value).toBe(false)
  })
})
