/**
 * 附注编辑器加载正文不得被隐藏的 TipTap 编辑器改写（spec disclosure-note-doc-upload-and-batch-fill 第 22 组）。
 *
 * DisclosureEditor 里还留着一个不渲染的 TipTap 编辑器（StarterKit，无表格扩展），只给 AI 续写 / 改写用；
 * 它的 onUpdate 会把 getHTML() 写回 textContent（富文本框 v-model）。TipTap 3 的 setContent 默认 emitUpdate=true
 * ⇒ 每次切章加载都触发 onUpdate，正文被 StarterKit 规范化后写回：markdown 表格渲染出的 <table> 被拍成一段文字
 * （真库安徽「四、投资性房地产」实测），编辑后保存即永久丢表格；Word 导出却按表格输出。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { renderNoteTextToHtml } from '@/utils/noteTextMarkdown'

const TABLE_TEXT = '变动如下：\n\n| 项目 | 金额 |\n| --- | --- |\n| 1. 期初余额 | 0.00 |'

describe('TipTap setContent 的更新事件（根因特征）', () => {
  let editor: Editor | null = null
  afterEach(() => { editor?.destroy(); editor = null })

  it('默认 setContent 触发 onUpdate，写回的是拍平表格后的 HTML', () => {
    const onUpdate = vi.fn()
    editor = new Editor({ extensions: [StarterKit], content: '', onUpdate: ({ editor: e }) => onUpdate(e.getHTML()) })
    const html = renderNoteTextToHtml(TABLE_TEXT)
    expect(html).toContain('<table>')
    editor.commands.setContent(html)
    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate.mock.calls[0][0]).not.toContain('<table')
  })

  it('emitUpdate: false 不触发 onUpdate', () => {
    const onUpdate = vi.fn()
    editor = new Editor({ extensions: [StarterKit], content: '', onUpdate })
    editor.commands.setContent(renderNoteTextToHtml(TABLE_TEXT), { emitUpdate: false })
    expect(onUpdate).not.toHaveBeenCalled()
  })
})

describe('DisclosureEditor 加载 / 恢复草稿不经隐藏编辑器改写正文', () => {
  const src = readFileSync(resolve(__dirname, '../DisclosureEditor.vue'), 'utf-8')

  it('全部 setContent 调用都带 emitUpdate: false', () => {
    const calls = src.match(/commands\.setContent\([^\n]*\)/g) ?? []
    expect(calls.length).toBeGreaterThanOrEqual(2)
    for (const call of calls) expect(call).toContain('{ emitUpdate: false }')
  })

  it('恢复草稿也走同一加载口径', () => {
    expect(src).toMatch(/textContent\.value = renderNoteTextToHtml\(data\.text_content\)/)
  })
})
