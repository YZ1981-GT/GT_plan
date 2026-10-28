/**
 * useProgramRowControl（spec procedure-trim-generation-delegation-chain 需求 6 / 7）：行归属的放开 / 收紧口径、
 * 切换底稿时丢弃过期回执、按行裁剪的错误人话，以及 HTML 保存回执里没生效的程序号提示。
 * spec procedure-chain-hardening-and-java-contracts：读不到整表只读（R7）、没有页名照常落任务（R6）、
 * 恢复回执带原执行人（R4）、只在页面标记的行另行提示。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'

const api = vi.hoisted(() => ({ setApplicability: vi.fn(), getAccess: vi.fn() }))
vi.mock('@/services/commonApi', () => ({
  setProgramRowApplicability: api.setApplicability,
  getProgramRowAccess: api.getAccess,
}))

import {
  ignoredProgramsText,
  isPageOnlyRow,
  restoredRowText,
  rowAccessErrorText,
  rowTrimErrorText,
  useProgramRowControl,
  warnIgnoredPrograms,
} from '../useProgramRowControl'

const ACCESS = { full_power: false, can_trim: false, own_program_nos: ['2'], assignees: { 2: '甲' }, template_code: 'D2A' }

beforeEach(() => {
  api.setApplicability.mockReset()
  api.getAccess.mockReset()
  vi.spyOn(ElMessage, 'warning').mockImplementation((() => undefined) as any)
  vi.spyOn(ElMessage, 'info').mockImplementation((() => undefined) as any)
})
afterEach(() => { vi.restoreAllMocks() })

describe('行归属', () => {
  it('读到之前 / 读不到 ⇒ 整表只读（R7：原先按全权放开）；受限 ⇒ 只放本人行', async () => {
    const ctl = useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => 'D2A' })
    let resolve: (v: unknown) => void = () => undefined
    api.getAccess.mockImplementationOnce(() => new Promise((r) => { resolve = r }))
    const pending = ctl.loadAccess()
    expect(ctl.accessState.value).toBe('loading')
    expect([ctl.canEditRow({ program_no: 2 }), ctl.canTrim.value, ctl.fullPower.value]).toEqual([false, false, false])
    resolve(ACCESS)
    await pending
    expect(api.getAccess).toHaveBeenCalledWith('wp1', 'D2A')
    expect(ctl.accessState.value).toBe('ready')
    expect([ctl.canEditRow({ program_no: 2 }), ctl.canEditRow({ program_no: '2' }), ctl.canEditRow({ program_no: 3 })])
      .toEqual([true, true, false])
    expect([ctl.canTrim.value, ctl.fullPower.value, ctl.assigneeOf({ program_no: 2 }), ctl.assigneeOf({ program_no: 3 })])
      .toEqual([false, false, '甲', ''])
    api.getAccess.mockRejectedValueOnce({ response: { status: 500, data: { detail: '服务暂不可用' } } })
    await ctl.loadAccess()
    expect([ctl.accessState.value, ctl.accessError.value]).toEqual(['error', '服务暂不可用'])
    expect([ctl.canEditRow({ program_no: 2 }), ctl.canEditRow({ program_no: 3 }), ctl.canTrim.value, ctl.fullPower.value])
      .toEqual([false, false, false, false])
    api.getAccess.mockResolvedValueOnce({ ...ACCESS, full_power: true, can_trim: true })
    await ctl.loadAccess() // 重试
    expect([ctl.accessState.value, ctl.accessError.value, ctl.canEditRow({ program_no: 3 })]).toEqual(['ready', '', true])
  })

  it('没有底稿 ⇒ 不请求、不限制（没有可写的服务端）；没有页名 ⇒ 照常请求（服务端按底稿编码定位，R6）', async () => {
    const none = useProgramRowControl({ projectId: () => 'p1', wpId: () => '', sheetName: () => 'D2A' })
    await none.loadAccess()
    expect([none.accessState.value, none.canEditRow({ program_no: 9 }), none.canTrim.value]).toEqual(['idle', true, true])
    expect(api.getAccess).not.toHaveBeenCalled()
    const bare = useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => '' })
    api.getAccess.mockResolvedValueOnce(ACCESS)
    await bare.loadAccess()
    expect(api.getAccess).toHaveBeenCalledWith('wp1', '')
    expect(bare.accessState.value).toBe('ready')
  })

  it('读不到的人话', () => {
    expect(rowAccessErrorText({ response: { status: 404 } })).toBe('没有这张底稿的访问权限')
    expect(rowAccessErrorText({ response: { status: 403 } })).toBe('没有这张底稿的访问权限')
    expect(rowAccessErrorText(new Error('x'))).toBe('网络或服务异常')
  })

  it('换了底稿 / 程序表后，旧请求晚到的结果丢弃；缺底稿不请求', async () => {
    const wpId = ref('wp1')
    const ctl = useProgramRowControl({ projectId: () => 'p1', wpId: () => wpId.value, sheetName: () => 'D2A' })
    let resolveOld: (v: unknown) => void = () => undefined
    api.getAccess.mockImplementationOnce(() => new Promise((r) => { resolveOld = r }))
    const pending = ctl.loadAccess()
    wpId.value = 'wp2'
    resolveOld(ACCESS)
    await pending
    await nextTick()
    expect(ctl.access.value).toBeNull()

    wpId.value = ''
    await ctl.loadAccess()
    expect(api.getAccess).toHaveBeenCalledTimes(1)
  })
})

describe('按行裁剪 / 恢复', () => {
  const ctl = () => useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => '程序表D2A' })

  it('逐行调用、带请求号；成功与只在页面标记的行计入，其余逐条提示', async () => {
    api.setApplicability
      .mockResolvedValueOnce({ changed: true })
      .mockRejectedValueOnce({ response: { status: 422, data: { detail: { error: 'row_trim_unsupported', message: 'x' } } } })
      .mockRejectedValueOnce({ response: { status: 403, data: { detail: '项目授权失败' } } })
    const { done, pageOnly } = await ctl().applyRows('trim', [{ program_no: 1 }, { program_no: 7 }, { program_no: 3 }], '不适用')
    expect([[...done], [...pageOnly]]).toEqual([['1', '7'], ['7']])
    const [first] = api.setApplicability.mock.calls
    expect(first.slice(0, 3)).toEqual(['p1', 'wp1', 'trim'])
    expect(first[3]).toMatchObject({ sheet_name: '程序表D2A', program_no: '1', reason: '不适用' })
    expect(typeof first[3].request_id).toBe('string')
    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    expect(ElMessage.warning).toHaveBeenCalledWith('裁剪没有生效 —— 第 3 条：只有项目经理 / 合伙人可以裁剪或恢复程序')
    expect(ElMessage.info).toHaveBeenCalledWith(expect.stringContaining('第 7 条仅页面标记，未写入任务'))
  })

  it('宿主没传程序表页名（汇总包内嵌控制台）⇒ 照常落任务，页名传空串由服务端按底稿编码定位（R6）', async () => {
    api.setApplicability.mockResolvedValue({ changed: true })
    const bare = useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => '' })
    expect([...(await bare.applyRows('trim', [{ program_no: 2 }], 'x')).done]).toEqual(['2'])
    expect([...(await bare.applyRows('restore', [{ program_no: 2 }])).done]).toEqual(['2'])
    expect(api.setApplicability.mock.calls.map((c: any[]) => [c[2], c[3].sheet_name])).toEqual([['trim', ''], ['restore', '']])
    expect(ElMessage.info).not.toHaveBeenCalled()
  })

  it('没有底稿 ⇒ 不调接口，只在页面上标记、不提示', async () => {
    const none = useProgramRowControl({ projectId: () => 'p1', wpId: () => '', sheetName: () => 'D2A' })
    const res = await none.applyRows('trim', [{ program_no: 2 }], 'x')
    expect([[...res.done], [...res.pageOnly]]).toEqual([['2'], ['2']])
    expect(api.setApplicability).not.toHaveBeenCalled()
    expect(ElMessage.info).not.toHaveBeenCalled()
  })

  it('恢复回执：需重新委派 + 原执行人去重汇总；提示文案', async () => {
    api.setApplicability
      .mockResolvedValueOnce({ changed: true, requires_reassign: true, previous_assignees: ['张三'] })
      .mockResolvedValueOnce({ changed: true, requires_reassign: true, previous_assignees: ['张三', '李四'] })
    const res = await ctl().applyRows('restore', [{ program_no: 1 }, { program_no: 2 }])
    expect([res.requiresReassign, res.previousAssignees]).toEqual([true, ['张三', '李四']])
    expect(restoredRowText(res)).toBe('已恢复执行，原执行人已清除（原执行人：张三、李四），请重新委派')
    expect(restoredRowText({ requiresReassign: true, previousAssignees: [] })).toBe('已恢复执行，原执行人已清除，请重新委派')
    expect(restoredRowText({ requiresReassign: false, previousAssignees: [] })).toBe('已恢复执行')
  })

  it('恢复遇到 422 不当成功（页面上的不适用由调用方保持）', async () => {
    api.setApplicability.mockRejectedValueOnce({ response: { status: 422, data: { detail: { error: 'row_trim_unsupported' } } } })
    expect((await ctl().applyRows('restore', [{ program_no: 5 }])).done.size).toBe(0)
  })

  it('错误人话：403 / 字符串详情 / 对象详情 / 兜底；只认 422 + row_trim_unsupported 为页面标记', () => {
    expect(rowTrimErrorText({ response: { status: 403 } })).toBe('只有项目经理 / 合伙人可以裁剪或恢复程序')
    expect(rowTrimErrorText({ response: { status: 409, data: { detail: '已复核任务不可取消' } } })).toBe('已复核任务不可取消')
    expect(rowTrimErrorText({ response: { status: 404, data: { detail: { message: '底稿不存在' } } } })).toBe('底稿不存在')
    expect(rowTrimErrorText(new Error('x'))).toBe('请求失败，请稍后重试')
    expect(isPageOnlyRow({ response: { status: 422, data: { detail: { error: 'row_trim_unsupported' } } } })).toBe(true)
    expect(isPageOnlyRow({ response: { status: 422, data: { detail: '裁剪理由必填' } } })).toBe(false)
    expect(isPageOnlyRow({ response: { status: 400, data: { detail: { error: 'row_trim_unsupported' } } } })).toBe(false)
  })
})

describe('HTML 保存回执', () => {
  it('有没生效的程序号才提示', () => {
    expect(ignoredProgramsText(['2', 4])).toBe(
      '第 2、4 条程序的修改没有保存：只能修改派给自己的程序行，裁剪 / 恢复须由项目经理或合伙人操作')
    expect(ignoredProgramsText([])).toBe('')
    expect(ignoredProgramsText(undefined)).toBe('')
    warnIgnoredPrograms({ saved_at: 'x', ignored_program_nos: [] })
    warnIgnoredPrograms(undefined)
    expect(ElMessage.warning).not.toHaveBeenCalled()
    warnIgnoredPrograms({ ignored_program_nos: ['3'] })
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('第 3 条程序的修改没有保存'))
  })
})
