/**
 * useD2FormData — D2 应收账款数据加载/debounce保存/即时保存/辅助
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
 * Task: 2.1
 *
 * 职责：
 * - 从 GET /api/workpapers/:wpId/checklist-responses 加载 D2-* 数据
 * - debounce 2s 文本字段保存 / 结论/状态/选择类字段立即保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 * - 保存 via PUT /api/workpapers/:wpId/checklist-responses
 * - trial_balance 回写：writebackTrialBalance
 * - 子底稿数据读取：loadSubWorkpaperData（D2-2）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { fetchTrialBalanceRows } from '@/services/trialBalanceRows'
import { getWpIndex } from '@/services/workpaperApi'
import {
  useChecklistPersistence,
  type ChecklistResponse as PersistenceChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { hasManualTbAmount } from './dCycleTbSeed'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ChecklistItem = PersistenceChecklistResponse
export type ChecklistResponse = ChecklistItem

// ─── Composable ──────────────────────────────────────────────────────────────

/** D2-1 TB 核对锚点（净额口径，公式推送独占键）。 */
const D2_TB_ANCHOR = 'D2-adj-tb-amount'

/** 试算表参考数：1122 应收账款原值 / 1231-02 坏账准备的审定额；`null` = 没取到（不拿 0 冒充）。 */
export interface D2TbReference {
  grossAudited: number | null
  provisionAudited: number | null
}

/** 从 `GET /api/projects/{pid}/trial-balance` 的行里取某标准科目的审定额（审定为空回退未审）。 */
export function pickTbAudited(tbRows: unknown, code: string): number | null {
  if (!Array.isArray(tbRows)) return null
  const row = tbRows.find((r: any) => r?.standard_account_code === code)
  if (!row) return null
  const v = Number(row.audited_amount ?? row.unadjusted_amount ?? 0)
  return Number.isFinite(v) ? v : null
}

/**
 * D2-adj-tb-amount 回退种子（净额）：render 下发的 `project_context.tb_amount`（净额）优先，
 * 其次试算表 1122 原值 − 1231-02 坏账准备；都没有返回 `null`（不补）。
 */
export function d2NetTbSeed(htmlData: unknown, ref_: D2TbReference): number | null {
  const raw = (htmlData as any)?.project_context?.tb_amount
  if (raw !== undefined && raw !== null && raw !== '') {
    const n = Number(raw)
    if (Number.isFinite(n)) return n
  }
  if (ref_.grossAudited == null) return null
  return ref_.grossAudited - Math.abs(ref_.provisionAudited ?? 0)
}

export function useD2FormData(wpId: Ref<string>, projectId?: Ref<string>, htmlData?: Ref<any>) {
  const persistence = useChecklistPersistence({ wpId, projectId, debounceMs: 2000 })
  const allResponses = persistence.responses
  const loading = ref(false)
  const saving = ref(false)

  // ─── 试算表参考数（D2-2↔TB 原值核对 + 锚点回退种子共用一次取数）──────────

  /**
   * D2-2 明细逐客户列的是**原值**，与试算表核对要拿 1122 原值审定额 —— 不能用
   * `D2-adj-tb-amount`（净额锚点），否则差异恰好等于坏账准备（spec
   * writeback-followup-issue-closure R11.2）。取不到时保持 `null`，核对条不显示。
   */
  const tbReference = ref<D2TbReference>({ grossAudited: null, provisionAudited: null })

  async function resolveAuditYear(): Promise<number | null> {
    const fromRender = Number((htmlData?.value as any)?.project_context?.audit_year)
    if (Number.isFinite(fromRender) && fromRender > 0) return fromRender
    if (!projectId?.value) return null
    try {
      const projRes = await api.get(`/api/projects/${projectId.value}`)
      const proj = projRes?.data ?? projRes
      const year = Number(proj?.audit_year)
      return Number.isFinite(year) && year > 0 ? year : null
    } catch {
      return null
    }
  }

  async function loadTbReference(): Promise<void> {
    if (!projectId?.value) return
    try {
      const year = await resolveAuditYear()
      if (year == null) return
      const { rows: tbData } = await fetchTrialBalanceRows(projectId.value, { year, accountPrefix: ['1122', '1231'] })
      tbReference.value = {
        grossAudited: pickTbAudited(tbData, '1122'),
        provisionAudited: pickTbAudited(tbData, '1231-02'),
      }
    } catch {
      // 取数失败不阻断加载；D2-2↔TB 核对条随之不显示
    }
  }

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    // 试算表参考数与底稿数据互不依赖：并行取，loadAll 结束前等它到位（在线编辑回写后的重载也走这里，
    // 串行会给「看到新值」多加一次往返）。loadTbReference 自己吞掉全部异常。
    const tbReferenceLoaded = projectId?.value ? loadTbReference() : Promise.resolve()
    try {
      await persistence.load()
      // D2 主入口只暴露本循环 item，避免其他历史响应污染业务 composable。
      const d2Responses = new Map<string, ChecklistResponse>()
      for (const [itemId, response] of allResponses.value) {
        if (itemId.startsWith('D2-')) d2Responses.set(itemId, response)
      }
      persistence.hydrate(d2Responses)

      // D2-adj-tb-amount 锚点的**回退种子**。锚点是净额（公式推送 TB('1122') − TB('1231-02')；
      // 源模板 D2-1 被比较项是「三、应收账款净值」合计 A27），主路径是公式推送 / Tier A 写入。
      // 🔴 库里已有值（手工或公式推送）一律不动：此前这里无条件用试算表原值覆盖内存里的锚点，
      //    在线编辑回写后重载（reloadHtml → loadAll）即把净额换成原值，D2-1 净值核对随之出现
      //    恰好等于坏账准备的假差异（spec writeback-followup-issue-closure R11.2）。补的种子也是净额。
      await tbReferenceLoaded
      if (projectId?.value) {
        if (!hasManualTbAmount(allResponses.value.get(D2_TB_ANCHOR)?.remark)) {
          const net = d2NetTbSeed(htmlData?.value, tbReference.value)
          if (net != null) {
            allResponses.value.set(D2_TB_ANCHOR, {
              item_id: D2_TB_ANCHOR,
              conclusion: null,
              remark: String(net),
            })
          }
        }
      }
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      await Promise.all(items.map((item) => persistence.save(item.item_id, item)))
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
      throw err
    } finally {
      saving.value = false
    }
  }

  /** 立即保存指定 items（结论/状态/选择类字段触发） */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    await doSave(items)
  }

  /** debounce 2000ms 文本字段保存；Adapter 按 item 独立调度。 */
  function saveDebouncedText(item: ChecklistItem): void {
    persistence.saveDebounced(item.item_id, item)
  }

  /** flush 未保存数据（组件卸载或切换 sheet 时调用） */
  async function flushPendingSave(): Promise<void> {
    await persistence.flush()
  }

  /** 子 composable 通过 D2 注入批量保存。 */
  async function saveItemsFromEvent(items: ChecklistResponse[]): Promise<void> {
    const validItems = items.filter((item) => item?.item_id)
    if (!validItems.length) return
    await doSave(validItems)
  }

  /** 用 render-config snapshot 初始化 Adapter，保持历史响应格式兼容。 */
  function hydrate(source: unknown): void {
    persistence.hydrate(source)
  }

  // ─── Helper 方法 ─────────────────────────────────────────────────────────

  /** 获取单个字段 */
  function getField(itemId: string): ChecklistResponse | undefined {
    return allResponses.value.get(itemId)
  }

  /** 设置字段 + 立即保存（选择变更、签字操作） */
  function setFieldImmediate(itemId: string, data: Partial<Omit<ChecklistResponse, 'item_id'>>): void {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    void saveImmediate([updated]).catch(() => undefined)
  }

  // 注：原 writebackTrialBalance（PUT /trial-balance/writeback）已移除 ——
  // TB 回写收敛为审定表 useD2Adjudication.publishToTb（显式二次确认 → publish-to-tb 端点）。
  // spec: tb-writeback-explicit-publish-gate Task 2 / Req 1,2,9。

  // ─── 子底稿数据读取 ──────────────────────────────────────────────────────

  /** 读取 D2-2 audit-sheet 子底稿数据供 SUMIF 跨 sheet 引用 */
  async function loadSubWorkpaperData(subWpCode: string): Promise<Record<string, string | number>> {
    if (!projectId?.value) return {}
    try {
      const wpIndex = await getWpIndex(projectId.value)
      const subWp = wpIndex.find((w: any) => w.wp_code === subWpCode)
      if (!subWp) return {}

      const res = await api.get(`/api/workpapers/${subWp.id}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const result: Record<string, string | number> = {}
      for (const r of responses) {
        if (r.remark != null) result[r.item_id] = r.remark
        if (r.conclusion != null) result[r.item_id] = r.conclusion
      }
      return result
    } catch {
      ElMessage.warning(`子底稿 ${subWpCode} 数据加载失败`)
      return {}
    }
  }

  return {
    allResponses,
    loading,
    saving,
    loadAll,
    hydrate,
    saveImmediate,
    saveDebouncedText,
    saveItemsFromEvent,
    flushPendingSave,
    getField,
    setFieldImmediate,
    loadSubWorkpaperData,
    tbReference,
    loadTbReference,
    stateOf: persistence.stateOf,
    cancelPendingSave: persistence.cancel,
  }
}

export default useD2FormData
