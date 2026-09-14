/**
 * useM10ClassificationCheck — M10-4 负债与权益区分检查表 composable
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.4
 * Requirements: 4.1-4.5
 *
 * 职责：
 * - 64行×8列 CAS37判定表管理
 * - 使用 classifyInstrument, splitAmount, calcClassificationConsistency from useM10ClassificationEngine
 * - 逐工具判定：是否存在交付现金/金融资产的合同义务
 * - 跟踪每项工具的分类状态（per-instrument judgment）
 * - 归入权益的部分→M10(4003)；归入负债的→生成负债警告
 * - 金额守恒校验：权益部分 + 负债部分 === 工具总额
 *
 * CAS37《金融工具列报》核心判定维度：
 * - 本金相关：存续期限/回购赎回条件
 * - 股利/利息：强制付息事件/递延取消
 * - 或有结算：违约/应急/约束条款
 * - 转股特征：转股条件/价格/调整
 * - 清算偿付顺序
 * - 最终判定：权益工具 or 金融负债
 *
 * 64×8结构
 */
import { computed, ref, type ComputedRef } from 'vue'
import {
  classifyInstrument,
  splitAmount,
  calcClassificationConsistency,
} from './useM10ClassificationEngine'
import type { useM10FormData } from './useM10FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** CAS37判定维度 */
export type M10JudgmentDimension =
  | 'principalObligation'    // 本金相关：存续期限/回购赎回条件
  | 'interestObligation'    // 股利/利息：强制付息事件
  | 'deferralRight'         // 递延权利：是否可无条件递延利息
  | 'contingentSettlement'  // 或有结算：违约/应急/约束条款
  | 'conversionFeature'     // 转股特征：转股条件/价格/调整
  | 'liquidationPriority'   // 清算偿付顺序
  | 'settlementMethod'      // 结算方式：固定/可变数量自身权益工具
  | 'finalConclusion'       // 最终判定

/** 判定值 */
export type M10JudgmentValue = 'yes' | 'no' | 'na' | ''

/** 单项工具的完整判定结果 */
export interface M10InstrumentJudgment {
  /** 工具标识（关联M10-2 detail key） */
  instrumentKey: string
  /** 工具名称 */
  instrumentName: string
  /** 工具总额 */
  totalAmount: number
  /** 各维度判定 */
  dimensions: Record<M10JudgmentDimension, M10JudgmentValue>
  /** 是否存在交付现金/金融资产的合同义务（核心判定字段） */
  hasContractualObligation: boolean
  /** 分类结论 */
  classification: 'equity' | 'liability' | ''
  /** 权益部分金额 */
  equityAmount: number
  /** 负债部分金额 */
  liabilityAmount: number
  /** 金额守恒（权益+负债===总额） */
  isConsistent: boolean
  /** 审计结论文本 */
  conclusion: string
  /** 备注 */
  remark: string
}

/** 检查表行（64行×8列，每行对应一个判定要素） */
export interface M10ClassificationRow {
  /** 行号 */
  rowNum: number
  /** 所属工具的key */
  instrumentKey: string
  /** 判定维度 */
  dimension: M10JudgmentDimension
  /** 检查项目描述 */
  checkItem: string
  /** 检查标准/依据 */
  criteria: string
  /** 判定值（是/否/不适用） */
  judgment: M10JudgmentValue
  /** 审计师结论 */
  auditorNote: string
  /** 索引号 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 分类汇总 */
export interface M10ClassificationSummary {
  /** 总工具数 */
  totalInstruments: number
  /** 判定为权益的数量 */
  equityCount: number
  /** 判定为负债的数量 */
  liabilityCount: number
  /** 未判定的数量 */
  pendingCount: number
  /** 权益部分总额 */
  totalEquityAmount: number
  /** 负债部分总额 */
  totalLiabilityAmount: number
  /** 工具总额 */
  totalAmount: number
  /** 全部守恒 */
  allConsistent: boolean
}

/** 负债警告 */
export interface M10LiabilityWarning {
  instrumentKey: string
  instrumentName: string
  amount: number
  message: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** CAS37判定维度标签 */
export const M10_JUDGMENT_DIMENSIONS: { key: M10JudgmentDimension; label: string }[] = [
  { key: 'principalObligation', label: '是否存在交付现金/金融资产偿还本金的合同义务' },
  { key: 'interestObligation', label: '是否存在强制付息义务' },
  { key: 'deferralRight', label: '是否可无条件递延利息/股息支付' },
  { key: 'contingentSettlement', label: '是否存在或有结算条款' },
  { key: 'conversionFeature', label: '转股特征是否导致交付可变数量自身权益工具' },
  { key: 'liquidationPriority', label: '清算时是否优先于普通股获得偿付' },
  { key: 'settlementMethod', label: '结算方式是否为固定数量自身权益工具' },
  { key: 'finalConclusion', label: '最终分类判定' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M10-4 负债与权益区分检查表逻辑（CAS37核心！64×8）
 *
 * @param formData 由调用方传入的 useM10FormData 实例
 */
export function useM10ClassificationCheck(formData: ReturnType<typeof useM10FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  /** 各工具的判定结果 */
  const instrumentJudgments = ref<M10InstrumentJudgment[]>([])

  /** 检查表行（64行×8列明细） */
  const classificationRows = ref<M10ClassificationRow[]>([])

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 自动计算分类结论（根据各维度判定自动推导） */
  const computedJudgments: ComputedRef<M10InstrumentJudgment[]> = computed(() => {
    return instrumentJudgments.value.map(j => {
      // 核心判定：是否存在合同义务
      const classification = j.hasContractualObligation
        ? classifyInstrument(true)
        : j.hasContractualObligation === false
          ? classifyInstrument(false)
          : '' as const

      // 金额拆分
      let equityAmount = j.equityAmount
      let liabilityAmount = j.liabilityAmount

      if (classification === 'equity') {
        equityAmount = j.totalAmount
        liabilityAmount = 0
      } else if (classification === 'liability') {
        // 纯负债：全部归入负债
        equityAmount = 0
        liabilityAmount = j.totalAmount
      } else if (j.totalAmount > 0 && j.equityAmount > 0) {
        // 复合工具：已手动拆分，计算负债部分
        liabilityAmount = splitAmount(j.totalAmount, j.equityAmount)
      }

      // 金额守恒校验
      const isConsistent = j.totalAmount > 0
        ? calcClassificationConsistency(equityAmount, liabilityAmount, j.totalAmount)
        : true

      return { ...j, classification, equityAmount, liabilityAmount, isConsistent }
    })
  })

  /** 分类汇总统计 */
  const summary: ComputedRef<M10ClassificationSummary> = computed(() => {
    const judgments = computedJudgments.value
    const totalInstruments = judgments.length
    const equityCount = judgments.filter(j => j.classification === 'equity').length
    const liabilityCount = judgments.filter(j => j.classification === 'liability').length
    const pendingCount = totalInstruments - equityCount - liabilityCount
    const totalEquityAmount = judgments.reduce((sum, j) => sum + j.equityAmount, 0)
    const totalLiabilityAmount = judgments.reduce((sum, j) => sum + j.liabilityAmount, 0)
    const totalAmount = judgments.reduce((sum, j) => sum + j.totalAmount, 0)
    const allConsistent = judgments.every(j => j.isConsistent)
    return {
      totalInstruments, equityCount, liabilityCount, pendingCount,
      totalEquityAmount, totalLiabilityAmount, totalAmount, allConsistent,
    }
  })

  /** 负债警告列表（判定为liability的工具） */
  const liabilityWarnings: ComputedRef<M10LiabilityWarning[]> = computed(() => {
    return computedJudgments.value
      .filter(j => j.classification === 'liability' && j.liabilityAmount > 0)
      .map(j => ({
        instrumentKey: j.instrumentKey,
        instrumentName: j.instrumentName,
        amount: j.liabilityAmount,
        message: `"${j.instrumentName}" 已判定为金融负债（CAS37），金额 ${j.liabilityAmount.toLocaleString()} 元应计入负债科目而非权益（4003）`,
      }))
  })

  /** 金额不守恒的工具 */
  const inconsistentItems: ComputedRef<M10InstrumentJudgment[]> = computed(() => {
    return computedJudgments.value.filter(j => !j.isConsistent && j.totalAmount > 0)
  })

  // ─── 3. 工具判定操作 ──────────────────────────────────────────────────

  /** 新增工具判定（从M10-2明细表带入） */
  function addInstrument(instrumentKey: string, instrumentName: string, totalAmount: number): void {
    // 避免重复
    if (instrumentJudgments.value.find(j => j.instrumentKey === instrumentKey)) return

    const newJudgment: M10InstrumentJudgment = {
      instrumentKey,
      instrumentName,
      totalAmount,
      dimensions: {
        principalObligation: '',
        interestObligation: '',
        deferralRight: '',
        contingentSettlement: '',
        conversionFeature: '',
        liquidationPriority: '',
        settlementMethod: '',
        finalConclusion: '',
      },
      hasContractualObligation: false,
      classification: '',
      equityAmount: 0,
      liabilityAmount: 0,
      isConsistent: true,
      conclusion: '',
      remark: '',
    }
    instrumentJudgments.value.push(newJudgment)
  }

  /** 删除工具判定 */
  function removeInstrument(instrumentKey: string): void {
    const idx = instrumentJudgments.value.findIndex(j => j.instrumentKey === instrumentKey)
    if (idx >= 0) {
      instrumentJudgments.value.splice(idx, 1)
      _triggerSaveAll()
    }
  }

  /** 更新某工具的判定维度 */
  function updateDimension(
    instrumentKey: string,
    dimension: M10JudgmentDimension,
    value: M10JudgmentValue,
  ): void {
    const judgment = instrumentJudgments.value.find(j => j.instrumentKey === instrumentKey)
    if (!judgment) return

    judgment.dimensions[dimension] = value

    // 自动推导核心判定：如果本金义务=yes或利息义务=yes且不可递延 → 有合同义务
    const hasPrincipalOb = judgment.dimensions.principalObligation === 'yes'
    const hasInterestOb = judgment.dimensions.interestObligation === 'yes'
    const canDefer = judgment.dimensions.deferralRight === 'yes'
    judgment.hasContractualObligation = hasPrincipalOb || (hasInterestOb && !canDefer)

    _triggerSaveInstrument(instrumentKey)
  }

  /** 更新核心判定字段 */
  function updateContractualObligation(instrumentKey: string, value: boolean): void {
    const judgment = instrumentJudgments.value.find(j => j.instrumentKey === instrumentKey)
    if (!judgment) return
    judgment.hasContractualObligation = value
    _triggerSaveInstrument(instrumentKey)
  }

  /** 更新权益部分金额（复合工具手动拆分） */
  function updateEquityAmount(instrumentKey: string, equityAmount: number): void {
    const judgment = instrumentJudgments.value.find(j => j.instrumentKey === instrumentKey)
    if (!judgment) return
    judgment.equityAmount = equityAmount
    judgment.liabilityAmount = splitAmount(judgment.totalAmount, equityAmount)
    _triggerSaveInstrument(instrumentKey)
  }

  /** 更新审计结论 */
  function updateConclusion(instrumentKey: string, conclusion: string): void {
    const judgment = instrumentJudgments.value.find(j => j.instrumentKey === instrumentKey)
    if (!judgment) return
    judgment.conclusion = conclusion
    _triggerSaveInstrument(instrumentKey)
  }

  // ─── 4. 检查表行操作（64行明细） ──────────────────────────────────────

  /** 更新检查表行判定值 */
  function updateCheckRow(rowNum: number, field: 'judgment' | 'auditorNote' | 'refIndex' | 'remark', value: string): void {
    const row = classificationRows.value.find(r => r.rowNum === rowNum)
    if (!row) return
    ;(row as any)[field] = value
    debouncedSave(`M10-4-row-${rowNum}`, {
      remark: JSON.stringify({
        rowNum: row.rowNum,
        instrumentKey: row.instrumentKey,
        dimension: row.dimension,
        judgment: row.judgment,
        auditorNote: row.auditorNote,
        refIndex: row.refIndex,
        remark: row.remark,
      }),
    })
  }

  // ─── 5. 批量保存 ──────────────────────────────────────────────────────

  /** 保存全部判定结果 */
  async function saveAll(): Promise<void> {
    const items = computedJudgments.value.map((j, i) => {
      const n = i + 1
      return [
        { itemId: `M10-4-instrument-${n}-key`, data: { remark: j.instrumentKey } },
        { itemId: `M10-4-instrument-${n}-name`, data: { remark: j.instrumentName } },
        { itemId: `M10-4-instrument-${n}-total`, data: { remark: String(j.totalAmount) } },
        { itemId: `M10-4-instrument-${n}-obligation`, data: { remark: String(j.hasContractualObligation) } },
        { itemId: `M10-4-instrument-${n}-classification`, data: { remark: j.classification } },
        { itemId: `M10-4-instrument-${n}-equity`, data: { remark: String(j.equityAmount) } },
        { itemId: `M10-4-instrument-${n}-liability`, data: { remark: String(j.liabilityAmount) } },
        { itemId: `M10-4-instrument-${n}-conclusion`, data: { remark: j.conclusion } },
        { itemId: `M10-4-instrument-${n}-dimensions`, data: { remark: JSON.stringify(j.dimensions) } },
      ]
    }).flat()

    // 汇总行
    items.push(
      { itemId: 'M10-4-summary-equity-total', data: { remark: String(summary.value.totalEquityAmount) } },
      { itemId: 'M10-4-summary-liability-total', data: { remark: String(summary.value.totalLiabilityAmount) } },
      { itemId: 'M10-4-summary-consistent', data: { remark: String(summary.value.allConsistent) } },
    )

    await saveBatch(items)
  }

  // ─── 6. 内部保存 ──────────────────────────────────────────────────────

  function _triggerSaveInstrument(instrumentKey: string): void {
    const idx = instrumentJudgments.value.findIndex(j => j.instrumentKey === instrumentKey)
    if (idx < 0) return
    const j = instrumentJudgments.value[idx]
    const n = idx + 1
    debouncedSave(`M10-4-instrument-${n}-data`, {
      remark: JSON.stringify({
        instrumentKey: j.instrumentKey,
        instrumentName: j.instrumentName,
        totalAmount: j.totalAmount,
        dimensions: j.dimensions,
        hasContractualObligation: j.hasContractualObligation,
        equityAmount: j.equityAmount,
        liabilityAmount: j.liabilityAmount,
        conclusion: j.conclusion,
        remark: j.remark,
      }),
    })
  }

  function _triggerSaveAll(): void {
    instrumentJudgments.value.forEach(j => _triggerSaveInstrument(j.instrumentKey))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    instrumentJudgments,
    classificationRows,

    // 计算属性
    computedJudgments,
    summary,
    liabilityWarnings,
    inconsistentItems,

    // 工具判定操作
    addInstrument,
    removeInstrument,
    updateDimension,
    updateContractualObligation,
    updateEquityAmount,
    updateConclusion,

    // 检查表行操作
    updateCheckRow,

    // 保存
    saveAll,
  }
}

export default useM10ClassificationCheck
