/**
 * useD2VcMethodology — D2-7 方法学参数管理 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 2.1
 *
 * 职责：
 * - 方法学参数管理（测试总体/特定样本/抽样总体/抽样方法/抽样程序）
 * - B15/B50 联动（可容忍错报 + 科目1122风险等级）
 * - 样本量推荐（MUS / 随机）
 * - 特定样本 AI 筛选（markSpecificSamples 纯函数）
 * - 抽样总体计算（computeSamplingPopulation 纯函数）
 * - 样本量偏离指示器（computeSampleSizeDeviation 纯函数）
 * - AI 推荐抽样方法（recommendSamplingMethod 纯函数）
 * - AI 生成测试总体描述
 * - 持久化到 D2-vc-methodology item_id
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 11.1, 11.2, 11.3, 11.4, 11.5
 */
import { ref, computed, watch, inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { D2_SAVE_ITEMS_KEY } from './d2InjectionKeys'
import {
  reliabilityFactor,
  computeMusInterval,
  computeSampleSize,
  CAS1314_RELIABILITY_TABLE,
} from './useSamplingAlgorithms'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PopulationDesc {
  amount: number    // 金额合计
  count: number     // 笔数
  description: string // 文字描述
}

export interface SpecificSampleItem {
  id: string
  customerName: string
  amount: number
  reason: string         // 标记原因
  confirmed: boolean     // 用户确认
}

export interface MethodologyState {
  testPopulation: Ref<PopulationDesc>       // 测试总体
  specificSamples: Ref<SpecificSampleItem[]> // 特定样本
  samplingPopulation: Ref<PopulationDesc>   // 抽样总体（自动计算）
  samplingMethod: Ref<string>               // 抽样方法
  samplingProcedure: Ref<string>            // 抽样程序
  recommendedMethod: Ref<string | null>     // AI 推荐方法
  recommendedSampleSize: Ref<number>        // AI 推荐样本量
  recommendedReason: Ref<string>            // 推荐理由
  userSampleSize: Ref<number>              // 用户设定样本量
  sampleSizeDeviation: Ref<'below' | 'ok' | null>
}

export type RiskLevel = '高' | '中' | '低'

/** 交易数据项（用于特定样本标记） */
export interface TransactionItem {
  id: string
  customerName: string
  amount: number
  isRelatedParty?: boolean
  transactionDate?: string
}

export interface UseD2VcMethodologyOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const METHODOLOGY_KEY = 'D2-vc-methodology'

/** CAS 1314 风险等级 → 置信度映射 */
const RISK_CONFIDENCE_MAP: Record<RiskLevel, number> = {
  '高': 0.95,
  '中': 0.90,
  '低': 0.80,
}

/** CAS 1314 风险等级 → 可靠性系数（E/T=0） */
const RISK_RELIABILITY_MAP: Record<RiskLevel, number> = {
  '高': 3.00,
  '中': 2.31,
  '低': 1.61,
}

/** 随机抽样查表：(置信度, 总体规模区间) → 样本量比例 */
const RANDOM_SAMPLE_TABLE: { confidence: number; thresholds: { maxPop: number; size: number }[] }[] = [
  {
    confidence: 0.95,
    thresholds: [
      { maxPop: 50, size: 44 },
      { maxPop: 100, size: 80 },
      { maxPop: 250, size: 152 },
      { maxPop: 500, size: 217 },
      { maxPop: 1000, size: 278 },
      { maxPop: 5000, size: 357 },
      { maxPop: 10000, size: 370 },
      { maxPop: Infinity, size: 384 },
    ],
  },
  {
    confidence: 0.90,
    thresholds: [
      { maxPop: 50, size: 38 },
      { maxPop: 100, size: 63 },
      { maxPop: 250, size: 102 },
      { maxPop: 500, size: 132 },
      { maxPop: 1000, size: 154 },
      { maxPop: 5000, size: 178 },
      { maxPop: 10000, size: 183 },
      { maxPop: Infinity, size: 186 },
    ],
  },
  {
    confidence: 0.80,
    thresholds: [
      { maxPop: 50, size: 29 },
      { maxPop: 100, size: 43 },
      { maxPop: 250, size: 60 },
      { maxPop: 500, size: 70 },
      { maxPop: 1000, size: 77 },
      { maxPop: 5000, size: 83 },
      { maxPop: 10000, size: 84 },
      { maxPop: Infinity, size: 85 },
    ],
  },
]

// ─── Pure Functions (exported for PBT) ───────────────────────────────────────

/**
 * MUS 样本量计算
 *
 * interval = tolerableMisstatement / reliabilityFactor
 * sampleSize = ceil(populationAmount / interval)
 *
 * @param tolerableMisstatement 可容忍错报
 * @param reliabilityFactor_ CAS 1314 可靠性系数（E/T=0时：高→3.00, 中→2.31, 低→1.61）
 * @param populationAmount 总体金额
 * @returns 推荐样本量（非负整数）
 */
export function computeMusSampleSize(
  tolerableMisstatement: number,
  reliabilityFactor_: number,
  populationAmount: number
): number {
  if (tolerableMisstatement <= 0 || reliabilityFactor_ <= 0 || populationAmount <= 0) return 0
  const interval = tolerableMisstatement / reliabilityFactor_
  if (interval <= 0) return 0
  return Math.ceil(populationAmount / interval)
}

/**
 * 随机抽样样本量计算
 *
 * 基于总体规模和置信水平查表确定样本量。
 * 置信度取最近邻匹配（0.80 / 0.90 / 0.95）。
 * 样本量不超过总体规模。
 *
 * @param populationSize 总体规模（笔数）
 * @param confidenceLevel 置信度（0.80 / 0.90 / 0.95）
 * @param _expectedErrorRate 预期错报率（保留参数，当前查表法不直接使用）
 * @returns 推荐样本量
 */
export function computeRandomSampleSize(
  populationSize: number,
  confidenceLevel: number,
  _expectedErrorRate = 0
): number {
  if (populationSize <= 0) return 0

  // 找最近邻的置信度表
  let bestTable = RANDOM_SAMPLE_TABLE[0]
  let bestDist = Math.abs(bestTable.confidence - confidenceLevel)
  for (const table of RANDOM_SAMPLE_TABLE) {
    const dist = Math.abs(table.confidence - confidenceLevel)
    if (dist < bestDist) {
      bestTable = table
      bestDist = dist
    }
  }

  // 查表：找到第一个 maxPop >= populationSize 的条目
  let sampleSize = bestTable.thresholds[bestTable.thresholds.length - 1].size
  for (const entry of bestTable.thresholds) {
    if (populationSize <= entry.maxPop) {
      sampleSize = entry.size
      break
    }
  }

  // 样本量不超过总体规模
  return Math.min(sampleSize, populationSize)
}

/**
 * 特定样本 AI 筛选（纯函数）
 *
 * 标记规则：
 * - 金额 ≥ 可容忍错报的交易
 * - 关联方交易
 * - 异常日期（非营业日 = 周六/周日，或期末集中 = 12月25日之后）
 *
 * @param transactions 交易列表
 * @param tolerableMisstatement 可容忍错报
 * @returns 被标记为特定样本的项目列表
 */
export function markSpecificSamples(
  transactions: TransactionItem[],
  tolerableMisstatement: number
): SpecificSampleItem[] {
  const results: SpecificSampleItem[] = []

  for (const tx of transactions) {
    const reasons: string[] = []

    // 规则1：金额 ≥ 可容忍错报
    if (tolerableMisstatement > 0 && tx.amount >= tolerableMisstatement) {
      reasons.push('金额≥可容忍错报')
    }

    // 规则2：关联方交易
    if (tx.isRelatedParty) {
      reasons.push('关联方交易')
    }

    // 规则3：异常日期
    if (tx.transactionDate) {
      if (isAbnormalDate(tx.transactionDate)) {
        reasons.push('异常日期')
      }
    }

    if (reasons.length > 0) {
      results.push({
        id: tx.id,
        customerName: tx.customerName,
        amount: tx.amount,
        reason: reasons.join('；'),
        confirmed: false,
      })
    }
  }

  return results
}

/**
 * 判断日期是否为异常日期
 * - 非营业日（周六/周日）
 * - 期末集中（12月25日之后）
 */
export function isAbnormalDate(dateStr: string): boolean {
  if (!dateStr) return false
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return false

  // 非营业日：周六(6) / 周日(0)
  const dayOfWeek = date.getDay()
  if (dayOfWeek === 0 || dayOfWeek === 6) return true

  // 期末集中：12月25日之后
  const month = date.getMonth() // 0-based
  const day = date.getDate()
  if (month === 11 && day >= 25) return true

  return false
}

/**
 * 计算抽样总体 = 测试总体 - 特定样本
 *
 * 金额和笔数同步扣除。
 *
 * @param testPopulation 测试总体
 * @param specificSamples 特定样本列表（仅扣除 confirmed=true 的）
 * @returns 抽样总体
 */
export function computeSamplingPopulation(
  testPopulation: PopulationDesc,
  specificSamples: SpecificSampleItem[]
): PopulationDesc {
  const confirmedSamples = specificSamples.filter(s => s.confirmed)
  const specificAmount = confirmedSamples.reduce((sum, s) => sum + s.amount, 0)
  const specificCount = confirmedSamples.length

  const amount = Math.max(0, testPopulation.amount - specificAmount)
  const count = Math.max(0, testPopulation.count - specificCount)

  return {
    amount,
    count,
    description: `抽样总体金额 ${amount.toLocaleString()} 元，${count} 笔（测试总体扣除特定样本）`,
  }
}

/**
 * 样本量偏离指示器
 *
 * @param userSize 用户设定样本量
 * @param recommendedSize AI 推荐样本量
 * @returns 'below' | 'ok' | null
 */
export function computeSampleSizeDeviation(
  userSize: number,
  recommendedSize: number
): 'below' | 'ok' | null {
  if (recommendedSize <= 0) return null
  if (userSize <= 0) return null
  return userSize < recommendedSize ? 'below' : 'ok'
}

/**
 * AI 推荐抽样方法
 *
 * 基于风险等级和可容忍错报推荐抽样方法：
 * - 高风险 + 可容忍错报较高：MUS（精确度高，覆盖面广）
 * - 高风险 + 可容忍错报较低：特定项目（关注大额/高风险交易）
 * - 中风险：随机抽样（覆盖适中）
 * - 低风险：随机抽样（样本量可适当缩小）
 *
 * @param riskLevel 风险等级
 * @param tolerableMisstatement 可容忍错报
 * @returns { method, reason } 推荐方法和推荐理由
 */
export function recommendSamplingMethod(
  riskLevel: RiskLevel,
  tolerableMisstatement: number
): { method: string; reason: string } {
  if (riskLevel === '高') {
    if (tolerableMisstatement > 0) {
      return {
        method: 'mus',
        reason: `科目风险=高 → 建议MUS（货币单元抽样），间隔=可容忍错报(${tolerableMisstatement.toLocaleString()}元)÷可靠性系数(3.00)，确保高风险科目获得充分审计覆盖`,
      }
    }
    return {
      method: '特定项目',
      reason: '科目风险=高，可容忍错报未设定 → 建议特定项目选取，优先覆盖大额/异常交易',
    }
  }

  if (riskLevel === '中') {
    return {
      method: '随机抽样',
      reason: `科目风险=中 → 建议随机抽样，置信度90%，基于总体规模查表确定样本量`,
    }
  }

  // 低风险
  return {
    method: '随机抽样',
    reason: `科目风险=低 → 建议随机抽样，置信度80%，样本量可适当缩小`,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2VcMethodology(options: UseD2VcMethodologyOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  // Inject save function
  const saveItems = inject(D2_SAVE_ITEMS_KEY, null)

  // ─── State ─────────────────────────────────────────────────────────────

  const testPopulation = ref<PopulationDesc>({ amount: 0, count: 0, description: '' })
  const specificSamples = ref<SpecificSampleItem[]>([])
  const samplingMethod = ref<string>('')
  const samplingProcedure = ref<string>('')
  const recommendedMethod = ref<string | null>(null)
  const recommendedSampleSize = ref<number>(0)
  const recommendedReason = ref<string>('')
  const userSampleSize = ref<number>(0)
  const tolerableMisstatement = ref<number>(0)
  const riskLevel = ref<RiskLevel | null>(null)
  const aiGenerating = ref(false)

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 抽样总体 = 测试总体 - 确认的特定样本 */
  const samplingPopulation = computed<PopulationDesc>(() => {
    return computeSamplingPopulation(testPopulation.value, specificSamples.value)
  })

  /** 样本量偏离指示器 */
  const sampleSizeDeviation = computed<'below' | 'ok' | null>(() => {
    return computeSampleSizeDeviation(userSampleSize.value, recommendedSampleSize.value)
  })

  // ─── B15 Materiality Data ──────────────────────────────────────────────

  /**
   * 从 allResponses 获取 B15 可容忍错报值
   * B15 底稿存储在 allResponses 中，键名包含 B15 相关前缀
   */
  function loadTolerableMisstatementFromB15(): void {
    const responses = allResponses.value

    // 尝试多种 B15 键名模式
    const b15Keys = ['B15-tolerable-misstatement', 'B15-materiality', 'b15-tolerable']
    for (const key of b15Keys) {
      const data = responses.get(key)
      if (data?.remark) {
        try {
          const parsed = JSON.parse(data.remark)
          if (parsed.tolerableMisstatement != null) {
            tolerableMisstatement.value = Number(parsed.tolerableMisstatement) || 0
            return
          }
          if (parsed.tolerable_misstatement != null) {
            tolerableMisstatement.value = Number(parsed.tolerable_misstatement) || 0
            return
          }
        } catch {
          // 可能是纯数字字符串
          const num = Number(data.remark)
          if (num > 0) {
            tolerableMisstatement.value = num
            return
          }
        }
      }
      // 也检查 conclusion 字段
      if (data?.conclusion) {
        const num = Number(data.conclusion)
        if (num > 0) {
          tolerableMisstatement.value = num
          return
        }
      }
    }

    // 尝试从 materiality 相关键获取
    for (const [key, val] of responses) {
      if (key.toLowerCase().includes('b15') && key.toLowerCase().includes('tolerable')) {
        const num = Number(val?.remark || val?.conclusion)
        if (num > 0) {
          tolerableMisstatement.value = num
          return
        }
      }
    }
  }

  // ─── B50 Risk Data ─────────────────────────────────────────────────────

  /**
   * 从 allResponses 获取 B50 科目1122风险等级
   */
  function loadRiskLevelFromB50(): void {
    const responses = allResponses.value

    // 尝试多种 B50 键名模式
    const b50Keys = ['B50-risk-1122', 'B50-account-risk', 'b50-risk']
    for (const key of b50Keys) {
      const data = responses.get(key)
      if (data?.remark) {
        try {
          const parsed = JSON.parse(data.remark)
          // 搜索 1122 科目的风险等级
          if (parsed.riskLevel && ['高', '中', '低'].includes(parsed.riskLevel)) {
            riskLevel.value = parsed.riskLevel as RiskLevel
            return
          }
          if (parsed.accounts?.['1122']?.riskLevel) {
            riskLevel.value = parsed.accounts['1122'].riskLevel as RiskLevel
            return
          }
          // 数组形式
          if (Array.isArray(parsed)) {
            const item = parsed.find((r: any) =>
              r.account_code === '1122' || r.accountCode === '1122'
            )
            if (item?.risk_level && ['高', '中', '低'].includes(item.risk_level)) {
              riskLevel.value = item.risk_level as RiskLevel
              return
            }
          }
        } catch {
          // 纯文本
          if (['高', '中', '低'].includes(data.remark.trim())) {
            riskLevel.value = data.remark.trim() as RiskLevel
            return
          }
        }
      }
    }

    // 扫描所有 B50 相关键
    for (const [key, val] of responses) {
      if (key.toLowerCase().includes('b50') && key.includes('1122')) {
        const text = val?.remark || val?.conclusion || ''
        if (['高', '中', '低'].includes(text.trim())) {
          riskLevel.value = text.trim() as RiskLevel
          return
        }
      }
    }
  }

  // ─── Trial Balance Data ────────────────────────────────────────────────

  /**
   * 从试算表获取科目1122本期借方发生额合计和交易笔数
   */
  async function loadTrialBalanceData(): Promise<void> {
    if (!projectId.value) return
    try {
      // 获取项目审计年度
      let year = new Date().getFullYear() - 1
      try {
        const projRes = await api.get(`/api/projects/${projectId.value}`)
        const proj = projRes?.data ?? projRes
        if (proj?.audit_year) year = Number(proj.audit_year)
      } catch { /* fallback */ }

      const tbRes = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { year },
      })
      const tbData = Array.isArray(tbRes?.data) ? tbRes.data : (Array.isArray(tbRes) ? tbRes : [])
      const tbRow = tbData.find((r: any) => r.standard_account_code === '1122')

      if (tbRow) {
        // 本期借方发生额
        const debitOccurrence = Number(tbRow.debit_occurrence ?? tbRow.debitOccurrence ?? 0)
        // 交易笔数（如有）
        const txCount = Number(tbRow.transaction_count ?? tbRow.transactionCount ?? 0)

        testPopulation.value = {
          amount: debitOccurrence,
          count: txCount || 0,
          description: txCount > 0
            ? `本期应收账款借方发生额合计 ${debitOccurrence.toLocaleString()} 元，涉及 ${txCount} 笔交易`
            : `本期应收账款借方发生额合计 ${debitOccurrence.toLocaleString()} 元`,
        }
      }
    } catch (err) {
      console.warn('[useD2VcMethodology] 试算表数据获取失败:', err)
    }
  }

  // ─── Recommendation Logic ──────────────────────────────────────────────

  /**
   * 基于 B15/B50 数据计算推荐抽样方法和样本量
   */
  function computeRecommendation(): void {
    if (!riskLevel.value) return

    // 推荐方法
    const rec = recommendSamplingMethod(riskLevel.value, tolerableMisstatement.value)
    recommendedMethod.value = rec.method
    recommendedReason.value = rec.reason

    // 推荐样本量
    const confidence = RISK_CONFIDENCE_MAP[riskLevel.value]
    const rf = RISK_RELIABILITY_MAP[riskLevel.value]
    const popAmount = samplingPopulation.value.amount
    const popCount = samplingPopulation.value.count

    if (rec.method === 'mus' && tolerableMisstatement.value > 0 && popAmount > 0) {
      // MUS: sampleSize = ceil(populationAmount / (T / reliabilityFactor))
      recommendedSampleSize.value = computeMusSampleSize(
        tolerableMisstatement.value,
        rf,
        popAmount
      )
    } else if (rec.method === '随机抽样' && popCount > 0) {
      // 随机：查表
      recommendedSampleSize.value = computeRandomSampleSize(popCount, confidence)
    } else {
      recommendedSampleSize.value = 0
    }
  }

  // ─── AI Text Generation ────────────────────────────────────────────────

  /**
   * AI 生成测试总体描述
   */
  async function generateTestPopulationDescription(): Promise<string | null> {
    if (!wpId.value) return null
    aiGenerating.value = true
    try {
      const context = {
        amount: testPopulation.value.amount,
        count: testPopulation.value.count,
        accountCode: '1122',
        accountName: '应收账款',
      }

      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: 'vc-test-population',
        context: JSON.stringify(context),
        existingContent: testPopulation.value.description,
      })

      const text = res?.data?.content ?? res?.content ?? res?.data ?? ''
      if (text) {
        testPopulation.value = {
          ...testPopulation.value,
          description: text,
        }
      }
      return text || null
    } catch (err) {
      ElMessage.warning('AI 服务暂不可用，请手动填写测试总体描述')
      return null
    } finally {
      aiGenerating.value = false
    }
  }

  // ─── Persistence ───────────────────────────────────────────────────────

  function loadFromResponses(): void {
    const data = allResponses.value.get(METHODOLOGY_KEY)
    if (!data?.remark) return
    try {
      const parsed = JSON.parse(data.remark)
      if (parsed.testPopulation) testPopulation.value = parsed.testPopulation
      if (parsed.specificSamples) specificSamples.value = parsed.specificSamples
      if (parsed.samplingMethod) samplingMethod.value = parsed.samplingMethod
      if (parsed.samplingProcedure) samplingProcedure.value = parsed.samplingProcedure
      if (parsed.recommendedMethod) recommendedMethod.value = parsed.recommendedMethod
      if (parsed.recommendedSampleSize != null) recommendedSampleSize.value = parsed.recommendedSampleSize
      if (parsed.recommendedReason) recommendedReason.value = parsed.recommendedReason
      if (parsed.userSampleSize != null) userSampleSize.value = parsed.userSampleSize
      if (parsed.tolerableMisstatement != null) tolerableMisstatement.value = parsed.tolerableMisstatement
      if (parsed.riskLevel) riskLevel.value = parsed.riskLevel
    } catch {
      // JSON 解析失败，使用默认值
    }
  }

  function saveToResponses(): void {
    const payload = {
      testPopulation: testPopulation.value,
      specificSamples: specificSamples.value,
      samplingMethod: samplingMethod.value,
      samplingProcedure: samplingProcedure.value,
      recommendedMethod: recommendedMethod.value,
      recommendedSampleSize: recommendedSampleSize.value,
      recommendedReason: recommendedReason.value,
      userSampleSize: userSampleSize.value,
      tolerableMisstatement: tolerableMisstatement.value,
      riskLevel: riskLevel.value,
    }

    const item = {
      item_id: METHODOLOGY_KEY,
      conclusion: null,
      remark: JSON.stringify(payload),
    }

    // Update local map
    allResponses.value.set(METHODOLOGY_KEY, item)

    // Persist
    if (saveItems) {
      saveItems([item])
    }
  }

  // ─── Initialize ────────────────────────────────────────────────────────

  function initialize(): void {
    loadFromResponses()
    loadTolerableMisstatementFromB15()
    loadRiskLevelFromB50()
    // Trial balance data loaded async
    loadTrialBalanceData().then(() => {
      computeRecommendation()
    })
  }

  // Watch allResponses for initial data
  watch(
    () => allResponses.value.get(METHODOLOGY_KEY)?.remark,
    (newVal, oldVal) => {
      if (newVal && !oldVal) {
        loadFromResponses()
      }
    },
    { immediate: true }
  )

  // ─── Public API ────────────────────────────────────────────────────────

  return {
    // State
    testPopulation,
    specificSamples,
    samplingPopulation,
    samplingMethod,
    samplingProcedure,
    recommendedMethod,
    recommendedSampleSize,
    recommendedReason,
    userSampleSize,
    sampleSizeDeviation,
    tolerableMisstatement,
    riskLevel,
    aiGenerating,

    // Actions
    initialize,
    loadTrialBalanceData,
    computeRecommendation,
    generateTestPopulationDescription,
    loadFromResponses,
    saveToResponses,
  }
}

export default useD2VcMethodology
