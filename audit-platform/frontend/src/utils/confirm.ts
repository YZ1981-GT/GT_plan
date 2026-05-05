/**
 * confirm.ts — 语义化确认弹窗工具
 *
 * 封装 ElMessageBox.confirm，提供三种语义化确认函数：
 * - confirmDelete：删除确认（红色/危险样式）
 * - confirmBatch：批量操作确认
 * - confirmDangerous：危险操作确认（不可恢复）
 *
 * 所有函数返回 Promise<void>，用户取消时 reject（与 ElMessageBox 行为一致）。
 * @module utils/confirm
 * @see R6.3
 */
import { ElMessageBox } from 'element-plus'

/** 对 HTML 特殊字符转义，防止含 < > & 的文件名在弹窗中显示异常 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 删除确认弹窗（红色确认按钮）
 * @param itemName 被删除项名称，如 "该分录"、"文档「xxx」"
 */
export async function confirmDelete(itemName?: string): Promise<void> {
  const safeName = itemName ? escapeHtml(itemName) : ''
  const msg = safeName
    ? `确定删除${safeName}？`
    : '确定删除该记录？'
  await ElMessageBox.confirm(msg, '删除确认', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
    dangerouslyUseHTMLString: false,
  })
}

/**
 * 批量操作确认弹窗
 * @param action 操作动词，如 "删除"、"通过"、"退回"
 * @param count 操作数量
 */
export async function confirmBatch(action: string, count: number): Promise<void> {
  await ElMessageBox.confirm(
    `确认${action}选中的 ${count} 项？`,
    `批量${action}确认`,
    {
      confirmButtonText: `确认${action}`,
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
}

/**
 * 危险操作确认弹窗（不可恢复操作，红色确认按钮）
 * @param message 自定义提示消息
 * @param title 弹窗标题，默认 "危险操作确认"
 */
export async function confirmDangerous(message: string, title?: string): Promise<void> {
  await ElMessageBox.confirm(message, title ?? '危险操作确认', {
    confirmButtonText: '确定执行',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  })
}
