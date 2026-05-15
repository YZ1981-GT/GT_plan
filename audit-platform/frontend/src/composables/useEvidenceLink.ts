/**
 * useEvidenceLink — 证据链 composable
 *
 * Sprint 6 Task 6.6: 封装证据链 CRUD / 批量关联 / 充分性检查
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export interface EvidenceLink {
  id: string
  wp_id: string
  sheet_name: string | null
  cell_ref: string | null
  attachment_id: string
  page_ref: string | null
  evidence_type: string | null
  check_conclusion: string | null
  created_by: string
  created_at: string | null
}

export interface SufficiencyResult {
  wp_id: string
  total_mandatory: number
  total_links: number
  sufficient: boolean
  warnings: Array<{
    procedure_id: string
    description: string
    message: string
  }>
}

export function useEvidenceLink(projectId: string, wpId: string) {
  const links = ref<EvidenceLink[]>([])
  const loading = ref(false)
  const sufficiency = ref<SufficiencyResult | null>(null)

  const basePath = `/api/projects/${projectId}/workpapers/${wpId}/evidence`

  const linkedCells = computed(() => {
    const cells = new Set<string>()
    for (const link of links.value) {
      if (link.cell_ref) cells.add(link.cell_ref)
    }
    return cells
  })

  const totalLinks = computed(() => links.value.length)

  async function fetchLinks() {
    loading.value = true
    try {
      const data = await api.get(basePath)
      links.value = data.items || []
    } catch (e: unknown) {
      handleApiError(e, '证据链')
    } finally {
      loading.value = false
    }
  }

  async function createLink(params: {
    attachment_id: string
    sheet_name?: string
    cell_ref?: string
    page_ref?: string
    evidence_type?: string
    check_conclusion?: string
  }) {
    try {
      const result = await api.post(`${basePath}/link`, params)
      links.value.unshift(result)
      return result
    } catch (e: unknown) {
      handleApiError(e, '证据链')
      throw e
    }
  }

  async function deleteLink(linkId: string) {
    try {
      await api.delete(`${basePath}/${linkId}`)
      links.value = links.value.filter(l => l.id !== linkId)
    } catch (e: unknown) {
      handleApiError(e, '证据链')
      throw e
    }
  }

  async function batchLink(items: Array<{
    attachment_id: string
    sheet_name?: string
    cell_ref?: string
    page_ref?: string
    evidence_type?: string
  }>) {
    try {
      const data = await api.post(`${basePath}/batch-link`, { links: items })
      links.value = [...(data.items || []), ...links.value]
      return data.items
    } catch (e: unknown) {
      handleApiError(e, '证据链')
      throw e
    }
  }

  async function checkSufficiency() {
    try {
      const data = await api.get(`${basePath}/sufficiency`)
      sufficiency.value = data
      return data
    } catch (e: unknown) {
      handleApiError(e, '证据链')
      return null
    }
  }

  /**
   * 判断某个单元格是否有证据链接（用于📎图标渲染）
   */
  function hasCellEvidence(cellRef: string): boolean {
    return linkedCells.value.has(cellRef)
  }

  /**
   * 获取某个单元格的所有证据链接（用于 hover 预览）
   */
  function getCellLinks(cellRef: string): EvidenceLink[] {
    return links.value.filter(l => l.cell_ref === cellRef)
  }

  return {
    links,
    loading,
    sufficiency,
    linkedCells,
    totalLinks,
    fetchLinks,
    createLink,
    deleteLink,
    batchLink,
    checkSufficiency,
    hasCellEvidence,
    getCellLinks,
  }
}
