/**
 * useK1Checks — K1-6/K1-9/K1-10/K1-11/K1-12 检查表通用逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 8.1-8.6, 9.1-9.2
 *
 * 职责：
 * - 段落型/列表型检查
 * - 合规/不合规/不适用 tri-state
 * - 不合规红色摘要
 * - AI辅助 per-section
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ComplianceState = '合规' | '不合规' | '不适用'

export interface K1CheckItem {
  id: string
  section: string          // 所属section（如 "K1-6" / "K1-9"）
  seq: number
  label: string
  description: string      // 检查项描述/内容
  compliance: ComplianceState | null
  evidence: string         // 审计证据/说明
  remark: string
}

export interface K1CheckSection {
  sectionId: string        // 如 "K1-6", "K1-9"
  sectionLabel: string
  type: 'paragraph' | 'list'  // 段落型/列表型
  items: K1CheckItem[]
}

export interface K1NonComplianceSummary {
  count: number
  items: Array<{ section: string; label: string; evidence: string }>
}

export interface UseK1ChecksOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Section配置 ─────────────────────────────────────────────────────────────

const SECTION_CONFIGS: Array<{ sectionId: string; sectionLabel: string; type: 'paragraph' | 'list' }> = [
  { sectionId: 'K1-6', sectionLabel: '信用减值损失会计政策检查', type: 'paragraph' },
  { sectionId: 'K1-9', sectionLabel: '坏账准备转回(收回)核销检查', type: 'list' },
  { sectionId: 'K1-10', sectionLabel: '长期未收回款项检查', type: 'list' },
  { sectionId: 'K1-11', sectionLabel: '关联方及交易检查', type: 'list' },
  { sectionId: 'K1-12', sectionLabel: '其他应收款检查', type: 'list' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1Checks(opts: UseK1ChecksOpts) {
  const { allResponses } = opts

  const sections = ref<K1CheckSection[]>([])

  // ─── 加载 ──────────────────────────────────────────────────────────────────

  function loadSections(): void {
    const loaded: K1CheckSection[] = []
    for (const config of SECTION_CONFIGS) {
      const raw = allResponses.value.get(`${config.sectionId}-check-items`)?.remark
      let items: K1CheckItem[] = []
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          items = Array.isArray(parsed) ? parsed : []
        } catch { items = [] }
      }
      loaded.push({ ...config, items })
    }
    sections.value = loaded
  }

  // ─── 检查项操作 ────────────────────────────────────────────────────────────

  function updateItemCompliance(sectionId: string, itemId: string, state: ComplianceState): void {
    const section = sections.value.find(s => s.sectionId === sectionId)
    if (!section) return
    const item = section.items.find(i => i.id === itemId)
    if (!item) return
    item.compliance = state
  }

  function updateItemEvidence(sectionId: string, itemId: string, evidence: string): void {
    const section = sections.value.find(s => s.sectionId === sectionId)
    if (!section) return
    const item = section.items.find(i => i.id === itemId)
    if (!item) return
    item.evidence = evidence
  }

  function addItem(sectionId: string, label: string): K1CheckItem | null {
    const section = sections.value.find(s => s.sectionId === sectionId)
    if (!section) return null
    const newItem: K1CheckItem = {
      id: `${sectionId}-item-${Date.now()}`,
      section: sectionId,
      seq: section.items.length + 1,
      label,
      description: '',
      compliance: null,
      evidence: '',
      remark: '',
    }
    section.items.push(newItem)
    return newItem
  }

  function removeItem(sectionId: string, itemId: string): void {
    const section = sections.value.find(s => s.sectionId === sectionId)
    if (!section) return
    section.items = section.items.filter(i => i.id !== itemId)
    section.items.forEach((item, i) => { item.seq = i + 1 })
  }

  // ─── 不合规红色摘要 ────────────────────────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K1NonComplianceSummary> = computed(() => {
    const items: K1NonComplianceSummary['items'] = []
    for (const section of sections.value) {
      for (const item of section.items) {
        if (item.compliance === '不合规') {
          items.push({ section: section.sectionLabel, label: item.label, evidence: item.evidence })
        }
      }
    }
    return { count: items.length, items }
  })

  // ─── Section级完成状态 ─────────────────────────────────────────────────────

  function getSectionProgress(sectionId: string): { total: number; completed: number } {
    const section = sections.value.find(s => s.sectionId === sectionId)
    if (!section) return { total: 0, completed: 0 }
    const total = section.items.length
    const completed = section.items.filter(i => i.compliance !== null).length
    return { total, completed }
  }

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeSection(sectionId: string): string {
    const section = sections.value.find(s => s.sectionId === sectionId)
    return JSON.stringify(section?.items ?? [])
  }

  function serializeAll(): Map<string, string> {
    const result = new Map<string, string>()
    for (const section of sections.value) {
      result.set(`${section.sectionId}-check-items`, JSON.stringify(section.items))
    }
    return result
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    sections,
    nonComplianceSummary,
    loadSections,
    updateItemCompliance,
    updateItemEvidence,
    addItem,
    removeItem,
    getSectionProgress,
    serializeSection,
    serializeAll,
  }
}
