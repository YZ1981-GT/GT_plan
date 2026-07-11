/**
 * useH1PolicyCheck — H1-5 会计政策估计检查 composable
 *
 * CAS4六段落结构定义 + 各段conclusion(Y/N/NA)
 * 折旧参数表（分类×方法×年限×残值率）
 * completionProgress computed
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.7
 * Requirements: 6.1-6.7
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** CAS4六段落结构 */
export interface PolicySection {
  key: string
  title: string
  description: string               // 准则条款引用
  actualPolicy: string              // 被审计单位实际政策
  evaluation: string                // 审计师评价
  conclusion: 'Y' | 'N' | 'NA' | '' // 结论
  explanationIfN: string            // N时强制说明
}

/** 折旧参数表行 */
export interface DepParamRow {
  rowId: string
  category: string                  // 资产分类
  depMethod: string                 // 折旧方法
  usefulLifeMin: number             // 使用年限下限
  usefulLifeMax: number             // 使用年限上限
  salvageRate: number               // 残值率(%)
  isReasonable: 'Y' | 'N' | ''     // 是否合理
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-5'

/** CAS4 六段落定义 */
const SECTION_DEFINITIONS: Omit<PolicySection, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfN'>[] = [
  { key: 'recognition', title: '(1) 固定资产确认条件', description: 'CAS4第3条：与该固定资产有关的经济利益很可能流入企业；该固定资产的成本能够可靠地计量。' },
  { key: 'classification', title: '(2) 固定资产分类与使用年限', description: 'CAS4第14-15条：企业应当根据固定资产的性质和使用情况，合理确定固定资产的使用寿命。' },
  { key: 'depreciation', title: '(3) 折旧方法与残值率', description: 'CAS4第17-19条：可选用年限平均法、工作量法、双倍余额递减法、年数总和法。预计净残值一经确定不得变更。' },
  { key: 'subsequent', title: '(4) 后续支出资本化/费用化', description: 'CAS4第6-7条：符合确认条件的后续支出计入固定资产成本；不符合的计入当期损益。' },
  { key: 'impairment', title: '(5) 减值政策', description: 'CAS8第4-5条：资产减值迹象判断标准、可收回金额确定方法、资产组划分。' },
  { key: 'disposal', title: '(6) 处置确认', description: 'CAS4第22-23条：固定资产满足下列条件之一时予以终止确认：处于处置状态/预期通过使用或处置不能产生经济利益。' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1PolicyCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const sections = ref<PolicySection[]>([])
  const depParams = ref<DepParamRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    // 加载六段落
    const sectData = _getJson(`${ITEM_PREFIX}-sections`)
    if (Array.isArray(sectData) && sectData.length > 0) {
      sections.value = sectData.map(_normalizePolicySection)
    } else {
      sections.value = SECTION_DEFINITIONS.map((def) => ({
        ...def,
        actualPolicy: '',
        evaluation: '',
        conclusion: '' as const,
        explanationIfN: '',
      }))
    }

    // 加载折旧参数表
    const paramData = _getJson(`${ITEM_PREFIX}-dep-params`)
    if (Array.isArray(paramData) && paramData.length > 0) {
      depParams.value = paramData.map(_normalizeDepParam)
    } else {
      depParams.value = _buildDefaultDepParams()
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _normalizePolicySection(raw: any): PolicySection {
    return {
      key: raw.key ?? '',
      title: raw.title ?? '',
      description: raw.description ?? '',
      actualPolicy: raw.actualPolicy ?? '',
      evaluation: raw.evaluation ?? '',
      conclusion: raw.conclusion ?? '',
      explanationIfN: raw.explanationIfN ?? '',
    }
  }

  function _normalizeDepParam(raw: any): DepParamRow {
    return {
      rowId: raw.rowId ?? `dp-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      depMethod: raw.depMethod ?? '直线法',
      usefulLifeMin: Number(raw.usefulLifeMin) || 0,
      usefulLifeMax: Number(raw.usefulLifeMax) || 0,
      salvageRate: Number(raw.salvageRate) || 0,
      isReasonable: raw.isReasonable ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _buildDefaultDepParams(): DepParamRow[] {
    const categories = ['房屋及建筑物', '机器设备', '运输设备', '电子设备', '办公设备']
    return categories.map((cat) => ({
      rowId: `dp-${cat}`,
      category: cat,
      depMethod: '直线法',
      usefulLifeMin: 0,
      usefulLifeMax: 0,
      salvageRate: 0,
      isReasonable: '' as const,
      remark: '',
    }))
  }

  // ─── Computed: 完成进度 ────────────────────────────────────────────────────

  const completionProgress = computed(() => {
    const total = sections.value.length
    if (total === 0) return 0
    const completed = sections.value.filter((s) => s.conclusion !== '').length
    return Math.round((completed / total) * 100)
  })

  const completedCount = computed(() =>
    sections.value.filter((s) => s.conclusion !== '').length,
  )

  // ─── Update ────────────────────────────────────────────────────────────────

  function updateSection(key: string, field: keyof PolicySection, value: any): void {
    const section = sections.value.find((s) => s.key === key)
    if (!section) return
    ;(section as any)[field] = value
    _persistSections()
  }

  function updateDepParam(rowId: string, field: keyof DepParamRow, value: any): void {
    const row = depParams.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistParams()
  }

  function addDepParam(category = ''): void {
    depParams.value.push({
      rowId: `dp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category,
      depMethod: '直线法',
      usefulLifeMin: 0,
      usefulLifeMax: 0,
      salvageRate: 0,
      isReasonable: '',
      remark: '',
    })
    _persistParams()
  }

  function removeDepParam(rowId: string): void {
    const idx = depParams.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      depParams.value.splice(idx, 1)
      _persistParams()
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSections(): void {
    options?.onSave?.(`${ITEM_PREFIX}-sections`, sections.value)
  }

  function _persistParams(): void {
    options?.onSave?.(`${ITEM_PREFIX}-dep-params`, depParams.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    sections,
    depParams,
    completionProgress,
    completedCount,
    updateSection,
    updateDepParam,
    addDepParam,
    removeDepParam,
    SECTION_DEFINITIONS,
  }
}

export default useH1PolicyCheck
