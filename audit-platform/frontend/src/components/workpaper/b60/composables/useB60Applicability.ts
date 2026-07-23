/**
 * useB60Applicability — B60 适用性矩阵 composable
 *
 * 管理 8 个子底稿（B60-2-1 ~ B60D）的适用性状态，
 * 通过 checklist_responses 持久化（item_id = 'B60-applicability'）。
 *
 * Validates: Requirements 3.2, 3.3, 3.4
 */
import { ref, watch, type Ref } from 'vue'
import http from '@/utils/http'

// ── 8 个子底稿编码 ──────────────────────────────────────────
export const B60_SUB_WP_CODES = [
  'B60-2-1',
  'B60-2-2',
  'B60-2-3',
  'B60-3',
  'B60A',
  'B60B',
  'B60C',
  'B60D',
] as const

export type B60SubWpCode = (typeof B60_SUB_WP_CODES)[number]

const ITEM_ID = 'B60-applicability'

export interface UseB60ApplicabilityOptions {
  wpId: Ref<string>
  responsesSnapshot: Ref<Record<string, { conclusion: string | null; remark: string | null }>>
}

export interface UseB60ApplicabilityReturn {
  applicabilityMap: Ref<Record<string, boolean>>
  toggleApplicability: (wpCode: string, value: boolean) => void
  isApplicable: (wpCode: string) => boolean
}

/**
 * 从 responsesSnapshot 解析已存的适用性 JSON。
 * 缺失键默认为 true（全部适用）。
 */
function parseApplicability(
  snapshot: Record<string, { conclusion: string | null; remark: string | null }> | null | undefined,
): Record<string, boolean> {
  const defaults: Record<string, boolean> = {}
  for (const code of B60_SUB_WP_CODES) {
    defaults[code] = true
  }

  if (!snapshot) return defaults

  const record = snapshot[ITEM_ID]
  if (!record || !record.remark) return defaults

  try {
    const parsed = JSON.parse(record.remark)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      // 合并：已存的值覆盖默认值，缺失的键保留 true
      for (const code of B60_SUB_WP_CODES) {
        if (typeof parsed[code] === 'boolean') {
          defaults[code] = parsed[code]
        }
        // 缺失键保留 true（默认适用）
      }
    }
  } catch {
    // JSON 解析失败，使用默认全适用
  }

  return defaults
}

export function useB60Applicability(options: UseB60ApplicabilityOptions): UseB60ApplicabilityReturn {
  const { wpId, responsesSnapshot } = options

  // ── 初始化适用性状态 ────────────────────────────────────
  const applicabilityMap = ref<Record<string, boolean>>(
    parseApplicability(responsesSnapshot.value),
  )

  // 监听 responsesSnapshot 变化（如模式切换后重新加载）
  watch(
    responsesSnapshot,
    (newSnapshot) => {
      applicabilityMap.value = parseApplicability(newSnapshot)
    },
    { deep: true },
  )

  // ── 800ms 防抖持久化 ────────────────────────────────────
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      persistApplicability()
    }, 800)
  }

  async function persistApplicability(): Promise<void> {
    const id = wpId.value
    if (!id) return

    try {
      await http.put(`/api/workpapers/${id}/checklist-responses`, {
        items: [
          {
            item_id: ITEM_ID,
            conclusion: null,
            remark: JSON.stringify(applicabilityMap.value),
          },
        ],
      })
    } catch {
      // 适用性保存失败时静默（非关键路径，不阻断 UI）
      // 下次 toggle 会再次触发保存
    }
  }

  // ── 公开方法 ────────────────────────────────────────────

  /**
   * 切换某个子底稿的适用性状态。
   * 立即更新本地 + 触发 800ms 防抖持久化。
   */
  function toggleApplicability(wpCode: string, value: boolean): void {
    applicabilityMap.value = { ...applicabilityMap.value, [wpCode]: value }
    scheduleSave()
  }

  /**
   * 查询某个子底稿是否适用。
   * 缺失键默认返回 true。
   */
  function isApplicable(wpCode: string): boolean {
    const val = applicabilityMap.value[wpCode]
    return val === undefined ? true : val
  }

  return {
    applicabilityMap,
    toggleApplicability,
    isApplicable,
  }
}
