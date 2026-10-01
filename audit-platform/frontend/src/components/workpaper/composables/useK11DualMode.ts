/**
 * useK11DualMode — K11 资产减值损失 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 1.1（P0 双模式对齐 D4/F2 七月十日"拉取成功"范式）
 *
 * 关键：切 OnlyOffice 前**预拉 onlyoffice-config（带 project_id）**，
 *      config 拉取成功才置 currentMode='onlyoffice'（"拉取成功才可以"），失败回退 html。
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - 单 sheet config 失败不全局禁用（isOoAvailable 由 health 决定）
 *
 * 收敛: .kiro/specs/k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
 *       Task 4（health 单源探针）· Task 5（localStorage 统一键）· KB-P5/P9/P10
 *
 * ═══ 为什么 health 不再自己打端点（BP-6 第一半，已收口）═══
 *
 * 原实现自己 `http.get('/api/workpapers/onlyoffice/health')` 并自己解信封 —— 平台上这段
 * 逻辑曾被抄过 20 份，2026-09-21 那批 bug 就是抄歪的产物（误用 `/api/onlyoffice/health`
 * 得 404、误读 `status === 'healthy'` 而真字段是 `data.healthy` ⇒ 在线编辑永久锁死），
 * 且各自抄的版本**都没有 TTL 缓存**，切一张底稿打一次探针。
 *
 * ⇒ 现在一律走 `sync/onlyOfficeHealth.ts` 的 `fetchOnlyOfficeHealthy()`：端点 / 字段 /
 *   15s 模块级 TTL 缓存 / 并发去重四合一，全平台唯一实现。
 *
 * 🔴 K11 的 `switchMode` **本来就没有**点击期 health 兜底（只在 `onMounted` 做后台探测
 * `void checkOoHealth().then(...)`，那里该用缓存值以免阻塞首屏）。这是形态差异而不是漏改
 * —— 统一要求 `checkOoHealth(true)` 会假红 K11，判据按 KC-15 的二分支写。
 *
 * ═══ 🔴 为什么 `onlyoffice-config` 直调**保留**（BP-6 第二半，卡外部依赖）═══
 *
 * 它本该改走 sync bridge 的 `materialize` / `flushHtml`。但 K 循环现状是
 * `backend/app/services/workpaper_sync/adapters/registry.py` 对 `gt-k*-` **零命中**
 * ⇒ 13 条 entry 一个 adapter 都没注册（`missing_adapter`）。此时调 bridge 的 flushHtml
 * 会抛 `StoreProjectionNotBackedError` —— 把一个能用的 OO 预检换成一个必然失败的调用。
 *
 * ⇒ 直调**有意保留**，等 BP-1 + BP-2 落地、K 的 adapter 注册后一并切换。这不是漏做。
 *
 * ═══ localStorage：从 `k11-dual-mode:` 收敛到统一键 ═══
 *
 * 旧键只按 wpId 分段 ⇒ 同一份底稿的不同 sheet 共用一个偏好。统一键
 * `workpaper-sync-mode:{entryId}:{wpId}:{sheetKey}` 三段全带，由 `workpaperSyncModeKey()`
 * 唯一生成；存量旧键由 `migrateWorkpaperSyncMode()` 按**键形态**扫描后读一次即归一并删除。
 *
 * 🔴 **只收模式偏好**：`useK11DetailColumnPrefs.ts` 是**列偏好**（KC-18 第二类），不动。
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'
import {
  migrateWorkpaperSyncMode,
  workpaperSyncModeKey,
  type WorkpaperSyncStoredMode,
} from '../sync/workpaperSyncModeStorage'

export type K11RenderMode = 'html' | 'onlyoffice'

/** K11 的 entry_id —— 统一模式键的第一段。 */
const K11_ENTRY_ID = 'xlsx/gt-k11-asset-impairment-loss'

/**
 * 本模块模式值 ↔ 统一真源值域（`'html' | 'oo'`）的双向映射。
 *
 * 🔴 落盘值只许是 `'html' | 'oo'`。本模块对外 API 用 `'onlyoffice'` 拼写（宿主 template
 * 与 `GtOnlyOfficeSheet` 的 v-if 都依赖它），两者**不是一个值域**。
 */
function toStoredMode(mode: K11RenderMode): WorkpaperSyncStoredMode {
  return mode === 'onlyoffice' ? 'oo' : 'html'
}

function fromStoredMode(stored: string | null): K11RenderMode | null {
  if (stored === 'oo') return 'onlyoffice'
  if (stored === 'html') return 'html'
  return null
}

export interface UseK11DualModeOptions {
  wpId: Ref<string>
  /** 当前 sheet 的真实 xlsx 名称（用于拉取 onlyoffice-config） */
  sheetName?: Ref<string>
  /** 项目 id（onlyoffice-config 必填 query 参，缺失会 422） */
  projectId?: Ref<string>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK11DualMode(options: UseK11DualModeOptions) {
  const { wpId, sheetName, projectId, reloadAll } = options

  const currentMode = ref<K11RenderMode>('html')
  /** OO 服务是否健康（health 检查） */
  const isOoAvailable = ref(false)
  /** 当前 sheet 的 onlyoffice-config 是否已拉取成功（"拉取成功"tag 依据） */
  const ooConfigReady = ref(false)
  /** config 拉取中 */
  const fetchingConfig = ref(false)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  /** 统一模式键（三段全需；sheetKey 缺省由生成器补 `default`）。 */
  function modeKey(): string {
    return workpaperSyncModeKey({
      entryId: K11_ENTRY_ID,
      wpId: wpId.value,
      sheetKey: sheetName?.value || undefined,
    })
  }

  /**
   * 迁移旧键 + 读回模式。
   *
   * 🔴 迁移传 `'bidirectional'` 而**不是** entry 的 manifest capability
   * （`single_onlyoffice`）：这里表达的是「本宿主的视图开关两侧都能开」—— 结构化视图是
   * 本地渲染、OO 是在线编辑，与「写回方向有没有 adapter 支撑」无关。传 `single_onlyoffice`
   * 会让 `migrate` 把存量 `'html'` 偏好**回落成 `'oo'`** 并落盘，等于每个老用户下次打开
   * 都被强推进 OO —— 那是数据迁移造成的行为变更，不是用户的选择。
   *
   * 🔴 同理**不用** `persistWorkpaperSyncMode()`：它按 capability 校验，
   * `single_onlyoffice` 下写 `'html'` 直接抛 `mode_not_supported_by_capability`。
   */
  function loadPersistedMode(): void {
    try {
      migrateWorkpaperSyncMode(
        { entryId: K11_ENTRY_ID, wpId: wpId.value, sheetKey: sheetName?.value || undefined },
        'bidirectional',
      )
    } catch { /* 迁移失败不该挡住首屏 */ }
    try {
      const stored = fromStoredMode(localStorage.getItem(modeKey()))
      if (stored) currentMode.value = stored
    } catch { /* ignore */ }
  }

  function persistMode(mode: K11RenderMode): void {
    try {
      localStorage.setItem(modeKey(), toStoredMode(mode))
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 —— 走平台唯一探针（带 15s TTL 缓存 + 并发去重）。
   *
   * 🔴 K11 只在 `onMounted` 调它（后台探测，不阻塞首屏）⇒ 这里**不传** `forceRefresh`
   * 是对的：缓存值足够，且首屏不该为探针等一个往返。
   */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      isOoAvailable.value = await fetchOnlyOfficeHealthy()
      return isOoAvailable.value
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  /**
   * 切换模式
   * - 切 onlyoffice：先预拉当前 sheet 的 onlyoffice-config（带 project_id），
   *   **拉取成功才切**，失败保持 html 并提示。
   * - 切回 html：清 config + reloadAll 刷新数据。
   */
  async function switchMode(target: K11RenderMode): Promise<void> {
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      if (!isOoAvailable.value) return
      const sn = sheetName?.value || ''
      if (!sn) return
      fetchingConfig.value = true
      ooConfigReady.value = false
      try {
        const params: Record<string, any> = {}
        if (projectId?.value) params.project_id = projectId.value
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { params, _silent: true } as any,
        )
        const payload = res.data?.data ?? res.data
        if (!payload) throw new Error('empty onlyoffice-config')
        // config 拉取成功 → 允许进入在线编辑
        ooConfigReady.value = true
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // config 拉取失败 → 保持结构化视图（不全局禁用 OO 服务）
        ooConfigReady.value = false
        currentMode.value = 'html'
      } finally {
        fetchingConfig.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfigReady.value = false
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K11RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    // 结构化视图为主：后台轻量健康探测，不阻塞首屏，也不自动切 OO
    void checkOoHealth().then((healthy) => {
      // 若持久化偏好是 OO 且健康，尝试预拉 config 恢复在线编辑
      if (healthy && currentMode.value === 'onlyoffice') {
        currentMode.value = 'html' // 先回退，交由 switchMode 校验 config
        void switchMode('onlyoffice')
      }
    })
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfigReady,
    fetchingConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useK11DualMode
