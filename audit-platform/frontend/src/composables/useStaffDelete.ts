/**
 * 删除人员档案（spec procedure-chain-hardening-and-java-contracts R12）。
 *
 * 先按原样删；人员仍在项目团队中 ⇒ 后端 409 列出项目 ⇒ 二次确认（写明会撤销这些项目的团队分配与项目成员权限）
 * 后带 `revoke_assignments` 重试。原先后端只要求登录、直接软删档案，分配与成员行原样留下（其账号照样能进项目）。
 */
import { deleteStaff, staffHasAssignments, type StaffHasAssignmentsDetail } from '@/services/staffApi'
import { confirmDangerous } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'

/**
 * 确认框正文：后端提示已点名全部项目时原样用（原先再拼一遍「涉及项目」⇒ 项目名出现两次）；
 * 后端只点名前几个（超出时写「等」）时补全部项目名。
 */
export function staffBusyConfirmMessage(busy: StaffHasAssignmentsDetail): string {
  const names = busy.projects.map((p) => p.project_name)
  const unnamed = names.filter((n) => !busy.message.includes(n))
  return unnamed.length ? `${busy.message}。全部项目：${names.join('、')}` : busy.message
}

/** 返回 true = 已删除；false = 用户取消，或删除失败（失败已提示）。 */
export async function deleteStaffWithConfirm(staff: { id: string; name: string }): Promise<boolean> {
  try {
    await deleteStaff(staff.id)
    return true
  } catch (e) {
    const busy = staffHasAssignments(e)
    if (!busy) {
      handleApiError(e, '删除')
      return false
    }
    try {
      await confirmDangerous({
        title: `「${staff.name}」仍在项目团队中`,
        message: staffBusyConfirmMessage(busy),
        confirmText: '撤销分配并删除',
      })
    } catch {
      return false
    }
    try {
      await deleteStaff(staff.id, { revokeAssignments: true })
      return true
    } catch (e2) {
      handleApiError(e2, '删除')
      return false
    }
  }
}
