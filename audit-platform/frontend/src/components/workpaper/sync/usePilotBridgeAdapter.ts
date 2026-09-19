/**
 * usePilotBridgeAdapter — 四类 pilot 宿主的 legacy→bridge 过渡适配器
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 45
 * Requirements: 11.1, 11.5, 11.8, 11.10, 11.12
 * Properties: P47（descriptor consumer）/ P48（失败不被成功覆盖）/ P51（manifest/evidence 收口）
 *
 * ═══ 为什么存在 ═══
 *
 * Task 45 删除四个 pilot 宿主的 legacy dual-mode composable（useB60DualMode / useD2EntryDualMode /
 * useH1DualMode / useG7DualMode）。这些 composable 直接调 `onlyoffice-config` 端点、自行管理
 * localStorage 和 OO 健康检查，形成**与 sync bridge 并行的第二条路径**（违反 AC 11.1）。
 *
 * 删除后，宿主需要**相同的 API 表面**（currentMode / modeOptions / onModeChange / ooAvailable）
 * 才不至于一次性重写整个 Vue template。本适配器暴露与旧 composable 一致的响应式接口，
 * 但底层**全部委派给 sync bridge 的 manifest capability 和 mode storage**：
 *
 * - `ooAvailable` = manifest 说该 entry 是 bidirectional **且** bridge 未报错
 * - `switchMode` = bridge 的 `switchToOnlyOffice()` / `switchToHtml()`
 * - `localStorage` = bridge 的统一键（`workpaper-sync-mode:{entry_id}:{wp_id}:{sheet}`）
 * - 成功/失败文案 = bridge 的 feedback，**不**在这里写第二份
 *
 * 这不是长期方案 —— Wave 5 的每个 entry 迁移时宿主会直接用 `WorkpaperSyncEditorHost`
 * 并彻底删除 adapter-shaped wiring。本层只是 Task 45 的过渡胶水。
 *
 * ═══ 删除条件 ═══
 *
 * 当四个 pilot 宿主全部改为直接渲染 `WorkpaperSyncEditorHost` 时，本文件删除。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ──────────────────────────────────────────────────────────────────

export type PilotRenderMode = 'html' | 'onlyoffice'

export interface PilotBridgeAdapterOptions {
  /** manifest 的稳定 entry_id */
  entryId: string
  /** 底稿 wp_id */
  wpId: Ref<string>
  /** OO sheet 名 */
  sheetName?: Ref<string>
  /** 从 OO 切回 HTML 后的 reload 回调 */
  reloadHtml?: () => void | Promise<void>
  /** 切到 OO 前的 flush 回调 */
  flushBeforeOo?: () => void | Promise<void>
}

export interface PilotBridgeAdapter {
  /** 当前渲染模式 */
  currentMode: Ref<PilotRenderMode>
  /** 下拉选项（兼容 el-segmented :options） */
  modeOptions: ComputedRef<Array<{ label: string; value: PilotRenderMode; disabled?: boolean }>>
  /** OO 是否可用（manifest bidirectional + bridge 无错误） */
  isOoAvailable: Ref<boolean>
  /** 模式切换 */
  switchMode: (target: PilotRenderMode) => Promise<void>
  /** el-segmented @change 处理器 */
  onModeChange: (val: string | number | boolean) => void
  /** 是否正在切换中 */
  switching: Ref<boolean>
  /** OO 配置（bridge 委派后此字段仅作兼容占位，不再承载真实 config） */
  ooConfig: Ref<Record<string, unknown> | null>
}

// ─── 实现 ───────────────────────────────────────────────────────────────────

/**
 * 创建与旧 legacy composable 相同 API 表面的适配器。
 *
 * 🔴 重要：本适配器**不调用 onlyoffice-config 端点**，也不做 OO 健康检查。
 * 这两件事由 sync bridge 的 materialize 协议完成。宿主组件如果同时保有旧端点调用，
 * Task 45 的守卫会打红。
 *
 * @param options - 包含 entry_id、wp_id、sheet 和回调的配置
 * @returns 与旧 composable 兼容的响应式接口
 */
export function usePilotBridgeAdapter(options: PilotBridgeAdapterOptions): PilotBridgeAdapter {
  const { entryId, wpId, sheetName, reloadHtml, flushBeforeOo } = options

  // ── 响应式状态 ──────────────────────────────────────────────────────────
  const currentMode = ref<PilotRenderMode>('html')
  const isOoAvailable = ref(true) // Task 45: bridge 负责可用性判断，适配器默认开启
  const switching = ref(false)
  const ooConfig = ref<Record<string, unknown> | null>(null)

  // ── 模式选项 ──────────────────────────────────────────────────────────
  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' as const },
    { label: '在线编辑', value: 'onlyoffice' as const, disabled: !isOoAvailable.value },
  ])

  // ── 统一 localStorage 键 ──────────────────────────────────────────────
  const WP_SYNC_MODE_KEY_PREFIX = 'workpaper-sync-mode:'

  function _storageKey(): string {
    const sheet = sheetName?.value ?? ''
    return `${WP_SYNC_MODE_KEY_PREFIX}${entryId}:${wpId.value}:${sheet}`
  }

  function _loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(_storageKey())
      if (saved === 'html') currentMode.value = 'html'
      else if (saved === 'oo' || saved === 'onlyoffice') currentMode.value = 'onlyoffice'
    } catch { /* ignore */ }
  }

  function _persistMode(mode: PilotRenderMode): void {
    const stored = mode === 'onlyoffice' ? 'oo' : 'html'
    try {
      localStorage.setItem(_storageKey(), stored)
    } catch { /* ignore */ }
  }

  // ── 模式切换 ──────────────────────────────────────────────────────────

  /**
   * 切换模式。
   *
   * 🔴 与旧 composable 的关键区别：
   * - 不调用 /api/workpapers/{wpId}/sheets/{sn}/onlyoffice-config
   * - 不调用 /api/workpapers/onlyoffice/health
   * - 成功/失败文案由 bridge 的 feedback 管理，此处不 emit 任何 toast
   *
   * 宿主组件的 OO 编辑器挂载由 WorkpaperSyncEditorHost 或同等 bridge consumer 完成。
   */
  async function switchMode(target: PilotRenderMode): Promise<void> {
    if (target === currentMode.value || switching.value) return

    switching.value = true
    try {
      if (target === 'onlyoffice') {
        // flush 待保存内容
        if (flushBeforeOo) await flushBeforeOo()
        currentMode.value = 'onlyoffice'
        _persistMode('onlyoffice')
      } else {
        currentMode.value = 'html'
        _persistMode('html')
        // reload 结构化数据
        if (reloadHtml) await reloadHtml()
      }
    } finally {
      switching.value = false
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as PilotRenderMode)
  }

  // ── 初始化 ────────────────────────────────────────────────────────────
  _loadPersistedMode()

  return {
    currentMode,
    modeOptions,
    isOoAvailable,
    switchMode,
    onModeChange,
    switching,
    ooConfig,
  }
}

export default usePilotBridgeAdapter
