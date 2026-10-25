/**
 * useK10DualMode — K10 其他收益 HTML ↔ OnlyOffice 双模式（比照 useD4DualMode / useF2DualMode）
 *
 * D4 范式核心："拉取成功才可以切在线编辑"：
 * - onMounted: health 轻量探测（http 带鉴权），失败不阻塞首屏
 * - switchMode('onlyoffice'): 先 GET onlyoffice-config，**拉取成功**才 currentMode='onlyoffice'；
 *   拉取失败则回退 html + isOoAvailable=false（绝不在 config 未就绪时切到 OO）
 * - 提供 ooConfig 供上层展示"拉取成功"状态
 *
 * Spec: K10 复盘 P0-1（双模式对齐 D4/F2）
 * 收敛: .kiro/specs/k-cycle-sync-foundation-and-first-canary Task 26（BP-6 / BP-7 在 K10）
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
 * ═══ localStorage：从 `k10-dual-mode:` 收敛到统一键 ═══
 *
 * 旧键只按 wpId 分段 ⇒ 同一份底稿的不同 sheet 共用一个偏好。统一键
 * `workpaper-sync-mode:{entryId}:{wpId}:{sheetKey}` 三段全带，由 `workpaperSyncModeKey()`
 * 唯一生成；存量旧键由 `migrateWorkpaperSyncMode()` 按**键形态**扫描后读一次即归一并删除。
 *
 * 🔴 **只收模式偏好**：`useK10DetailColumnPrefs.ts` / `useK10GrantColumnPrefs.ts` 是**列
 * 偏好**（KC-18 的第二类），与模式无关，本轮一律不动。
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { fetchOnlyOfficeHealthy } from '../sync/onlyOfficeHealth'
import {
  migrateWorkpaperSyncMode,
  workpaperSyncModeKey,
  type WorkpaperSyncStoredMode,
} from '../sync/workpaperSyncModeStorage'

export type K10RenderMode = 'html' | 'onlyoffice'

/** K10 的 entry_id —— 统一模式键的第一段（canary entry）。 */
const K10_ENTRY_ID = 'xlsx/gt-k10-other-income'

/**
 * 本模块模式值 ↔ 统一真源值域（`'html' | 'oo'`）的双向映射。
 *
 * 🔴 落盘值只许是 `'html' | 'oo'`。本模块对外 API 用 `'onlyoffice'` 拼写（宿主 template
 * 与 `GtOnlyOfficeSheet` 的 v-if 都依赖它），两者**不是一个值域**。
 */
function toStoredMode(mode: K10RenderMode): WorkpaperSyncStoredMode {
  return mode === 'onlyoffice' ? 'oo' : 'html'
}

function fromStoredMode(stored: string | null): K10RenderMode | null {
  if (stored === 'oo') return 'onlyoffice'
  if (stored === 'html') return 'html'
  return null
}

export interface UseK10DualModeOptions {
  wpId: Ref<string>
  /** 项目ID —— onlyoffice-config 端点必填 query 参数（缺失会 422） */
  projectId?: Ref<string>
  sheetName?: Ref<string>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK10DualMode(options: UseK10DualModeOptions) {
  const { wpId, projectId, sheetName, reloadAll } = options

  const currentMode = ref<K10RenderMode>('html')
  const isOoAvailable = ref(false)
  /** onlyoffice-config 拉取结果；非空表示"拉取成功" */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  /** 统一模式键（三段全需；sheetKey 缺省由生成器补 `default`）。 */
  function modeKey(): string {
    return workpaperSyncModeKey({
      entryId: K10_ENTRY_ID,
      wpId: wpId.value,
      sheetKey: sheetName?.value || undefined,
    })
  }

  /** 读统一键里的模式（`null` = 没有偏好）。 */
  function readPersistedMode(): K10RenderMode | null {
    try {
      return fromStoredMode(localStorage.getItem(modeKey()))
    } catch {
      return null
    }
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
        { entryId: K10_ENTRY_ID, wpId: wpId.value, sheetKey: sheetName?.value || undefined },
        'bidirectional',
      )
    } catch { /* 迁移失败不该挡住首屏 */ }
    const stored = readPersistedMode()
    if (stored) currentMode.value = stored
  }

  function persistMode(mode: K10RenderMode): void {
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
   * 切换模式。
   * - 切到 onlyoffice：先 GET onlyoffice-config，**拉取成功**才切；失败回退 html。
   * - 切回 html：清 config + reloadAll 刷新结构化数据。
   */
  async function switchMode(target: K10RenderMode): Promise<void> {
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      // 🔴 点击期用 forceRefresh 重探一次：缓存可能刚好过期在点击那一瞬。
      if (!isOoAvailable.value) {
        const healthy = await checkOoHealth(true)
        if (!healthy) return
      }
      const sn = sheetName?.value || 'K10'
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { params: projectId?.value ? { project_id: projectId.value } : {}, _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        ooConfig.value = result.data || result
        // 拉取成功才切
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // 该 sheet 拉取失败（如合成"底稿目录"无 OO 底稿）：不切、保持结构化。
        // 不置 isOoAvailable=false —— 单个 sheet 失败不应全局禁用在线编辑（其它数据 sheet 仍可用）。
        ooConfig.value = null
        currentMode.value = 'html'
        persistMode('html')
        try {
          const { ElMessage } = await import('element-plus')
          ElMessage.warning('该表暂不支持在线编辑（OnlyOffice 底稿拉取失败），已保持结构化视图')
        } catch { /* ignore */ }
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
    void switchMode(val as K10RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      // 🔴 迁移后统一键才是真源 —— 这里复用 readPersistedMode() 而不是再读一次旧前缀。
      if (readPersistedMode() === 'onlyoffice') {
        const healthy = await checkOoHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      } else {
        // 结构化视图：后台轻量探测，失败不影响渲染
        void checkOoHealth()
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useK10DualMode
