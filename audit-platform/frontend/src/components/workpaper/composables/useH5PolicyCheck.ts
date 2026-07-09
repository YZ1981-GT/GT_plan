/**
 * useH5PolicyCheck — H5-5 会计政策 composable
 *
 * CAS27段落型, 逐项合规勾选
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 4.2
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicyCheckItem {
  id: string
  clause: string              // CAS27条款编号
  description: string         // 条款内容描述
  compliant: 'yes' | 'no' | 'na' | '' // 合规/不合规/不适用
  evidence: string            // 审计证据
  remark: string              // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-5'

/** CAS27 石油天然气开采准则核心段落 */
export const CAS27_CLAUSES: { clause: string; description: string }[] = [
  { clause: 'CAS27.4', description: '矿区权益的确认和计量' },
  { clause: 'CAS27.5', description: '井及相关设施的确认' },
  { clause: 'CAS27.6', description: '油气资产的折耗方法（单位产量法）' },
  { clause: 'CAS27.7', description: '折耗计算基础（证实储量+概算储量）' },
  { clause: 'CAS27.8', description: '储量估计变更的会计处理（未来适用法）' },
  { clause: 'CAS27.9', description: '油气资产减值测试' },
  { clause: 'CAS27.10', description: '弃置义务的确认' },
  { clause: 'CAS27.11', description: '勘探支出资本化条件' },
  { clause: 'CAS27.12', description: '开发支出资本化条件' },
  { clause: 'CAS27.13', description: '油气资产处置损益' },
  { clause: 'CAS27.14', description: '披露要求：探明储量/储量变动' },
  { clause: 'CAS27.15', description: '披露要求：折耗方法及残值' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5PolicyCheck(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const items = ref<PolicyCheckItem[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw = allResponses.value.get(`${ITEM_PREFIX}-items`)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        items.value = Array.isArray(parsed) ? parsed : _buildDefaults()
      } catch { items.value = _buildDefaults() }
    } else {
      items.value = _buildDefaults()
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _buildDefaults(): PolicyCheckItem[] {
    return CAS27_CLAUSES.map((c) => ({
      id: `policy-${c.clause}`,
      clause: c.clause,
      description: c.description,
      compliant: '' as const,
      evidence: '',
      remark: '',
    }))
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const completionRate = computed(() => {
    const total = items.value.length
    if (total === 0) return 0
    const done = items.value.filter((i) => i.compliant !== '').length
    return Math.round((done / total) * 100)
  })

  const nonCompliantItems = computed(() => items.value.filter((i) => i.compliant === 'no'))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateItem(id: string, field: keyof PolicyCheckItem, value: any): void {
    const item = items.value.find((i) => i.id === id)
    if (!item) return
    ;(item as any)[field] = value
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-items`, items.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    items, auditNote, auditConclusion,
    completionRate, nonCompliantItems,
    updateItem, saveNote, saveConclusion,
    CAS27_CLAUSES,
  }
}
