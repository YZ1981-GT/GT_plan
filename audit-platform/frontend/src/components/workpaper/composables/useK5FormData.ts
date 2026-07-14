/**
 * useK5FormData — K5 预计负债 selfLoad/checklist_responses/writebackTB(2701 负债口径)/TB取数
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.7
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文 + checklist_responses
 * - loadTbData(): 从 trial_balance 获取科目 2701 未审/审定数据
 * - writebackTB2701(): 审定数回写 trial_balance(2701) + EventBus 'substantive:adjudicated'
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "K5-{sheet}-{field}"（如 "K5-1-audited-total", "K5-2-detail-row-1"）
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * 科目：2701 预计负债（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+计提-转销（与资产类方向相反）
 */
import { computed, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { decodeRemark } from '@/composables/workpaper/remarkCodec'
import { collectK5Responses, toK5PersistencePatch } from '../k5/k5Persistence'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface K5TbData {
  /** 2701预计负债 未审数 */
  unadjusted2701: number
  /** 2701预计负债 审定数 */
  audited2701: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
/** 科目：2701 预计负债（贷方/负债类） */
const ACCOUNT_CODE_2701 = '2701'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5FormData(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  year?: Ref<number | undefined>
  sheetPrefix: string
}) {
  const { wpId, projectId, sheetPrefix } = params
  const year = params.year ?? ref<number | undefined>(undefined)

  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const isSaving = ref(false)
  const persistence = useChecklistPersistence({
    wpId,
    projectId: computed(() => projectId.value || undefined),
    debounceMs: DEBOUNCE_MS,
  })
  const allResponses = persistence.responses
  const tbData = ref<K5TbData>({ unadjusted2701: 0, audited2701: 0 })
  const renderMeta = ref<Record<string, any>>({})

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * 完整自加载入口：render-config → checklist_responses → TB。
   * bundle内嵌场景 htmlData 为 null 时自行调用。
   * 404 静默处理（_silent:true）。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true
    try {
      // 1. 加载 render-config
      const configRes = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'k5-provisions' },
        _silent: true,
      } as any)
      const configData = configRes?.data ?? configRes
      renderMeta.value = configData?.html_data ?? configData ?? {}

      // 2. 合并 render-config 快照（兼容 responses_snapshot / allResponses / checklist_responses）
      const sheetsArr = configData?.sheets ?? configData?.data?.sheets
      const snapshotSources: unknown[] = []
      if (Array.isArray(sheetsArr)) {
        for (const sheet of sheetsArr) {
          const htmlData = sheet?.html_data
          if (htmlData) snapshotSources.push(
            htmlData.responses_snapshot,
            htmlData.allResponses,
            htmlData.checklist_responses,
          )
        }
      }
      const snapshot = collectK5Responses(...snapshotSources)

      // 3. checklist 读取统一经 Adapter；API 数据优先，快照补足未返回项。
      try {
        await persistence.load()
        persistence.hydrate(collectK5Responses(snapshot, allResponses.value))
      } catch {
        persistence.hydrate(snapshot)
      }

      // 4. 加载 TB 数据
      await loadTbData()
    } catch {
      // selfLoad 404 静默处理
    } finally {
      isLoading.value = false
    }
  }

  // ─── loadTbData: 从 trial_balance 获取 2701 数据 ───────────────────────────

  /**
   * 从 trial_balance 获取科目 2701 的未审数和审定数。
   * 优先从 renderMeta seed 读取，否则请求 TB 端点。
   *
   * 科目：2701 预计负债（贷方/负债类）
   */
  async function loadTbData(): Promise<void> {
    if (!projectId.value) return

    // 优先从 render-config seed 取值
    const seededUnadj = renderMeta.value?.tb_values?.provisions_2701_unadjusted
    const seededAudited = renderMeta.value?.tb_values?.provisions_2701_audited
    if (seededUnadj != null) {
      tbData.value = {
        unadjusted2701: Number(seededUnadj) || 0,
        audited2701: Number(seededAudited) || 0,
      }
      return
    }

    try {
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: '2701', year: year.value },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])

      let unadjusted = 0
      let audited = 0
      let found = false

      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (code.startsWith(ACCOUNT_CODE_2701)) {
          unadjusted += Number(item.unadjusted_amount ?? 0)
          audited += Number(item.audited_amount ?? 0)
          found = true
        }
      }

      tbData.value = { unadjusted2701: unadjusted, audited2701: audited }

      if (!found) {
        ElMessage.warning('科目2701预计负债未在试算表中找到，请先导入试算表')
      }
    } catch {
      tbData.value = { unadjusted2701: 0, audited2701: 0 }
    }
  }

  // ─── writebackTB2701（2701 预计负债 负债口径） ──────────────────────────────

  /**
   * 审定数回写 trial_balance：科目2701预计负债（贷方/负债类）。
   * 回写成功后发布 EventBus 'substantive:adjudicated' 通知附注刷新。
   *
   * ⚠️ 负债类2701！正数口径回写（v2 trial_balance 正数，无需取反）。
   * 负债类方向：期末=期初+计提-转销
   *
   * Req 2.7: WHEN 审定数变化时 SHALL 回写trial_balance(2701)+发布'substantive:adjudicated'
   */
  async function writebackTB2701(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    isSaving.value = true
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_2701,
        audited_amount: auditedAmount,
      })

      // EventBus publish 'substantive:adjudicated'
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE_2701,
        auditedAmount,
        wpCode: 'K5',
        timestamp: Date.now(),
      })

      // 同步更新本地 tbData
      tbData.value.audited2701 = auditedAmount
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    } finally {
      isSaving.value = false
    }
  }

  // ─── saveResponse（统一 Persistence Adapter） ───────────────────────────────

  /** 立即保存单个 checklist item，字段名自动加 K5 sheet 前缀。 */
  async function saveResponse(field: string, value: unknown): Promise<void> {
    const itemId = `K5-${sheetPrefix}-${field}`
    isSaving.value = true
    try {
      await persistence.save(itemId, toK5PersistencePatch(value))
    } catch (err: any) {
      if (err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地，请稍后重试')
      }
    } finally {
      isSaving.value = false
    }
  }

  /** 多 item 复用 Adapter 的独立状态与重试语义。 */
  async function saveResponses(items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }>): Promise<void> {
    isSaving.value = true
    try {
      await Promise.all(items.map(({ item_id, conclusion, remark }) => persistence.save(item_id, {
        ...(conclusion !== undefined ? { conclusion } : {}),
        ...(remark !== undefined ? { remark: toK5PersistencePatch({ remark }).remark } : {}),
      })))
    } catch (err: any) {
      if (err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地，请稍后重试')
      }
    } finally {
      isSaving.value = false
    }
  }

  // ─── getResponse（读取单条） ───────────────────────────────────────────────

  /**
   * 从 allResponses Map 中获取指定 field 的值（自动加前缀，尝试 JSON 解析 remark）。
   * @param field 字段名（会自动加前缀 "K5-{sheetPrefix}-{field}"）
   */
  function getResponse(field: string): any {
    const itemId = `K5-${sheetPrefix}-${field}`
    const item = allResponses.value.get(itemId)
    if (!item) return undefined
    const raw = item.remark ?? item.conclusion
    if (raw == null) return undefined
    return decodeRemark(raw)
  }

  // ─── debouncedSave（文本字段 debounce 2s） ────────────────────────────────

  /**
   * debounce 2s 保存，per-item 独立计时器。
   * 适用于 textarea / 备注等文本字段。
   */
  function debouncedSave(itemId: string, data: Partial<ChecklistItem>): void {
    persistence.saveDebounced(itemId, {
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined
        ? { remark: toK5PersistencePatch({ remark: data.remark }).remark }
        : {}),
    })
  }

  // ─── setTbValues（外部设置TB值，render策略seed回读） ────────────────────────

  /**
   * 外部设置 TB 值（从 render 策略 seed 或组件 watch 调用）。
   */
  function setTbValues(values: Partial<K5TbData>): void {
    if (values.unadjusted2701 != null) {
      tbData.value.unadjusted2701 = values.unadjusted2701
    }
    if (values.audited2701 != null) {
      tbData.value.audited2701 = values.audited2701
    }
  }

  // Adapter 在所属 effect scope 释放时自动 flush pending items。

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    allResponses,
    isLoading,
    isSaving,
    tbData,
    renderMeta,
    // Actions
    selfLoad,
    saveResponse,
    saveResponses,
    getResponse,
    writebackTB2701,
    loadTbData,
    // Extras
    debouncedSave,
    setTbValues,
  }
}

export default useK5FormData
