/**
 * useK5Detail — K5-2 明细表逻辑（42行×23列，3区段Tab + 或有事项判断）
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 3.1-3.6, 4.1-4.4
 *
 * 职责：
 * - 42行动态行管理（ElMessageBox.prompt命名）
 * - 23列拆为3区段Tab：基础(序号/项目/类型/现时义务描述/期初/期末)
 *                     判断(可能性级别/是否确认/确认依据/计量方法)
 *                     估计(最佳估计数/上限/下限/期望值/凭证/结论)
 * - 或有事项三级可能性判断 + 色标
 * - 合计行与K5-1审定表交叉验证
 * - 虚拟滚动42行
 * - Save with prefix "K5-2-"
 *
 * 科目：2701 预计负债（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useK5FormulaEngine'
import {
  determineRecognition,
  type LikelihoodLevel,
  type Recognition,
} from './useK5ContingencyEngine'
import {
  calcRangeMidpoint,
  calcExpectedValue,
} from './useK5BestEstimateEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K5MeasurementMethod = 'single' | 'range' | 'expected' | ''

export interface K5DetailRow {
  rowId: string
  // 区段0: 基础
  seqNo: number
  projectName: string              // 项目名称
  provisionType: string            // 类型（产品质保/未决诉讼/亏损合同/重组义务/弃置义务/其他）
  obligationDesc: string           // 现时义务描述
  beginBalance: number             // 期初余额
  provision: number                // 本期计提
  release: number                  // 本期转销
  endBalance: number               // 期末余额（负债类：期初+计提-转销）
  // 区段1: 判断
  likelihood: LikelihoodLevel | '' // 可能性级别
  recognition: Recognition | ''    // 是否确认（自动派生）
  recognitionBasis: string         // 确认依据
  measurementMethod: K5MeasurementMethod // 计量方法
  // 区段2: 估计
  bestEstimate: number             // 最佳估计数
  rangeUpper: number               // 区间上限
  rangeLower: number               // 区间下限
  expectedAmounts: string          // 期望值各情形金额（JSON数组字符串）
  expectedProbs: string            // 期望值各情形概率（JSON数组字符串）
  voucherRef: string               // 凭证号
  conclusion: string               // 结论
  remark: string
}

export type K5DetailSection = 0 | 1 | 2

export const K5_DETAIL_SECTION_LABELS = ['基础', '判断', '估计'] as const

export interface K5DetailSubtotals {
  beginBalance: number
  provision: number
  release: number
  endBalance: number
  bestEstimate: number
  count: number
}

/** 三级可能性色标映射 */
export const LIKELIHOOD_COLOR_MAP: Record<LikelihoodLevel, string> = {
  very_likely: '#F56C6C',   // 红色 — 很可能
  possible: '#E6A23C',      // 橙色 — 可能
  remote: '#909399',        // 灰色 — 极小可能
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-2-rows'
const PROVISION_TYPE_OPTIONS = ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '其他']
const MEASUREMENT_OPTIONS: Array<{ value: K5MeasurementMethod; label: string }> = [
  { value: 'single', label: '单一最可能金额' },
  { value: 'range', label: '区间中值' },
  { value: 'expected', label: '期望值加权' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K5DetailRow[]>([])
  const activeSection = ref<K5DetailSection>(0)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { detailRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed.map(_normalizeRow)
      } else {
        detailRows.value = []
      }
    } catch {
      detailRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K5DetailRow {
    const likelihood = raw.likelihood || ''
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      projectName: raw.projectName ?? '',
      provisionType: raw.provisionType ?? '',
      obligationDesc: raw.obligationDesc ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      provision: Number(raw.provision) || 0,
      release: Number(raw.release) || 0,
      endBalance: Number(raw.endBalance) || 0,
      likelihood,
      recognition: likelihood ? determineRecognition(likelihood as LikelihoodLevel) : '',
      recognitionBasis: raw.recognitionBasis ?? '',
      measurementMethod: raw.measurementMethod ?? '',
      bestEstimate: Number(raw.bestEstimate) || 0,
      rangeUpper: Number(raw.rangeUpper) || 0,
      rangeLower: Number(raw.rangeLower) || 0,
      expectedAmounts: raw.expectedAmounts ?? '[]',
      expectedProbs: raw.expectedProbs ?? '[]',
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K5DetailRow): void {
    // 负债类期末=期初+计提-转销
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.provision, row.release)

    // 或有事项判断自动派生
    if (row.likelihood) {
      row.recognition = determineRecognition(row.likelihood as LikelihoodLevel)
    }

    // 最佳估计数自动计算（基于计量方法）
    if (row.measurementMethod === 'range') {
      row.bestEstimate = calcRangeMidpoint(row.rangeUpper, row.rangeLower)
    } else if (row.measurementMethod === 'expected') {
      try {
        const amounts = JSON.parse(row.expectedAmounts || '[]')
        const probs = JSON.parse(row.expectedProbs || '[]')
        row.bestEstimate = calcExpectedValue(amounts, probs)
      } catch {
        // 解析失败保持原值
      }
    }
    // 'single' 直接用手工填入的 bestEstimate
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K5DetailSubtotals> = computed(() => {
    const r = detailRows.value
    return {
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      provision: calcSubtotal(r.map(x => x.provision)),
      release: calcSubtotal(r.map(x => x.release)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      bestEstimate: calcSubtotal(r.map(x => x.bestEstimate)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K5DetailSection): void {
    activeSection.value = section
  }

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = detailRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 3.5: ElMessageBox.prompt输入名称) ────────────────

  async function addRow(projectName?: string): Promise<void> {
    let name = projectName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入预计负债项目名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX产品质量保修',
            inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const newRow: K5DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      projectName: name,
      provisionType: '',
      obligationDesc: '',
      beginBalance: 0,
      provision: 0,
      release: 0,
      endBalance: 0,
      likelihood: '',
      recognition: '',
      recognitionBasis: '',
      measurementMethod: '',
      bestEstimate: 0,
      rangeUpper: 0,
      rangeLower: 0,
      expectedAmounts: '[]',
      expectedProbs: '[]',
      voucherRef: '',
      conclusion: '',
      remark: '',
    }
    detailRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= detailRows.value.length) return
    detailRows.value.splice(idx, 1)
    detailRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    detailRows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 需披露的或有负债（possible → 进附注） ────────────────────────────────

  const disclosureItems = computed(() => {
    return detailRows.value.filter(r => r.recognition === 'disclose')
  })

  // ─── 统计方法 ──────────────────────────────────────────────────────────────

  /** 明细表期末合计（供跨sheet交叉验证） */
  function getDetailTotal(): number {
    return subtotals.value.endBalance
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('2-rows', { remark: JSON.stringify(detailRows.value) })
    saveResponse('2-detail-total', { remark: String(getDetailTotal()) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailRows,
    activeSection,
    subtotals,
    disclosureItems,
    sections: K5_DETAIL_SECTION_LABELS,
    provisionTypeOptions: PROVISION_TYPE_OPTIONS,
    measurementOptions: MEASUREMENT_OPTIONS,
    likelihoodColorMap: LIKELIHOOD_COLOR_MAP,
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getDetailTotal,
  }
}
