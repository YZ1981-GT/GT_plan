/**
 * useK9DualMode — K9 管理费用 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.3（2026-07-23 对齐 D4/F2「拉取成功」范式重写）
 * 收敛: .kiro/specs/k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
 *       Task 4（health 单源探针）· Task 5（localStorage 统一键）· KB-P5/P9/P10
 *
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - 🔴 切到 OnlyOffice 前**预拉该 sheet 的 onlyoffice-config**，
 *   拉取成功(config 非空) 才真正进入 OO 模式；失败则回退结构化视图
 *   （对齐 7-10 D4 范式 useF2DualMode / useWorkpaperEntryDualMode）
 *
 * K9 管理费用损益类底稿（实质性分析+截止双向），
 * 结构化视图为主要交互模式，OnlyOffice 作为降级/偏好切换备选。
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
 * ═══ 🔴 为什么 `onlyoffice-config` 直调**保留**（BP-6 第二半，卡外部依赖）═══
 *
 * 它本该改走 sync bridge 的 `materialize` / `flushHtml`。但 K 循环现状是
 * `backend/app/services/workpaper_sync/adapters/registry.py` 对 `gt-k*-` **零命中**
 * ⇒ 13 条 entry 一个 adapter 都没注册（`missing_adapter`）。此时调 bridge 的 flushHtml
 * 会抛 `StoreProjectionNotBackedError` —— 把一个能用的 OO 预检换成一个必然失败的调用。
 *
 * ⇒ 直调**有意保留**，等 BP-1 + BP-2 落地、K 的 adapter 注册后一并切换。这不是漏做。
 *
 * ═══ localStorage：从 `k9-dual-mode:` 收敛到统一键 ═══
 *
 * 旧键只按 wpId 分段 ⇒ 同一份底稿的不同 sheet 共用一个偏好。统一键
 * `workpaper-sync-mode:{entryId}:{wpId}:{sheetKey}` 三段全带，由 `workpaperSyncModeKey()`
 * 唯一生成；存量旧键由 `migrateWorkpaperSyncMode()` 按**键形态**扫描后读一次即归一并删除。
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'
import {
  migrateWorkpaperSyncMode,
  workpaperSyncModeKey,
  type WorkpaperSyncStoredMode,
} from '../sync/workpaperSyncModeStorage'

export type K9RenderMode = 'html' | 'onlyoffice'

/** K9 的 entry_id —— 统一模式键的第一段。 */
const K9_ENTRY_ID = 'xlsx/gt-k9-admin-expenses'

/**
 * 本模块模式值 ↔ 统一真源值域（`'html' | 'oo'`）的双向映射。
 *
 * 🔴 落盘值只许是 `'html' | 'oo'`。本模块对外 API 用 `'onlyoffice'` 拼写（宿主 template
 * 与 `GtOnlyOfficeSheet` 的 v-if 都依赖它），两者**不是一个值域** —— 直接把 `'onlyoffice'`
 * 落盘会让统一键里混进第三种拼写，下次换个模块读就读不懂。
 */
function toStoredMode(mode: K9RenderMode): WorkpaperSyncStoredMode {
  return mode === 'onlyoffice' ? 'oo' : 'html'
}

function fromStoredMode(stored: string | null): K9RenderMode | null {
  if (stored === 'oo') return 'onlyoffice'
  if (stored === 'html') return 'html'
  return null
}

export interface UseK9DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK9DualMode(options: UseK9DualModeOptions) {
  const { wpId, sheetName, autoSave, reloadAll } = options

  const currentMode = ref<K9RenderMode>('html')
  const isOoAvailable = ref(false)
  /** 预拉成功的 OO 配置（拉取成功的标志） */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)
  /** 正在预拉 config */
  const fetchingConfig = ref(false)

  /** 在线编辑项在 OO 不可用时禁用（el-segmented 单项 disabled） */
  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOoAvailable.value },
  ])

  /** 统一模式键（三段全需；sheetKey 缺省由生成器补 `default`）。 */
  function modeKey(): string {
    return workpaperSyncModeKey({
      entryId: K9_ENTRY_ID,
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
        { entryId: K9_ENTRY_ID, wpId: wpId.value, sheetKey: sheetName?.value || undefined },
        'bidirectional',
      )
    } catch { /* 迁移失败不该挡住首屏 */ }
    try {
      const stored = fromStoredMode(localStorage.getItem(modeKey()))
      if (stored) currentMode.value = stored
    } catch { /* ignore */ }
  }

  function persistMode(mode: K9RenderMode): void {
    try {
      localStorage.setItem(modeKey(), toStoredMode(mode))
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 —— 走平台唯一探针（带 15s TTL 缓存 + 并发去重）。
   *
   * `forceRefresh`：用户**已经点了**「在线编辑」时传 `true`。此时不能信一个可能刚好卡在
   * 过期边界的旧值挡住这次真实点击（D4 的竞态兜底）。
   */
  async function checkOoHealth(forceRefresh = false): Promise<boolean> {
    checking.value = true
    try {
      isOoAvailable.value = await fetchOnlyOfficeHealthy(forceRefresh)
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
   * - 切换前 autoSave
   * - 🔴 切到 OO：先预拉 onlyoffice-config，拉取成功才进入 OO；失败回退 HTML
   * - 切回 HTML 时调 reloadAll 刷新数据
   */
  async function switchMode(target: K9RenderMode): Promise<void> {
    if (target === currentMode.value) return
    // 🔴 点击期用 forceRefresh 重探一次：缓存可能刚好过期在点击那一瞬。
    if (target === 'onlyoffice' && !isOoAvailable.value) {
      if (!(await checkOoHealth(true))) return
    }

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'K9'
      fetchingConfig.value = true
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        const cfg = result.data ?? result
        if (!cfg || (!cfg.config && !cfg.token && !cfg.onlyoffice_url)) {
          // 拉取内容为空视为失败
          throw new Error('empty onlyoffice-config')
        }
        ooConfig.value = cfg
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // 拉取失败 → 不进入 OO，回退结构化视图
        isOoAvailable.value = false
        ooConfig.value = null
        currentMode.value = 'html'
        persistMode('html')
      } finally {
        fetchingConfig.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K9RenderMode)
  }

  /**
   * GtOnlyOfficeSheet 加载失败（@fallback）回调：
   * config 已拉取但文档渲染/就绪失败 → 回退结构化视图并标记不可用，
   * 避免「拉取成功」标签与实际错误页不一致（P0-B）。
   */
  function onOoLoadFailed(): void {
    isOoAvailable.value = false
    ooConfig.value = null
    currentMode.value = 'html'
    persistMode('html')
    if (reloadAll) void reloadAll()
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      const healthy = await checkOoHealth()
      // 若持久化偏好为 OO 且健康，尝试预拉 config 恢复 OO 模式；否则留结构化
      if (currentMode.value === 'onlyoffice') {
        if (healthy) {
          currentMode.value = 'html' // 先回退，交由 switchMode 走「拉取成功」门控
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    fetchingConfig,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
    onOoLoadFailed,
  }
}

export default useK9DualMode
