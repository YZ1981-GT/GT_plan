/**
 * 公式「导入导出▾」下拉接入后的行为（spec formula-governance-coverage-closure R4.1 / R4.2）：
 * - 预设库模式：导入入库按角色门控（禁用 + 原因，点了也不弹选文件）；非管理员导入提示「已提交为全局候选」。
 * - 公式包模式：导入须有本项目编辑权限；导出 0 条不生成文件；导入走 PUT overrides 并通知宿主刷新。
 * 只替换网络层（http / formulaSettingsApi）与消息框。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const fs = vi.hoisted(() => ({ domains: vi.fn(), effective: vi.fn(), saveOverrides: vi.fn() }))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: fs }))
const httpPost = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', () => ({ default: { post: httpPost, get: vi.fn() } }))
const msg = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const confirm = vi.hoisted(() => vi.fn())
vi.mock('element-plus', async (orig) => ({
  ...(await orig<typeof import('element-plus')>()), ElMessage: msg, ElMessageBox: { confirm },
}))

import FormulaImportExportDropdown from '../FormulaImportExportDropdown.vue'

const stubs = {
  ElButton: { template: '<button><slot /></button>' },
  ElDropdown: { template: '<div><slot /><slot name="dropdown" /></div>' },
  ElDropdownMenu: { template: '<ul><slot /></ul>' },
  ElDropdownItem: {
    props: ['command', 'disabled'],
    template: '<li :data-command="command" :data-disabled="String(!!disabled)"><slot /></li>',
  },
}
const mountDd = (props: Record<string, unknown>) =>
  mount(FormulaImportExportDropdown, { props, global: { stubs }, attachTo: document.body })

const INFOS = [{ key: 'report', label: '报表公式', scope_kind: 'standard', wired: true, scopes: [], exec_fields: [], desc_fields: [] }]

function pickFile(w: ReturnType<typeof mountDd>, accept: string, file: File) {
  const input = w.find(`input[accept="${accept}"]`).element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input.dispatchEvent(new Event('change'))
}
/** jsdom 的 File 不一定有 text()：公式包只读文本，给一个带 text() 的文件对象 */
const jsonFile = (text: string) => ({ name: 'p.json', text: async () => text }) as unknown as File

let clickSpy: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  vi.clearAllMocks()
  clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {})
  fs.domains.mockResolvedValue({ domains: INFOS, is_admin: false })
  fs.saveOverrides.mockResolvedValue({ saved: [] })
})

describe('预设库模式', () => {
  it('无写预设角色：「导入数据」禁用并写明原因，点了也不弹选文件', async () => {
    const w = mountDd({ mode: 'preset', canImport: false, pageKey: 'workpaper:D2' })
    const item = w.find('[data-command="import"]')
    expect(item.attributes('data-disabled')).toBe('true')
    expect(item.attributes('title')).toBe('导入入库仅限管理员 / 合伙人')
    expect(w.find('[data-command="export"]').text()).toBe('导出数据（workpaper:D2）')
    await (w.vm as any).$.setupState.onCommand('import')
    expect(clickSpy).not.toHaveBeenCalled()
    expect(w.findAll('[data-command="export-package"]')).toHaveLength(0)
  })

  it('合伙人导入：提交为全局候选，提示审核后生效（不说「成功导入」）', async () => {
    const w = mountDd({ mode: 'preset', canImport: true })
    await (w.vm as any).$.setupState.onCommand('import')
    expect(clickSpy).toHaveBeenCalledTimes(1)
    httpPost.mockResolvedValueOnce({ data: { ok: true, imported_count: 2, skipped_count: 0, imported: [], skipped: [],
      pending_review: true, candidate: { id: 'c1', status: 'pending' } } })
    pickFile(w, '.xlsx', new File(['x'], 'f.xlsx'))
    await flushPromises()
    expect(httpPost.mock.calls[0][0]).toBe('/api/formula-management/import-export/import-data')
    expect(httpPost.mock.calls[0][2].params).toEqual({})
    expect(msg.success).toHaveBeenCalledWith(expect.stringContaining('提交为全局候选'))
    expect(msg.success.mock.calls[0][0]).not.toContain('成功导入')
    expect(w.emitted('imported')![0][0]).toMatchObject({ pending_review: true })
  })
})

describe('公式包模式', () => {
  it('只读账号：「导入公式包」禁用，点了也不弹选文件', async () => {
    const w = mountDd({ mode: 'package', projectId: 'p1', canEditProject: false })
    expect(w.find('[data-command="import-package"]').attributes('data-disabled')).toBe('true')
    expect(w.find('[data-command="export-package"]').attributes('data-disabled')).toBe('false')
    await (w.vm as any).$.setupState.onCommand('import-package')
    expect(clickSpy).not.toHaveBeenCalled()
    expect(w.findAll('[data-command="import"]')).toHaveLength(0)
  })

  it('本项目没有适配：导出提示原因、不生成文件', async () => {
    // jsdom 没有 createObjectURL：装一个桩，断言它没被调（没生成文件）
    const created = vi.fn()
    ;(URL as any).createObjectURL = created
    fs.effective.mockResolvedValue({ domain: 'report', project_id: 'p1', scope: 'soe_standalone', frozen: false,
      can_edit_global: false, slots: [{ slot_key: 'a', label: 'a', layer: 'preset', definition: { formula: '1' } }] })
    const w = mountDd({ mode: 'package', projectId: 'p1', canEditProject: true })
    await (w.vm as any).$.setupState.onCommand('export-package')
    await flushPromises()
    expect(msg.info).toHaveBeenCalledWith('本项目没有公式适配可导出（全部沿用全局设置 / 系统预设）')
    expect(created).not.toHaveBeenCalled()
  })

  it('有适配：生成 JSON 文件并提示条数', async () => {
    const blobs: Blob[] = []
    ;(URL as any).createObjectURL = vi.fn((b: Blob) => { blobs.push(b); return 'blob:x' })
    ;(URL as any).revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}) // jsdom 不做下载导航
    fs.effective.mockResolvedValue({ domain: 'report', project_id: 'p1', scope: 'soe_standalone', frozen: false,
      can_edit_global: false, slots: [{ slot_key: 'a', label: 'A', layer: 'project', definition: { formula: '1' } }] })
    const w = mountDd({ mode: 'package', projectId: 'p1', canEditProject: false })
    await (w.vm as any).$.setupState.onCommand('export-package')
    await flushPromises()
    expect(blobs).toHaveLength(1)
    const text = await new Promise<string>((res) => {
      const r = new FileReader()
      r.onload = () => res(String(r.result))
      r.readAsText(blobs[0])
    })
    const pack = JSON.parse(text)
    expect(pack.domains.report.slots.map((s: any) => s.slot_key)).toEqual(['a'])
    expect(msg.success).toHaveBeenCalledWith('已导出 1 条本项目公式适配（1 类）')
  })

  it('导入公式包：确认后 PUT 写本项目适配，按结果提示并通知宿主刷新', async () => {
    fs.effective.mockResolvedValue({ domain: 'report', project_id: 'p1', scope: 'soe_standalone', frozen: false,
      can_edit_global: false, slots: [{ slot_key: 'a', label: 'A', layer: 'project', definition: { formula: '1' },
        local_version: 4, structure: {} }] })
    confirm.mockResolvedValue('confirm')
    const w = mountDd({ mode: 'package', projectId: 'p1', canEditProject: true })
    const text = JSON.stringify({ format: 'gt_formula_package', version: '1.1', domains: {
      report: { scope: 'soe_standalone', slots: [{ slot_key: 'a', definition: { formula: '2' } }] } } })
    pickFile(w, '.json', jsonFile(text))
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(fs.saveOverrides).toHaveBeenCalledWith('p1', 'report', [
      { slot_key: 'a', definition: { formula: '2' }, expected_version: 4, label: 'A', structure: null }])
    expect(msg.success).toHaveBeenCalledWith('已写入 1 条')
    expect(w.emitted('package-applied')).toEqual([[['report']]])
  })

  it('取消确认：不写', async () => {
    confirm.mockRejectedValue('cancel')
    const w = mountDd({ mode: 'package', projectId: 'p1', canEditProject: true })
    const text = JSON.stringify({ format: 'gt_formula_package', domains: {
      report: { scope: 'soe_standalone', slots: [{ slot_key: 'a', definition: { formula: '2' } }] } } })
    pickFile(w, '.json', jsonFile(text))
    await flushPromises()
    expect(fs.saveOverrides).not.toHaveBeenCalled()
    expect(w.emitted('package-applied')).toBeUndefined()
  })
})
