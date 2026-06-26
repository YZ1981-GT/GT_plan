/**
 * useA17Navigation — wp_code 跳转逻辑 composable
 *
 * 封装 wp_code → wpId 查找（复用 getWpIndex API）+ router.push 跳转。
 * 处理 wp_code 不存在情况（返回 disabled 状态）。
 */
import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface WpCodeNavState {
  /** wp_code 是否在当前项目 wp_index 中存在 */
  exists: boolean
  /** 对应的 workpaper ID（不存在时为 null） */
  wpId: string | null
  /** 是否禁用（不存在时禁用） */
  disabled: boolean
  /** 禁用时的 tooltip */
  tooltip: string
}

// ─── 纯逻辑函数（可单独测试，不依赖 Vue Router） ─────────────────────────────────

/**
 * 根据 wp_index 列表查找 wp_code 对应的导航状态
 */
export function resolveWpCodeState(
  wpCode: string,
  wpIndex: WpIndexItem[],
): WpCodeNavState {
  const item = wpIndex.find((i) => i.wp_code === wpCode)
  if (item) {
    return {
      exists: true,
      wpId: item.id,
      disabled: false,
      tooltip: item.wp_name || wpCode,
    }
  }
  return {
    exists: false,
    wpId: null,
    disabled: true,
    tooltip: '该底稿在当前项目中不存在',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA17Navigation(projectId: Ref<string>) {
  const router = useRouter()
  const wpIndex = ref<WpIndexItem[]>([])
  const loading = ref(false)

  /** 加载项目的 wp_index（缓存在 composable 生命周期内） */
  async function loadWpIndex() {
    if (wpIndex.value.length > 0) return
    loading.value = true
    try {
      wpIndex.value = await getWpIndex(projectId.value)
    } catch {
      wpIndex.value = []
    } finally {
      loading.value = false
    }
  }

  /** 查询 wp_code 的导航状态 */
  function getNavState(wpCode: string): WpCodeNavState {
    return resolveWpCodeState(wpCode, wpIndex.value)
  }

  /** 跳转到 wp_code 对应的底稿 */
  async function navigateToWpCode(wpCode: string) {
    await loadWpIndex()
    const state = getNavState(wpCode)
    if (state.disabled || !state.wpId) return

    router.push({
      name: 'WorkpaperEditor',
      params: {
        projectId: projectId.value,
        wpId: state.wpId,
      },
    })
  }

  return {
    wpIndex,
    loading,
    loadWpIndex,
    getNavState,
    navigateToWpCode,
  }
}
