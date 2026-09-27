/**
 * useH10FormData — H10 资产处置损益底稿数据层
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { H10_ACCOUNT_CODE } from './h10Constants'
import { parseNum } from './useH10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

const DRAFT_PREFIX = 'h10-draft'

function draftKey(wpId: string, itemId: string): string {
  return `${DRAFT_PREFIX}:${wpId}:${itemId}`
}

export function useH10FormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const renderMeta = ref<Record<string, any>>({})
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()

  function restoreDrafts(): void {
    if (!opts.wpId.value) return
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(`${DRAFT_PREFIX}:${opts.wpId.value}:`)) continue
      try {
        const itemId = key.slice(`${DRAFT_PREFIX}:${opts.wpId.value}:`.length)
        const updated = JSON.parse(localStorage.getItem(key) || '') as ChecklistResponse
        if (itemId && updated?.item_id) {
          allResponses.value.set(itemId, updated)
          void saveImmediate(itemId, updated, 1)
          localStorage.removeItem(key)
        }
      } catch { /* ignore corrupt draft */ }
    }
  }

  async function loadResponses() {
    if (!opts.wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        const id = r.item_id ?? ''
        if (id.startsWith('H10')) {
          map.set(id, { item_id: id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
        }
      }
      allResponses.value = map
      restoreDrafts()
    } catch {
      ElMessage.warning('H10数据加载失败，可手动填写')
    }
  }

  async function loadRenderConfig() {
    const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
      params: { force_component_type: 'h10-asset-disposal-income' },
      _silent: true,
    } as any)
    const data = res?.data ?? res
    renderMeta.value = data?.html_data ?? data ?? {}
    for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
      const name = s.sheet_name || s.name || 'default'
      sheetCache.value[name] = s.html_data ?? s
    }
  }

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([loadResponses(), loadRenderConfig()])
    } finally {
      isLoading.value = false
    }
  }

  async function saveImmediate(
    itemId: string,
    data: Partial<ChecklistResponse>,
    retries = 3,
  ): Promise<void> {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    for (let i = 0; i < retries; i++) {
      try {
        await api.put(`/api/workpapers/${opts.wpId.value}/checklist-responses`, {
          project_id: opts.projectId.value,
          items: [{ item_id: itemId, conclusion: updated.conclusion, remark: updated.remark }],
        })
        try {
          localStorage.removeItem(draftKey(opts.wpId.value, itemId))
        } catch { /* ignore */ }
        return
      } catch {
        if (i < retries - 1) await new Promise((r) => setTimeout(r, 500 * 2 ** i))
      }
    }
    try {
      localStorage.setItem(draftKey(opts.wpId.value, itemId), JSON.stringify(updated))
      ElMessage.warning(`H10 数据暂存本地（${itemId}），网络恢复后将自动同步`)
    } catch { /* ignore */ }
  }

  /** 还在防抖窗口里、尚未发出的载荷（item_id → payload）。 */
  const _pending = new Map<string, ChecklistResponse>()

  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated = { ...existing, ...data, item_id: itemId }
    allResponses.value.set(itemId, updated)
    _pending.set(itemId, updated)
    const prev = _debounceTimers.get(itemId)
    if (prev) clearTimeout(prev)
    _debounceTimers.set(itemId, setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pending.delete(itemId)
      void saveImmediate(itemId, updated)
    }, 2000))
  }

  /**
   * 清防抖 + 立即落库，**await 到真正写完**。切「在线编辑」前的必经一步。
   *
   * 🔴 防抖窗口是 **2000ms**（全 H 与 H3/H5 并列最长）：漏 flush 就会丢最多 2 秒的编辑，
   * 而 materialize 出的 xlsx 不会有任何提示。
   *
   * 🔴 逐个 await 而不是 `Promise.all`：`saveImmediate` 自带 3 次重试 + 指数退避，并发发多个
   * PUT 到同一个 wpId 会让后端的 upsert 相互覆盖（这也是原 `debouncedSave` 按 item 拆 PUT
   * 的原因）。待写盘最多就是屏幕上改过的那几个 item，串行代价可忽略。
   */
  async function flushPendingSaves(): Promise<void> {
    for (const t of _debounceTimers.values()) clearTimeout(t)
    _debounceTimers.clear()
    if (_pending.size === 0) return
    const batch = [..._pending.entries()]
    _pending.clear()
    for (const [itemId, payload] of batch) {
      await saveImmediate(itemId, payload)
    }
  }

  /** 6115 损益类：贷方发生 − 借方发生 */
  async function fetchTrialBalanceAmount(): Promise<number | null> {
    const seeded = renderMeta.value?.tb_values?.current_amount
    if (seeded != null && seeded !== '') return Number(seeded)
    if (!opts.projectId.value) return null
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: H10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(H10_ACCOUNT_CODE),
      )
      if (!hit) return null
      const credit = parseNum(hit.credit_amount ?? hit.period_credit)
      const debit = parseNum(hit.debit_amount ?? hit.period_debit)
      return credit - debit
    } catch {
      return null
    }
  }

  // 注：原 writebackTB（PUT /trial-balance/writeback，科目 6115 资产处置损益 + saveImmediate）
  // 在 H10-1 迁移到显式发布门后成为零消费死代码，已移除（原被 useH10Adjudication.publishAdjudicated
  // 的 mount/1.5s debounce 自动写 + GtH10 跨 wp 监听自动写调用，三者均自动写、违反 Req 1，已一并移除）。
  // 活路径 = useH10Adjudication.publishToTb（中文二次确认 → POST publish-to-tb 科目 6115 occurrence 发生额）。
  // spec: tb-writeback-explicit-publish-gate Task 10 / Req 1,2,6,8。

  function getSheet(name: string) {
    return sheetCache.value[name] ?? { rows: [] }
  }

  /** H6 disposal:completed → 追加 H10-2 明细行（主入口唯一监听，防重复） */
  function handleDisposalCompleted(payload: Record<string, unknown>): void {
    const ITEM_ID = 'H10-detail-rows'
    const linkageId = String(payload.linkageId ?? `h6-${Date.now()}`)
    let rows: any[] = []
    try {
      const raw = allResponses.value.get(ITEM_ID)?.remark
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) rows = parsed
      }
    } catch { /* ignore */ }
    if (rows.some((r) => r.linkageId === linkageId)) return
    rows = [
      ...rows,
      {
        id: linkageId,
        linkageId,
        assetName: payload.assetName ?? 'H6清理结转',
        assetType: payload.assetType ?? '固定资产',
        sourceWp: 'H6',
        disposalIncome: payload.disposalIncome,
        disposalGainLoss: payload.disposalGainLoss ?? payload.disposalIncome ?? 0,
        originalCost: payload.netBookValue,
      },
    ]
    debouncedSave(ITEM_ID, { remark: JSON.stringify(rows) })
  }

  /** H1~H8 disposal:source-updated → 更新/追加明细来源行 */
  function handleSourceDisposalUpdated(payload: Record<string, unknown>): void {
    const ITEM_ID = 'H10-detail-rows'
    const linkageId = String(payload.linkageId ?? `${payload.sourceWp}-${Date.now()}`)
    let rows: any[] = []
    try {
      const raw = allResponses.value.get(ITEM_ID)?.remark
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) rows = parsed
      }
    } catch { /* ignore */ }
    const idx = rows.findIndex((r) => r.linkageId === linkageId)
    const entry = {
      ...(idx >= 0 ? rows[idx] : { id: linkageId }),
      linkageId,
      assetName: payload.assetName ?? rows[idx]?.assetName ?? '',
      sourceWp: payload.sourceWp ?? 'OTHER',
      sourceIndex: payload.sourceIndex ?? '',
      disposalGainLoss: payload.disposalGainLoss,
    }
    if (idx >= 0) rows[idx] = entry
    else rows.push(entry)
    debouncedSave(ITEM_ID, { remark: JSON.stringify(rows) })
  }

  onScopeDispose(() => {
    // 🔴 原实现是裸 `clearTimeout`：防抖窗口内那批改动**直接丢掉**且无提示
    //    （H9/H8/H6 三个宿主同源缺陷已修，这里是同一条）。改为先落库再退出。
    void flushPendingSaves()
  })

  return {
    isLoading,
    sheetCache,
    allResponses,
    renderMeta,
    accountCode: H10_ACCOUNT_CODE,
    loadAll,
    getSheet,
    saveImmediate,
    debouncedSave,
    flushPendingSaves,
    fetchTrialBalanceAmount,
    handleDisposalCompleted,
    handleSourceDisposalUpdated,
  }
}
