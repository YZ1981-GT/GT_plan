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

export type D2SyncMode = 'html' | 'onlyoffice'

export interface D2SyncStatus {
  entry_id: string
  bidirectional: boolean
  managed_sheet: string
  html: { rows: number }
  excel: {
    exists: boolean
    instrumented?: boolean
    business_rows?: number
    identity_rows?: number
    error?: string
  }
}

export interface D2SyncBridgeOptions {
  wpId: Ref<string>
  /** 切回 HTML 后重新加载结构化数据 */
  reloadHtml?: () => void | Promise<void>
  /** 切到 OO 前把未保存的 HTML 编辑 flush 落库（否则推送的是旧数据） */
  flushBeforeOo?: () => void | Promise<void>
}

export interface D2SyncBridge {
  currentMode: Ref<D2SyncMode>
  modeOptions: ComputedRef<Array<{ label: string; value: D2SyncMode; disabled?: boolean }>>
  isOoAvailable: Ref<boolean>
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
  const { wpId, reloadHtml, flushBeforeOo } = options

  const currentMode = ref<D2SyncMode>('html')
  const isOoAvailable = ref(true)
  const switching = ref(false)
  const lastSync = ref('')
  const status = ref<D2SyncStatus | null>(null)

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

  /** Excel → HTML。切回「结构化视图」前必须成功，否则会丢掉 OO 里的编辑。 */
  async function pullFromExcel(): Promise<void> {
    const { data } = await http.post(
      `/api/workpapers/${wpId.value}/d2-sync/pull-from-excel`,
      {},
    )
    const r = (data?.data ?? data) as { rows?: number; fields?: number }
    lastSync.value = `已从在线编辑回写 ${r?.rows ?? 0} 行 / ${r?.fields ?? 0} 个字段`
  }

  async function switchMode(target: D2SyncMode): Promise<void> {
    if (target === currentMode.value || switching.value) return
    switching.value = true
    try {
      if (target === 'onlyoffice') {
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
      lastSync.value = `同步失败：${reason}`
      // 不切模式 —— 让用户留在数据确定是最新的那一侧
      ElMessage.error({
        message: `同步失败，已留在当前视图：${reason}`,
        duration: 6000,
      })
    } finally {
      switching.value = false
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as D2SyncMode)
  }

  restore()

  return {
    currentMode,
    modeOptions,
    isOoAvailable,
    switching,
    lastSync,
    status,
    switchMode,
    onModeChange,
    refreshStatus,
  }
}

export default useD2SyncBridge
