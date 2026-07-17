/** 监盘 bundle 双模式 — 结构化 ↔ OnlyOffice；F2-22/F2-23 支持双向回写 */
import { ref, watch, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F2StRenderMode = 'html' | 'onlyoffice'
const STORAGE_PREFIX = 'f2-st-dual-mode:'

export function useF2StocktakeDualMode(options: {
  wpId: Ref<string>
  projectId?: Ref<string>
  /** 当前 sheet 编码，如 F2-22 / F2-23 */
  sheetCode?: Ref<string>
  /** 切回结构化前刷盘 pending 保存 */
  flushPending?: () => Promise<void>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, projectId, sheetCode, flushPending, reloadAll } = options
  const currentMode = ref<F2StRenderMode>('html')
  const isOoAvailable = ref(false)
  /** 切换到 OO 前同步成功后递增，强制 GtOnlyOfficeSheet 重挂载 */
  const ooRemountKey = ref(0)
  const syncing = ref(false)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function syncSheet(): 'F2-22' | 'F2-23' | null {
    const code = sheetCode?.value || ''
    if (code === 'F2-22' || code.includes('F2-22')) return 'F2-22'
    if (code === 'F2-23' || code.includes('F2-23')) return 'F2-23'
    return null
  }

  const supportsBidirectionalSync = () => syncSheet() != null

  function storageKey(): string {
    const sheet = sheetCode?.value || 'default'
    return `${STORAGE_PREFIX}${wpId.value}:${sheet}`
  }

  function loadModeFromStorage(): void {
    try {
      const perSheet = localStorage.getItem(storageKey())
      if (perSheet === 'html' || perSheet === 'onlyoffice') {
        currentMode.value = perSheet
        return
      }
      // 兼容旧版：仅按 wpId 存储
      const legacy = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (legacy === 'html' || legacy === 'onlyoffice') {
        currentMode.value = legacy
      }
    } catch { /* ignore */ }
  }

  function persistMode(target: F2StRenderMode): void {
    try {
      localStorage.setItem(storageKey(), target)
    } catch { /* ignore */ }
  }

  function syncEndpoints(sheet: 'F2-22' | 'F2-23'): { to: string; from: string } {
    if (sheet === 'F2-23') {
      return {
        to: `/api/workpapers/${wpId.value}/f2-st/summary-sync-to-oo`,
        from: `/api/workpapers/${wpId.value}/f2-st/summary-sync-from-oo`,
      }
    }
    return {
      to: `/api/workpapers/${wpId.value}/f2-st/plan-sync-to-oo`,
      from: `/api/workpapers/${wpId.value}/f2-st/plan-sync-from-oo`,
    }
  }

  async function checkOOHealth(): Promise<boolean> {
    try {
      const res = await fetch('/api/workpapers/onlyoffice/health')
      if (!res.ok) { isOoAvailable.value = false; return false }
      const j = await res.json()
      isOoAvailable.value = j.data?.healthy ?? j.healthy ?? false
      return isOoAvailable.value
    } catch {
      isOoAvailable.value = false
      return false
    }
  }

  async function syncDocToOo(): Promise<boolean> {
    const sheet = syncSheet()
    if (!sheet) return true
    try {
      const params: Record<string, string> = { sheet }
      const pid = projectId?.value?.trim()
      if (pid) params.project_id = pid
      await http.post(syncEndpoints(sheet).to, null, { params, _silent: true } as any)
      return true
    } catch (e: any) {
      const detail = formatApiDetail(e)
      ElMessage.warning(detail || '结构化写入 Word 失败，仍将打开在线编辑')
      return false
    }
  }

  async function syncDocFromOo(): Promise<boolean> {
    const sheet = syncSheet()
    if (!sheet) return true
    try {
      const params: Record<string, string> = { sheet }
      const pid = projectId?.value?.trim()
      if (pid) params.project_id = pid
      await http.post(syncEndpoints(sheet).from, null, { params, _silent: true } as any)
      return true
    } catch (e: any) {
      const detail = formatApiDetail(e)
      if (String(detail).includes('尚未生成')) return true
      ElMessage.warning(detail || 'Word 回写结构化失败，请稍后重试')
      return false
    }
  }

  function formatApiDetail(e: any): string {
    const raw = e?.response?.data?.detail ?? e?.response?.data?.message
    if (Array.isArray(raw)) {
      return raw.map((x: any) => x?.msg || JSON.stringify(x)).join('; ')
    }
    if (typeof raw === 'string') return raw
    if (raw && typeof raw === 'object' && raw.message) return String(raw.message)
    return ''
  }

  async function switchMode(target: F2StRenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice' && !supportsBidirectionalSync()) {
      try {
        await ElMessageBox.confirm(
          '本表为表格类底稿，暂不支持结构化与 Word 双向同步。在线编辑仅作预览或手工改 Word；切回结构化视图不会自动回写表格数据。是否仍打开？',
          '仅预览 · 无双向回写',
          { type: 'warning', confirmButtonText: '仍打开', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
    }

    syncing.value = true
    try {
      if (target === 'onlyoffice') {
        if (flushPending) await flushPending()
        await syncDocToOo()
        ooRemountKey.value += 1
        currentMode.value = 'onlyoffice'
      } else {
        await syncDocFromOo()
        currentMode.value = 'html'
        if (reloadAll) await reloadAll()
      }
      persistMode(target)
    } finally {
      syncing.value = false
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as F2StRenderMode)
  }

  if (sheetCode) {
    watch(sheetCode, () => {
      loadModeFromStorage()
    })
  }

  onMounted(() => {
    loadModeFromStorage()
    void checkOOHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    modeOptions,
    onModeChange,
    switchMode,
    ooRemountKey,
    syncing,
    supportsBidirectionalSync,
  }
}
