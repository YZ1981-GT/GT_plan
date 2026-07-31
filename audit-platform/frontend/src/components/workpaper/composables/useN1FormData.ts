/**
 * useN1FormData — N1 递延所得税资产数据加载/debounce保存/即时保存/TB回写
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.7, 8.1-8.3
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "N1-{sheet}-{field}"（如 "N1-1-adjudicated-amount", "N1-2-temp-diff"）
 * - writebackTB(1811): 审定数回写 trial_balance 科目 1811 递延所得税资产（**期末余额！**）
 * - tbSeed: 从 htmlData.trial_balance 读取TB种子数据（期初/借方/贷方/期末）
 * - EventBus: 回写成功后发布 'substantive:adjudicated'
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * ─── 资产类方向铁律（与N2/N3负债类、N4/N5损益类根本不同！） ───
 * 科目：1811 递延所得税资产（**借方/资产类！取期末余额**）
 * 期末余额 = 期初余额 + 本期借方 - 本期贷方（借增贷减）
 * 从 tb_balance 取 期末余额（direction=借）
 * 回写TB用期末余额口径（audited_amount = 审定期末余额，NOT 发生额！）
 * ─────────────────────────────────────────────────────────────
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseN1FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string> | string
  /** 审计年度（/ledger/balance 端点 year 为必填，缺失会 422） */
  year?: Ref<number | undefined>
}

/** TB种子数据（资产类科目1811：期初/借方/贷方/期末） */
export interface TbSeedData {
  /** 期初余额 */
  beginBalance: number
  /** 本期借方发生额（资产增加） */
  debitAmount: number
  /** 本期贷方发生额（资产减少） */
  creditAmount: number
  /** 期末余额 = 期初 + 借方 - 贷方 */
  endBalance: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'N1-'
const ACCOUNT_CODE = '1811' // 递延所得税资产（借方/资产类！取期末余额）

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1FormData(options: UseN1FormDataOptions) {
  const { wpId, projectId, year } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  /** TB种子数据（资产类：期初/借方/贷方/期末余额） */
  const tbSeed = ref<TbSeedData>({ beginBalance: 0, debitAmount: 0, creditAmount: 0, endBalance: 0 })

  /**
   * 审定表未审数预填（后端 `_build_adjudication_prefill` 按 1811 子科目归类）。
   * 结构：{ 暂时性差异类别: {opening, closing} }；仅无持久化时由 N1-1 套用。
   */
  const adjudicationPrefill = ref<Record<string, { opening: number; closing: number }>>({})

  /**
   * 递延所得税负债 TB 种子（后端按报表行 `BS-067` 映射解析出的科目集取数，
   * 贷方科目已 `abs()` 归一为披露口径正数）。
   */
  const tbLiabilitySeed = ref<TbSeedData>({
    beginBalance: 0,
    debitAmount: 0,
    creditAmount: 0,
    endBalance: 0,
  })

  /**
   * 披露表负债段预填（后端 `_build_liability_prefill` 按 2901 叶子子科目归槽）。
   * 结构：{ 语义槽: {opening, closing} }；槽 → 两版显示名的映射在
   * `useN1DisclosureTables.N1_LIABILITY_SLOT_LABEL` 单一真源。
   */
  const liabilityPrefill = ref<Record<string, { opening: number; closing: number }>>({})

  /**
   * 取数溯源：报表行规则映射（`report_config`）解析出的科目集。
   * 供底稿展示「本页取数来自哪些科目、依据哪个报表行」。
   */
  const tbSourceCodes = ref<{
    asset: { row_code: string; codes: string[] }
    liability: { row_code: string; codes: string[] }
  }>({
    asset: { row_code: '', codes: [] },
    liability: { row_code: '', codes: [] },
  })

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * selfLoad: 当组件在bundle内嵌时无htmlData，自行加载render-config。
   * 用 _silent:true 避免触发全局404弹窗。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res: any = await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=n1-deferred-tax-assets`,
        { _silent: true } as any,
      )
      // 铁律：render-config 是 TB 取数的单一真源（后端 _n1_deferred_tax_assets.render
      // 已按 active dataset + 叶子口径聚合科目1811），此前 selfLoad 把响应直接丢弃，
      // 前端又另走 /ledger/balance（缺 year → 422）→ TB 种子恒 0。
      _applyTbSeedFromRenderConfig(res)
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  /** `{槽: {opening, closing}}` 归一（NaN / 缺字段 → 0） */
  function _normPrefill(raw: unknown): Record<string, { opening: number; closing: number }> {
    if (!raw || typeof raw !== 'object') return {}
    const out: Record<string, { opening: number; closing: number }> = {}
    for (const [k, v] of Object.entries(raw as Record<string, any>)) {
      out[k] = { opening: Number(v?.opening) || 0, closing: Number(v?.closing) || 0 }
    }
    return out
  }

  function _normTb(raw: any): TbSeedData {
    return {
      beginBalance: Number(raw?.begin_balance) || 0,
      debitAmount: Number(raw?.debit_amount) || 0,
      creditAmount: Number(raw?.credit_amount) || 0,
      endBalance: Number(raw?.end_balance) || 0,
    }
  }

  /**
   * 从 render-config 响应提取四表取数种子。
   *
   * 🔴 以「首个含 `trial_balance` 的 sheet」为锚点，同一 `html_data` 的兄弟键
   * （`trial_balance_liability` / `adjudication_prefill` / `liability_prefill` /
   * `tb_source_codes`）一并抽取；后端未重启导致新键缺失时逐个静默跳过，
   * 不能让披露表报错。
   */
  function _applyTbSeedFromRenderConfig(res: any): boolean {
    const cfg = res?.data ?? res
    const sheets: any[] = cfg?.sheets ?? []
    for (const s of sheets) {
      const h = s?.html_data
      const tb = h?.trial_balance
      if (!tb) continue
      tbSeed.value = _normTb(tb)
      if (h?.trial_balance_liability) tbLiabilitySeed.value = _normTb(h.trial_balance_liability)
      const prefill = _normPrefill(h?.adjudication_prefill)
      if (Object.keys(prefill).length > 0) adjudicationPrefill.value = prefill
      const liabPrefill = _normPrefill(h?.liability_prefill)
      if (Object.keys(liabPrefill).length > 0) liabilityPrefill.value = liabPrefill
      const src = h?.tb_source_codes
      if (src && typeof src === 'object') {
        tbSourceCodes.value = {
          asset: {
            row_code: String(src.asset?.row_code ?? ''),
            codes: Array.isArray(src.asset?.codes) ? src.asset.codes.map(String) : [],
          },
          liability: {
            row_code: String(src.liability?.row_code ?? ''),
            codes: Array.isArray(src.liability?.codes) ? src.liability.codes.map(String) : [],
          },
        }
      }
      return true
    }
    return false
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 N1 数据（item_id 前缀 "N1-"）
   */
  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith(ITEM_PREFIX)) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
          })
        }
      }
      allResponses.value = map
    } catch {
      ElMessage.warning('N1数据加载失败，可手动填写')
    }
  }

  // ─── Load TB seed data（资产类！期末余额） ──────────────────────────────────

  /**
   * 从 tb_balance 取科目1811的余额数据。
   *
   * 资产类科目方向铁律：
   *   期末余额 = 期初余额 + 本期借方 - 本期贷方
   *   递延所得税资产为借方科目：借增贷减
   *   direction = 借
   *
   * API: GET /api/projects/{pid}/ledger/balance?account_code=1811
   * 返回: [{ account_code, begin_balance, debit_amount, credit_amount, end_balance, ... }]
   */
  async function loadTbSeed(): Promise<void> {
    if (!projectId.value) return
    // ⚠️ /ledger/balance 的 year 为必填 Query，缺失直接 422。
    // 无年度时不调用（TB 种子已由 selfLoad 从 render-config 取得）。
    const yr = year?.value
    if (!yr) return
    try {
      const data = await api.get(
        `/api/projects/${projectId.value}/ledger/balance`,
        { params: { account_code: ACCOUNT_CODE, year: yr }, _silent: true } as any,
      )
      const rows: any[] = Array.isArray(data) ? data : (data?.data ?? [])
      // 找到1811科目行
      const row = rows.find((r: any) => r.account_code === ACCOUNT_CODE)
      if (row) {
        const beginBalance = Number(row.begin_balance) || 0
        const debitAmount = Number(row.debit_amount) || 0
        const creditAmount = Number(row.credit_amount) || 0
        // 资产类期末余额 = 期初 + 借方 - 贷方
        const endBalance = Number(row.end_balance) || (beginBalance + debitAmount - creditAmount)
        tbSeed.value = { beginBalance, debitAmount, creditAmount, endBalance }
      }
      // 未匹配到科目行时保持既有种子（不清零，避免覆盖 render-config 已取到的值）
    } catch {
      // tb_balance 无数据/端点异常时不阻塞，保持既有种子
    }
  }

  /** TB 种子是否已有非零值（判断是否还需要走 API 兜底） */
  function _hasTbSeed(): boolean {
    const s = tbSeed.value
    return !!(s.beginBalance || s.debitAmount || s.creditAmount || s.endBalance)
  }

  // ─── loadData（统一加载入口） ─────────────────────────────────────────────

  /**
   * 统一加载入口：render-config（TB 单一真源）+ checklist_responses 并行，
   * 仅当 render 未给出 TB 时才走 /ledger/balance 兜底（避免双源互相覆盖）。
   */
  async function loadData(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([selfLoad(), loadResponses()])
      if (!_hasTbSeed()) await loadTbSeed()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Save core ─────────────────────────────────────────────────────────────

  async function _doSave(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  // ─── getField / setField（便捷接口） ──────────────────────────────────────

  /**
   * 获取指定 sheet + field 的值
   * @param sheet - 如 "1", "2", "3", "4", "5"（不含N1-前缀，最终item_id为 "N1-1-xxx"）
   * @param field - 如 "adjudicated-amount", "temp-diff-total", "loss-recognizable"
   * @returns 存储的值（conclusion 字段）
   */
  function getField(sheet: string, field: string): any {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const resp = allResponses.value.get(itemId)
    if (!resp) return null
    // 尝试 JSON 解析（支持存储对象/数组）
    if (resp.conclusion) {
      try {
        return JSON.parse(resp.conclusion)
      } catch {
        return resp.conclusion
      }
    }
    return null
  }

  /**
   * 设置指定 sheet + field 的值（即时保存）
   * @param sheet - 如 "1", "2", "3", "4", "5"
   * @param field - 如 "adjudicated-amount", "temp-diff-total"
   * @param value - 要存储的值（会 JSON.stringify 非字符串值）
   */
  async function setField(sheet: string, field: string, value: any): Promise<void> {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
    await saveField(itemId, { conclusion })
  }

  /**
   * setTbValues — 从 render-config html_data 的 TB 种子数据设置只读字段。
   * 用于 FormData 初始化时接收后端自动取数（期初/借方/贷方/期末等TB字段）。
   * @param values - Record<itemId, value>
   */
  function setTbValues(values: Record<string, any>): void {
    for (const [itemId, value] of Object.entries(values)) {
      const fullId = itemId.startsWith(ITEM_PREFIX) ? itemId : `${ITEM_PREFIX}${itemId}`
      const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
      const existing = allResponses.value.get(fullId) || { item_id: fullId, conclusion: null, remark: null }
      allResponses.value.set(fullId, { ...existing, conclusion })
    }
  }

  // ─── saveField (单字段保存，即时) ──────────────────────────────────────────

  /**
   * 保存单个字段（结论/状态/选择类字段立即保存）
   * @param itemId - 如 "N1-1-adjudicated-amount"
   * @param value - { conclusion?, remark? }
   */
  async function saveField(itemId: string, value: { conclusion?: string; remark?: string }): Promise<void> {
    // 取消该 item 的 debounce 定时器
    const timer = _debounceTimers.get(itemId)
    if (timer) {
      clearTimeout(timer)
      _debounceTimers.delete(itemId)
    }
    _pendingItems.delete(itemId)

    // 合并到 allResponses
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(value.conclusion !== undefined ? { conclusion: value.conclusion } : {}),
      ...(value.remark !== undefined ? { remark: value.remark } : {}),
    }
    allResponses.value.set(itemId, updated)

    await _doSave([updated])
  }

  // ─── saveBatch (批量保存) ──────────────────────────────────────────────────

  /**
   * 批量保存多个 items
   */
  async function saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>): Promise<void> {
    // 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失
    //    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。
    //    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。
    const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
    const toSave: ChecklistResponse[] = []
    for (const { itemId, data } of deduped) {
      // 取消 debounce
      const timer = _debounceTimers.get(itemId)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(itemId)
      }
      _pendingItems.delete(itemId)

      const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const updated: ChecklistResponse = {
        ...existing,
        ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
        ...(data.remark !== undefined ? { remark: data.remark } : {}),
      }
      allResponses.value.set(itemId, updated)
      toSave.push(updated)
    }

    await _doSave(toSave)
  }

  // ─── debouncedSave (文本字段 debounce 2s) ──────────────────────────────────

  /**
   * debounce 2s 文本字段保存（per item_id 独立计时器）
   */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    // 合并到 allResponses
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const updated: ChecklistResponse = {
      ...existing,
      ...(data.conclusion !== undefined ? { conclusion: data.conclusion } : {}),
      ...(data.remark !== undefined ? { remark: data.remark } : {}),
    }
    allResponses.value.set(itemId, updated)
    _pendingItems.add(itemId)

    // 重置该 item 的定时器
    const prevTimer = _debounceTimers.get(itemId)
    if (prevTimer) clearTimeout(prevTimer)

    const timer = setTimeout(() => {
      _debounceTimers.delete(itemId)
      _pendingItems.delete(itemId)
      _doSave([updated])
    }, DEBOUNCE_MS)
    _debounceTimers.set(itemId, timer)
  }

  // ─── writebackTB (回写审定数到 trial_balance 1811, 期末余额口径) ─────────────

  /**
   * 回写审定数到 trial_balance（科目 1811 递延所得税资产，**期末余额口径！**）。
   *
   * ⚠️ 资产类特殊：
   * - 回写的 audited_amount 代表审定的期末余额（非发生额！）
   * - 递延所得税资产为借方科目：正值=资产余额
   * - 期末余额 = 期初 + 本期借方(确认递延税资产) - 本期贷方(转回递延税资产)
   *
   * 并发布 EventBus 'substantive:adjudicated' + 'deferred-tax:asset-updated' 事件。
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!projectId.value) return
    try {
      await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE,
        audited_amount: auditedAmount,
      })
      // 发布 EventBus 通知审定数变更（附注等组件订阅刷新）
      eventBus.emit('substantive:adjudicated', {
        accountCode: ACCOUNT_CODE,
        auditedAmount,
        wpCode: 'N1',
        timestamp: Date.now(),
      })
      // 发布递延所得税资产更新事件（供N5递延所得税费用核对表接收）
      eventBus.emit('deferred-tax:asset-updated', {
        accountCode: ACCOUNT_CODE,
        auditedAmount,
        // 本期变动额 = 审定期末余额 - 期初余额（供N5核对递延所得税费用）
        periodChange: auditedAmount - tbSeed.value.beginBalance,
        wpCode: 'N1',
        timestamp: Date.now(),
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── Flush（组件卸载） ───────────────────────────────────────────────────

  function _flushPending(): void {
    // 清除所有 debounce 定时器
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    // 保存所有 pending items
    if (_pendingItems.size > 0) {
      const items: ChecklistResponse[] = []
      for (const itemId of _pendingItems) {
        const resp = allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) {
        _doSave(items)
      }
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    isLoading,
    allResponses,
    tbSeed,
    adjudicationPrefill,
    tbLiabilitySeed,
    liabilityPrefill,
    tbSourceCodes,
    // Actions
    loadData,
    getField,
    setField,
    setTbValues,
    saveField,
    saveBatch,
    debouncedSave,
    writebackTB,
  }
}

export default useN1FormData
