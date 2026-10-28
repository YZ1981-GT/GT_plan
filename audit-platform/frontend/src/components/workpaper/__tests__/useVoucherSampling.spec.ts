/**
 * useVoucherSampling — 单元测试
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 15.3
 *
 * 测试范围：
 * - 配置初始化：accountCode → config.accountCodes
 * - 校验逻辑：各方法缺必填参数
 * - updateField：字段更新 + trail 追加
 * - batchMarkChecked：批量标记 + trail
 * - confirmFill：只记日志、返回本次样本（合并归共享回填函数）；撤销返回成败；历史带批次号
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── Mock http ───────────────────────────────────────────────────────────────
vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import http from '@/utils/http'
import {
  useVoucherSampling,
  undoFailureReason,
  type VoucherSamplingOptions,
} from '../composables/useVoucherSampling'
import type { SampledVoucher, Phase } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeOptions(overrides?: Partial<VoucherSamplingOptions>): VoucherSamplingOptions {
  return {
    projectId: ref('proj-001'),
    year: ref(2025),
    workpaperId: ref('wp-001'),
    accountCode: '1122',
    phase: ref<Phase>('preliminary'),
    defaultMethod: 'random',
    ...overrides,
  }
}

function makeVoucher(partial: Partial<SampledVoucher> = {}): SampledVoucher {
  return {
    voucherNo: 'V-001',
    voucherDate: '2025-06-01',
    summary: '测试摘要',
    debitAmount: '1000.00',
    creditAmount: null,
    accountCode: '1122',
    accountName: '应收账款',
    counterpartAccount: '6001',
    counterpartAccountName: null,
    isMultiAccount: false,
    voucherEntries: [],
    voucherType: '记',
    accountingPeriod: 6,
    checkResult: '',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'preliminary',
    editTrail: [],
    ...partial,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 配置初始化
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVoucherSampling - 配置初始化', () => {
  it('accountCode="1122" → config.accountCodes=["1122"]', () => {
    const { config } = useVoucherSampling(makeOptions({ accountCode: '1122' }))
    expect(config.value.accountCodes).toEqual(['1122'])
  })

  it('accountCode="1122,1123" → config.accountCodes=["1122","1123"]', () => {
    const { config } = useVoucherSampling(makeOptions({ accountCode: '1122,1123' }))
    expect(config.value.accountCodes).toEqual(['1122', '1123'])
  })

  it('accountCode 含空格 → 自动 trim', () => {
    const { config } = useVoucherSampling(makeOptions({ accountCode: '1122, 1123 ' }))
    expect(config.value.accountCodes).toEqual(['1122', '1123'])
  })

  it('defaultMethod="stratified" → config.samplingMethod="stratified"', () => {
    const { config } = useVoucherSampling(makeOptions({ defaultMethod: 'stratified' }))
    expect(config.value.samplingMethod).toBe('stratified')
  })

  it('未指定 defaultMethod → 默认 random', () => {
    const opts = makeOptions()
    delete (opts as any).defaultMethod
    const { config } = useVoucherSampling(opts)
    expect(config.value.samplingMethod).toBe('random')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 校验逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVoucherSampling - 校验逻辑', () => {
  it('random 方法 sampleSize=0 → 校验失败', () => {
    const { config, validateConfig, configErrors } = useVoucherSampling(makeOptions())
    config.value.samplingMethod = 'random'
    config.value.sampleSize = 0
    expect(validateConfig()).toBe(false)
    expect(configErrors.value.sampleSize).toBeDefined()
  })

  it('stratified 方法 strata 为空 → 校验失败', () => {
    const { config, validateConfig, configErrors } = useVoucherSampling(makeOptions())
    config.value.samplingMethod = 'stratified'
    config.value.strata = []
    expect(validateConfig()).toBe(false)
    expect(configErrors.value.strata).toBeDefined()
  })

  it('specific_item 方法 materialityThreshold 为空 → 校验失败', () => {
    const { config, validateConfig, configErrors } = useVoucherSampling(makeOptions())
    config.value.samplingMethod = 'specific_item'
    config.value.materialityThreshold = ''
    expect(validateConfig()).toBe(false)
    expect(configErrors.value.materialityThreshold).toBeDefined()
  })

  it('systematic 方法 startPoint=0 → 校验失败', () => {
    const { config, validateConfig, configErrors } = useVoucherSampling(makeOptions())
    config.value.samplingMethod = 'systematic'
    config.value.startPoint = 0
    config.value.interval = 5
    expect(validateConfig()).toBe(false)
    expect(configErrors.value.startPoint).toBeDefined()
  })

  it('mus 方法 musSampleSize=0 → 校验失败', () => {
    const { config, validateConfig, configErrors } = useVoucherSampling(makeOptions())
    config.value.samplingMethod = 'mus'
    config.value.musSampleSize = 0
    expect(validateConfig()).toBe(false)
    expect(configErrors.value.musSampleSize).toBeDefined()
  })

  it('有效 random 配置 → 校验通过', () => {
    const { validateConfig, configErrors } = useVoucherSampling(makeOptions())
    expect(validateConfig()).toBe(true)
    expect(Object.keys(configErrors.value)).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. updateField
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVoucherSampling - updateField', () => {
  it('更新 remark 字段 → 值更新 + trail 追加', () => {
    const { sampledVouchers, updateField } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [makeVoucher({ voucherNo: 'V-001', remark: '旧备注' })]

    updateField(0, 'remark', '新备注')

    expect(sampledVouchers.value[0].remark).toBe('新备注')
    expect(sampledVouchers.value[0].editTrail).toHaveLength(1)
    expect(sampledVouchers.value[0].editTrail[0].field).toBe('remark')
    expect(sampledVouchers.value[0].editTrail[0].oldValue).toBe('旧备注')
    expect(sampledVouchers.value[0].editTrail[0].newValue).toBe('新备注')
  })

  it('更新 checkResult → trail 记录正确', () => {
    const { sampledVouchers, updateField } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [makeVoucher({ voucherNo: 'V-001', checkResult: '' })]

    updateField(0, 'checkResult', 'Y')

    expect(sampledVouchers.value[0].checkResult).toBe('Y')
    expect(sampledVouchers.value[0].editTrail[0].oldValue).toBe('')
    expect(sampledVouchers.value[0].editTrail[0].newValue).toBe('Y')
  })

  it('多次 updateField → trail 累积', () => {
    const { sampledVouchers, updateField } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [makeVoucher({ voucherNo: 'V-001', remark: '' })]

    updateField(0, 'remark', '第一次')
    updateField(0, 'remark', '第二次')

    expect(sampledVouchers.value[0].editTrail).toHaveLength(2)
    expect(sampledVouchers.value[0].editTrail[1].oldValue).toBe('第一次')
    expect(sampledVouchers.value[0].editTrail[1].newValue).toBe('第二次')
  })

  it('无效索引 → 不抛错', () => {
    const { sampledVouchers, updateField } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [makeVoucher()]
    expect(() => updateField(999, 'remark', 'test')).not.toThrow()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. batchMarkChecked
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVoucherSampling - batchMarkChecked', () => {
  it('批量设置 checkResult="Y" + 追加 trail', () => {
    const { sampledVouchers, batchMarkChecked } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', checkResult: '' }),
      makeVoucher({ voucherNo: 'V-002', checkResult: '' }),
      makeVoucher({ voucherNo: 'V-003', checkResult: '' }),
    ]

    batchMarkChecked([0, 2])

    expect(sampledVouchers.value[0].checkResult).toBe('Y')
    expect(sampledVouchers.value[1].checkResult).toBe('')  // 未标记
    expect(sampledVouchers.value[2].checkResult).toBe('Y')
  })

  it('每个标记行追加一条 trail', () => {
    const { sampledVouchers, batchMarkChecked } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', checkResult: 'N' }),
      makeVoucher({ voucherNo: 'V-002', checkResult: '' }),
    ]

    batchMarkChecked([0, 1])

    expect(sampledVouchers.value[0].editTrail).toHaveLength(1)
    expect(sampledVouchers.value[0].editTrail[0].oldValue).toBe('N')
    expect(sampledVouchers.value[0].editTrail[0].newValue).toBe('Y')
    expect(sampledVouchers.value[1].editTrail).toHaveLength(1)
    expect(sampledVouchers.value[1].editTrail[0].oldValue).toBe('')
  })

  it('无效索引跳过不抛错', () => {
    const { sampledVouchers, batchMarkChecked } = useVoucherSampling(makeOptions())
    sampledVouchers.value = [makeVoucher({ voucherNo: 'V-001' })]
    expect(() => batchMarkChecked([0, 999])).not.toThrow()
    expect(sampledVouchers.value[0].checkResult).toBe('Y')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. confirmFill / 撤销 / 历史批次号（voucher-identity-writeback-and-audit-phase 任务 9）
//    合并进底稿归宿主的共享回填函数（ADR-VK-07），撤销按批次删行（ADR-VK-08）
// ═══════════════════════════════════════════════════════════════════════════════

describe('confirmFill 只记日志、返回本次勾选的样本', () => {
  beforeEach(() => {
    mockHttp.post.mockReset()
    mockHttp.get.mockReset()
  })

  it('返回勾选的样本（不与任何已有行合并），日志不带 before_data，旧「合并」按追加记', async () => {
    mockHttp.post.mockResolvedValue({ data: { data: { batch_id: 'b-1' } } })
    const s = useVoucherSampling(makeOptions())
    s.fillMode.value = 'merge'
    const a = makeVoucher({ voucherNo: 'V1', lineFp: 'fp-1', voucherKey: 'vk-1' })
    const b = makeVoucher({ voucherNo: 'V2', lineFp: 'fp-2', voucherKey: 'vk-1', selected: false })
    s.sampledVouchers.value = [a, b]
    const result = await s.confirmFill()
    expect(result.map(v => v.voucherNo)).toEqual(['V1'])
    const body = mockHttp.post.mock.calls.find(c => String(c[0]).includes('/sampling/cutoff-fill'))![1] as any
    expect(body.fill_mode).toBe('append')
    expect('before_data' in body).toBe(false)
    expect(body.extraction_criteria.filled_line_fps).toEqual(['fp-1'])
    expect(s.filledBatchId.value).toBe('b-1')
  })

  it('「替换本阶段抽凭行」记 replace', async () => {
    mockHttp.post.mockResolvedValue({ data: {} })
    const s = useVoucherSampling(makeOptions())
    s.fillMode.value = 'replace'
    s.sampledVouchers.value = [makeVoucher()]
    await s.confirmFill()
    const body = mockHttp.post.mock.calls.find(c => String(c[0]).includes('/sampling/cutoff-fill'))![1] as any
    expect(body.fill_mode).toBe('replace')
  })
})

describe('undoLastExtraction 返回成败、不谎称底稿已恢复', () => {
  beforeEach(() => {
    mockHttp.post.mockReset()
    mockHttp.get.mockReset()
  })

  it('成功：返回 true，静默请求（提示由删行方按实际行数写），并刷新历史', async () => {
    const { ElMessage } = await import('element-plus')
    vi.mocked(ElMessage.success).mockClear()
    mockHttp.post.mockResolvedValue({ data: { success: true } })
    mockHttp.get.mockResolvedValue({ data: [] })
    const s = useVoucherSampling(makeOptions())
    expect(await s.undoLastExtraction('log-1')).toBe(true)
    const call = mockHttp.post.mock.calls[0]
    expect(String(call[0])).toContain('/sampling/voucher-undo')
    expect(call[2]).toMatchObject({ params: { log_id: 'log-1' }, _silent: true })
    expect(mockHttp.get).toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('失败：返回 false，提示后端给的原因与「底稿未改动」', async () => {
    const { ElMessage } = await import('element-plus')
    vi.mocked(ElMessage.error).mockClear()
    mockHttp.post.mockRejectedValue({
      response: { status: 409, data: { detail: { error_code: 'PRELIMINARY_BATCH_LOCKED', message: '预审批次只读' } } },
    })
    const s = useVoucherSampling(makeOptions())
    expect(await s.undoLastExtraction('log-1')).toBe(false)
    expect(ElMessage.error).toHaveBeenCalledWith('撤销失败：预审批次只读，底稿未改动')
    expect(mockHttp.get).not.toHaveBeenCalled()
  })

  it('撤销失败原因：403 / 404 / 字符串详情 / 其他', () => {
    expect(undoFailureReason({ response: { status: 403, data: {} } })).toBe('没有本底稿的编辑权限')
    expect(undoFailureReason({ response: { status: 404, data: {} } })).toBe('抽凭记录不存在')
    expect(undoFailureReason({ response: { status: 400, data: { detail: '仅可撤销最近一次操作' } } })).toBe('仅可撤销最近一次操作')
    expect(undoFailureReason(new Error('x'))).toBe('请稍后重试')
  })

  it('历史条目带批次号（宿主撤销时按它删行）', async () => {
    mockHttp.get.mockResolvedValue({ data: [{ id: 'log-1', batch_id: 'b-9', extraction_criteria: { phase: 'final' } }] })
    const s = useVoucherSampling(makeOptions())
    await s.loadHistory()
    expect(s.historyList.value[0]).toMatchObject({ id: 'log-1', batchId: 'b-9', phase: 'final' })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. 方法学增强（Task 4：useVoucherSampling 引擎编排扩展）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useVoucherSampling - 方法学增强', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ─── R16 重要性联动 ───────────────────────────────────────────────────
  describe('loadTolerableMisstatement (R16)', () => {
    it('取到执行重要性 → 写入 config.tolerableMisstatement 并标记来源', async () => {
      mockHttp.get.mockResolvedValueOnce({
        data: { performance_materiality: '80000.00', overall_materiality: '120000.00' },
      })
      const s = useVoucherSampling(makeOptions())
      const val = await s.loadTolerableMisstatement()
      expect(val).toBe('80000.00')
      expect(s.config.value.tolerableMisstatement).toBe('80000.00')
      expect(s.tolerableFromMateriality.value).toBe(true)
    })

    it('未取到重要性数据 → 返回 null 允许手填（R16.3）', async () => {
      mockHttp.get.mockRejectedValueOnce(new Error('404'))
      const s = useVoucherSampling(makeOptions())
      const val = await s.loadTolerableMisstatement()
      expect(val).toBeNull()
      expect(s.tolerableFromMateriality.value).toBe(false)
    })

    it('执行重要性为 0 → 视为未取到，返回 null', async () => {
      mockHttp.get.mockResolvedValueOnce({ data: { performance_materiality: '0' } })
      const s = useVoucherSampling(makeOptions())
      expect(await s.loadTolerableMisstatement()).toBeNull()
    })
  })

  // ─── R15 科学样本量推导 ───────────────────────────────────────────────
  describe('computeSuggestedSampleSize / applySuggestedSampleSize (R15)', () => {
    it('有置信度+可容忍错报 → 推导正数样本量并留痕间隔', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.confidenceLevel = 0.95
      s.config.value.expectedMisstatement = '0'
      const size = s.computeSuggestedSampleSize('3000000')
      expect(size).toBeGreaterThan(0)
      expect(s.suggestedSampleSize.value).toBe(size)
      expect(s.config.value.suggestedSampleSize).toBe(size)
      expect(s.samplingInterval.value).not.toBeNull()
      expect(Number(s.samplingInterval.value)).toBeGreaterThan(0)
    })

    it('缺少可容忍错报或置信度 → 返回 0 不推导', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      expect(s.computeSuggestedSampleSize('3000000')).toBe(0)
    })

    it('可容忍错报越大 → 建议样本量不增（单调性）', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.confidenceLevel = 0.95
      s.config.value.expectedMisstatement = '0'
      s.config.value.tolerableMisstatement = '50000'
      const small = s.computeSuggestedSampleSize('3000000')
      s.config.value.tolerableMisstatement = '200000'
      const large = s.computeSuggestedSampleSize('3000000')
      expect(large).toBeLessThanOrEqual(small)
    })

    it('applySuggestedSampleSize → MUS 写入 musSampleSize（保留建议值留痕）', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.confidenceLevel = 0.95
      const size = s.computeSuggestedSampleSize('3000000')
      s.applySuggestedSampleSize()
      expect(s.config.value.musSampleSize).toBe(size)
      expect(s.suggestedSampleSize.value).toBe(size) // 留痕不丢
    })

    it('applySuggestedSampleSize → 非 MUS 写入 sampleSize', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'random' }))
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.confidenceLevel = 0.95
      const size = s.computeSuggestedSampleSize('3000000')
      s.applySuggestedSampleSize()
      expect(s.config.value.sampleSize).toBe(size)
    })
  })

  // ─── R18 错报推断与总体结论 ───────────────────────────────────────────
  describe('inferMisstatement / recordActualMisstatement (R18)', () => {
    it('录入实际错报 → 推断错报≥0 并给出结论（tolerable 存在时）', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.confidenceLevel = 0.95
      s.samplingInterval.value = '10000'
      s.coverageStats.value = {
        populationCount: 100, populationAmount: '1000000',
        sampleCount: 2, sampleAmount: '15000',
        countCoverageRate: '2.00', amountCoverageRate: '1.50',
      }
      s.sampledVouchers.value = [
        makeVoucher({ voucherNo: 'V1', debitAmount: '5000', creditAmount: null }),
        makeVoucher({ voucherNo: 'V2', debitAmount: '8000', creditAmount: null }),
      ]
      s.recordActualMisstatement(0, '500')
      expect(s.sampledVouchers.value[0].actualMisstatement).toBe('500')
      // trail 留痕
      const trail = s.sampledVouchers.value[0].editTrail
      expect(trail[trail.length - 1].field).toBe('actualMisstatement')
      // 推断结果存在且非负
      expect(s.misstatementResult.value).not.toBeNull()
      expect(Number(s.misstatementResult.value!.projected)).toBeGreaterThanOrEqual(0)
      expect(Number(s.misstatementResult.value!.upperLimit)).toBeGreaterThanOrEqual(
        Number(s.misstatementResult.value!.projected),
      )
      // 结论存在
      expect(s.samplingConclusion.value).not.toBeNull()
      expect(typeof s.samplingConclusion.value!.accepted).toBe('boolean')
    })

    it('样本错报全为 0 → 推断错报为 0', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.confidenceLevel = 0.95
      s.samplingInterval.value = '10000'
      s.coverageStats.value = {
        populationCount: 100, populationAmount: '1000000',
        sampleCount: 1, sampleAmount: '5000',
        countCoverageRate: '1.00', amountCoverageRate: '0.50',
      }
      s.sampledVouchers.value = [makeVoucher({ voucherNo: 'V1', debitAmount: '5000', actualMisstatement: '0' })]
      const { result } = s.inferMisstatement()
      expect(Number(result.projected)).toBe(0)
    })

    it('无可容忍错报 → 结论为 null（仍产出推断结果）', () => {
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'random' }))
      s.coverageStats.value = {
        populationCount: 10, populationAmount: '100000',
        sampleCount: 1, sampleAmount: '5000',
        countCoverageRate: '10.00', amountCoverageRate: '5.00',
      }
      s.sampledVouchers.value = [makeVoucher({ voucherNo: 'V1', debitAmount: '5000', actualMisstatement: '100' })]
      const { conclusion } = s.inferMisstatement()
      expect(conclusion).toBeNull()
      expect(s.misstatementResult.value).not.toBeNull()
    })
  })

  // ─── R22 重抽治理 ─────────────────────────────────────────────────────
  describe('resample (R22)', () => {
    it('空原因 → 拒绝重抽，不设置 resampleReason', async () => {
      const s = useVoucherSampling(makeOptions())
      const ok = await s.resample('   ')
      expect(ok).toBe(false)
      expect(s.config.value.resampleReason).toBeUndefined()
      expect(mockHttp.post).not.toHaveBeenCalled()
    })

    it('有原因 → 记录原因、重置种子并触发重抽', async () => {
      mockHttp.post.mockResolvedValueOnce({ data: { items: [] } })
      const s = useVoucherSampling(makeOptions())
      const ok = await s.resample('系统抽样代表性不足，扩大样本重抽')
      expect(ok).toBe(true)
      expect(s.config.value.resampleReason).toBe('系统抽样代表性不足，扩大样本重抽')
      expect(s.config.value.randomSeed).toBeNull()
      expect(mockHttp.post).toHaveBeenCalled()
    })
  })

  // ─── R22.2 / R17 / R18 历史回显兜底 ───────────────────────────────────
  describe('loadHistory 方法学字段回显 (R22/R17/R18)', () => {
    it('从 extraction_criteria 兜底解析 seed/间隔/重抽原因/结论', async () => {
      mockHttp.get.mockResolvedValueOnce({
        data: {
          items: [
            {
              id: 'log-1', created_at: '2025-06-01T00:00:00Z', user_id: 'u1',
              filled_count: 5, fill_mode: 'append',
              extraction_criteria: {
                sampling_method: 'mus', phase: 'preliminary',
                random_seed: 12345, sampling_interval: '10000.00',
                resample_reason: '重抽原因X', conclusion: '总体可接受：错报上限未超过可容忍错报',
              },
            },
          ],
        },
      })
      const s = useVoucherSampling(makeOptions())
      await s.loadHistory()
      const h = s.historyList.value[0]
      expect(h.randomSeed).toBe(12345)
      expect(h.samplingInterval).toBe('10000.00')
      expect(h.resampleReason).toBe('重抽原因X')
      expect(h.conclusion).toContain('总体可接受')
    })

    it('后端未就绪缺字段 → 兜底为 null 不报错', async () => {
      mockHttp.get.mockResolvedValueOnce({
        data: { items: [{ id: 'log-2', created_at: '', user_id: 'u1', filled_count: 3, extraction_criteria: {} }] },
      })
      const s = useVoucherSampling(makeOptions())
      await s.loadHistory()
      const h = s.historyList.value[0]
      expect(h.randomSeed).toBeNull()
      expect(h.samplingInterval).toBeNull()
      expect(h.resampleReason).toBeNull()
      expect(h.conclusion).toBeNull()
    })
  })

  // ─── cutoff-fill 载荷方法学字段扩展 ───────────────────────────────────
  describe('confirmFill 方法学字段扩展 + 版本快照兜底', () => {
    it('extraction_criteria 携带 confidence/tolerable/interval/resample 等字段', async () => {
      mockHttp.post.mockResolvedValue({ data: {} })
      const s = useVoucherSampling(makeOptions({ defaultMethod: 'mus' }))
      s.config.value.confidenceLevel = 0.95
      s.config.value.tolerableMisstatement = '100000'
      s.config.value.expectedMisstatement = '2000'
      s.config.value.suggestedSampleSize = 30
      s.config.value.resampleReason = '重抽A'
      s.samplingInterval.value = '10000.00'
      s.sampledVouchers.value = [makeVoucher({ voucherNo: 'V1', selected: true })]

      // 无 Pinia 环境下版本快照会静默失败，不应阻断回填
      const result = await s.confirmFill()
      expect(result.length).toBeGreaterThan(0)

      // 找到 cutoff-fill 调用
      const cutoffCall = mockHttp.post.mock.calls.find(c => String(c[0]).includes('/sampling/cutoff-fill'))
      expect(cutoffCall).toBeDefined()
      const criteria = (cutoffCall![1] as any).extraction_criteria
      expect(criteria.confidence_level).toBe(0.95)
      expect(criteria.tolerable_misstatement).toBe('100000')
      expect(criteria.expected_misstatement).toBe('2000')
      expect(criteria.suggested_sample_size).toBe(30)
      expect(criteria.sampling_interval).toBe('10000.00')
      expect(criteria.resample_reason).toBe('重抽A')
    })
  })
})
