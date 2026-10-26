/**
 * useProgramRowControl（spec procedure-trim-generation-delegation-chain 需求 6 / 7）：行归属的放开 / 收紧口径、
 * 切换底稿时丢弃过期回执、按行裁剪的错误人话，以及 HTML 保存回执里没生效的程序号提示。
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
  rowTrimErrorText,
  useProgramRowControl,
  warnIgnoredPrograms,
} from '../useProgramRowControl'

const ACCESS = { full_power: false, can_trim: false, own_program_nos: ['2'], assignees: { 2: '甲' }, template_code: 'D2A' }

beforeEach(() => {
  api.setApplicability.mockReset()
  api.getAccess.mockReset()
  vi.spyOn(ElMessage, 'warning').mockImplementation((() => undefined) as any)
})
afterEach(() => { vi.restoreAllMocks() })

describe('行归属', () => {
  it('没加载 / 读不到 ⇒ 放开；受限 ⇒ 只放本人行', async () => {
    const ctl = useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => 'D2A' })
    expect([ctl.canEditRow({ program_no: 9 }), ctl.canTrim.value, ctl.fullPower.value]).toEqual([true, true, true])
    api.getAccess.mockResolvedValueOnce(ACCESS)
    await ctl.loadAccess()
    expect(api.getAccess).toHaveBeenCalledWith('wp1', 'D2A')
    expect([ctl.canEditRow({ program_no: 2 }), ctl.canEditRow({ program_no: '2' }), ctl.canEditRow({ program_no: 3 })])
      .toEqual([true, true, false])
    expect([ctl.canTrim.value, ctl.fullPower.value, ctl.assigneeOf({ program_no: 2 }), ctl.assigneeOf({ program_no: 3 })])
      .toEqual([false, false, '甲', ''])
    api.getAccess.mockRejectedValueOnce(new Error('网络错误'))
    await ctl.loadAccess()
    expect(ctl.canEditRow({ program_no: 3 })).toBe(true)
  })

  it('换了底稿 / 程序表后，旧请求晚到的结果丢弃；缺底稿或页名不请求', async () => {
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
    const done = await ctl().applyRows('trim', [{ program_no: 1 }, { program_no: 7 }, { program_no: 3 }], '不适用')
    expect([...done]).toEqual(['1', '7'])
    const [first] = api.setApplicability.mock.calls
    expect(first.slice(0, 3)).toEqual(['p1', 'wp1', 'trim'])
    expect(first[3]).toMatchObject({ sheet_name: '程序表D2A', program_no: '1', reason: '不适用' })
    expect(typeof first[3].request_id).toBe('string')
    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    expect(ElMessage.warning).toHaveBeenCalledWith('裁剪没有生效 —— 第 3 条：只有项目经理 / 合伙人可以裁剪或恢复程序')
  })

  it('宿主没传程序表页名（汇总包内嵌控制台）⇒ 不调接口，只在页面上标记（与改前相同）', async () => {
    const bare = useProgramRowControl({ projectId: () => 'p1', wpId: () => 'wp1', sheetName: () => '' })
    expect([...(await bare.applyRows('trim', [{ program_no: 2 }], 'x'))]).toEqual(['2'])
    expect([...(await bare.applyRows('restore', [{ program_no: 2 }]))]).toEqual(['2'])
    expect(api.setApplicability).not.toHaveBeenCalled()
  })

  it('恢复遇到 422 不当成功（页面上的不适用由调用方保持）', async () => {
    api.setApplicability.mockRejectedValueOnce({ response: { status: 422, data: { detail: { error: 'row_trim_unsupported' } } } })
    expect((await ctl().applyRows('restore', [{ program_no: 5 }])).size).toBe(0)
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
