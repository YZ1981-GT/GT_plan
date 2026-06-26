/**
 * useA115Checklist — A1-15 企业会计准则财务报表列报及披露核对表 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a1-15-disclosure-checklist/
 * Task: 3.1
 *
 * 职责：
 * - loadData(): 自加载 render-config?force_component_type=a1-15-disclosure-checklist
 * - updateItemResponse(itemId, field, value): debounce 2s 批量保存
 * - setTocApplicability(sectionId, applicable): 级联 NA + 保存 field_overrides
 * - globalProgress: computed（y/n/na/unfilled 各数量）
 * - sectionProgress(sectionId): {filled, total}
 * - searchQuery + conclusionFilter + filteredSections: 搜索与筛选
 * - saving/lastSavedAt 状态指示
 * - 保存失败重试 3 次 + ElMessage.warning
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A115Template {
  wp_code: string
  title: string
  sections: A115Section[]
  toc: A115TocEntry[]
  stats: { total_actionable: number; total_guidance: number; total_sections: number }
  parsed_at: string
}

export interface A115Section {
  id: string
  title: string
  items: A115Item[]
}

export interface A115Item {
  id: string
  type: 'actionable' | 'header'
  standard_ref: string
  content: string
  children: A115GuidanceChild[]
}

export interface A115GuidanceChild {
  id: string
  content: string
  standard_ref: string
}

export interface A115TocEntry {
  id: string
  title: string
  applicable: boolean | null
}

export interface A115Responses {
  items: Record<string, A115ItemResponse>
  toc_applicability: Record<string, boolean>
}

export interface A115ItemResponse {
  conclusion: 'Y' | 'N' | 'NA' | null
  remark: string
  wp_ref: string
}

// ─── 静态配置：科目章节 → 建议关联底稿编码 ──────────────────────────────────

export const CROSS_REFERENCE_MAP: Record<string, string> = {
  'S02': 'D0',   // 货币资金
  'S03': 'D1',   // 应收票据
  'S04': 'D2',   // 应收账款
  'S05': 'D3',   // 预付款项
  'S06': 'E1',   // 存货
  'S07': 'I1',   // 长期股权投资
  'S08': 'G1',   // 固定资产
  'S09': 'H1',   // 无形资产
  'S10': 'F1',   // 应付账款
  'S11': 'F2',   // 应付职工薪酬
  'S12': 'K1',   // 收入
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA115Checklist(wpId: Ref<string>, readonly: Ref<boolean>) {
  // ─── State ─────────────────────────────────────────────────────────────────
  const template = ref<A115Template | null>(null)
  const responses = ref<A115Responses>({ items: {}, toc_applicability: {} })
  const crossRefMap = ref<Record<string, string>>({ ...CROSS_REFERENCE_MAP })
  const loading = ref(false)
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const searchQuery = ref('')
  const conclusionFilter = ref<'all' | 'filled' | 'unfilled' | 'Y' | 'N' | 'NA'>('all')
  const error = ref<string | null>(null)

  // ─── Debounce 机制 ──────────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  /** 待保存的 item_id 集合（增量批量） */
  const pendingItemIds = new Set<string>()

  // ─── loadData ──────────────────────────────────────────────────────────────

  async function loadData(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    error.value = null
    try {
      const res = await api.get<any>(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=a1-15-disclosure-checklist`,
      )
      if (res?.template) {
        template.value = res.template
      }
      if (res?.responses) {
        // 合并 items
        const items: Record<string, A115ItemResponse> = {}
        if (res.responses.items) {
          for (const [k, v] of Object.entries(res.responses.items as Record<string, any>)) {
            items[k] = {
              conclusion: v.conclusion ?? null,
              remark: v.remark ?? '',
              wp_ref: v.wp_ref ?? '',
            }
          }
        }
        responses.value = {
          items,
          toc_applicability: res.responses.toc_applicability ?? {},
        }
      }
      if (res?.cross_reference_map) {
        crossRefMap.value = { ...CROSS_REFERENCE_MAP, ...res.cross_reference_map }
      }
    } catch (e: any) {
      error.value = e?.message || '数据加载失败'
    } finally {
      loading.value = false
    }
  }

  // ─── Save（checklist-responses） ──────────────────────────────────────────

  async function doSaveItems(retryCount = 0): Promise<void> {
    if (readonly.value) return
    if (pendingItemIds.size === 0) return

    // 快照待保存的 ids
    const idsToSave = [...pendingItemIds]
    pendingItemIds.clear()

    const items = idsToSave.map((itemId) => {
      const resp = responses.value.items[itemId]
      return {
        item_id: itemId,
        conclusion: resp?.conclusion ?? null,
        remark: resp?.remark ?? null,
        wp_ref: resp?.wp_ref ?? null,
      }
    })

    if (items.length === 0) return

    saving.value = true
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: getProjectId(),
        items,
      })
      lastSavedAt.value = new Date()
      error.value = null
    } catch (e: any) {
      if (retryCount < 3) {
        // 重试：将 ids 放回待保存集合
        for (const id of idsToSave) pendingItemIds.add(id)
        await delay(1000 * (retryCount + 1))
        await doSaveItems(retryCount + 1)
        return
      }
      ElMessage.warning('保存失败，请检查网络后重试')
      // 放回未保存的，下次可再触发
      for (const id of idsToSave) pendingItemIds.add(id)
    } finally {
      saving.value = false
    }
  }

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      doSaveItems()
    }, 2000)
  }

  // ─── updateItemResponse ──────────────────────────────────────────────────

  function updateItemResponse(
    itemId: string,
    field: keyof A115ItemResponse,
    value: any,
  ): void {
    if (readonly.value) return
    if (!responses.value.items[itemId]) {
      responses.value.items[itemId] = { conclusion: null, remark: '', wp_ref: '' }
    }
    ;(responses.value.items[itemId] as any)[field] = value
    pendingItemIds.add(itemId)
    scheduleSave()
  }

  // ─── setTocApplicability ──────────────────────────────────────────────────

  async function setTocApplicability(sectionId: string, applicable: boolean): Promise<void> {
    if (readonly.value) return

    responses.value.toc_applicability[sectionId] = applicable

    // 级联：不适用 → 该章节所有 actionable 条目 → NA
    if (!applicable && template.value) {
      const section = template.value.sections.find((s) => s.id === sectionId)
      if (section) {
        for (const item of section.items) {
          if (item.type === 'actionable') {
            if (!responses.value.items[item.id]) {
              responses.value.items[item.id] = { conclusion: null, remark: '', wp_ref: '' }
            }
            responses.value.items[item.id].conclusion = 'NA'
            pendingItemIds.add(item.id)
          }
        }
      }
    }

    // 保存 TOC 适用性到 checklist_responses（用 TOC-{sectionId} 格式）
    pendingItemIds.add(`TOC-${sectionId}`)
    if (!responses.value.items[`TOC-${sectionId}`]) {
      responses.value.items[`TOC-${sectionId}`] = {
        conclusion: applicable ? 'Y' : 'N',
        remark: '',
        wp_ref: '',
      } as any
    } else {
      (responses.value.items[`TOC-${sectionId}`] as any).conclusion = applicable ? 'Y' : 'N'
    }

    // 立即保存（不走 debounce，因为级联可能影响大量条目）
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSaveItems()

    // 同步保存到 field_overrides（备份存储）
    await saveFieldOverrideToc(sectionId, applicable)
  }

  async function saveFieldOverrideToc(sectionId: string, applicable: boolean): Promise<void> {
    try {
      await api.post('/api/workpapers/field-overrides', {
        project_id: getProjectId(),
        year: getCurrentYear(),
        scope: `a115_disclosure:${wpId.value}`,
        item_key: `toc-${sectionId.toLowerCase()}`,
        field: 'applicable',
        value: applicable,
      })
    } catch {
      // field_overrides 保存失败不阻塞（主数据已在 checklist_responses 中）
    }
  }

  // ─── Progress 计算 ──────────────────────────────────────────────────────────

  const globalProgress: ComputedRef<{
    filled: number
    total: number
    y: number
    n: number
    na: number
  }> = computed(() => {
    const total = template.value?.stats?.total_actionable ?? 0
    let y = 0
    let n = 0
    let na = 0

    if (template.value) {
      for (const section of template.value.sections) {
        for (const item of section.items) {
          if (item.type !== 'actionable') continue
          const resp = responses.value.items[item.id]
          if (!resp?.conclusion) continue
          if (resp.conclusion === 'Y') y++
          else if (resp.conclusion === 'N') n++
          else if (resp.conclusion === 'NA') na++
        }
      }
    }

    return { filled: y + n + na, total, y, n, na }
  })

  function sectionProgress(sectionId: string): { filled: number; total: number } {
    if (!template.value) return { filled: 0, total: 0 }
    const section = template.value.sections.find((s) => s.id === sectionId)
    if (!section) return { filled: 0, total: 0 }

    let total = 0
    let filled = 0
    for (const item of section.items) {
      if (item.type !== 'actionable') continue
      total++
      const resp = responses.value.items[item.id]
      if (resp?.conclusion) filled++
    }
    return { filled, total }
  }

  // ─── 搜索与筛选 ────────────────────────────────────────────────────────────

  const filteredSections: ComputedRef<A115Section[]> = computed(() => {
    if (!template.value) return []

    const query = searchQuery.value.trim().toLowerCase()
    const filter = conclusionFilter.value

    // 无筛选条件：返回所有章节
    if (!query && filter === 'all') {
      return template.value.sections
    }

    const result: A115Section[] = []

    for (const section of template.value.sections) {
      const matchedItems = section.items.filter((item) => {
        // 搜索条件：content 或 standard_ref 包含关键词（case-insensitive）
        if (query) {
          const contentMatch = item.content.toLowerCase().includes(query)
          const refMatch = item.standard_ref.toLowerCase().includes(query)
          if (!contentMatch && !refMatch) return false
        }

        // 结论筛选条件
        if (filter !== 'all' && item.type === 'actionable') {
          const resp = responses.value.items[item.id]
          const conclusion = resp?.conclusion ?? null
          if (filter === 'filled') {
            if (!conclusion) return false
          } else if (filter === 'unfilled') {
            if (conclusion) return false
          } else {
            // 'Y' | 'N' | 'NA'
            if (conclusion !== filter) return false
          }
        } else if (filter !== 'all' && item.type === 'header') {
          // header 不参与筛选（但如果搜索匹配则显示）
          if (!query) return false
        }

        return true
      })

      if (matchedItems.length > 0) {
        result.push({ ...section, items: matchedItems })
      }
    }

    return result
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  /** 从 URL 获取 project_id（简易实现，匹配 /projects/:id 路径） */
  function getProjectId(): string {
    try {
      const match = window.location.pathname.match(/\/projects\/([^/]+)/)
      return match?.[1] ?? ''
    } catch {
      return ''
    }
  }

  function getCurrentYear(): number {
    return new Date().getFullYear()
  }

  function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  /** 组件卸载时 flush 未保存数据 */
  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingItemIds.size > 0) {
      doSaveItems()
    }
  }

  return {
    // State
    template,
    responses,
    crossRefMap,
    loading,
    saving,
    lastSavedAt,
    error,
    searchQuery,
    conclusionFilter,

    // Actions
    loadData,
    updateItemResponse,
    setTocApplicability,
    flushPendingSave,

    // Computed
    globalProgress,
    sectionProgress,
    filteredSections,
  }
}

export default useA115Checklist
