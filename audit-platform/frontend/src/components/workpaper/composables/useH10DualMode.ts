/**
 * useH10DualMode — H10 HTML ↔ OnlyOffice 双模式
 *
 * @deprecated 已被 `composables/useHSyncMode` 取代（spec
 * `h2-h6-h10-pilot-cross-reference-lanes`）。`GtH10AssetDisposalIncome.vue` 于 H10 接桥时
 * 改用统一双向宿主，本模块现算**零生产消费**。
 *
 * 🔴 为什么不直接删：`backend/tests/workpaper_sync/test_h_foundation_hc_guards.py` 的
 * localStorage 判据（HC-10）逐字列了 `useH{2,3,4,6,8,9,10}DualMode.ts` 七个文件 ——
 * 那条判据守的是「只有 H10 的载体用 localStorage 草稿、其余不得出现」这个 HD-6 事实。
 * 删文件要与该判据同批处置，归 BP-8 收口批次（同 useH2DualMode / useH3DualMode）。
 *
 * 原设计（保留以备复核）：对齐 K10/K12/F2 范式：
 * - 切 OO 前先 GET onlyoffice-config **拉取成功** 才置 currentMode
 * - 失败回退 html，不全局禁用 OO
 * - el-segmented 必须 :model-value + @change（v-model 先改值使 switchMode 短路）
 * - 正向 tag（拉取成功/拉取中/不可用）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type H10RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h10-dual-mode:'

export function useH10DualMode(options: {
  wpId: Ref<string>
  projectId?: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const currentMode = ref<H10RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfigReady = ref(false)
  const fetchingConfig = ref(false)

  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice', disabled: !isOoAvailable.value },
  ])

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + options.wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') {
        // 仅在 OO 健康时恢复 onlyoffice 模式
        if (saved === 'onlyoffice' && !isOoAvailable.value) return
        currentMode.value = saved
      }
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const result = res?.data ?? res
      const healthy = result?.data?.healthy ?? result?.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    }
  }

  async function onModeChange(val: string | number | boolean): Promise<void> {
    const target = val as H10RenderMode
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      if (!isOoAvailable.value) return
      // 切到 OO 前预拉 config，拉取成功才切
      fetchingConfig.value = true
      try {
        const pid = options.projectId?.value
        const res = await http.get(`/api/workpapers/${options.wpId.value}/sheets/default/onlyoffice-config`, {
          params: pid ? { project_id: pid } : undefined,
          _silent: true,
        } as any)
        const config = res?.data ?? res
        if (!config || (typeof config === 'object' && Object.keys(config).length === 0)) {
          // config 空 → 拉取失败，不切
          ooConfigReady.value = false
          return
        }
        ooConfigReady.value = true
      } catch {
        ooConfigReady.value = false
        return
      } finally {
        fetchingConfig.value = false
      }
    }

    currentMode.value = target
    try {
      localStorage.setItem(STORAGE_PREFIX + options.wpId.value, target)
    } catch { /* ignore */ }
    if (target === 'html' && options.reloadAll) await options.reloadAll()
  }

  function onOoLoadFailed(): void {
    isOoAvailable.value = false
    ooConfigReady.value = false
    currentMode.value = 'html'
  }

  onMounted(() => {
    void checkOOHealth().then(() => loadPersistedMode())
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfigReady,
    fetchingConfig,
    modeOptions,
    onModeChange,
    onOoLoadFailed,
    checkOOHealth,
  }
}
