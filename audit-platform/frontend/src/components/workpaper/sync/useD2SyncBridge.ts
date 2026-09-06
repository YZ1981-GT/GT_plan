/**
 * useD2SyncBridge — D2 明细表「结构化视图 ↔ 在线编辑」真双向同步
 *
 * ═══ 为什么新增 ═══
 *
 * `usePilotBridgeAdapter` 的 docstring 声称「底层全部委派给 sync bridge」，但实现里
 * `switchMode()` 只做 `currentMode.value = target` + `localStorage.setItem`，
 * **零 API 调用**；`isOoAvailable` 更是硬编码 `ref(true)`。于是：
 *
 * * 点「在线编辑」→ OO 打开项目存储里那份**从未被写入过**的 xlsx（实测业务行 0 行）；
 * * 点回「结构化视图」→ 只 `reloadHtml()` 重查库，Excel 里的编辑一个字都不带回来。
 *
 * 这就是 43 个宿主常显「两侧数据未互通」的真因 —— 缺的是接线，不是能力。
 *
 * ═══ 同步时机（两个方向都在模式切换的边界上）═══
 *
 * ```
 * 结构化视图 --[切换]--> push-to-excel --> 在线编辑(OO 看到最新数据)
 * 在线编辑   --[切换]--> pull-from-excel --> reloadHtml --> 结构化视图(看到 OO 的编辑)
 * ```
 *
 * 🔴 失败**不静默**：同步失败时不切换模式并显示真实原因。若失败还照切，
 * 审计师会在另一侧看到旧数据却以为是最新的 —— 那比报错危险得多。
 */
import { ElMessage } from 'element-plus'
import { computed, ref, type ComputedRef, type Ref } from 'vue'

import http from '@/utils/http'

import type { ForceSaveResult } from './forceSaveTypes'

export type D2SyncMode = 'html' | 'onlyoffice'

export interface D2SyncStatus {
  entry_id: string
  /** 后端如实标注该 entry 是否真支持双向；false ⇒ UI 必须禁用「在线编辑」 */
  bidirectional: boolean
  managed_sheet: string
  html: { rows: number; narratives?: Record<string, number> }
  excel: {
    exists: boolean
    instrumented?: boolean
    business_rows?: number
    identity_rows?: number
    /** 读 Excel 失败的真实原因（观测端点不吞异常） */
    error?: string
  }
  /** 表头是单向下行到 Excel，不可从 Excel 改回 */
  header_sync?: string
}

export interface D2SyncBridgeOptions {
  wpId: Ref<string>
  /** 切回 HTML 后重新加载结构化数据 */
  reloadHtml?: () => void | Promise<void>
  /** 切到 OO 前把未保存的 HTML 编辑 flush 落库（否则推送的是旧数据） */
  flushBeforeOo?: () => void | Promise<void>
  /**
   * 切回 HTML 前命令 OO 落盘并等耐久确认。
   *
   * 🔴 宿主**必须**传：`pull-from-excel` 读的是磁盘文件，而 OO 的编辑在编辑器销毁后
   * 才由容器异步保存。不传 ⇒ pull 必然读到切换前的旧版本，并把旧值写回覆盖 HTML
   * 新录入（2026-09-06 实测：pull 于 19:51:19 读旧文件，OO 19:51:31 才落盘）。
   * 返回 `null` 视为「拿不到确认」，按拒绝处理。
   */
  requestForceSave?: () => Promise<ForceSaveResult | null>
}

export interface D2SyncBridge {
  currentMode: Ref<D2SyncMode>
  modeOptions: ComputedRef<Array<{ label: string; value: D2SyncMode; disabled?: boolean }>>
  /** 「在线编辑」是否真可用；真源是 status 端点，不是硬编码 */
  isOoAvailable: ComputedRef<boolean>
  /** 不可用原因（中文，可直接显示）；可用时为空串 */
  unavailableReason: ComputedRef<string>
  switching: Ref<boolean>
  /** 最近一次同步的可读摘要（供状态栏显示，不是 toast） */
  lastSync: Ref<string>
  status: Ref<D2SyncStatus | null>
  switchMode: (target: D2SyncMode) => Promise<void>
  onModeChange: (val: string | number | boolean) => void
  refreshStatus: () => Promise<void>
}

const STORAGE_PREFIX = 'workpaper-sync-mode:'
const ENTRY_ID = 'xlsx/gt-d2-accounts-receivable'

/**
 * 拿不到耐久确认时抛这个 —— 调用方据此拒绝切换且**不**发起 pull。
 *
 * 单独一个错误类型而不是复用 `Error`：`switchMode` 的 catch 要能区分
 * 「没落盘所以主动不做」与「请求真的失败了」，两者的用户文案不同。
 */
class NotDurableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NotDurableError'
  }
}

function reasonOf(err: unknown): string {
  const e = err as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return (
    e?.response?.data?.detail ||
    e?.response?.data?.message ||
    e?.message ||
    '未知错误'
  )
}

export function useD2SyncBridge(options: D2SyncBridgeOptions): D2SyncBridge {
  // 🔴 `requestForceSave` 必须在这里解构出来。漏一个名字就是「定了参数没人接」，
  // 与本 spec 反复踩到的缺陷 A 完全同型 —— 而 TS 不会报错（options 上确实有这个键），
  // 运行时才炸 `requestForceSave is not defined`。守卫测试 d2SyncDurableGate 锁死这条。
  const { wpId, reloadHtml, flushBeforeOo, requestForceSave } = options

  const currentMode = ref<D2SyncMode>('html')
  const switching = ref(false)
  const lastSync = ref('')
  const status = ref<D2SyncStatus | null>(null)

  /**
   * 「在线编辑」是否真的可用 —— 真源是 `GET /d2-sync/status`，**不再硬编码 `ref(true)`**。
   *
   * 🔴 硬编码 true 的后果（2026-09-06 实测）：后端 `adapter_registered=False`、
   * finalize 被 supply_gap 阻塞时，按钮照样可点，用户切过去才发现两侧不通。
   * AC 1.4 明令「adapter 未通过契约校验时前端不得显示可双向，并显示可操作原因」。
   *
   * 状态未取回（null）时保持可用：首屏还没查完就禁用会让正常项目也点不动，
   * 真正不可用的情形由 `unavailableReason` 给出并在切换时被后端 4xx 挡住。
   */
  const isOoAvailable = computed(() => {
    const s = status.value
    if (s == null) return true
    if (s.bidirectional === false) return false
    if (s.excel?.exists === false) return false
    return true
  })

  /** 不可用时的可操作原因（中文），供 UI 直接显示；可用时为空串。 */
  const unavailableReason = computed(() => {
    const s = status.value
    if (s == null) return ''
    if (s.bidirectional === false) {
      return '该底稿尚未完成双向回写接线，当前只能使用结构化视图'
    }
    if (s.excel?.exists === false) {
      return 'OnlyOffice 文件尚未生成，请先在结构化视图录入数据后再切换'
    }
    if (s.excel?.error) {
      return `Excel 侧读取异常：${s.excel.error}`
    }
    return ''
  })

  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' as const },
    { label: '在线编辑', value: 'onlyoffice' as const, disabled: !isOoAvailable.value },
  ])

  const storageKey = () => `${STORAGE_PREFIX}${ENTRY_ID}:${wpId.value}`

  function persist(mode: D2SyncMode): void {
    try {
      localStorage.setItem(storageKey(), mode === 'onlyoffice' ? 'oo' : 'html')
    } catch {
      /* localStorage 不可用不影响同步本身 */
    }
  }

  function restore(): void {
    try {
      const saved = localStorage.getItem(storageKey())
      if (saved === 'html') currentMode.value = 'html'
      else if (saved === 'oo' || saved === 'onlyoffice') currentMode.value = 'onlyoffice'
    } catch {
      /* ignore */
    }
  }

  async function refreshStatus(): Promise<void> {
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/d2-sync/status`)
      status.value = (data?.data ?? data) as D2SyncStatus
    } catch (err) {
      // 状态查询失败不阻塞使用，但要留痕（不能静默成「一切正常」）
      lastSync.value = `状态查询失败：${reasonOf(err)}`
    }
  }

  /** HTML → Excel。切到「在线编辑」前必须成功，否则 OO 会显示旧数据。 */
  async function pushToExcel(): Promise<void> {
    const { data } = await http.post(
      `/api/workpapers/${wpId.value}/d2-sync/push-to-excel`,
      {},
    )
    const r = (data?.data ?? data) as { rows?: number; fields?: number }
    lastSync.value = `已推送 ${r?.rows ?? 0} 行 / ${r?.fields ?? 0} 个字段到在线编辑`
  }

  /**
   * Excel → HTML。切回「结构化视图」前必须成功，否则会丢掉 OO 里的编辑。
   *
   * 🔴 两道门，缺一不可：
   *   1. 先 `await requestForceSave()`，**只有** `durable === true` 才继续；
   *   2. 后端 pull 自己还会做陈旧校验（比对 forcesave 冻结的 mtime/size/sha256），
   *      读到切换前旧版本即 409。
   * 任一门不过就**不写库**，让用户留在 OO 侧（数据确定最新的那一侧）。
   */
  async function pullFromExcel(): Promise<void> {
    let durableFingerprint: unknown = null

    if (requestForceSave) {
      const saved = await requestForceSave()
      if (!saved || !saved.durable) {
        const why = saved?.detail || '编辑器未确认已保存'
        throw new NotDurableError(
          `在线编辑的内容尚未落盘（${why}）—— 已留在在线编辑，避免用旧数据覆盖你的修改`,
        )
      }
      lastSync.value = `在线编辑已落盘：${saved.detail}`
      durableFingerprint = saved.artifact ?? null
    }

    const { data } = await http.post(
      `/api/workpapers/${wpId.value}/d2-sync/pull-from-excel`,
      durableFingerprint ? { durable_fingerprint: durableFingerprint } : {},
    )
    const r = (data?.data ?? data) as {
      rows?: number
      fields?: number
      rows_changed?: number
    }
    const changed = r?.rows_changed
    lastSync.value =
      changed == null
        ? `已从在线编辑回写 ${r?.rows ?? 0} 行 / ${r?.fields ?? 0} 个字段`
        : `已从在线编辑回写 ${r?.rows ?? 0} 行（其中 ${changed} 行有变化）`
  }

  async function switchMode(target: D2SyncMode): Promise<void> {
    if (target === currentMode.value || switching.value) return
    switching.value = true
    try {
      if (target === 'onlyoffice') {
        // 🔴 flush 必须在 push 之前：HTML 录入走 debounce，不 flush 推的是旧数据。
        if (flushBeforeOo) await flushBeforeOo()
        await pushToExcel()
        currentMode.value = 'onlyoffice'
        persist('onlyoffice')
        ElMessage.success(lastSync.value)
      } else {
        // 🔴 先回写再切：切了再回写的话，reloadHtml 会先跑、拿到的还是旧库数据。
        await pullFromExcel()
        currentMode.value = 'html'
        persist('html')
        if (reloadHtml) await reloadHtml()
        ElMessage.success(lastSync.value)
      }
      void refreshStatus()
    } catch (err) {
      const reason = reasonOf(err)
      if (err instanceof NotDurableError) {
        // 「没落盘所以主动不做」——不是失败，是保护。文案要说清为什么没切。
        lastSync.value = err.message
        ElMessage.warning({ message: err.message, duration: 8000 })
      } else {
        lastSync.value = `同步失败：${reason}`
        // 不切模式 —— 让用户留在数据确定是最新的那一侧
        ElMessage.error({
          message: `同步失败，已留在当前视图：${reason}`,
          duration: 6000,
        })
      }
    } finally {
      switching.value = false
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as D2SyncMode)
  }

  restore()
  // 首屏就查一次真实能力态 —— `isOoAvailable` 靠它，不查则永远是「未知即可用」。
  void refreshStatus()

  return {
    currentMode,
    modeOptions,
    isOoAvailable,
    unavailableReason,
    switching,
    lastSync,
    status,
    switchMode,
    onModeChange,
    refreshStatus,
  }
}

export default useD2SyncBridge
