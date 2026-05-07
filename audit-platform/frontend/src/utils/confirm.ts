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

// ══ R8-S1-02 新增语义化确认函数 ══════════════════════════════════

/**
 * 签字确认弹窗（必须输入客户名全称）
 * @param clientName 客户名（用户必须输入匹配才能确认）
 * @param reportType 报告类型描述
 */
export async function confirmSignature(clientName: string, reportType: string): Promise<boolean> {
  const { value } = await ElMessageBox.prompt(
    `您即将签字「${escapeHtml(clientName)}」的${escapeHtml(reportType)}。\n\n签字一旦完成将：\n1. 不可撤销（只能通过撤回流程）\n2. 锁定底稿、报表、附注编辑\n\n请输入客户名全称确认：`,
    '签字确认',
    {
      confirmButtonText: '确认签字',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      inputPattern: new RegExp(`^${clientName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
      inputErrorMessage: `请输入正确的客户名：${clientName}`,
    },
  )
  return value === clientName
}

/**
 * 强制重置确认弹窗（导入锁、卡住任务等）
 * @param context 重置上下文描述
 */
export async function confirmForceReset(context: string): Promise<void> {
  await ElMessageBox.confirm(
    `${escapeHtml(context)}\n\n确定要强制重置吗？已入库的数据不受影响。`,
    '确认重置',
    {
      confirmButtonText: '强制重置',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    },
  )
}

/**
 * 回滚版本确认弹窗
 * @param version 目标版本号
 */
export async function confirmRollback(version: number): Promise<void> {
  await ElMessageBox.confirm(
    `确定回滚到版本 ${version}？当前未保存的编辑将丢失。`,
    '确认回滚',
    {
      confirmButtonText: '确认回滚',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
}

/**
 * 分享给项目组确认弹窗
 * @param target 被分享内容描述
 * @param audience 目标受众描述
 */
export async function confirmShare(target: string, audience: string): Promise<void> {
  await ElMessageBox.confirm(
    `确定将「${escapeHtml(target)}」分享给${escapeHtml(audience)}？分享后对方可见。`,
    '分享确认',
    {
      confirmButtonText: '确认分享',
      cancelButtonText: '取消',
      type: 'info',
    },
  )
}

/**
 * 重复数据/已存在操作确认弹窗
 * @param message 描述信息
 * @returns 'overwrite' 覆盖 / 'skip' 跳过（用户取消时 reject）
 */
export async function confirmDuplicateAction(message: string): Promise<'overwrite' | 'skip'> {
  try {
    await ElMessageBox.confirm(
      `${escapeHtml(message)}\n\n选择"覆盖"将删除旧数据后重新处理，选择"跳过"将保留现有数据。`,
      '检测到重复',
      {
        confirmButtonText: '覆盖',
        cancelButtonText: '跳过',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
    return 'overwrite'
  } catch (action) {
    if (action === 'cancel') return 'skip'
    throw action // close（点 X）时 reject
  }
}

/**
 * 强制通过确认弹窗（复核有未解决意见时）
 * @param reason 强制通过的原因提示
 * @returns { confirmed: true, note: 用户输入的备注 }（取消时 reject）
 */
export async function confirmForcePass(reason: string): Promise<{ confirmed: boolean; note: string }> {
  const { value } = await ElMessageBox.prompt(
    `${escapeHtml(reason)}\n\n确定要强制通过吗？请填写原因：`,
    '强制通过确认',
    {
      confirmButtonText: '强制通过',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      inputPlaceholder: '请输入强制通过的原因...',
      inputValidator: (v: string) => (v && v.trim().length >= 2) || '原因至少 2 个字符',
    },
  )
  return { confirmed: true, note: value }
}
