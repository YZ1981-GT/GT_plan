/**
 * 抽样评价持久化 / 回读 / 推断错报推送 A13 守卫
 *
 * Spec: .kiro/specs/sampling-compliance-closure/
 * Validates: Requirements 1.2, 2.7, 2.8, 2.9, 3.5, 3.6, 3.7
 * Properties: Property 5, Property 7, Property 8
 *
 * 背景：CAS 1314 的评价输出此前只存在于组件裸 ref，抽凭 dialog 一律 destroy-on-close
 * → 关弹窗即丢；且推断错报从不进入错报汇总（A13 桥把类型硬编码 factual）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
// 🔴 哨兵必须是具体文件不能是目录 —— `audit-platform/backend/app/...` 是历史遗留空目录，
//    用目录当哨兵会在 `audit-platform` 层提前停下。
const SENTINELS = [
  join('backend', 'app', 'services', 'sampling_registry_service.py'),
  join('backend', 'tests', 'test_sampling_registry_service.py'),
]
function findRepoRoot(from: string): string {
  let cur = resolve(from)
  for (let i = 0; i < 12; i++) {
    if (SENTINELS.every((s) => existsSync(join(cur, s)))) return cur
    const parent = dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error(`未能定位仓库根（从 ${from}）`)
}
const REPO_ROOT = findRepoRoot(__dirname)

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const emitted: Array<{ type: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (type: string, payload: any) => emitted.push({ type, payload }),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import http from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useVoucherSampling,
  type VoucherSamplingOptions,
} from '../composables/useVoucherSampling'
import type { SampledVoucher, Phase } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as {
  post: ReturnType<typeof vi.fn>
  get: ReturnType<typeof vi.fn>
}
const mockMsg = ElMessage as unknown as Record<string, ReturnType<typeof vi.fn>>
const mockBox = ElMessageBox as unknown as { confirm: ReturnType<typeof vi.fn> }

function makeOptions(overrides?: Partial<VoucherSamplingOptions>): VoucherSamplingOptions {
  return {
    projectId: ref('proj-001'),
    year: ref(2025),
    workpaperId: ref('wp-001'),
    accountCode: '1122',
    phase: ref<Phase>('preliminary'),
    defaultMethod: 'random',
    wpCode: 'D2',
    ...overrides,
  }
}

function makeVoucher(partial: Partial<SampledVoucher> = {}): SampledVoucher {
  return {
    voucherNo: 'V-001',
    voucherDate: '2025-06-01',
    summary: '摘要',
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

/**
 * 一个已完成推断且结论已确认的引擎实例。
 *
 * 🔴 必须设置 coverageStats.populationAmount —— `inferMisstatement` 的经典比率法
 * 以总体金额为外推分母，缺省 '0' 会让 projected 恒为 0，测试就成了空转。
 */
function makeEvaluatedEngine(overrides?: Partial<VoucherSamplingOptions>) {
  const s = useVoucherSampling(makeOptions(overrides))
  s.sampledVouchers.value = [
    makeVoucher({ voucherNo: 'V-001', checkResult: 'Y', actualMisstatement: '300' }),
    makeVoucher({ voucherNo: 'V-002', checkResult: 'Y', actualMisstatement: '0' }),
  ]
  s.coverageStats.value = {
    populationCount: 100,
    populationAmount: '1000000.00',
    sampleCount: 2,
    sampleAmount: '2000.00',
    countCoverageRate: '2.00',
    amountCoverageRate: '0.20',
  }
  s.config.value.tolerableMisstatement = '500000'
  s.config.value.confidenceLevel = 0.95
  s.seedUsed.value = 424242
  s.inferMisstatement()
  s.confirmConclusion()
  return s
}

beforeEach(() => {
  vi.clearAllMocks()
  emitted.length = 0
  mockHttp.post.mockResolvedValue({ data: { success: true, log_id: 'log-1', batch_id: 'batch-1', evaluation: {} } })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 5：新抽样清空回读评价
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 5 — 新抽样清空上一批次评价', () => {
  it('triggerSampling 成功后 misstatementResult/结论/来源批次/确认状态全部归零', async () => {
    const s = makeEvaluatedEngine()
    // 前置：确实有评价与确认状态，否则下面的断言空转
    expect(s.misstatementResult.value).not.toBeNull()
    expect(s.conclusionConfirmed.value).toBe(true)
    s.loadedFromBatch.value = { logId: 'log-old', batchId: 'batch-old', evaluatedAt: '2026-08-01T00:00:00Z' }

    mockHttp.post.mockResolvedValueOnce({
      data: {
        items: [{ voucher_no: 'V-100', voucher_date: '2025-07-01', debit_amount: '5000' }],
        stats: { population_count: 10, population_amount: '50000', dataset_id: 'ds-1' },
        seed_used: 999,
      },
    })
    await s.triggerSampling()

    expect(s.misstatementResult.value).toBeNull()
    expect(s.samplingConclusion.value).toBeNull()
    expect(s.loadedFromBatch.value).toBeNull()
    // 结论清空触发 watch → 人工确认同时失效（结论与样本不匹配是比无结论更坏的状态）
    await nextTick()
    expect(s.conclusionConfirmed.value).toBe(false)
  })

  it('R1.2：extract 未返回 dataset_id 时提示未绑定抽样框版本且不阻断', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce({
      data: {
        items: [{ voucher_no: 'V-1', debit_amount: '1' }],
        stats: { population_count: 1, population_amount: '1' }, // 无 dataset_id
        seed_used: 1,
      },
    })
    await s.triggerSampling()
    expect(s.datasetId.value).toBeNull()
    expect(mockMsg.info).toHaveBeenCalled()
    expect(s.sampledVouchers.value.length).toBe(1) // 未阻断
  })

  it('extract 返回 dataset_id 时记录且不提示', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce({
      data: {
        items: [{ voucher_no: 'V-1', debit_amount: '1' }],
        stats: { population_count: 1, population_amount: '1', dataset_id: 'ds-abc' },
        seed_used: 1,
      },
    })
    await s.triggerSampling()
    expect(s.datasetId.value).toBe('ds-abc')
    expect(mockMsg.info).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// R2：评价载荷 / 持久化 / 回读
// ═══════════════════════════════════════════════════════════════════════════

describe('R2 — 评价载荷与持久化', () => {
  it('未推断时 buildEvaluationPayload 返回 null（「没算」≠「算出来是 0」）', () => {
    const s = useVoucherSampling(makeOptions())
    expect(s.buildEvaluationPayload()).toBeNull()
  })

  it('载荷承载 R2.3 全部字段', () => {
    const s = makeEvaluatedEngine()
    const p = s.buildEvaluationPayload()!
    for (const key of [
      'projected', 'known_high_value', 'basic_precision', 'incremental_allowance',
      'upper_limit', 'tolerable_misstatement', 'checked_sample_count',
      'unchecked_sample_count', 'deviation_count', 'conclusion_code',
      'conclusion_message', 'conclusion_confirmed', 'algo_version',
    ]) {
      expect(p).toHaveProperty(key)
    }
  })

  it('偏差笔数只数「已检查且实际错报 > 0」的样本', () => {
    const s = useVoucherSampling(makeOptions())
    s.sampledVouchers.value = [
      makeVoucher({ checkResult: 'Y', actualMisstatement: '100' }),  // 计
      makeVoucher({ checkResult: 'Y', actualMisstatement: '0' }),    // 不计（无错报）
      makeVoucher({ checkResult: '', actualMisstatement: '500' }),   // 不计（未检查）
    ]
    expect(s.countDeviations()).toBe(1)
  })

  it('persistEvaluation 未推断时不发请求', async () => {
    const s = useVoucherSampling(makeOptions())
    const ok = await s.persistEvaluation()
    expect(ok).toBe(false)
    expect(mockHttp.post).not.toHaveBeenCalled()
  })

  it('persistEvaluation 打到 voucher-evaluation 端点并回填来源批次', async () => {
    const s = makeEvaluatedEngine()
    mockHttp.post.mockResolvedValueOnce({
      data: { success: true, log_id: 'log-9', batch_id: 'batch-9', evaluation: { evaluated_at: '2026-08-04T12:00:00Z' } },
    })
    const ok = await s.persistEvaluation()
    expect(ok).toBe(true)
    const [url, body] = mockHttp.post.mock.calls.at(-1)!
    expect(String(url)).toContain('/sampling/voucher-evaluation')
    expect(body.workpaper_id).toBe('wp-001')
    expect(body.evaluation).toHaveProperty('projected')
    expect(s.loadedFromBatch.value).toEqual({
      logId: 'log-9', batchId: 'batch-9', evaluatedAt: '2026-08-04T12:00:00Z',
    })
  })

  it('保存失败必须明示，禁静默吞（平台已有 catch{} 吞 422 的踩坑）', async () => {
    const s = makeEvaluatedEngine()
    mockHttp.post.mockRejectedValueOnce({ response: { status: 500 } })
    const ok = await s.persistEvaluation()
    expect(ok).toBe(false)
    expect(mockMsg.error).toHaveBeenCalled()
  })

  it('404（尚无批次）降级为信息提示而非报错', async () => {
    const s = makeEvaluatedEngine()
    mockHttp.post.mockRejectedValueOnce({ response: { status: 404 } })
    await s.persistEvaluation()
    expect(mockMsg.info).toHaveBeenCalled()
    expect(mockMsg.error).not.toHaveBeenCalled()
  })
})

describe('R2.7 — 回读既有批次评价', () => {
  const historyPayload = [
    {
      id: 'log-5',
      batch_id: 'batch-5',
      is_undone: false,
      evaluation: {
        projected: '1234.56',
        known_high_value: '200.00',
        basic_precision: '900.00',
        incremental_allowance: '100.00',
        upper_limit: '2334.56',
        conclusion_code: 'acceptable',
        conclusion_message: '总体可接受',
        conclusion_confirmed: true,
        a13_pushed_at: '2026-08-03T10:00:00Z',
        evaluated_at: '2026-08-03T09:00:00Z',
      },
    },
  ]

  it('还原推断结果 / 结论 / 确认状态 / 已推送标记 / 来源批次', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.get.mockResolvedValueOnce({ data: historyPayload })
    const ok = await s.loadLatestEvaluation()
    expect(ok).toBe(true)
    expect(s.misstatementResult.value?.projected).toBe('1234.56')
    expect(s.misstatementResult.value?.upperLimit).toBe('2334.56')
    expect(s.samplingConclusion.value).toEqual({ accepted: true, message: '总体可接受' })
    expect(s.a13PushedAt.value).toBe('2026-08-03T10:00:00Z')
    expect(s.loadedFromBatch.value?.logId).toBe('log-5')
  })

  it('🔴 回读的人工确认状态不得被「结论变化⇒确认失效」watch 打回 false', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.get.mockResolvedValueOnce({ data: historyPayload })
    await s.loadLatestEvaluation()
    await nextTick()
    expect(s.conclusionConfirmed.value).toBe(true)
  })

  it('已有当前批次样本时不回读（不覆盖正在做的批次）', async () => {
    const s = useVoucherSampling(makeOptions())
    s.sampledVouchers.value = [makeVoucher()]
    const ok = await s.loadLatestEvaluation()
    expect(ok).toBe(false)
    expect(mockHttp.get).not.toHaveBeenCalled()
  })

  it('已撤销批次与无评价批次都跳过', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.get.mockResolvedValueOnce({
      data: [
        { id: 'log-a', is_undone: true, evaluation: { projected: '9' } },
        { id: 'log-b', is_undone: false, evaluation: null },
      ],
    })
    expect(await s.loadLatestEvaluation()).toBe(false)
    expect(s.misstatementResult.value).toBeNull()
  })

  it('回读失败静默降级，绝不把失败当「无评价」写回库', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.get.mockRejectedValueOnce(new Error('network'))
    expect(await s.loadLatestEvaluation()).toBe(false)
    expect(mockMsg.error).not.toHaveBeenCalled()
    expect(mockHttp.post).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 7 / 8：推断错报推送 A13
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 8 — 门控：未确认结论 / 推断错报为 0 不得推送', () => {
  it('未推断 → 不推送', async () => {
    const s = useVoucherSampling(makeOptions())
    expect(await s.pushProjectedToA13()).toBe(false)
    expect(emitted.length).toBe(0)
  })

  it('已推断但结论未确认 → 不推送', async () => {
    const s = makeEvaluatedEngine()
    s.conclusionConfirmed.value = false
    expect(await s.pushProjectedToA13()).toBe(false)
    expect(emitted.length).toBe(0)
    expect(mockMsg.warning).toHaveBeenCalled()
  })

  it('推断错报为 0 → 不推送', async () => {
    const s = useVoucherSampling(makeOptions())
    s.sampledVouchers.value = [makeVoucher({ checkResult: 'Y', actualMisstatement: '0' })]
    s.config.value.tolerableMisstatement = '500000'
    s.inferMisstatement()
    s.confirmConclusion()
    expect(Number(s.misstatementResult.value!.projected)).toBe(0)
    expect(await s.pushProjectedToA13()).toBe(false)
    expect(emitted.length).toBe(0)
  })
})

describe('Property 7 — 推送草稿的金额、类型与描述标识', () => {
  it('恰 1 条事件，类型 projected，金额 = projected', async () => {
    const s = makeEvaluatedEngine()
    const projected = s.misstatementResult.value!.projected
    expect(Number(projected)).toBeGreaterThan(0)

    const ok = await s.pushProjectedToA13()
    expect(ok).toBe(true)
    expect(emitted.length).toBe(1)
    expect(emitted[0].type).toBe('a13:push-misstatement')
    expect(emitted[0].payload.misstatementType).toBe('projected')
    expect(emitted[0].payload.amount).toBe(Number(projected))
  })

  it('描述含方法 / 样本量 / 随机种子 / 批次 四项标识', async () => {
    const s = makeEvaluatedEngine()
    s.loadedFromBatch.value = { logId: 'log-1', batchId: 'batch-abc', evaluatedAt: null }
    await s.pushProjectedToA13()
    const desc = String(emitted[0].payload.description)
    expect(desc).toContain('random')          // 抽样方法
    expect(desc).toContain('样本量:2')
    expect(desc).toContain('随机种子:424242')
    expect(desc).toContain('批次:batch-abc')
  })

  it('高值层已知错报 > 0 时描述追加「应按事实错报单独记入」提示', async () => {
    const s = makeEvaluatedEngine()
    // 构造高值层已知错报
    s.misstatementResult.value = {
      projected: '1000.00',
      knownHighValue: '888.00',
      basicPrecision: '0.00',
      incrementalAllowance: '0.00',
      upperLimit: '1000.00',
    }
    await s.pushProjectedToA13()
    const desc = String(emitted[0].payload.description)
    expect(desc).toContain('888.00')
    expect(desc).toContain('事实错报单独记入')
  })

  it('金额不并入高值层已知错报（否则与逐笔 factual 推送重复计入）', async () => {
    const s = makeEvaluatedEngine()
    s.misstatementResult.value = {
      projected: '1000.00',
      knownHighValue: '888.00',
      basicPrecision: '0.00',
      incremental_allowance: '0.00',
      incrementalAllowance: '0.00',
      upperLimit: '1000.00',
    } as any
    await s.pushProjectedToA13()
    expect(emitted[0].payload.amount).toBe(1000)
    expect(emitted[0].payload.amount).not.toBe(1888)
  })

  it('wpCode 透传供 source_wp_code 溯源', async () => {
    const s = makeEvaluatedEngine()
    await s.pushProjectedToA13()
    expect(emitted[0].payload.wpCode).toBe('D2')
  })

  it('宿主未传 wpCode 时留空（不用科目码冒充底稿编码）', async () => {
    const s = makeEvaluatedEngine({ wpCode: undefined })
    await s.pushProjectedToA13()
    expect(emitted.length).toBe(1)
    expect(emitted[0].payload.wpCode).toBe('')
    expect(emitted[0].payload.wpCode).not.toBe('1122')
  })
})

describe('R3.7/3.8 — 重复推送确认与已推送标记', () => {
  it('推送成功后写回 a13_pushed_at 并随评价落库', async () => {
    const s = makeEvaluatedEngine()
    await s.pushProjectedToA13()
    expect(s.a13PushedAt.value).not.toBeNull()
    const [, body] = mockHttp.post.mock.calls.at(-1)!
    expect(body.evaluation.a13_pushed_at).toBe(s.a13PushedAt.value)
  })

  it('持久化失败时回滚内存标记以便重试（否则重试被自己的标记挡住）', async () => {
    const s = makeEvaluatedEngine()
    mockHttp.post.mockRejectedValueOnce({ response: { status: 500 } })
    await s.pushProjectedToA13()
    expect(s.a13PushedAt.value).toBeNull()
  })

  it('已推送过 → 二次确认；取消则不再推送', async () => {
    const s = makeEvaluatedEngine()
    s.a13PushedAt.value = '2026-08-03T10:00:00Z'
    mockBox.confirm.mockRejectedValueOnce(new Error('cancel'))
    expect(await s.pushProjectedToA13()).toBe(false)
    expect(mockBox.confirm).toHaveBeenCalled()
    expect(emitted.length).toBe(0)
  })

  it('已推送过 → 二次确认通过则推送', async () => {
    const s = makeEvaluatedEngine()
    s.a13PushedAt.value = '2026-08-03T10:00:00Z'
    mockBox.confirm.mockResolvedValueOnce('confirm')
    expect(await s.pushProjectedToA13()).toBe(true)
    expect(emitted.length).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// R1.3 / R2.5：回填留痕携带 dataset_id 与 evaluation
// ═══════════════════════════════════════════════════════════════════════════

describe('R1.3 / R2.5 — confirmFill 留痕', () => {
  it('criteria 携带 dataset_id 与 evaluation', async () => {
    const s = makeEvaluatedEngine()
    s.datasetId.value = 'ds-777'
    await s.confirmFill([])
    const fillCall = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )
    expect(fillCall).toBeTruthy()
    const criteria = fillCall![1].extraction_criteria
    expect(criteria.dataset_id).toBe('ds-777')
    expect(criteria.evaluation).toHaveProperty('projected')
  })

  it('未推断时 evaluation 为 null（不伪造全 0 评价）', async () => {
    const s = useVoucherSampling(makeOptions())
    s.sampledVouchers.value = [makeVoucher()]
    await s.confirmFill([])
    const fillCall = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )
    expect(fillCall![1].extraction_criteria.evaluation).toBeNull()
  })

  // ── R5.1：coverage_stats 必须带总体/样本金额 ──────────────────────────────
  // 后端 `sampling_registry_service.build_record_fields` 从
  // `coverage_stats.population_amount` 投影 `sampling_records.population_total_amount`
  // （CAS 1314 的「总体金额」记录项）。改造前只发 count_rate/amount_rate →
  // 该列在生产里恒为 NULL，而后端单测的 fixture 自带 population_amount 故全绿
  // ＝典型「fixture 与真实载荷分叉」的假绿。这两条断言把写入侧钉死。
  it('criteria.coverage_stats 携带 population_amount / sample_amount', async () => {
    const s = makeEvaluatedEngine()
    await s.confirmFill([])
    const fillCall = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )
    const cs = fillCall![1].extraction_criteria.coverage_stats
    expect(cs).toBeTruthy()
    // 反向自检：改造前的键集只有这两项，若退回旧形态本断言必红
    expect(Object.keys(cs)).toEqual(
      expect.arrayContaining(['count_rate', 'amount_rate', 'population_amount', 'sample_amount']),
    )
    expect(cs.population_amount).toBe('1000000.00')
    expect(cs.sample_amount).toBe('2000.00')
  })

  it('历史回读的 coverage_stats 金额与写入侧同键（写一个键读另一个键=丢数据）', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.get.mockResolvedValue({
      data: [
        {
          id: 'log-1',
          created_at: '2026-08-04T10:00:00Z',
          user_id: 'u-1',
          total_matched: 100,
          filled_count: 2,
          extraction_criteria: {
            coverage_stats: {
              count_rate: '2.00',
              amount_rate: '0.20',
              population_amount: '1000000.00',
              sample_amount: '2000.00',
            },
          },
        },
        // 既有记录（无这两个 key）→ 降级 '0'，不报错
        { id: 'log-0', created_at: '2026-08-01T10:00:00Z', user_id: 'u-1', extraction_criteria: {} },
      ],
    })
    await s.loadHistory()
    expect(s.historyList.value[0].coverageStats.populationAmount).toBe('1000000.00')
    expect(s.historyList.value[0].coverageStats.sampleAmount).toBe('2000.00')
    expect(s.historyList.value[1].coverageStats.populationAmount).toBe('0')
  })

  it('后端投影读的正是 coverage_stats.population_amount（跨文件锁死）', () => {
    const py = readFileSync(
      join(REPO_ROOT, 'backend/app/services/sampling_registry_service.py'),
      'utf-8',
    )
    // 取 build_record_fields 函数体（禁固定字符窗口截取）
    const start = py.indexOf('def build_record_fields(')
    expect(start).toBeGreaterThan(0)
    const rest = py.slice(start + 1)
    const nextDef = rest.search(/^(?:async\s+)?def\s|^class\s/m)
    const body = nextDef > 0 ? rest.slice(0, nextDef) : rest
    expect(body).toContain('coverage_stats')
    expect(body).toContain('population_amount')
  })
})
