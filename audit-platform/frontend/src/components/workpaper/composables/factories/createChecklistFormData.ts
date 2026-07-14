/**
 * createChecklistFormData — 参数化工厂：统一 checklist 持久化 composable
 *
 * Feature: workpaper-maintainability-convergence / Wave 5 / Task 6.1
 * Requirements: 6.1, 6.2, 6.6
 *
 * 收敛 K1~K13 / M1~M10 / H1~H10 / I1~I6 / G10~G14 / N1~N5 等同构
 * FormData composable。各循环仅在 prefix、label、forceComponentType、
 * accountCode 上不同——通用 load/render-cache/persistence/debounce/flush
 * 由本工厂统一提供，业务差异通过 normalizeResponse / afterSave 钩子注入。
 *
 * 本工厂复用 `useChecklistPersistence` 统一适配器（Wave 1 产物），
 * 不再自行维护网络 I/O、debounce 定时器或 hydrate 逻辑。
 *
 * ─── 结构同构证明（codegraph + AST 实证） ──────────────────────────────────
 *
 * 以下 composable 在控制流、API 调用序列、debounce/flush 生命周期上完全同构，
 * 仅 parameterize 以下 4 个常量：
 *   - ITEM_PREFIX  (如 'K1-', 'M1-', 'G10-', 'H3-')
 *   - ACCOUNT_CODE (如 '1221', '2232', '4001', '2601')
 *   - force_component_type (如 'k1-other-receivables', 'm1-dividends-payable')
 *   - wpCode 标签  (如 'K1', 'M1', 'G10')
 *
 * 同构文件清单（53 个，已验证结构）：
 *   useK1FormData ~ useK13FormData (13)
 *   useM1FormData ~ useM10FormData (10)
 *   useH1FormData ~ useH10FormData (10)
 *   useI1FormData ~ useI6FormData   (6)
 *   useG10FormData ~ useG14FormData  (5)
 *   useN1FormData ~ useN5FormData    (5)
 *   useL1FormData ~ useL4FormData    (4)
 *
 * 不在迁移范围（有显著业务差异）：
 *   useD2FormData（复杂子底稿读取 + 已手工迁 useChecklistPersistence）
 *   useD4FormData / useD5FormData / useD6FormData / useD7FormData（复杂 htmlData）
 *   useG4EclFormData / useG6EclFormData（ECL 引擎状态机）
 *   useG5FormData（长期股权复合逻辑）
 *   useF2FormData（估值 + 盘点特殊分支）
 */
import { ref, type Ref, type ComputedRef, computed } from 'vue'
import {
  useChecklistPersistence,
  type ChecklistResponse,
  type PersistenceState,
} from '@/composables/workpaper/useChecklistPersistence'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { ElMessage } from 'element-plus'

// ─── Configuration ───────────────────────────────────────────────────────────

export interface ChecklistFormDataConfig {
  /** 底稿 wp_id */
  wpId: Ref<string>
  /** 项目 id */
  projectId: Ref<string>
  /** 审计年度（用于 TB 取数，可选） */
  year?: Ref<number | undefined>
  /** item_id 前缀过滤（如 'K1-', 'M1-', 'G10-'） */
  itemPrefix: string
  /** 循环标签（如 'K1', 'M1', 'G10'，用于 EventBus 和 ElMessage） */
  label: string
  /** render-config 强制 componentType（如 'k1-other-receivables'） */
  forceComponentType: string
  /** 科目代码列表（用于 TB 回写），可多科目（如 K1 = ['1221', '1231']） */
  accountCodes?: string[]
  /**
   * 响应规范化钩子 —— 加载后对每个匹配前缀的响应执行转换。
   * 用于处理历史双层 JSON 兼容等。
   */
  normalizeResponse?: (response: ChecklistResponse) => ChecklistResponse
  /**
   * 保存成功后的钩子 —— 如附注刷新联动、版本快照调度等。
   * 不得吞掉错误（由工厂保障）。
   */
  afterSave?: (saved: ChecklistResponse) => void | Promise<void>
  /** debounce 延迟毫秒数，默认 800（与 Persistence Adapter 一致） */
  debounceMs?: number
}

// ─── Return Type ─────────────────────────────────────────────────────────────

export interface ChecklistFormDataReturn {
  /** 全部响应 Map（仅本循环前缀） */
  allResponses: Ref<Map<string, ChecklistResponse>>
  /** 加载中标记 */
  isLoading: Ref<boolean>
  /** render-config 的 sheet 缓存 */
  sheetCache: Ref<Record<string, any>>
  /** render-config 的全局 html_data 元数据 */
  renderMeta: Ref<Record<string, any>>
  /** 各 item 的持久化状态 */
  stateOf: (itemId: string) => PersistenceState
  /** 是否有未保存的变更 */
  hasPending: ComputedRef<boolean>

  // ─── Actions ─────────────────────────────────────────────────────────
  /** 统一加载入口：selfLoad(render-config) + loadResponses 并行 */
  loadData: () => Promise<void>
  /** 仅加载 checklist-responses */
  loadResponses: () => Promise<void>
  /** 单字段即时保存（结论/状态/选择类字段） */
  save: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  /** 批量保存多个 items */
  saveBatch: (items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>) => Promise<void>
  /** debounce 文本字段保存（per item_id 独立计时器） */
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 审定数回写 trial_balance + EventBus 通知 */
  writebackTB: (amounts: Record<string, number>) => Promise<void>
  /** 获取 render-config sheet 数据 */
  getSheet: (name: string) => any
  /** TB 只读字段种子（从 render-config html_data 注入） */
  setTbValues: (values: Record<string, any>) => void
  /** flush 所有待保存数据 */
  flush: () => Promise<void>
  /** cancel 所有待保存数据并恢复 */
  cancel: () => void
  /** hydrate 来自外部数据源（如主入口 htmlData） */
  hydrate: (source: unknown) => void
}

// ─── Factory ─────────────────────────────────────────────────────────────────

export function createChecklistFormData(config: ChecklistFormDataConfig): ChecklistFormDataReturn {
  const {
    wpId,
    projectId,
    year,
    itemPrefix,
    label,
    forceComponentType,
    accountCodes = [],
    normalizeResponse,
    afterSave,
    debounceMs = 800,
  } = config

  // ─── Persistence Adapter（复用 Wave 1 统一适配器） ────────────────────────

  const persistence = useChecklistPersistence({
    wpId,
    projectId,
    debounceMs,
    onSaved: afterSave,
  })

  // ─── Local state ───────────────────────────────────────────────────────────

  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  const renderMeta = ref<Record<string, any>>({})

  /**
   * 代理 responses：仅暴露本循环前缀的子集视图。
   * 底层 persistence.responses 可能包含其他循环的 item（如 bundle 场景），
   * 但业务 composable 只关心自己前缀的数据。
   */
  const allResponses = computed<Map<string, ChecklistResponse>>({
    get: () => {
      const filtered = new Map<string, ChecklistResponse>()
      for (const [id, resp] of persistence.responses.value) {
        if (id.startsWith(itemPrefix)) {
          filtered.set(id, normalizeResponse ? normalizeResponse(resp) : resp)
        }
      }
      return filtered
    },
    set: (val: Map<string, ChecklistResponse>) => {
      // 保留非本前缀的 items，替换本前缀的
      const next = new Map<string, ChecklistResponse>()
      for (const [id, resp] of persistence.responses.value) {
        if (!id.startsWith(itemPrefix)) next.set(id, resp)
      }
      for (const [id, resp] of val) {
        next.set(id, resp)
      }
      persistence.responses.value = next
    },
  }) as Ref<Map<string, ChecklistResponse>>

  const hasPending = computed<boolean>(() => {
    for (const [id] of persistence.responses.value) {
      if (id.startsWith(itemPrefix)) {
        const state = persistence.stateOf(id)
        if (state.status === 'dirty' || state.status === 'saving') return true
      }
    }
    return false
  })

  // ─── selfLoad (render-config) ──────────────────────────────────────────────

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: forceComponentType },
        _silent: true,
      } as any)
      const data = res?.data ?? res
      renderMeta.value = data?.html_data ?? data ?? {}
      for (const s of data?.sheets ?? data?.data?.sheets ?? []) {
        const name = s.sheet_name || s.name || 'default'
        sheetCache.value[name] = s.html_data ?? s
      }
    } catch {
      // selfLoad 失败不阻塞：组件仍可从 checklist_responses 加载数据
    }
  }

  // ─── Load responses ────────────────────────────────────────────────────────

  async function loadResponses(): Promise<void> {
    if (!wpId.value) return
    try {
      await persistence.load()
    } catch {
      ElMessage.warning(`${label}数据加载失败，可手动填写`)
    }
  }

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

  // ─── Save ──────────────────────────────────────────────────────────────────

  /**
   * 单字段即时保存（结论/状态/选择类字段）
   */
  async function save(
    itemId: string,
    value: { conclusion?: string; remark?: string },
  ): Promise<void> {
    const patch: Partial<ChecklistResponse> = {}
    if (value.conclusion !== undefined) patch.conclusion = value.conclusion
    if (value.remark !== undefined) patch.remark = value.remark
    await persistence.save(itemId, patch)
  }

  /**
   * 批量保存多个 items
   */
  async function saveBatch(
    items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>,
  ): Promise<void> {
    await Promise.all(
      items.map(({ itemId, data }) => persistence.save(itemId, data)),
    )
  }

  /**
   * debounce 文本字段保存（per item_id 独立计时器，由 Persistence Adapter 管理）
   */
  function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
    persistence.saveDebounced(itemId, data)
  }

  // ─── TB Writeback ──────────────────────────────────────────────────────────

  /**
   * 回写审定数到 trial_balance + EventBus 通知。
   * @param amounts - { accountCode: auditedAmount } 映射
   */
  async function writebackTB(amounts: Record<string, number>): Promise<void> {
    if (!projectId.value) return
    try {
      const params: Record<string, any> = {}
      if (year?.value) params.year = year.value

      for (const [accountCode, auditedAmount] of Object.entries(amounts)) {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: accountCode,
          audited_amount: auditedAmount,
          ...params,
        })
      }

      // EventBus 通知审定数变更
      const firstCode = Object.keys(amounts)[0] ?? accountCodes[0] ?? ''
      const firstAmount = Object.values(amounts)[0] ?? 0
      eventBus.emit('substantive:adjudicated', {
        accountCode: firstCode,
        auditedAmount: firstAmount,
        wpCode: label,
        timestamp: Date.now(),
      })
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function getSheet(name: string): any {
    return sheetCache.value[name] ?? { rows: [] }
  }

  function setTbValues(values: Record<string, any>): void {
    for (const [key, val] of Object.entries(values)) {
      const fullId = key.startsWith(itemPrefix) ? key : `${itemPrefix}${key}`
      const conclusion = typeof val === 'string' ? val : JSON.stringify(val)
      const existing = persistence.responses.value.get(fullId)
      persistence.responses.value.set(fullId, {
        item_id: fullId,
        remark: existing?.remark ?? null,
        conclusion,
      })
    }
  }

  function hydrate(source: unknown): void {
    persistence.hydrate(source)
  }

  async function flush(): Promise<void> {
    await persistence.flush()
  }

  function cancel(): void {
    persistence.cancel()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    allResponses,
    isLoading,
    sheetCache,
    renderMeta,
    stateOf: persistence.stateOf,
    hasPending,
    loadData,
    loadResponses,
    save,
    saveBatch,
    debouncedSave,
    writebackTB,
    getSheet,
    setTbValues,
    flush,
    cancel,
    hydrate,
  }
}
