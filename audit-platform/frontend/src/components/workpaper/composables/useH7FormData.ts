/**
 * useH7FormData — H7 生产性生物资产底稿数据加载/保存/selfLoad/writebackTB
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 3.1
 * Requirements: 1.9, 1.10, 2.7
 *
 * 职责：
 * - allResponses Map 加载 + saveResponse(即时) + debouncedSave(2s) + saveBatch
 * - writebackTB（科目1621生产性生物资产借方 + 累计折旧贷方/备抵）
 * - selfLoad逻辑（render-config?force_component_type=h7-biological-assets）
 * - TB自动取数 unadjusted_amount → 审定表未审数
 * - EventBus publish 'substantive:adjudicated' 通知附注刷新
 *
 * 科目：1621 生产性生物资产（借方/资产类）+ 累计折旧（贷方/备抵类）
 * ⚠️ 资产负债表科目！取期末余额（非发生额）！
 * - 1621为借方科目：期末=期初+借方-贷方（资产类）
 * - 累计折旧为贷方科目（备抵）：期末=期初+贷方-借方
 * - 净值=生产性生物资产原值-累计折旧-减值准备
 *
 * item_id 命名规则：前缀 "H7-{sheet编号}-{field}"
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface H7TbData {
  /** 1621生产性生物资产 未审期末余额（借方科目） */
  costUnadjusted: number
  /** 累计折旧 未审期末余额（贷方/备抵） */
  depUnadjusted: number
  /** 1621 审定数 */
  costAudited: number
  /** 累计折旧 审定数 */
  depAudited: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ACCOUNT_CODE_1621 = '1621'
const COMPONENT_TYPE = 'h7-biological-assets'

// ─── Helper ──────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH7FormData(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string>
}) {
  const { wpId, projectId } = opts

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  const tbData = ref<H7TbData>({ costUnadjusted: 0, depUnadjusted: 0, costAudited: 0, depAudited: 0 })
  const htmlData = ref<any>(null)

  // ─── debounce timer ────────────────────────────────────────────────────────
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  onScopeDispose(() => { if (debounceTimer) clearTimeout(debounceTimer) })

  // ─── selfLoad ─────────────────────────────────────────────────────────────

  async function selfLoad(): Promise<void> {
    isLoading.value = true
    try {
      const { data } = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: COMPONENT_TYPE },
      })
      const sheets = data?.data?.sheets ?? data?.sheets ?? []
      if (sheets.length > 0) {
        htmlData.value = sheets[0]?.html_data ?? null
      }
      // Load checklist_responses
      await loadResponses()
      // Load TB data
      await loadTbData()
    } catch (err: any) {
      ElMessage.error('H7数据加载失败: ' + (err?.message || ''))
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadResponses ────────────────────────────────────────────────────────

  async function loadResponses(): Promise<void> {
    try {
      const { data } = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const items: ChecklistItem[] = data?.data ?? data ?? []
      const map = new Map<string, ChecklistItem>()
      for (const item of items) {
        if (item.item_id?.startsWith('H7-')) {
          map.set(item.item_id, item)
        }
      }
      allResponses.value = map
    } catch { /* silently ignore — first time empty */ }
  }

  // ─── loadTbData ───────────────────────────────────────────────────────────

  async function loadTbData(): Promise<void> {
    try {
      const { data } = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_codes: ACCOUNT_CODE_1621 },
      })
      const rows = data?.data ?? data ?? []
      for (const row of rows) {
        if (row.standard_account_code === ACCOUNT_CODE_1621) {
          tbData.value.costUnadjusted = parseNum(row.unadjusted_amount)
          tbData.value.costAudited = parseNum(row.audited_amount)
        }
      }
    } catch { /* TB may not be imported yet */ }
  }

  // ─── saveResponse (immediate) ──────────────────────────────────────────────

  async function saveResponse(itemId: string, conclusion: string | null, remark?: string | null): Promise<void> {
    isSaving.value = true
    try {
      await api.post(`/api/workpapers/${wpId.value}/checklist-responses`, {
        items: [{ item_id: itemId, conclusion, remark: remark ?? null }],
      })
      allResponses.value.set(itemId, { item_id: itemId, conclusion, remark: remark ?? null })
    } catch (err: any) {
      ElMessage.error('保存失败: ' + (err?.message || ''))
    } finally {
      isSaving.value = false
    }
  }

  // ─── debouncedSave ────────────────────────────────────────────────────────

  function debouncedSave(itemId: string, conclusion: string | null, remark?: string | null): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    // Optimistic update local map
    allResponses.value.set(itemId, { item_id: itemId, conclusion, remark: remark ?? null })
    debounceTimer = setTimeout(() => {
      saveResponse(itemId, conclusion, remark)
    }, DEBOUNCE_MS)
  }

  // ─── getValue ─────────────────────────────────────────────────────────────

  function getValue(itemId: string): any {
    return allResponses.value.get(itemId)?.remark ?? allResponses.value.get(itemId)?.conclusion ?? null
  }

  // ─── writebackTB ──────────────────────────────────────────────────────────

  async function writebackTB(auditedCost: number, auditedDep: number): Promise<void> {
    try {
      await api.post(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        items: [
          { standard_account_code: ACCOUNT_CODE_1621, audited_amount: auditedCost },
        ],
      })
      tbData.value.costAudited = auditedCost
      tbData.value.depAudited = auditedDep
      // Publish event for notes to refresh
      eventBus.emit('substantive:adjudicated', {
        source: 'h7-biological-assets',
        accountCodes: [ACCOUNT_CODE_1621],
      })
    } catch (err: any) {
      ElMessage.error('TB回写失败: ' + (err?.message || ''))
    }
  }

  return {
    isLoading,
    isSaving,
    allResponses,
    tbData,
    htmlData,
    selfLoad,
    loadResponses,
    saveResponse,
    debouncedSave,
    getValue,
    writebackTB,
  }
}

export default useH7FormData
