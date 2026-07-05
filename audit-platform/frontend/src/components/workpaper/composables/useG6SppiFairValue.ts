/**
 * useG6SppiFairValue — G6-5 公允价值测试表（18列→2区段Tab）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 4.1
 * Requirements: 2.1, 2.2, 7.1
 *
 * 职责：
 * - FairValueItem 行数据模型管理
 * - Row CRUD（新增ElMessageBox.prompt / 删除确认）
 * - calcFairValueDiff 公式调用，差异红色高亮逻辑（|审定-未审|>0）
 * - 2区段Tab行同步（activeTab + selectedRowIndex）
 * - Level3必填校验（层次=L3时Tab2相关字段必填）
 * - 公允价值层次分层逻辑（L1/L2/L3）
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { calcFairValueDiff, parseNum } from '@/composables/useG6SppiFormulaEngine'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** Tab1 基础+审定 10列 */
export interface FairValueTab1 {
  investProject: string       // 投资项目
  faceValue: number           // 面值
  unadjQty: number            // 期末未审-数量
  unadjPrice: number          // 期末未审-单价
  unadjFairValue: number      // 期末未审-公允价值
  auditedQty: number          // 期末审定-数量
  auditedPrice: number        // 期末审定-单价
  auditedFairValue: number    // 期末审定-公允价值
  difference: number          // 差异（公式：审定-未审）
  fairValueLevel: 'L1' | 'L2' | 'L3' | '' // 公允价值层次
}

/** Tab2 估值详情 8列 */
export interface FairValueTab2 {
  investProject: string       // 投资项目（与Tab1行同步）
  valuationMethod: string     // 估值方法
  consistencyWithPrior: string // 与上期一致性
  sourceInstitution: string   // 来源机构
  inputSource: string         // 输入值来源
  valuationTechnique: string  // 估值技术
  unobservableInputs: string  // 不可观察输入值
  valuationFileRef: string    // 估值文件索引
}

/** 完整行（Tab1 + Tab2 合并） */
export interface FairValueItem extends FairValueTab1, Omit<FairValueTab2, 'investProject'> {
  id: string
  seq: number
}

/** 完整数据结构 */
export interface FairValueTestData {
  rows: FairValueItem[]
  conclusion: string
}

// ─── Level3必填字段列表 ──────────────────────────────────────────────────────

const L3_REQUIRED_FIELDS: (keyof FairValueTab2)[] = [
  'valuationMethod',
  'valuationTechnique',
  'unobservableInputs',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiFairValue() {
  const rows = ref<FairValueItem[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const selectedRowIndex = ref(0)
  const conclusion = ref('')

  // ─── 公式计算 ──────────────────────────────────────────────────────────────

  /** 重算指定行的差异 */
  function recalcRow(row: FairValueItem): void {
    row.difference = calcFairValueDiff(
      parseNum(row.auditedFairValue),
      parseNum(row.unadjFairValue),
    )
  }

  // watch rows 变化时自动重算差异
  watch(rows, (newRows) => {
    for (const row of newRows) {
      recalcRow(row)
    }
  }, { deep: true })

  // ─── 差异高亮逻辑 ─────────────────────────────────────────────────────────

  /** 判断行是否有差异需高亮（|diff| > 0） */
  function hasDifference(row: FairValueItem): boolean {
    return Math.abs(parseNum(row.difference)) > 0
  }

  /** 获取差异列样式 */
  function getDiffCellStyle(row: FairValueItem): Record<string, string> {
    if (hasDifference(row)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  // ─── Level3 校验逻辑 ──────────────────────────────────────────────────────

  /** 判断行是否为Level3 */
  function isLevel3(row: FairValueItem): boolean {
    return row.fairValueLevel === 'L3'
  }

  /** 获取Level3必填校验结果 */
  function getL3ValidationErrors(row: FairValueItem): string[] {
    if (!isLevel3(row)) return []
    const errors: string[] = []
    for (const field of L3_REQUIRED_FIELDS) {
      if (!row[field as keyof FairValueItem]) {
        const labels: Record<string, string> = {
          valuationMethod: '估值方法',
          valuationTechnique: '估值技术',
          unobservableInputs: '不可观察输入值',
        }
        errors.push(labels[field] || field)
      }
    }
    return errors
  }

  /** 行Level3是否有校验错误 */
  function hasL3Errors(row: FairValueItem): boolean {
    return getL3ValidationErrors(row).length > 0
  }

  /** 全表Level3校验 */
  const l3ValidationSummary = computed(() => {
    const issues: Array<{ row: FairValueItem; errors: string[] }> = []
    for (const row of rows.value) {
      const errors = getL3ValidationErrors(row)
      if (errors.length > 0) {
        issues.push({ row, errors })
      }
    }
    return issues
  })

  // ─── 行 CRUD ──────────────────────────────────────────────────────────────

  async function addRow(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入投资项目名称',
        '新增公允价值测试行',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '投资项目名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return

      const newRow: FairValueItem = {
        id: `fv-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        seq: rows.value.length + 1,
        investProject: value.trim(),
        faceValue: 0,
        unadjQty: 0,
        unadjPrice: 0,
        unadjFairValue: 0,
        auditedQty: 0,
        auditedPrice: 0,
        auditedFairValue: 0,
        difference: 0,
        fairValueLevel: '',
        valuationMethod: '',
        consistencyWithPrior: '',
        sourceInstitution: '',
        inputSource: '',
        valuationTechnique: '',
        unobservableInputs: '',
        valuationFileRef: '',
      }
      rows.value.push(newRow)
      selectedRowIndex.value = rows.value.length - 1
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch {
      // 用户取消
    }
  }

  async function removeRow(id: string): Promise<void> {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${row.investProject}"？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      rows.value = rows.value.filter(r => r.id !== id)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      if (selectedRowIndex.value >= rows.value.length) {
        selectedRowIndex.value = Math.max(0, rows.value.length - 1)
      }
      ElMessage.success(`已删除"${row.investProject}"`)
    } catch {
      // 用户取消
    }
  }

  /** 更新指定行字段 */
  function updateRow(id: string, field: keyof FairValueItem, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    recalcRow(row)
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  function loadData(data: FairValueTestData | null): void {
    if (!data?.rows?.length) {
      rows.value = []
      conclusion.value = data?.conclusion || ''
      return
    }
    rows.value = data.rows.map((r, i) => {
      const item: FairValueItem = {
        id: r.id || `fv-${Date.now()}-${i}`,
        seq: i + 1,
        investProject: r.investProject || '',
        faceValue: parseNum(r.faceValue),
        unadjQty: parseNum(r.unadjQty),
        unadjPrice: parseNum(r.unadjPrice),
        unadjFairValue: parseNum(r.unadjFairValue),
        auditedQty: parseNum(r.auditedQty),
        auditedPrice: parseNum(r.auditedPrice),
        auditedFairValue: parseNum(r.auditedFairValue),
        difference: 0,
        fairValueLevel: r.fairValueLevel || '',
        valuationMethod: r.valuationMethod || '',
        consistencyWithPrior: r.consistencyWithPrior || '',
        sourceInstitution: r.sourceInstitution || '',
        inputSource: r.inputSource || '',
        valuationTechnique: r.valuationTechnique || '',
        unobservableInputs: r.unobservableInputs || '',
        valuationFileRef: r.valuationFileRef || '',
      }
      recalcRow(item)
      return item
    })
    conclusion.value = data.conclusion || ''
  }

  function toJSON(): FairValueTestData {
    return {
      rows: rows.value.map(r => ({ ...r })),
      conclusion: conclusion.value,
    }
  }

  // ─── 汇总统计 ──────────────────────────────────────────────────────────────

  /** 按层次分组统计 */
  const levelSummary = computed(() => {
    const summary = { L1: 0, L2: 0, L3: 0, unset: 0 }
    for (const row of rows.value) {
      if (row.fairValueLevel === 'L1') summary.L1++
      else if (row.fairValueLevel === 'L2') summary.L2++
      else if (row.fairValueLevel === 'L3') summary.L3++
      else summary.unset++
    }
    return summary
  })

  /** 差异行数 */
  const diffCount = computed(() => rows.value.filter(hasDifference).length)

  return {
    // State
    rows,
    activeTab,
    selectedRowIndex,
    conclusion,
    // Computed
    l3ValidationSummary,
    levelSummary,
    diffCount,
    // Methods
    recalcRow,
    hasDifference,
    getDiffCellStyle,
    isLevel3,
    getL3ValidationErrors,
    hasL3Errors,
    addRow,
    removeRow,
    updateRow,
    loadData,
    toJSON,
  }
}

export default useG6SppiFairValue
