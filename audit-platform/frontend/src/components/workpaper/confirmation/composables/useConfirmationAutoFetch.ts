/**
 * useConfirmationAutoFetch — 函证自动取数 composable
 *
 * 职责：
 * - 从 trial_balance 取账面金额（按科目映射）
 * - 自动生成函证索引号（D0-1-001 格式）
 * - 标记字段来源 _source
 */
import { ref, type Ref } from 'vue'
import type { ConfirmationRow } from '../confirmationTypes'

export interface AutoFetchOptions {
  projectId: string
  year: string
  wpCode: string
}

export function useConfirmationAutoFetch(options: Ref<AutoFetchOptions>) {
  const loading = ref(false)

  /**
   * 生成函证索引号
   * 格式: {wp_code}-{seq} 如 D0-1-001
   */
  function generateConfirmIndex(seq: number): string {
    const code = options.value.wpCode || 'D0-1'
    return `${code}-${String(seq).padStart(3, '0')}`
  }

  /**
   * 为行填充自动取数字段
   * - confirm_index: 自动生成
   * - amount: 从 TB 取账面金额（当前为桩，返回 null）
   * - _source 标记为 'auto'
   */
  async function autoFillRow(
    row: ConfirmationRow,
    existingRows: ConfirmationRow[]
  ): Promise<Partial<ConfirmationRow>> {
    const updates: Partial<ConfirmationRow> = {}

    // 自动索引号（如果为空）
    if (!row.confirm_index) {
      const maxSeq = existingRows.reduce((max, r) => {
        const match = r.confirm_index?.match(/-(\d+)$/)
        return match ? Math.max(max, parseInt(match[1], 10)) : max
      }, 0)
      updates.confirm_index = generateConfirmIndex(maxSeq + 1)
    }

    // 账面金额从 TB 取（桩实现：等后端接口就绪后替换）
    // Future: GET /api/trial-balance/{projectId}/{year}?account_type={account_type}
    // updates.amount = fetchedAmount
    // updates._source = 'auto'

    return updates
  }

  /**
   * 批量自动取数（对所有无索引号的行填充）
   */
  async function batchAutoFill(
    rows: ConfirmationRow[]
  ): Promise<Map<string, Partial<ConfirmationRow>>> {
    loading.value = true
    const updates = new Map<string, Partial<ConfirmationRow>>()
    try {
      for (const row of rows) {
        if (!row.confirm_index && row._row_id) {
          const patch = await autoFillRow(row, rows)
          if (Object.keys(patch).length > 0) {
            updates.set(row._row_id, patch)
          }
        }
      }
    } finally {
      loading.value = false
    }
    return updates
  }

  return { loading, generateConfirmIndex, autoFillRow, batchAutoFill }
}
