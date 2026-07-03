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
 * - fill mode 逻辑：含阶段约束（applyFillMode 纯函数）
 */
import { describe, it, expect, vi } from 'vitest'
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

import {
  useVoucherSampling,
  applyFillMode,
  type VoucherSamplingOptions,
} from '../composables/useVoucherSampling'
import type { SampledVoucher, Phase } from '../composables/useSamplingAlgorithms'

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
// 5. applyFillMode 纯函数（含阶段约束）
// ═══════════════════════════════════════════════════════════════════════════════

describe('applyFillMode - 填充策略含阶段约束', () => {
  const preliminaryRows: SampledVoucher[] = [
    makeVoucher({ voucherNo: 'P-001', phase: 'preliminary' }),
    makeVoucher({ voucherNo: 'P-002', phase: 'preliminary' }),
  ]

  const finalRows: SampledVoucher[] = [
    makeVoucher({ voucherNo: 'F-001', phase: 'final' }),
  ]

  const existing = [...preliminaryRows, ...finalRows]

  const newSelected: SampledVoucher[] = [
    makeVoucher({ voucherNo: 'N-001', phase: 'final' }),
    makeVoucher({ voucherNo: 'N-002', phase: 'final' }),
  ]

  describe('append 模式', () => {
    it('追加到末尾，保留所有 existing', () => {
      const result = applyFillMode(existing, newSelected, 'append', 'final')
      expect(result).toHaveLength(5) // 2 preliminary + 1 final + 2 new
      expect(result[0].voucherNo).toBe('P-001')
      expect(result[3].voucherNo).toBe('N-001')
    })

    it('年审 append 不影响预审行', () => {
      const result = applyFillMode(existing, newSelected, 'append', 'final')
      const prelimRows = result.filter(v => v.phase === 'preliminary')
      expect(prelimRows).toHaveLength(2)
      expect(prelimRows[0].voucherNo).toBe('P-001')
      expect(prelimRows[1].voucherNo).toBe('P-002')
    })
  })

  describe('replace 模式', () => {
    it('仅清除当前 phase 行，保留其他 phase', () => {
      const result = applyFillMode(existing, newSelected, 'replace', 'final')
      // preliminary 2 行保留 + new final 2 行（旧 final 1 行被替换）
      expect(result).toHaveLength(4)
      const prelimRows = result.filter(v => v.phase === 'preliminary')
      expect(prelimRows).toHaveLength(2)
    })

    it('replace 时预审行完整保留', () => {
      const result = applyFillMode(existing, newSelected, 'replace', 'final')
      const prelimRows = result.filter(v => v.phase === 'preliminary')
      expect(prelimRows[0].voucherNo).toBe('P-001')
      expect(prelimRows[1].voucherNo).toBe('P-002')
    })

    it('replace 当前 phase 行变为 selected', () => {
      const result = applyFillMode(existing, newSelected, 'replace', 'final')
      const finalResult = result.filter(v => v.phase === 'final')
      expect(finalResult).toHaveLength(2)
      expect(finalResult[0].voucherNo).toBe('N-001')
      expect(finalResult[1].voucherNo).toBe('N-002')
    })
  })

  describe('merge 模式', () => {
    it('按 voucher_no 去重，仅添加新凭证', () => {
      const existingWithFinal = [
        ...preliminaryRows,
        makeVoucher({ voucherNo: 'N-001', phase: 'final' }), // 与 selected 重复
      ]
      const result = applyFillMode(existingWithFinal, newSelected, 'merge', 'final')
      // P-001, P-002, N-001（existing）, N-002（新增）
      expect(result).toHaveLength(4)
      const nos = result.map(v => v.voucherNo)
      expect(nos.filter(n => n === 'N-001')).toHaveLength(1) // 不重复
    })

    it('merge 无重复时等同 append', () => {
      const result = applyFillMode(existing, newSelected, 'merge', 'final')
      expect(result).toHaveLength(5) // no overlap
    })

    it('merge 保留预审行不动', () => {
      const result = applyFillMode(existing, newSelected, 'merge', 'final')
      const prelimRows = result.filter(v => v.phase === 'preliminary')
      expect(prelimRows).toHaveLength(2)
    })
  })

  describe('阶段约束', () => {
    it('预审阶段 replace 仅清预审行，保留年审行', () => {
      const newPrelim: SampledVoucher[] = [
        makeVoucher({ voucherNo: 'NP-001', phase: 'preliminary' }),
      ]
      const result = applyFillMode(existing, newPrelim, 'replace', 'preliminary')
      // 年审 F-001 保留 + new preliminary 1 行
      expect(result).toHaveLength(2)
      const finalResult = result.filter(v => v.phase === 'final')
      expect(finalResult).toHaveLength(1)
      expect(finalResult[0].voucherNo).toBe('F-001')
    })

    it('空 existing + append → 结果等于 selected', () => {
      const result = applyFillMode([], newSelected, 'append', 'final')
      expect(result).toHaveLength(2)
      expect(result[0].voucherNo).toBe('N-001')
    })

    it('空 selected + replace → 当前 phase 被清空', () => {
      const result = applyFillMode(existing, [], 'replace', 'final')
      // preliminary 2 行保留，final 0 行
      expect(result).toHaveLength(2)
      expect(result.every(v => v.phase === 'preliminary')).toBe(true)
    })
  })
})
