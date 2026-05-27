/**
 * useFirstLoad — 首次加载 vs 后续 refetch 区分
 *
 * 首次加载时 isFirstLoad=true，视图可显示 el-skeleton 骨架屏。
 * 后续 refetch 时 isFirstLoad=false，视图保留已有数据 + v-loading 蒙层。
 *
 * @example
 * const { data, loading, isFirstLoad, refetch } = useFirstLoad(() => api.get('/items'))
 *
 * <el-skeleton v-if="isFirstLoad && loading" :rows="5" animated />
 * <el-table v-else v-loading="loading" :data="data" />
 */
import { ref, type Ref } from 'vue'

export function useFirstLoad<T>(loader: () => Promise<T>) {
  const isFirstLoad = ref(true)
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)

  async function refetch() {
    loading.value = true
    try {
      data.value = await loader()
    } finally {
      loading.value = false
      isFirstLoad.value = false
    }
  }

  return { data, loading, isFirstLoad, refetch }
}
