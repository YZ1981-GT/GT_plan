/**
 * 模板复制弹窗（spec procedure-chain-hardening-and-java-contracts R3）：不再提供未实现的「覆盖」，
 * 结果按复制 / 跳过 / 失败计数提示（原先不论结果都提示「模板复制完成」），失败显示后端原因。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const copy = vi.hoisted(() => ({ templateCopy: vi.fn() }))
const msg = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock('@/composables/useWpExportImport', async () => {
  const { ref } = await import('vue')
  return { useWpExportImport: () => ({ templateCopy: copy.templateCopy, loading: ref(false) }) }
})
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: msg,
}))

import WpTemplateCopyDialog from '../WpTemplateCopyDialog.vue'

// 结果表的列模板带作用域插槽（{ row }）：未注册的 el-table-column 会被当成普通元素、无参调用插槽 ⇒ 存根掉
const stubs = {
  'el-dialog': { template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-table': true,
  'el-table-column': true,
}
const mk = () => mount(WpTemplateCopyDialog, { props: { modelValue: true, projectId: 'p1' }, global: { stubs } })

beforeEach(() => {
  copy.templateCopy.mockReset()
  Object.values(msg).forEach((f) => f.mockReset())
})

describe('WpTemplateCopyDialog', () => {
  it('没有「覆盖」勾选项，请求不带 overwrite', async () => {
    const w = mk()
    expect(w.html()).not.toContain('<el-checkbox')
    expect(w.text()).not.toContain('覆盖目标已有同编码底稿')
    copy.templateCopy.mockResolvedValueOnce({ source_wp_code: 'D2', status: 'copied' })
    const vm = w.vm as any
    vm.sourceWpId = ' wp-src '
    await vm.handleCopy()
    expect(copy.templateCopy).toHaveBeenCalledWith('p1', { source_wp_id: 'wp-src' })
    expect(msg.success).toHaveBeenCalledWith('已复制 1 份底稿')
  })

  it('全部跳过 ⇒ 提示没有复制任何底稿（原先提示「模板复制完成」）', async () => {
    copy.templateCopy.mockResolvedValueOnce([
      { source_wp_code: 'D2', status: 'skipped', message: '无权查看该底稿（未委派给你），未复制' },
    ])
    const w = mk()
    const vm = w.vm as any
    vm.copyMode = 'cycle'
    vm.sourceProjectId = 'src-p'
    vm.auditCycle = 'D'
    await vm.handleCopy()
    expect(copy.templateCopy).toHaveBeenCalledWith('p1', { source_project_id: 'src-p', audit_cycle: 'D' })
    expect(msg.success).not.toHaveBeenCalled()
    expect(msg.warning).toHaveBeenCalledWith('没有复制任何底稿：跳过 1 份（原因见下表）')
    expect(w.emitted('copied')![0][0]).toHaveLength(1)
  })

  it('请求失败 ⇒ 显示后端原因；没有原因给中文兜底', async () => {
    const vm = mk().vm as any
    vm.sourceWpId = 'wp-src'
    copy.templateCopy.mockRejectedValueOnce({ response: { status: 404, data: { detail: '源底稿不存在' } } })
    await vm.handleCopy()
    expect(msg.error).toHaveBeenLastCalledWith('源底稿不存在')
    copy.templateCopy.mockRejectedValueOnce(new Error('Network Error'))
    await vm.handleCopy()
    expect(msg.error).toHaveBeenLastCalledWith('模板复制失败，请稍后重试')
  })
})
