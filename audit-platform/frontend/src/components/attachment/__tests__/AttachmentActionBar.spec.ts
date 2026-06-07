/**
 * AttachmentActionBar — P0-4.4 UAT 测试
 *
 * 验证：docx/xlsx/pdf 三类附件动作清晰
 * - docx: 预览+编辑+下载+引用（OnlyOffice healthy 时）
 * - xlsx: 同上
 * - pdf: 预览+下载+引用（无编辑按钮）
 * - readOnly 模式：编辑按钮隐藏
 * - OnlyOffice 不可用：编辑按钮隐藏
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AttachmentActionBar from '../AttachmentActionBar.vue'

const mountBar = (overrides: Record<string, any> = {}) =>
  mount(AttachmentActionBar, {
    props: {
      attachment: { id: 'att-1', file_name: 'test.docx', file_type: 'docx' },
      projectId: 'proj-1',
      onlyofficeHealth: 'healthy',
      readOnly: false,
      ...overrides,
    },
    global: {
      stubs: {
        ElButton: { template: '<button :disabled="$attrs.disabled" @click="$emit(\'click\')"><slot /></button>', inheritAttrs: true },
        ElTag: { template: '<span class="el-tag"><slot /></span>' },
      },
    },
  })

describe('AttachmentActionBar', () => {
  it('docx + healthy: 显示预览、编辑、下载、引用四个按钮', () => {
    const wrapper = mountBar({
      attachment: { id: '1', file_name: '合同.docx', file_type: 'docx' },
      onlyofficeHealth: 'healthy',
    })
    const buttons = wrapper.findAll('button')
    const texts = buttons.map((b) => b.text())
    expect(texts).toContain('预览')
    expect(texts).toContain('编辑')
    expect(texts).toContain('下载')
    expect(texts).toContain('引用')
  })

  it('xlsx + healthy: 显示编辑按钮', () => {
    const wrapper = mountBar({
      attachment: { id: '2', file_name: '明细.xlsx', file_type: 'xlsx' },
      onlyofficeHealth: 'healthy',
    })
    const texts = wrapper.findAll('button').map((b) => b.text())
    expect(texts).toContain('编辑')
  })

  it('pdf: 无编辑按钮', () => {
    const wrapper = mountBar({
      attachment: { id: '3', file_name: '报告.pdf', file_type: 'pdf' },
      onlyofficeHealth: 'healthy',
    })
    const texts = wrapper.findAll('button').map((b) => b.text())
    expect(texts).not.toContain('编辑')
    expect(texts).toContain('预览')
    expect(texts).toContain('下载')
    expect(texts).toContain('引用')
  })

  it('readOnly 模式：无编辑按钮', () => {
    const wrapper = mountBar({
      attachment: { id: '4', file_name: '合同.docx', file_type: 'docx' },
      onlyofficeHealth: 'healthy',
      readOnly: true,
    })
    const texts = wrapper.findAll('button').map((b) => b.text())
    expect(texts).not.toContain('编辑')
  })

  it('OnlyOffice unavailable: 无编辑按钮', () => {
    const wrapper = mountBar({
      attachment: { id: '5', file_name: '合同.docx', file_type: 'docx' },
      onlyofficeHealth: 'unavailable',
    })
    const texts = wrapper.findAll('button').map((b) => b.text())
    expect(texts).not.toContain('编辑')
  })

  it('healthy 状态显示"在线编辑可用"', () => {
    const wrapper = mountBar({ onlyofficeHealth: 'healthy' })
    expect(wrapper.text()).toContain('在线编辑可用')
  })

  it('unavailable 状态显示"仅支持预览"', () => {
    const wrapper = mountBar({ onlyofficeHealth: 'unavailable' })
    expect(wrapper.text()).toContain('仅支持预览')
  })

  it('readOnly 时显示只读标签', () => {
    const wrapper = mountBar({ readOnly: true })
    expect(wrapper.text()).toContain('只读')
  })

  it('点击预览按钮触发 preview 事件', async () => {
    const wrapper = mountBar()
    const previewBtn = wrapper.findAll('button').find((b) => b.text() === '预览')
    await previewBtn!.trigger('click')
    expect(wrapper.emitted('preview')).toBeTruthy()
  })

  it('点击引用按钮触发 cite 事件', async () => {
    const wrapper = mountBar()
    const citeBtn = wrapper.findAll('button').find((b) => b.text() === '引用')
    await citeBtn!.trigger('click')
    expect(wrapper.emitted('cite')).toBeTruthy()
  })
})
