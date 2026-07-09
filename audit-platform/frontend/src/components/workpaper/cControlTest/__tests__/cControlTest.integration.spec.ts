/**
 * cControlTest.integration.spec.ts — C2~C15 控制测试端到端集成测试
 *
 * Spec: .kiro/specs/c-control-test-refresh/  Task 7.1
 * Validates: Requirements 1.5, 4.3, 5.2, 7.2
 *
 * 测试三大场景：
 * 1. 历史数据加载兼容 — C{n}- 前缀 checklist_responses 旧/新格式共存加载，字段值不丢失
 * 2. 汇总/子页/决策树端到端 — 完整流程验证数据在各视图间正确传递
 * 3. EventBus B50 — 循环结论变更时正确发布 control:test-concluded 事件
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Mock api ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: 'test' }) },
}))

// ─── Mock eventBus to capture emissions ──────────────────────────────────────

const emittedEvents: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emittedEvents.push({ event, payload }) },
    on: vi.fn(),
    off: vi.fn(),
    all: { clear: vi.fn() },
  },
}))

// ─── Mock project store ──────────────────────────────────────────────────────

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    clientName: '测试客户',
    year: 2025,
    projectId: 'proj-1',
  }),
}))

// ─── Import composables under test ──────────────────────────────────────────

import { useCControlTestData, extractCycleNumber } from '@/composables/useCControlTestData'
import { evaluateDecisionTree, createEmptyState } from '@/composables/useDeviationDecisionTree'
import type { DecisionTreeState } from '@/composables/useDeviationDecisionTree'

// ─── Test fixtures: 历史数据 ─────────────────────────────────────────────────

/** 模拟后端返回的 C2 历史 checklist_responses（新格式 + 旧格式共存） */
function buildHistoryResponses() {
  return [
    // ─── 汇总表行 1（新格式 C2-sum-*） ───
    { item_id: 'C2-sum-1-subProcess', conclusion: null, remark: '销售合同审批', wp_ref: null },
    { item_id: 'C2-sum-1-controlId', conclusion: null, remark: 'D-C1', wp_ref: null },
    { item_id: 'C2-sum-1-controlName', conclusion: null, remark: '合同审批控制', wp_ref: null },
    { item_id: 'C2-sum-1-description', conclusion: null, remark: '所有销售合同需经主管审批', wp_ref: null },
    { item_id: 'C2-sum-1-affectedItems', conclusion: null, remark: '收入/应收账款', wp_ref: null },
    { item_id: 'C2-sum-1-assertion', conclusion: '完整性', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-attribute', conclusion: '预防性', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-frequency', conclusion: '每天', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-relatedRisk', conclusion: null, remark: '合同未经授权', wp_ref: null },
    { item_id: 'C2-sum-1-testMethod', conclusion: '检查', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-sampleSize', conclusion: '25', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-hasDeviation', conclusion: '是', remark: null, wp_ref: null },
    { item_id: 'C2-sum-1-remediation', conclusion: null, remark: '已整改', wp_ref: null },
    { item_id: 'C2-sum-1-defect', conclusion: null, remark: '审批记录不完整', wp_ref: null },
    { item_id: 'C2-sum-1-indexRef', conclusion: null, remark: 'C2-1-1', wp_ref: null },

    // ─── 汇总表行 2（部分填写） ───
    { item_id: 'C2-sum-2-controlName', conclusion: null, remark: '发货确认控制', wp_ref: null },
    { item_id: 'C2-sum-2-frequency', conclusion: '每周', remark: null, wp_ref: null },
    { item_id: 'C2-sum-2-hasDeviation', conclusion: '否', remark: null, wp_ref: null },

    // ─── 子页 1 字段（新格式 C2-ctrl-*） ───
    { item_id: 'C2-ctrl-1-attribute', conclusion: '预防性', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-frequency', conclusion: '每天', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-relatedRisk', conclusion: '销售合同授权风险', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-testMethod', conclusion: '检查', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-testProcedure', conclusion: null, remark: '抽取25份合同检查审批签字', wp_ref: null },
    { item_id: 'C2-ctrl-1-populationDef', conclusion: null, remark: '2025年度全部销售合同', wp_ref: null },
    { item_id: 'C2-ctrl-1-populationSource', conclusion: null, remark: 'ERP合同管理模块', wp_ref: null },
    { item_id: 'C2-ctrl-1-sampleSize', conclusion: '25', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-samplingMethod', conclusion: null, remark: '随机抽样', wp_ref: null },
    { item_id: 'C2-ctrl-1-samplingProcess', conclusion: null, remark: '使用IDEA随机数生成器', wp_ref: null },
    { item_id: 'C2-ctrl-1-deviationDef', conclusion: null, remark: '缺少审批签字', wp_ref: null },

    // ─── 子页 1 样本数据 ───
    { item_id: 'C2-ctrl-1-sample-1-description', conclusion: null, remark: '合同HT-2025-001', wp_ref: null },
    { item_id: 'C2-ctrl-1-sample-1-result', conclusion: '有效', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-sample-2-description', conclusion: null, remark: '合同HT-2025-002', wp_ref: null },
    { item_id: 'C2-ctrl-1-sample-2-result', conclusion: '偏差', remark: null, wp_ref: null },
    { item_id: 'C2-ctrl-1-sample-3-description', conclusion: null, remark: '合同HT-2025-003', wp_ref: null },
    { item_id: 'C2-ctrl-1-sample-3-result', conclusion: '有效', remark: null, wp_ref: null },

    // ─── 偏差决策树 1（新格式 C2-dev-*） ───
    { item_id: 'C2-dev-1-step1', conclusion: '是', remark: null, wp_ref: null },
    { item_id: 'C2-dev-1-step2', conclusion: '随机性偏差', remark: null, wp_ref: null },
    { item_id: 'C2-dev-1-step3', conclusion: '扩大样本量', remark: null, wp_ref: null },
    { item_id: 'C2-dev-1-step4', conclusion: '否', remark: null, wp_ref: null },
    { item_id: 'C2-dev-1-conclusion', conclusion: '控制有效', remark: null, wp_ref: null },

    // ─── 循环结论 ───
    { item_id: 'C2-cycle-conclusion', conclusion: '控制有效运行', remark: null, wp_ref: null },

    // ─── 不相关数据（其他循环，应被忽略） ───
    { item_id: 'C3-sum-1-controlName', conclusion: null, remark: '不应被 C2 加载', wp_ref: null },
  ]
}

// ─── Helper: instantiate composable ──────────────────────────────────────────

function createComposable(wpCode = 'C2', readonly = false) {
  const wpId = ref('wp-c2-test')
  const projectId = ref('proj-1')
  const wpCodeRef = ref(wpCode)
  const isReadonly = ref(readonly)
  return useCControlTestData(wpId, projectId, wpCodeRef, isReadonly)
}

// ─── Setup / Teardown ────────────────────────────────────────────────────────

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPut.mockResolvedValue([])
  emittedEvents.length = 0
})

afterEach(() => {
  vi.clearAllTimers()
})

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 历史数据加载兼容（Requirement 1.5）
// ═══════════════════════════════════════════════════════════════════════════════

describe('历史数据加载兼容（Req 1.5）', () => {
  it('加载 C2- 前缀数据并正确解析到汇总表、子页、决策树', async () => {
    const responses = buildHistoryResponses()
    mockGet.mockResolvedValue(responses)

    const { selfLoad, state } = createComposable('C2')
    await selfLoad()

    // 验证汇总表行数
    expect(state.value.summaryRows.length).toBe(2)

    // 验证汇总表行 1 全部 15 列字段值不丢失
    const row1 = state.value.summaryRows[0]
    expect(row1.subProcess).toBe('销售合同审批')
    expect(row1.controlId).toBe('D-C1')
    expect(row1.controlName).toBe('合同审批控制')
    expect(row1.description).toBe('所有销售合同需经主管审批')
    expect(row1.affectedItems).toBe('收入/应收账款')
    expect(row1.assertion).toBe('完整性')
    expect(row1.attribute).toBe('预防性')
    expect(row1.frequency).toBe('每天')
    expect(row1.relatedRisk).toBe('合同未经授权')
    expect(row1.testMethod).toBe('检查')
    expect(row1.sampleSize).toBe(25)
    expect(row1.hasDeviation).toBe('是')
    expect(row1.remediation).toBe('已整改')
    expect(row1.defect).toBe('审批记录不完整')
    expect(row1.indexRef).toBe('C2-1-1')

    // 验证汇总表行 2 部分填写
    const row2 = state.value.summaryRows[1]
    expect(row2.controlName).toBe('发货确认控制')
    expect(row2.frequency).toBe('每周')
    expect(row2.hasDeviation).toBe('否')
    // 未填字段应为空默认值
    expect(row2.subProcess).toBe('')
    expect(row2.sampleSize).toBeNull()
  })

  it('子页数据正确解析：字段值、样本数据不丢失', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const { selfLoad, state } = createComposable('C2')
    await selfLoad()

    // 子页 1 字段
    const page1 = state.value.controlPages[0]
    expect(page1.attribute).toBe('预防性')
    expect(page1.frequency).toBe('每天')
    expect(page1.relatedRisk).toBe('销售合同授权风险')
    expect(page1.testMethod).toBe('检查')
    expect(page1.testProcedure).toBe('抽取25份合同检查审批签字')
    expect(page1.populationDef).toBe('2025年度全部销售合同')
    expect(page1.populationSource).toBe('ERP合同管理模块')
    expect(page1.sampleSize).toBe(25)
    expect(page1.samplingMethod).toBe('随机抽样')
    expect(page1.samplingProcess).toBe('使用IDEA随机数生成器')
    expect(page1.deviationDef).toBe('缺少审批签字')

    // 样本数据
    expect(page1.samples.length).toBe(3)
    expect(page1.samples[0]).toEqual({ description: '合同HT-2025-001', result: '有效' })
    expect(page1.samples[1]).toEqual({ description: '合同HT-2025-002', result: '偏差' })
    expect(page1.samples[2]).toEqual({ description: '合同HT-2025-003', result: '有效' })
  })

  it('决策树状态正确解析并可由 evaluateDecisionTree 推导结论', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const { selfLoad, state } = createComposable('C2')
    await selfLoad()

    // 偏差决策树 1：step1=是, step2=随机性偏差, step3=扩大样本量, step4=否 → Path E 控制有效
    const dev1 = state.value.deviationStates[0]
    expect(dev1.step1).toBe('是')
    expect(dev1.step2).toBe('随机性偏差')
    expect(dev1.step3).toBe('扩大样本量')
    expect(dev1.step4).toBe('否')

    // 纯函数推导验证
    const result = evaluateDecisionTree(dev1)
    expect(result.conclusion).toBe('控制有效')
    expect(result.goToA14).toBe(false)
    expect(result.path).toBe('E')
  })

  it('循环结论正确加载', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const { selfLoad, state } = createComposable('C2')
    await selfLoad()

    expect(state.value.cycleConclusion).toBe('控制有效运行')
  })

  it('不同循环（C3~C15）数据隔离：仅加载对应前缀', async () => {
    const mixedResponses = [
      { item_id: 'C5-sum-1-controlName', conclusion: null, remark: '存货盘点控制', wp_ref: null },
      { item_id: 'C5-sum-1-frequency', conclusion: '每年', remark: null, wp_ref: null },
      { item_id: 'C2-sum-1-controlName', conclusion: null, remark: '不应被 C5 加载', wp_ref: null },
      { item_id: 'C5-ctrl-1-testProcedure', conclusion: null, remark: '观察盘点过程', wp_ref: null },
      { item_id: 'C5-dev-1-step1', conclusion: '否', remark: null, wp_ref: null },
      { item_id: 'C5-dev-1-step6', conclusion: '否', remark: null, wp_ref: null },
      { item_id: 'C5-cycle-conclusion', conclusion: '控制有效', remark: null, wp_ref: null },
    ]
    mockGet.mockResolvedValue(mixedResponses)
    const { selfLoad, state } = createComposable('C5')
    await selfLoad()

    expect(state.value.cycleNumber).toBe(5)
    expect(state.value.summaryRows.length).toBe(1)
    expect(state.value.summaryRows[0].controlName).toBe('存货盘点控制')
    expect(state.value.controlPages[0].testProcedure).toBe('观察盘点过程')
    expect(state.value.cycleConclusion).toBe('控制有效')

    // 决策树验证：step1=否 → step6=否 → Path A
    const result = evaluateDecisionTree(state.value.deviationStates[0])
    expect(result.conclusion).toBe('不构成偏差或缺陷，控制有效')
    expect(result.path).toBe('A')
  })

  it('空数据加载不崩溃：无历史数据返回空 state', async () => {
    mockGet.mockResolvedValue([])
    const { selfLoad, state } = createComposable('C10')
    await selfLoad()

    expect(state.value.cycleNumber).toBe(10)
    expect(state.value.summaryRows.length).toBe(0)
    expect(state.value.controlPages.length).toBe(0)
    expect(state.value.deviationStates.length).toBe(0)
    expect(state.value.cycleConclusion).toBe('')
  })

  it('ensureDeviationSlots：空偏差槽位时自动创建可编辑槽位', async () => {
    mockGet.mockResolvedValue([])
    const composable = createComposable('C10')
    await composable.selfLoad()

    expect(composable.state.value.deviationStates.length).toBe(0)
    composable.ensureDeviationSlots()
    expect(composable.state.value.deviationStates.length).toBe(1)
    expect(composable.state.value.summaryRows.length).toBe(1)

    composable.updateDeviationStep(0, 'step1', '是')
    expect(composable.state.value.deviationStates[0].step1).toBe('是')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 汇总/子页/决策树端到端（Requirements 4.3, 5.2）
// ═══════════════════════════════════════════════════════════════════════════════

describe('汇总/子页/决策树端到端流程（Req 4.3, 5.2）', () => {
  it('完整流程：添加控制点 → 录入样本 → 偏差回填汇总 → 决策树推导结论', async () => {
    mockGet.mockResolvedValue([])
    const composable = createComposable('C2')
    await composable.selfLoad()
    const { state } = composable

    // ① 汇总表添加控制点
    composable.addControlPoint('收入确认控制')
    expect(state.value.summaryRows.length).toBe(1)
    expect(state.value.summaryRows[0].controlName).toBe('收入确认控制')
    expect(state.value.controlPages.length).toBe(1)
    expect(state.value.deviationStates.length).toBe(1)

    // ② 设置汇总表基本信息
    composable.updateSummaryEnum(0, 'frequency', '每月')
    composable.updateSummaryEnum(0, 'attribute', '检查性')
    composable.updateSummaryEnum(0, 'testMethod', '检查')
    expect(state.value.summaryRows[0].frequency).toBe('每月')
    expect(state.value.summaryRows[0].attribute).toBe('检查性')

    // ③ 子页录入样本
    composable.addSample(0)
    composable.addSample(0)
    composable.addSample(0)
    expect(state.value.controlPages[0].samples.length).toBe(3)

    composable.updateSampleResult(0, 0, '有效')
    composable.updateSampleResult(0, 1, '偏差')
    composable.updateSampleResult(0, 2, '有效')
    expect(state.value.controlPages[0].samples[1].result).toBe('偏差')

    // ④ 偏差回填汇总（Req 4.3）：子页存在偏差 → hasDeviation = '是'
    // 模拟组件级偏差回填逻辑（统计偏差数回填）
    const deviationCount = state.value.controlPages[0].samples.filter(
      s => s.result === '偏差'
    ).length
    const hasDeviation = deviationCount > 0 ? '是' : '否'
    composable.updateSummaryEnum(0, 'hasDeviation', hasDeviation)
    expect(state.value.summaryRows[0].hasDeviation).toBe('是')

    // ⑤ 进入 Cx-2 决策树：逐步推导（Req 5.2）
    composable.updateDeviationStep(0, 'step1', '是')     // 属于控制偏差
    composable.updateDeviationStep(0, 'step2', '系统性偏差') // 偏差性质

    const devState = state.value.deviationStates[0]
    expect(devState.step1).toBe('是')
    expect(devState.step2).toBe('系统性偏差')

    // 决策树推导：系统性偏差 → Path C → 属于控制缺陷 → goToA14
    const result = evaluateDecisionTree(devState)
    expect(result.conclusion).toBe('属于控制缺陷，进入内控缺陷评价')
    expect(result.goToA14).toBe(true)
    expect(result.path).toBe('C')
  })

  it('决策树全路径覆盖：Path A~F 各路径推导正确', () => {
    // Path A: step1=否, step6=否 → 不构成偏差或缺陷，控制有效
    const stateA: DecisionTreeState = { ...createEmptyState(), step1: '否', step6: '否' }
    expect(evaluateDecisionTree(stateA)).toMatchObject({
      conclusion: '不构成偏差或缺陷，控制有效', goToA14: false, path: 'A',
    })

    // Path B: step1=否, step6=是 → 存在设计缺陷 → goToA14
    const stateB: DecisionTreeState = { ...createEmptyState(), step1: '否', step6: '是' }
    expect(evaluateDecisionTree(stateB)).toMatchObject({
      conclusion: '存在设计缺陷，进入内控缺陷评价', goToA14: true, path: 'B',
    })

    // Path C: step1=是, step2=人为偏差 → 属于控制缺陷 → goToA14
    const stateC: DecisionTreeState = { ...createEmptyState(), step1: '是', step2: '人为偏差' }
    expect(evaluateDecisionTree(stateC)).toMatchObject({
      conclusion: '属于控制缺陷，进入内控缺陷评价', goToA14: true, path: 'C',
    })

    // Path D: step1=是, step2=随机, step3=直接认定 → goToA14
    const stateD: DecisionTreeState = {
      ...createEmptyState(), step1: '是', step2: '随机性偏差', step3: '直接认定为偏差',
    }
    expect(evaluateDecisionTree(stateD)).toMatchObject({
      conclusion: '直接认定为偏差，进入内控缺陷评价', goToA14: true, path: 'D',
    })

    // Path E: step1=是, step2=随机, step3=扩大, step4=否 → 控制有效
    const stateE: DecisionTreeState = {
      ...createEmptyState(), step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '否',
    }
    expect(evaluateDecisionTree(stateE)).toMatchObject({
      conclusion: '控制有效', goToA14: false, path: 'E',
    })

    // Path F: step1=是, step2=随机, step3=扩大, step4=是 → 控制无效 → goToA14
    const stateF: DecisionTreeState = {
      ...createEmptyState(), step1: '是', step2: '随机性偏差', step3: '扩大样本量', step4: '是',
    }
    expect(evaluateDecisionTree(stateF)).toMatchObject({
      conclusion: '控制无效，进入内控缺陷评价', goToA14: true, path: 'F',
    })
  })

  it('偏差回填一致性：无偏差样本 → hasDeviation=否', async () => {
    mockGet.mockResolvedValue([])
    const composable = createComposable('C2')
    await composable.selfLoad()
    const { state } = composable

    composable.addControlPoint('无偏差控制点')
    composable.addSample(0)
    composable.addSample(0)
    composable.updateSampleResult(0, 0, '有效')
    composable.updateSampleResult(0, 1, '有效')

    // 模拟偏差回填逻辑
    const hasDeviation = state.value.controlPages[0].samples.some(
      s => s.result === '偏差'
    ) ? '是' : '否'
    composable.updateSummaryEnum(0, 'hasDeviation', hasDeviation)
    expect(state.value.summaryRows[0].hasDeviation).toBe('否')
  })

  it('数据往返：加载 → 序列化 → item_id 格式一致', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const composable = createComposable('C2')
    await composable.selfLoad()

    // 序列化后验证 item_id 格式
    const items = composable.serializeAll()
    expect(items.length).toBeGreaterThan(0)

    // 所有 item_id 都以 C2- 开头
    for (const item of items) {
      expect(item.item_id).toMatch(/^C2-/)
    }

    // 验证关键值保留
    const sumControlName = items.find(i => i.item_id === 'C2-sum-1-controlName')
    expect(sumControlName?.remark).toBe('合同审批控制')

    const sampleResult = items.find(i => i.item_id === 'C2-ctrl-1-sample-2-result')
    expect(sampleResult?.conclusion).toBe('偏差')

    const devStep2 = items.find(i => i.item_id === 'C2-dev-1-step2')
    expect(devStep2?.conclusion).toBe('随机性偏差')
  })

  it('persistAll 调用 PUT 接口并包含正确 payload', async () => {
    mockGet.mockResolvedValue([])
    const composable = createComposable('C2')
    await composable.selfLoad()

    composable.addControlPoint('测试控制点')
    composable.updateSummaryEnum(0, 'frequency', '每月')

    // addControlPoint 和 updateSummaryEnum 都调 saveImmediate → persistAll
    // 等待所有异步完成
    await nextTick()

    expect(mockPut).toHaveBeenCalled()
    const lastCall = mockPut.mock.calls[mockPut.mock.calls.length - 1]
    const url = lastCall[0]
    const body = lastCall[1]

    expect(url).toContain('/checklist-responses')
    expect(body.project_id).toBe('proj-1')
    expect(body.items).toBeInstanceOf(Array)
    expect(body.items.some((i: any) => i.item_id === 'C2-sum-1-controlName')).toBe(true)
    expect(body.items.some((i: any) => i.item_id === 'C2-sum-1-frequency')).toBe(true)
  })

  it('readonly 模式阻止所有修改操作', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const composable = createComposable('C2', true)  // readonly=true
    await composable.selfLoad()
    const { state } = composable

    const originalLength = state.value.summaryRows.length

    // 尝试各种修改操作
    composable.addControlPoint('不应被添加')
    composable.removeControlPoint(0)
    composable.updateSummaryEnum(0, 'frequency', '每年')
    composable.updateSummaryText(0, 'controlName', '不应被更改')
    composable.addSample(0)
    composable.updateDeviationStep(0, 'step1', '否')
    composable.updateCycleConclusion('不应变更')

    // 验证 state 未变
    expect(state.value.summaryRows.length).toBe(originalLength)
    expect(state.value.summaryRows[0].controlName).toBe('合同审批控制')
    expect(state.value.summaryRows[0].frequency).toBe('每天')
    expect(state.value.deviationStates[0].step1).toBe('是')
    expect(state.value.cycleConclusion).toBe('控制有效运行')
    expect(mockPut).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. EventBus B50（Requirement 7.2）
// ═══════════════════════════════════════════════════════════════════════════════

describe('EventBus B50 — control:test-concluded 事件（Req 7.2）', () => {
  it('循环结论变更时发布 control:test-concluded 事件且载荷正确', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const composable = createComposable('C2')
    await composable.selfLoad()

    emittedEvents.length = 0

    // 变更循环结论
    composable.updateCycleConclusion('控制存在偏差')

    // 验证事件发布
    expect(emittedEvents.length).toBe(1)
    const evt = emittedEvents[0]
    expect(evt.event).toBe('control:test-concluded')
    expect(evt.payload.wpCode).toBe('C2')
    expect(evt.payload.cycleName).toBe('销售与收款循环')
    expect(evt.payload.conclusion).toBe('控制存在偏差')
    // 历史数据有 defect 字段 → defectSummary 非空
    expect(evt.payload.defectSummary).toBe('存在控制缺陷')
  })

  it('仅新旧值不同时才发布事件（相同值不触发）', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const composable = createComposable('C2')
    await composable.selfLoad()
    // 当前结论为 '控制有效运行'

    emittedEvents.length = 0

    // 设置相同值 → 不发布
    composable.updateCycleConclusion('控制有效运行')
    expect(emittedEvents.length).toBe(0)

    // 设置不同值 → 发布
    composable.updateCycleConclusion('控制无效')
    expect(emittedEvents.length).toBe(1)
    expect(emittedEvents[0].payload.conclusion).toBe('控制无效')

    // 再设置相同值 → 不发布
    composable.updateCycleConclusion('控制无效')
    expect(emittedEvents.length).toBe(1) // 仍然只有 1 个
  })

  it('无缺陷时 defectSummary 为空字符串', async () => {
    // 加载无缺陷数据
    const noneDefectResponses = [
      { item_id: 'C3-sum-1-controlName', conclusion: null, remark: '现金收付控制', wp_ref: null },
      { item_id: 'C3-sum-1-defect', conclusion: null, remark: '', wp_ref: null },
      { item_id: 'C3-cycle-conclusion', conclusion: '控制有效', remark: null, wp_ref: null },
    ]
    mockGet.mockResolvedValue(noneDefectResponses)
    const composable = createComposable('C3')
    await composable.selfLoad()

    emittedEvents.length = 0

    composable.updateCycleConclusion('部分有效')
    expect(emittedEvents.length).toBe(1)
    expect(emittedEvents[0].payload.defectSummary).toBe('')
    expect(emittedEvents[0].payload.cycleName).toBe('货币资金循环')
  })

  it('readonly 模式不发布 EventBus 事件', async () => {
    mockGet.mockResolvedValue(buildHistoryResponses())
    const composable = createComposable('C2', true)  // readonly
    await composable.selfLoad()

    emittedEvents.length = 0

    composable.updateCycleConclusion('控制无效')
    expect(emittedEvents.length).toBe(0)
  })

  it('多次结论变更：每次都发布且载荷正确', async () => {
    mockGet.mockResolvedValue([
      { item_id: 'C7-sum-1-controlName', conclusion: null, remark: '融资审批', wp_ref: null },
      { item_id: 'C7-sum-1-defect', conclusion: null, remark: '授权不足', wp_ref: null },
      { item_id: 'C7-cycle-conclusion', conclusion: '', remark: null, wp_ref: null },
    ])
    const composable = createComposable('C7')
    await composable.selfLoad()

    emittedEvents.length = 0

    // 第一次变更
    composable.updateCycleConclusion('控制有效运行')
    expect(emittedEvents.length).toBe(1)
    expect(emittedEvents[0].payload.wpCode).toBe('C7')
    expect(emittedEvents[0].payload.cycleName).toBe('筹资循环')
    expect(emittedEvents[0].payload.conclusion).toBe('控制有效运行')
    expect(emittedEvents[0].payload.defectSummary).toBe('存在控制缺陷')

    // 第二次变更
    composable.updateCycleConclusion('控制无效')
    expect(emittedEvents.length).toBe(2)
    expect(emittedEvents[1].payload.conclusion).toBe('控制无效')
  })
})
