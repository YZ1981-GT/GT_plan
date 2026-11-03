/**
 * useM8FormData — M8 一般风险准备数据加载/debounce保存/即时保存/TB回写
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6
 *
 * 职责：
 * - selfLoad(): bundle内嵌场景从 render-config 加载上下文
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 "M8-{sheet}-{field}"（如 "M8-1-adjudicated-amount", "M8-2-detail-total"）
 * - writebackTB: 审定数回写 trial_balance 的一般风险准备科目 —— 该科目没有统一标准码，
 *   码取 render 下发的本项目语义定位结果（`tb_source_codes.gross_standard`）；定位不到 / 定位到
 *   多个标准码时**不发布**（`publishBlockReason` 给原因），不拿别的科目顶替
 *   （2026-10-24 前写死 4104 = 利润分配，发布会覆盖未分配利润的试算表行）
 * - EventBus: 回写成功后发布 'substantive:adjudicated'
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - 组件卸载时 flush 未保存数据（onScopeDispose）
 *
 * ─── 权益类方向铁律 ───
 * 科目：一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业从净利润中计提时贷方增加，转回/使用时借方减少
 * 回写TB用期末余额口径（audited_amount = 审定期末余额）
 * ─── 金融企业专属 ───
 * 一般风险准备仅适用于金融企业（银行/证券/保险），非金融企业不适用
 * 原则上不低于风险资产期末余额的1.5%
 * ─────────────────────────────────────────────────
 */
import { computed, ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { mAccountCodeOf, mPublishBlockReason, pickMTbSourceCodes, useMTbSource } from './mCycleAccountScope'
import type { TbSourceCodes } from './shared/tbSourceCodes'
import { readM8FieldValue } from './mEquityDisclosureForm'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export interface UseM8FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetName?: Ref<string> | string
  /**
   * render 溯源（`tb_source_codes`）。不传时取主入口 GtM8 provide 的 `tbSourceCodes`；
   * 都没有（bundle 内嵌）时用 selfLoad 拉到的 render-config。
   */
  tbSourceCodes?: Ref<TbSourceCodes | null | undefined>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000
const ITEM_PREFIX = 'M8-'
/** 审定表 sheet 名（含子码 M8-1，供后端 extract_determination_wp_code 解出） */
const DETERMINATION_SHEET_NAME = '审定表M8-1'

/** render-config 响应里取 `tb_source_codes`（html_data 在 `sheets[].html_data`，兼容顶层） */
function pickRenderConfigTbSource(res: any): TbSourceCodes | null {
  const cfg = res?.data ?? res
  for (const s of Array.isArray(cfg?.sheets) ? cfg.sheets : []) {
    const found = pickMTbSourceCodes(s?.html_data)
    if (found) return found
  }
  return pickMTbSourceCodes(cfg?.html_data) ?? pickMTbSourceCodes(cfg)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useM8FormData(options: UseM8FormDataOptions) {
  const { wpId, projectId } = options

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const isLoading = ref(false)

  // ─── 科目定位（一般风险准备没有统一标准码） ─────────────────────────────────
  const providedSrc = useMTbSource(options.tbSourceCodes)
  const selfLoadedSrc = ref<TbSourceCodes | null>(null)
  const tbSource = computed<TbSourceCodes | null>(() => providedSrc.value ?? selfLoadedSrc.value)
  /** 本项目一般风险准备的标准码；空串 = 定位不到（不发布、不带入） */
  const accountCode = computed(() => mAccountCodeOf('M8', tbSource.value))
  /** 不能发布到试算表的原因；空串 = 可以发布 */
  const publishBlockReason = computed(() => mPublishBlockReason('M8', tbSource.value))

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
      const res = await api.get(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=m8-general-risk-reserve`,
        { _silent: true } as any,
      )
      selfLoadedSrc.value = pickRenderConfigTbSource(res)
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 M8 数据（item_id 前缀 "M8-"）
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
      ElMessage.warning('M8数据加载失败，可手动填写')
    }
  }

  // ─── loadData（统一加载入口） ─────────────────────────────────────────────

  /**
   * 统一加载入口：selfLoad + loadResponses 并行
   */
  async function loadData(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([selfLoad(), loadResponses()])
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
      // 发送自定义事件（EventBus集成）
      window.dispatchEvent(new CustomEvent('m8:save-items'))
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
   * @param sheet - 如 "1", "2", "3", "4"（不含M8-前缀，最终item_id为 "M8-1-xxx"）
   * @param field - 如 "adjudicated-amount", "detail-total", "risk-provision"
   * @returns 存储的值（conclusion 字段）
   */
  function getField(sheet: string, field: string): any {
    return readM8FieldValue(allResponses.value.get(`${ITEM_PREFIX}${sheet}-${field}`))
  }

  /**
   * 设置指定 sheet + field 的值（即时保存）
   * @param sheet - 如 "1", "2", "3", "4"
   * @param field - 如 "adjudicated-amount", "detail-total", "risk-provision"
   * @param value - 要存储的值（会 JSON.stringify 非字符串值）
   */
  async function setField(sheet: string, field: string, value: any): Promise<void> {
    const itemId = `${ITEM_PREFIX}${sheet}-${field}`
    const conclusion = typeof value === 'string' ? value : JSON.stringify(value)
    await saveField(itemId, { conclusion })
  }

  /**
   * setTbValues — 从 render-config html_data 的 TB 种子数据设置只读字段。
   * 用于 FormData 初始化时接收后端自动取数（期初/未审等TB字段）。
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
   * @param itemId - 如 "M8-1-adjudicated-amount"
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

  // ─── writebackTB (回写审定数到 trial_balance 的一般风险准备科目) ─────────────────

  /**
   * 回写审定数到 trial_balance（一般风险准备科目，**贷方/权益类！金融企业专属**）。
   *
   * 科目码取本项目定位结果；`publishBlockReason` 非空时抛错、不发请求（调用方 catch 后提示原因）。
   *
   * 权益类贷方方向铁律：
   * - 期末 = 期初 + 贷方(增加：从净利润计提) - 借方(减少：转回/使用)
   * - 回写的 audited_amount 代表期末余额（正数=一般风险准备贷方余额）
   * - 金融企业从净利润中计提：贷方增加（原则上≥风险资产期末余额×1.5%）
   * - 转回/使用：借方减少（弥补已识别损失）
   *
   * 并发布 EventBus 'substantive:adjudicated' 事件通知其他组件（附注刷新等）。
   */
  // spec: tb-writeback-explicit-publish-gate Task 5 / Req 1,2,8。改走显式发布门：
  // 仅在用户显式确认（useM8Adjudication.publishToTb 二次确认）后调用 →
  // `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（携审定表 sheet 名 +
  // writeback_rows 预算行），后端发 publish_confirmed=True + token → handler 幂等回写。
  // 此前直调旧端点 PUT trial-balance/writeback 且由 watcher 数据变化自动触发（违反 Req 1）。
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (!wpId.value) return
    const blocked = publishBlockReason.value
    if (blocked) throw new Error(blocked)
    const code = accountCode.value
    await api.post(`/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`, {
      sheet_name: DETERMINATION_SHEET_NAME,
      writeback_rows: [
        { account_code: code, audited_amount: auditedAmount, amount_kind: 'balance' },
      ],
    })
    // 发布 EventBus 通知审定数变更（附注等组件订阅刷新）
    eventBus.emit('substantive:adjudicated', {
      accountCode: code,
      auditedAmount,
      wpCode: 'M8',
      timestamp: Date.now(),
    })
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
    /** 本项目一般风险准备标准码（空串 = 定位不到） */
    accountCode,
    /** 不能发布到试算表的原因（空串 = 可以发布） */
    publishBlockReason,
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

export default useM8FormData
