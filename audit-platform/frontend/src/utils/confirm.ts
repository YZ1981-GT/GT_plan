/**
 * confirm.ts — 语义化确认弹窗工具
 *
 * 封装 ElMessageBox.confirm，提供语义化确认函数：
 * - confirmDelete：删除确认（红色/危险样式）
 * - confirmBatch：批量操作确认
 * - confirmDangerous：危险操作确认（不可恢复）
 * - confirmSubmitReview：提交复核确认
 * - confirmVersionConflict：版本冲突确认
 * - confirmLeave：离开未保存确认
 * - confirmConvert：转换确认（分录→错报等）
 * - confirmEscalate：升级催办确认
 *
 * 所有函数返回 Promise<void>，用户取消时 reject（与 ElMessageBox 行为一致）。
 * 新代码禁止直接使用 ElMessageBox.confirm，必须走本文件的语义化函数。
 *
 * @module utils/confirm
 * @see R6.3, R7-S1-08
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

/**
 * 提交复核确认弹窗 [R7-S1-08]
 */
export async function confirmSubmitReview(wpCode: string, wpName: string): Promise<void> {
  await ElMessageBox.confirm(
    `提交后底稿 ${escapeHtml(wpCode)}「${escapeHtml(wpName)}」将进入复核流程，复核通过前您将无法编辑。确认提交？`,
    '提交复核',
    { confirmButtonText: '确认提交', cancelButtonText: '取消', type: 'info' },
  )
}

/**
 * 版本冲突确认弹窗 [R7-S1-08]
 */
export async function confirmVersionConflict(serverVer: number, localVer: number): Promise<void> {
  await ElMessageBox.confirm(
    `底稿已被他人修改（服务器版本 v${serverVer}，您的版本 v${localVer}）。刷新将放弃本地修改。`,
    '版本冲突',
    { confirmButtonText: '刷新', cancelButtonText: '取消', type: 'warning', distinguishCancelAndClose: true },
  )
}

/**
 * 离开未保存确认弹窗 [R7-S1-08]
 */
export async function confirmLeave(moduleLabel: string): Promise<void> {
  await ElMessageBox.confirm(
    `当前${escapeHtml(moduleLabel)}有未保存的变更，离开将丢失这些变更。`,
    '确认离开',
    { confirmButtonText: '离开', cancelButtonText: '留下', type: 'warning' },
  )
}

/**
 * 转换确认弹窗（分录→错报等）[R7-S1-08]
 */
export async function confirmConvert(fromLabel: string, toLabel: string): Promise<void> {
  await ElMessageBox.confirm(
    `将${escapeHtml(fromLabel)}转为${escapeHtml(toLabel)}？转换后将出现在对应汇总表中。`,
    '确认转换',
    { confirmButtonText: '确认转换', cancelButtonText: '取消', type: 'info' },
  )
}

/**
 * 升级催办确认弹窗 [R7-S1-08]
 */
export async function confirmEscalate(targetRole: string): Promise<void> {
  await ElMessageBox.confirm(
    `确认将此事项升级通知${escapeHtml(targetRole)}？`,
    '升级确认',
    { confirmButtonText: '确认升级', cancelButtonText: '取消', type: 'warning' },
  )
}
