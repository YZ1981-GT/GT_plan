/**
 * useD01DiffImport — 从 D0-1 函证汇总表自动带入差异行
 *
 * 规则：
 * - 仅带入已回函且不符（差异≠0）的行
 * - 未回函行不纳入（归替代程序 D0-5/D0-6）
 * - 字段映射：confirm_index / entity_name / amount→sent_amount / reply_amount
 * - 按 confirm_index 去重（已有相同索引号不重复导入）
 * - _source = 'auto'（自动取数视觉标识）
 * - 降级处理：D0-1 不可达时仅 console.warn 不阻塞
 */
import { ref, type Ref } from 'vue'
import type { DiffReconcileRow } from '../diffReconcileTypes'
import type { ConfirmationRow } from '../../confirmationTypes'

export interface UseD01DiffImportProps {
  /** 当前 D0-4 已有行的 confirm_index 集合（用于去重） */
  existingIndexes: () => Set<string>
  /** 导入回调：将映射好的行传入 useDiffReconcileData.importRows */
  onImport: (rows: DiffReconcileRow[]) => void
}

export interface UseD01DiffImportReturn {
  /** 是否正在加载 */
  loading: Ref<boolean>
  /** 最近一次导入的行数 */
  lastImportCount: Ref<number>
  /** 触发从 D0-1 带入 */
  fetchAndImport: (d01Rows: ConfirmationRow[]) => void
  /** 映射单行（纯函数，可单测） */
  mapD01Row: (row: ConfirmationRow) => DiffReconcileRow | null
}

export function useD01DiffImport(props: UseD01DiffImportProps): UseD01DiffImportReturn {
  const loading = ref(false)
  const lastImportCount = ref(0)

  /**
   * 映射 D0-1 行 → D0-4 行
   * 仅映射已回函+差异≠0的行；未回函/差异=0 返回 null
   */
  function mapD01Row(row: ConfirmationRow): DiffReconcileRow | null {
    // 过滤：仅已回函(is_replied=true) + 不符(差异≠0)
    if (!row.is_replied) return null
    const sent = row.amount ?? 0
    const reply = row.reply_amount ?? 0
    const diff = Math.round((sent - reply) * 100) / 100
    if (diff === 0) return null

    return {
      confirm_index: row.confirm_index,
      entity_name: row.entity_name,
      subject: row.account_type,  // D0-1 的 account_type 映射为 D0-4 的 subject
      sent_amount: sent,
      reply_amount: reply,
      difference: diff,
      _source: 'auto',
    }
  }

  /**
   * 批量处理 D0-1 数据并导入
   */
  function fetchAndImport(d01Rows: ConfirmationRow[]) {
    loading.value = true
    try {
      const existing = props.existingIndexes()
      const mapped: DiffReconcileRow[] = []

      for (const row of d01Rows) {
        // confirm_index 去重
        if (row.confirm_index && existing.has(row.confirm_index)) continue
        const diffRow = mapD01Row(row)
        if (diffRow) mapped.push(diffRow)
      }

      if (mapped.length > 0) {
        props.onImport(mapped)
      }
      lastImportCount.value = mapped.length
    } catch (e) {
      console.warn('[useD01DiffImport] 从 D0-1 带入失败（降级）:', e)
      lastImportCount.value = 0
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    lastImportCount,
    fetchAndImport,
    mapD01Row,
  }
}
