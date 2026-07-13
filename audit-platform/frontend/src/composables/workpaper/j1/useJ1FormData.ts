/**
 * useJ1FormData — J1 应付职工薪酬 selfLoad 数据管理 + writebackTB 2211
 *
 * 科目：2211应付职工薪酬（贷方/负债类）
 * TB回写：审定表期末余额 → trial_balance 2211
 *
 * 职责：
 * - selfLoad 从 render-config 获取 html_data
 * - checklist_responses 存取
 * - writebackTB 回写期末余额到2211
 * - EventBus publish substantive:adjudicated
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 1.9, 1.10, 6.1
 */
import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

export interface J1FormDataOptions {
  wpId: string
  projectId: string
  year?: string | number
  sheetName?: string
  htmlData?: Record<string, unknown> | null
}

export interface J1SectionData {
  label: string
  beginBalance: number       // 期初余额
  creditIncrease: number     // 贷方增加（计提）
  debitDecrease: number      // 借方减少（发放）
  unauditedEnd: number       // 期末未审数
  ajeAdjustment: number      // AJE调整
  rjeAdjustment: number      // RJE重分类
  auditedEnd: number         // 期末审定数
}

export function useJ1FormData(options: J1FormDataOptions) {
  const isLoading = ref(false)
  const isSaving = ref(false)
  const htmlData: Ref<Record<string, unknown>> = ref({})
  const responses: Ref<Record<string, unknown>> = ref({})
  const sections: Ref<J1SectionData[]> = ref([])

  // ── selfLoad ──────────────────────────────────────────────────────────────

  async function loadData() {
    isLoading.value = true
    try {
      if (options.htmlData) {
        parseHtmlData(options.htmlData)
        return
      }
      const res = await http.get(`/api/workpapers/${options.wpId}/render-config`)
      const sheets = res.data?.data?.sheets || res.data?.sheets || []
      if (sheets.length > 0 && sheets[0].html_data) {
        parseHtmlData(sheets[0].html_data)
      }
    } catch (e) {
      console.error('[J1 FormData] selfLoad failed:', e)
    } finally {
      isLoading.value = false
    }
  }

  function parseHtmlData(data: Record<string, unknown>) {
    htmlData.value = data
    if (data.sections && Array.isArray(data.sections)) {
      sections.value = data.sections as J1SectionData[]
    }
    if (data.responses && typeof data.responses === 'object') {
      responses.value = data.responses as Record<string, unknown>
    }
  }

  // ── checklist_responses 存取 ─────────────────────────────────────────────

  function getResponse(key: string): unknown {
    return responses.value[key]
  }

  function setResponse(key: string, value: unknown) {
    responses.value[key] = value
  }

  async function saveResponses() {
    isSaving.value = true
    try {
      const items = Object.entries(responses.value).map(([key, val]) => ({
        item_id: `J1-${key}`,
        content: typeof val === 'string' ? val : JSON.stringify(val),
      }))
      await http.put(`/api/workpapers/${options.wpId}/checklist-responses`, { items })
    } catch (e) {
      console.error('[J1 FormData] save failed:', e)
    } finally {
      isSaving.value = false
    }
  }

  // ── writebackTB 回写 2211 期末余额 ─────────────────────────────────────

  async function writebackTB(auditedEndBalance: number) {
    try {
      await http.post(`/api/projects/${options.projectId}/trial-balance/writeback`, {
        account_code: '2211',
        audited_amount: auditedEndBalance,
        year: options.year,
        source_wp_id: options.wpId,
      })
    } catch (e) {
      console.warn('[J1 FormData] writebackTB failed:', e)
    }
  }

  // ── EventBus publish ───────────────────────────────────────────────────────

  async function publishAdjudicated(auditedEndBalance: number) {
    try {
      await http.post(`/api/projects/${options.projectId}/events/publish`, {
        event_type: 'substantive:adjudicated',
        payload: {
          accountCode: '2211',
          accountName: '应付职工薪酬',
          auditedAmount: auditedEndBalance,
          wpId: options.wpId,
          direction: 'credit',
        },
      })
    } catch (e) {
      console.warn('[J1 FormData] EventBus publish failed:', e)
    }
  }

  // ── computed ──────────────────────────────────────────────────────────────

  const totalAuditedEnd = computed(() =>
    sections.value.reduce((sum, s) => sum + (s.auditedEnd || 0), 0),
  )

  const totalBeginBalance = computed(() =>
    sections.value.reduce((sum, s) => sum + (s.beginBalance || 0), 0),
  )

  return {
    isLoading,
    isSaving,
    htmlData,
    responses,
    sections,
    loadData,
    getResponse,
    setResponse,
    saveResponses,
    writebackTB,
    publishAdjudicated,
    totalAuditedEnd,
    totalBeginBalance,
  }
}
