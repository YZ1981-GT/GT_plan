/**
 * NoteSourceBadge（Task 50 / AC-11.3）：编辑器章节标题旁的来源标记。
 *
 * - 按项目年度一次取回各章来源（静默请求），当前章有来源才显示；切章不重复请求；
 * - 批量写入成功（同项目同年度）后自动刷新，别的项目 / 年度的广播不触发；
 * - 取数失败不显示、不弹错（标记只是辅助信息）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

const get = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => get(...a), post: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))

import { eventBus } from '@/utils/eventBus'
import NoteSourceBadge from '@/components/disclosure/NoteSourceBadge.vue'
import type { NoteTextSource } from '@/composables/useNoteTextBatch'

const TEMPLATE: NoteTextSource = {
  application_id: 'a1', source_kind: 'content_template', mode: 'replace', source_title: '公司基本情况',
  applied_at: '2026-10-01T09:00:00', applied_by_name: '审计助理甲', modified_after: false,
  template_name: '集团通用模板', version_no: 2,
}

function mountBadge(noteId: string | null = 'n1', projectId = 'p1') {
  return mount(NoteSourceBadge, { props: { projectId, year: 2025, noteId } })
}

beforeEach(() => get.mockReset())
// 每例结束卸载：卸载时必须注销事件监听，否则上一例的实例也会响应广播（下面「卸载后不再响应」一例专门钉住）
enableAutoUnmount(afterEach)

describe('NoteSourceBadge', () => {
  it('当前章有来源 ⇒ 显示来源与写入人 / 时间；请求静默且带年度', async () => {
    get.mockResolvedValueOnce({ items: { n1: TEMPLATE } })
    const w = mountBadge()
    await flushPromises()
    expect(w.find('.gt-nsb').text()).toBe('📋 来自内容模板「集团通用模板」v2')
    expect(w.find('.gt-nsb').attributes('title')).toBe('2026/10/01 审计助理甲 批量写入（替换）')
    expect(get).toHaveBeenCalledWith('/api/projects/p1/disclosure-note-text-batch/sources',
      expect.objectContaining({ params: { year: 2025 }, _silent: true }))
  })

  it('切到没被批量写入过的章 ⇒ 不显示，也不重新请求', async () => {
    get.mockResolvedValueOnce({ items: { n1: TEMPLATE } })
    const w = mountBadge()
    await flushPromises()
    await w.setProps({ noteId: 'n2' })
    expect(w.find('.gt-nsb').exists()).toBe(false)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('同项目同年度批量写入成功 ⇒ 刷新；别的项目的广播不触发', async () => {
    get.mockResolvedValueOnce({ items: {} })
    const w = mountBadge()
    await flushPromises()
    expect(w.find('.gt-nsb').exists()).toBe(false)
    eventBus.emit('note-text-batch:applied', { projectId: 'other', year: 2025 })
    eventBus.emit('note-text-batch:applied', { projectId: 'p1', year: 2024 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    get.mockResolvedValueOnce({ items: { n1: { ...TEMPLATE, modified_after: true } } })
    eventBus.emit('note-text-batch:applied', { projectId: 'p1', year: 2025 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(w.find('.gt-nsb').text()).toBe('📋 来自内容模板「集团通用模板」v2（之后有修改）')
    expect(w.find('.gt-nsb').classes()).toContain('is-modified')
  })

  it('卸载后不再响应写入广播（监听已注销，不泄漏）', async () => {
    get.mockResolvedValueOnce({ items: {} })
    const w = mountBadge()
    await flushPromises()
    w.unmount()
    eventBus.emit('note-text-batch:applied', { projectId: 'p1', year: 2025 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('取数失败 ⇒ 不显示', async () => {
    get.mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 500'), { response: { status: 500 } }))
    const w = mountBadge()
    await flushPromises()
    expect(w.find('.gt-nsb').exists()).toBe(false)
  })

  it('切项目时上一个项目迟到的结果不覆盖（只认最后一发请求）', async () => {
    let resolveOld: (v: unknown) => void = () => {}
    get.mockImplementationOnce(() => new Promise((r) => { resolveOld = r }))
    get.mockResolvedValueOnce({ items: {} })
    const w = mountBadge('n1', 'p1')
    await w.setProps({ projectId: 'p2' })
    await flushPromises()
    resolveOld({ items: { n1: TEMPLATE } })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(w.find('.gt-nsb').exists()).toBe(false)
  })
})

describe('编辑器挂载（源码级，界面效果另经浏览器实测）', () => {
  const read = (p: string) => fs.readFileSync(path.resolve(__dirname, p), 'utf-8').replace(/\r\n/g, '\n')

  it('章节标题区按当前章挂来源标记，经 noteContentTools 一个 import 引入', () => {
    const editor = read('../../../views/DisclosureEditor.vue')
    // 剥注释：注释掉的标签 / import 不算挂载
    const template = editor.replace(/<!--[\s\S]*?-->/g, '')
    const script = editor.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    expect(template).toContain('<NoteSourceBadge :project-id="projectId" :year="year" :note-id="currentNote.id" />')
    expect(script).toContain("import { DisclosureNoteContentTools, NoteSourceBadge } from '@/components/disclosure/noteContentTools'")
    expect(read('../noteContentTools.ts')).toContain("export { default as NoteSourceBadge } from './NoteSourceBadge.vue'")
  })
})
