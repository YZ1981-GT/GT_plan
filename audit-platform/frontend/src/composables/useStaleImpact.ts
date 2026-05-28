/**
 * useStaleImpact — 单元格变更影响范围 + stale 传播链路
 *
 * 用法：
 *   const wpCode = computed(() => wpDetail.value?.wp_code || '')
 *   const { affected, notify, refresh } = useStaleImpact(wpCode)
 *
 *   // 编辑器单元格变更时
 *   await notify({ sheet: '审定表D2-1', cell: 'C10' })
 *
 *   // affected.value 是受影响的下游底稿/单元格列表
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import http from '@/utils/http'
import { logger } from '@/utils/logger'
import { addressRegistry, linkageBus } from '@/services/apiPaths'

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

type WpCodeSource = string | Ref<string> | ComputedRef<string>

function unref(src: WpCodeSource): string {
  if (typeof src === 'string') return src
  return (src as any).value || ''
}

export function useStaleImpact(wpCodeSource: WpCodeSource) {
  const affected = ref<StaleAffectedItem[]>([])
  const totalAffected = ref(0)
  const loading = ref(false)
  const lastNotifyTs = ref(0)

  const wpCode = computed(() => unref(wpCodeSource))

  /** 通知单元格变更，调用统一联动总线 /api/linkage-bus/impact */
  async function notify(payload: {
    sheet?: string
    cell?: string
    max_depth?: number
    project_id?: string
    year?: number
  }) {
    const code = wpCode.value
    if (!code) return
    loading.value = true
    try {
      // 构建统一 URI: WP:{wp_code}:{sheet}:{cell_or_label}
      const sourceUri = `WP:${code}:${payload.sheet || ''}:${payload.cell || '审定数'}`

      const res: any = await http.post(linkageBus.impact, {
        source_uri: sourceUri,
        project_id: payload.project_id || '',
        year: payload.year || new Date().getFullYear(),
      })

      // 将 affected URIs 转换为 StaleAffectedItem 格式
      const affectedUris: string[] = res.data?.affected || res?.affected || []
      affected.value = affectedUris.map((uri: string, idx: number) => {
        const parts = uri.split(':')
        return {
          target_module: parts[0] || '',
          wp_code: parts[0] === 'WP' ? parts[1] : undefined,
          report_row_code: parts[0] === 'REPORT' ? parts[1] : undefined,
          note_section_code: parts[0] === 'NOTE' ? parts[1] : undefined,
          sheet: parts[2] || '',
          description: parts[3] || '',
          depth: 1,
        }
      })
      totalAffected.value = res.data?.total || res?.total || affectedUris.length
      lastNotifyTs.value = Date.now()
      return res.data || res
    } catch (e: any) {
      // 降级模式：503 时静默（不显示黄条，不阻断保存）
      if (e?.response?.status === 503) {
        logger.log('[useStaleImpact] Engine degraded (503), silently skipping')
        return null
      }
      console.warn('[useStaleImpact] notify failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 仅查询不通知（GET，兼容旧端点） */
  async function refresh(payload: { sheet?: string; cell?: string; max_depth?: number } = {}) {
    const code = wpCode.value
    if (!code) return
    loading.value = true
    try {
      const res: any = await http.get(addressRegistry.v2.staleImpact, {
        params: {
          wp_code: code,
          sheet: payload.sheet || '',
          cell: payload.cell || '',
          max_depth: payload.max_depth || 3,
        },
      })
      affected.value = res.data?.affected || []
      totalAffected.value = res.data?.total_affected || 0
      return res.data
    } catch (e) {
      console.warn('[useStaleImpact] refresh failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 清空当前已加载的影响列表 */
  function clear() {
    affected.value = []
    totalAffected.value = 0
    lastNotifyTs.value = 0
  }

  return {
    wpCode,
    affected,
    totalAffected,
    loading,
    notify,
    refresh,
    clear,
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
