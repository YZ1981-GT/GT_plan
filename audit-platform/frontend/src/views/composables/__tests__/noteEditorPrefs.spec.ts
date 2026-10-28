/**
 * 附注编辑器两处体验修正（spec note-pull-followup-closure R18 / R19）。
 *
 * - R19「保存后跳下一章」默认关闭：没设置过 / 设成 false ⇒ 不跳；只有显式打开（'true'）才跳；读写失败不抛。
 * - R18 编辑态行名格靠左：行名格与金额格共用 `gt-cell-editable`（justify-content: flex-end），行名格另加修饰类。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { AUTO_ADVANCE_KEY, readAutoAdvance, writeAutoAdvance } from '../noteEditorPrefs'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => { data.set(k, v) },
    data,
  }
}

describe('保存后跳下一章：默认关闭', () => {
  it('没设置过 ⇒ 关；false ⇒ 关；true ⇒ 开', () => {
    expect(readAutoAdvance(memoryStorage())).toBe(false)
    expect(readAutoAdvance(memoryStorage({ [AUTO_ADVANCE_KEY]: 'false' }))).toBe(false)
    expect(readAutoAdvance(memoryStorage({ [AUTO_ADVANCE_KEY]: 'true' }))).toBe(true)
    expect(readAutoAdvance(null)).toBe(false)
  })

  it('开关写回本地偏好；读写抛错不影响编辑器', () => {
    const s = memoryStorage()
    writeAutoAdvance(s, true)
    expect(s.data.get(AUTO_ADVANCE_KEY)).toBe('true')
    writeAutoAdvance(s, false)
    expect(readAutoAdvance(s)).toBe(false)
    const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') } }
    expect(readAutoAdvance(broken)).toBe(false)
    expect(() => writeAutoAdvance(broken, true)).not.toThrow()
  })

  it('编辑器用的是这里的读写（不再在组件里写死「未设置即开启」）', () => {
    const editor = readFileSync(resolve(__dirname, '../../DisclosureEditor.vue'), 'utf-8')
    expect(editor).toContain('const autoAdvance = ref(readAutoAdvance(localStorage))')
    expect(editor).toContain('writeAutoAdvance(localStorage, val)')
    expect(editor).not.toContain("getItem('gt_note_auto_advance') !== 'false'")
  })
})

describe('编辑态行名格靠左', () => {
  it('行名格带修饰类，样式把它改回靠左', () => {
    const editor = readFileSync(resolve(__dirname, '../../DisclosureEditor.vue'), 'utf-8')
    const css = readFileSync(resolve(__dirname, '../../DisclosureEditor.css'), 'utf-8')
    const labelCell = editor.slice(editor.indexOf('<template v-if="headerIdx === 0">'), editor.indexOf('<template v-else>', editor.indexOf('<template v-if="headerIdx === 0">')))
    expect(labelCell).toContain('class="gt-cell-editable gt-cell-editable--label"')
    expect(css).toMatch(/\.gt-cell-editable\.gt-cell-editable--label\s*\{\s*justify-content:\s*flex-start;\s*\}/)
    // 金额格不受影响：仍是共用类、靠右
    expect(css).toMatch(/\.gt-cell-editable \{[^}]*justify-content: flex-end;/)
  })
})
