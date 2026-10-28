/**
 * 删除人员档案的二次确认（spec procedure-chain-hardening-and-java-contracts R12）。
 *
 * 真 staffApi（只替换 http）：仍在项目团队中 ⇒ 后端 409 列出项目 ⇒ 弹确认写明撤销范围 ⇒ 带 revoke_assignments 重试；
 * 请求一律 `_silent`（错误由调用方提示，全局拦截器不先弹一次笼统提示）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  del: vi.fn(),
  confirmDangerous: vi.fn(),
  handleApiError: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { delete: (...a: any[]) => mocks.del(...a) } }))
vi.mock('@/utils/confirm', () => ({ confirmDangerous: (...a: any[]) => mocks.confirmDangerous(...a) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: (...a: any[]) => mocks.handleApiError(...a) }))

import { staffHasAssignments, type StaffHasAssignmentsDetail } from '@/services/staffApi'
import { deleteStaffWithConfirm, staffBusyConfirmMessage } from '../useStaffDelete'

const BUSY: StaffHasAssignmentsDetail = {
  error: 'staff_has_assignments',
  message: '该人员仍在 2 个项目的团队中（【测试】甲、【测试】乙），确认删除将同时撤销其在这些项目的团队分配与项目成员权限',
  projects: [
    { project_id: 'p1', project_name: '【测试】甲', roles: ['auditor'] },
    { project_id: 'p2', project_name: '【测试】乙', roles: ['manager'] },
  ],
}

function httpError(status: number, data: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data } })
}

beforeEach(() => {
  mocks.del.mockReset()
  mocks.confirmDangerous.mockReset()
  mocks.handleApiError.mockReset()
})

describe('deleteStaffWithConfirm', () => {
  it('没有项目分配：直接删除，请求静默且不带撤权参数', async () => {
    mocks.del.mockResolvedValueOnce({ data: { message: '已删除' } })
    expect(await deleteStaffWithConfirm({ id: 's1', name: '张三' })).toBe(true)
    expect(mocks.del).toHaveBeenCalledTimes(1)
    expect(mocks.del).toHaveBeenCalledWith('/api/staff/s1', { params: undefined, _silent: true })
    expect(mocks.confirmDangerous).not.toHaveBeenCalled()
  })

  it('仍在项目团队中：确认框列出项目与撤销范围，确认后带 revoke_assignments 重试', async () => {
    mocks.del.mockRejectedValueOnce(httpError(409, { code: 409, message: BUSY }))
    mocks.del.mockResolvedValueOnce({ data: { message: '已删除', revoked_assignments: 2 } })
    mocks.confirmDangerous.mockResolvedValueOnce(undefined)
    expect(await deleteStaffWithConfirm({ id: 's1', name: '张三' })).toBe(true)
    const [opts] = mocks.confirmDangerous.mock.calls[0]
    expect(opts.title).toBe('「张三」仍在项目团队中')
    // 后端提示已点名全部项目 ⇒ 原样展示，项目名不重复出现（浏览器实测曾显示两遍）
    expect(opts.message).toBe(BUSY.message)
    expect(opts.message.split('【测试】甲').length - 1).toBe(1)
    expect(opts.confirmText).toBe('撤销分配并删除')
    expect(mocks.del).toHaveBeenLastCalledWith('/api/staff/s1', { params: { revoke_assignments: true }, _silent: true })
    expect(mocks.handleApiError).not.toHaveBeenCalled()
  })

  it('取消确认：不重试、不提示错误', async () => {
    mocks.del.mockRejectedValueOnce(httpError(409, { code: 409, message: BUSY }))
    mocks.confirmDangerous.mockRejectedValueOnce('cancel')
    expect(await deleteStaffWithConfirm({ id: 's1', name: '张三' })).toBe(false)
    expect(mocks.del).toHaveBeenCalledTimes(1)
    expect(mocks.handleApiError).not.toHaveBeenCalled()
  })

  it('其他错误（无权 / 初始导入不许删）：交给 handleApiError，不弹确认', async () => {
    const forbidden = httpError(403, { code: 403, message: '权限不足' })
    mocks.del.mockRejectedValueOnce(forbidden)
    expect(await deleteStaffWithConfirm({ id: 's1', name: '张三' })).toBe(false)
    expect(mocks.handleApiError).toHaveBeenCalledWith(forbidden, '删除')
    expect(mocks.confirmDangerous).not.toHaveBeenCalled()
  })
})

describe('staffBusyConfirmMessage', () => {
  it('后端只点名前 5 个项目（写「等」）⇒ 补全部项目名；全部点名 ⇒ 原样', () => {
    const projects = ['甲', '乙', '丙', '丁', '戊', '己'].map((n, i) => ({
      project_id: `p${i}`, project_name: `【测试】${n}`, roles: ['auditor'],
    }))
    const busy: StaffHasAssignmentsDetail = {
      error: 'staff_has_assignments',
      message: '该人员仍在 6 个项目的团队中（【测试】甲、【测试】乙、【测试】丙、【测试】丁、【测试】戊 等），确认删除将同时撤销其在这些项目的团队分配与项目成员权限',
      projects,
    }
    expect(staffBusyConfirmMessage(busy)).toBe(
      `${busy.message}。全部项目：【测试】甲、【测试】乙、【测试】丙、【测试】丁、【测试】戊、【测试】己`,
    )
    expect(staffBusyConfirmMessage(BUSY)).toBe(BUSY.message)
  })
})

describe('删除入口与后端同一角色口径（只有 admin）', () => {
  it('人员管理页「删除」只对 admin 显示；后端 delete_staff 挂 require_role(["admin"])', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    let root = __dirname
    while (!fs.existsSync(path.join(root, 'backend', 'app', 'routers', 'staff.py'))) {
      const up = path.dirname(root)
      if (up === root) throw new Error('找不到仓库根')
      root = up
    }
    const strip = (s: string) => s.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    const view = strip(fs.readFileSync(path.join(root, 'audit-platform/frontend/src/views/StaffManagement.vue'), 'utf-8'))
    expect(view).toMatch(/v-if="row\.source === 'custom' && isAdmin" command="delete"/)
    expect(view).toMatch(/const isAdmin = computed\(\(\) => \(useAuthStore\(\)\.user\?\.role \|\| ''\) === 'admin'\)/)
    const router = fs.readFileSync(path.join(root, 'backend/app/routers/staff.py'), 'utf-8')
    const sig = (router.split('async def delete_staff(')[1] ?? '').split('):')[0]
    expect(sig).toMatch(/Depends\(require_role\(\["admin"\]\)\)/)
  })
})

describe('staffHasAssignments', () => {
  it('认平台错误信封（message 是对象）与 FastAPI 原生 detail；其他 409 / 状态码返回 null', () => {
    expect(staffHasAssignments(httpError(409, { code: 409, message: BUSY }))?.projects).toHaveLength(2)
    expect(staffHasAssignments(httpError(409, { detail: BUSY }))?.error).toBe('staff_has_assignments')
    expect(staffHasAssignments(httpError(409, { code: 409, message: '程序编码已存在' }))).toBeNull()
    expect(staffHasAssignments(httpError(400, { code: 400, message: BUSY }))).toBeNull()
    expect(staffHasAssignments(new Error('network'))).toBeNull()
  })
})
