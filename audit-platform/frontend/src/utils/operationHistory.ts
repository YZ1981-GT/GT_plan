/**
 * 操作历史 + 撤销功能
 *
 * Phase 8 Task 9.2: 操作撤销功能
 * - OperationHistory 类：execute(op) / undo() 模式
 * - 集成 ElNotification：操作成功后显示"撤销"按钮
 */

import { h } from 'vue'
import { ElNotification, ElButton } from 'element-plus'

export interface Operation {
  /** 操作描述（显示在通知中） */
  description: string
  /** 执行操作 */
  execute: () => Promise<void> | void
  /** 撤销操作 */
  undo: () => Promise<void> | void
}

interface HistoryEntry {
  operation: Operation
  executedAt: number
}

const MAX_HISTORY = 20

class OperationHistory {
  private history: HistoryEntry[] = []

  /**
   * 执行操作并记录到历史
   * 执行成功后弹出带"撤销"按钮的通知
   */
  async execute(op: Operation): Promise<void> {
    await op.execute()

    this.history.push({
      operation: op,
      executedAt: Date.now(),
    })

    // 限制历史长度
    if (this.history.length > MAX_HISTORY) {
      this.history.shift()
    }

    // 弹出带撤销按钮的通知
    this.showUndoNotification(op.description)
  }

  /**
   * 撤销最近一次操作
   */
  async undo(): Promise<boolean> {
    const entry = this.history.pop()
    if (!entry) return false

    try {
      await entry.operation.undo()
      ElNotification({
        title: '已撤销',
        message: entry.operation.description,
        type: 'info',
        duration: 3000,
      })
      return true
    } catch (e) {
      ElNotification({
        title: '撤销失败',
        message: String(e),
        type: 'error',
        duration: 4000,
      })
      return false
    }
  }

  /**
   * 是否有可撤销的操作
   */
  get canUndo(): boolean {
    return this.history.length > 0
  }

  /**
   * 历史记录数量
   */
  get size(): number {
    return this.history.length
  }

  /**
   * 清空历史
   */
  clear(): void {
    this.history = []
  }

  private showUndoNotification(description: string) {
    const notif = ElNotification({
      title: '操作成功',
      message: h('div', { style: 'display:flex;align-items:center;gap:8px' }, [
        h('span', description),
        h(
          ElButton,
          {
            size: 'small',
            type: 'warning',
            plain: true,
            onClick: () => {
              notif.close()
              this.undo()
            },
          },
          () => '撤销',
        ),
      ]),
      type: 'success',
      duration: 5000,
    })
  }
}

// 全局单例
export const operationHistory = new OperationHistory()

export default operationHistory
