/**
 * useStaleImpact — 单元格变更影响范围 + stale 传播链路
 *
 * 用法：
 *   const { affected, notify, refresh } = useStaleImpact(wpCode)
 *
 *   // 编辑器单元格变更时
 *   await notify({ sheet: '审定表D2-1', cell: 'C10' })
 *
 *   // affected.value 是受影响的下游底稿/单元格列表
 */
import { ref } from 'vue'
import http from '@/utils/http'
import { addressRegistry } from '@/services/apiPaths'

export interface StaleAffectedItem {
  wp_code?: string
  file?: string
  sheet?: string
  cell?: string
  matched_anchor?: string
  depth: number
  via_ref?: string
  via_formula?: string
  description?: string
  severity?: string
  match_type?: string
  // 模块级目标
  target_module?: string
  target_type?: string
  note_section_code?: string
  report_row_code?: string
}

export function useStaleImpact(wpCode: string) {
  const affected = ref<StaleAffectedItem[]>([])
  const totalAffected = ref(0)
  const loading = ref(false)
  const lastNotifyTs = ref(0)

  /** 通知单元格变更，获取下游影响 */
  async function notify(payload: { sheet?: string; cell?: string; max_depth?: number }) {
    if (!wpCode) return
    loading.value = true
    try {
      const res: any = await http.post(addressRegistry.v2.notifyCellChange, {
        wp_code: wpCode,
        sheet: payload.sheet || '',
        cell: payload.cell || '',
        max_depth: payload.max_depth || 3,
      })
      affected.value = res.data?.stale_targets || []
      totalAffected.value = res.data?.total_affected || 0
      lastNotifyTs.value = Date.now()
    } catch (e) {
      console.warn('[useStaleImpact] notify failed:', e)
    } finally {
      loading.value = false
    }
  }

  /** 仅查询不通知（GET） */
  async function refresh(payload: { sheet?: string; cell?: string; max_depth?: number } = {}) {
    if (!wpCode) return
    loading.value = true
    try {
      const res: any = await http.get(addressRegistry.v2.staleImpact, {
        params: {
          wp_code: wpCode,
          sheet: payload.sheet || '',
          cell: payload.cell || '',
          max_depth: payload.max_depth || 3,
        },
      })
      affected.value = res.data?.affected || []
      totalAffected.value = res.data?.total_affected || 0
    } catch (e) {
      console.warn('[useStaleImpact] refresh failed:', e)
    } finally {
      loading.value = false
    }
  }

  return {
    affected,
    totalAffected,
    loading,
    notify,
    refresh,
    lastNotifyTs,
  }
}

/** 解析语义描述到物理坐标（一次性 API） */
export async function resolveAddress(wpCode: string, sheet: string, cellDesc: string) {
  try {
    const res: any = await http.get(addressRegistry.v2.resolve, {
      params: { wp_code: wpCode, sheet, cell_desc: cellDesc },
    })
    return res.data
  } catch {
    return { matched: false }
  }
}

/** 获取某底稿的全部依赖 */
export async function getDependencies(wpCode: string) {
  try {
    const res: any = await http.get(addressRegistry.v2.dependencies, {
      params: { wp_code: wpCode },
    })
    return res.data
  } catch {
    return { upstream: [], downstream: [], formula_dependencies: [] }
  }
}
