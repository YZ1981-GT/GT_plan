/**
 * spec excel-style-table-editing R8（5.3 触类旁通）：
 * - 整张只读的表（列表、报表）把 Enter / Backspace / Delete 交还页面 —— 页面常拿它们做「返回上级 / 返回上一页」
 *   （试算表溯源返回、查账穿透、全局返回栈），选中单元格（焦点在承接框）后照常可用；
 * - 有可编辑格的表照 Excel：Enter 下移、Backspace 清空开始输入，按键不冒泡到页面；
 * - 页面「在输入框里不拦截」的判定（isTextEntryTarget）不把表格承接框当输入框。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { Router } from 'vue-router'
import { isTextEntryTarget } from '@/utils/shortcuts'
import { initGlobalBackspace, useNavigationStack } from '@/composables/useNavigationStack'
import { activeInput, cell, click, key, mountGrid, settle, unmountAll } from './gridHarness'

afterEach(() => unmountAll())

const READONLY = `
<el-table :data="rows">
  <el-table-column label="科目" prop="name" />
  <el-table-column label="金额" prop="amt" />
</el-table>`

const DISABLED_ONLY = `
<el-table :data="rows">
  <el-table-column label="科目" prop="name" />
  <el-table-column label="金额"><template #default="{ row }"><el-input v-model="row.amt" disabled /></template></el-table-column>
</el-table>`

const EDITABLE = `
<el-table :data="rows">
  <el-table-column label="科目" prop="name" />
  <el-table-column label="金额"><template #default="{ row }"><el-input v-model="row.amt" /></template></el-table-column>
</el-table>`

/** 只读外表的格里嵌一张可编辑的子表：子表的编辑器不算外表的可编辑格 */
const NESTED = `
<el-table :data="rows">
  <el-table-column label="科目" prop="name" />
  <el-table-column label="明细"><template #default="{ row }">
    <gt-grid-table><tbody><tr><td><el-input v-model="row.amt" /></td></tr></tbody></gt-grid-table>
  </template></el-table-column>
</el-table>`

const rows = () => [{ name: '甲', amt: '1' }, { name: '乙', amt: '2' }, { name: '丙', amt: '3' }]

/** 外表自己的承接框（嵌套子表也有一个，按所属表格根节点区分） */
function outerSink(w: VueWrapper): HTMLTextAreaElement {
  const root = w.element as HTMLElement
  const s = Array.from(root.querySelectorAll<HTMLTextAreaElement>('.gt-grid-sink')).find((x) => x.closest('[data-gt-grid-root]') === root)
  if (!s) throw new Error('没有外表的承接框')
  return s
}

/** 页面在 document 上的按键监听（与试算表 / 查账穿透的写法一致） */
function pageListener() {
  const seen: string[] = []
  const fn = (e: KeyboardEvent) => { seen.push(e.key) }
  document.addEventListener('keydown', fn)
  return { seen, off: () => document.removeEventListener('keydown', fn) }
}

describe('只读表：Enter / Backspace / Delete 交还页面', () => {
  it.each([
    ['纯文字列', READONLY],
    ['编辑器全禁用', DISABLED_ONLY],
    ['子表里的编辑器不算', NESTED],
  ])('%s：三个键冒泡到页面、不阻止默认、选区不动、不提示', async (_name, tpl) => {
    const w = await mountGrid(tpl, () => ({ rows: rows() }))
    click(cell(w, 0, 0))
    await settle()
    expect(document.activeElement).toBe(outerSink(w))
    const page = pageListener()
    try {
      for (const k of ['Enter', 'Backspace', 'Delete']) {
        const ev = key(outerSink(w), k)
        expect(ev.defaultPrevented, k).toBe(false)
      }
      await settle()
      expect(page.seen).toEqual(['Enter', 'Backspace', 'Delete'])
      expect(cell(w, 0, 0).hasAttribute('data-gt-active')).toBe(true)
      expect(document.querySelector('.el-message')).toBeNull()
    } finally {
      page.off()
    }
  })

  it('方向键仍由表格处理（不冒泡）', async () => {
    const w = await mountGrid(READONLY, () => ({ rows: rows() }))
    click(cell(w, 0, 0))
    const page = pageListener()
    try {
      const ev = key(outerSink(w), 'ArrowDown')
      expect(ev.defaultPrevented).toBe(true)
      expect(page.seen).toEqual([])
      expect(cell(w, 1, 0).hasAttribute('data-gt-active')).toBe(true)
    } finally {
      page.off()
    }
  })
})

describe('有可编辑格的表照 Excel', () => {
  it('Enter 在只读格上同样下移，不冒泡', async () => {
    const w = await mountGrid(EDITABLE, () => ({ rows: rows() }))
    click(cell(w, 0, 0))
    const page = pageListener()
    try {
      const ev = key(outerSink(w), 'Enter')
      expect(ev.defaultPrevented).toBe(true)
      expect(page.seen).toEqual([])
      expect(cell(w, 1, 0).hasAttribute('data-gt-active')).toBe(true)
    } finally {
      page.off()
    }
  })

  it('Backspace 在可编辑格清空开始输入，不冒泡', async () => {
    const w = await mountGrid(EDITABLE, () => ({ rows: rows() }))
    click(cell(w, 0, 1))
    const page = pageListener()
    try {
      key(outerSink(w), 'Backspace')
      await settle()
      expect(activeInput(w).value).toBe('')
      expect(page.seen).toEqual([])
    } finally {
      page.off()
    }
  })

  it('Backspace 在只读格上给轻提示，不冒泡（不会误触页面「返回」）', async () => {
    const w = await mountGrid(EDITABLE, () => ({ rows: rows() }))
    click(cell(w, 0, 0))
    const page = pageListener()
    try {
      const ev = key(outerSink(w), 'Backspace')
      await settle()
      expect(ev.defaultPrevented).toBe(true)
      expect(page.seen).toEqual([])
      expect(document.querySelector('.el-message')?.textContent).toContain('该单元格不可编辑')
    } finally {
      page.off()
    }
  })
})

describe('isTextEntryTarget：承接框不算输入框', () => {
  it('承接框 false；输入框 / 文本域 / 可编辑区 true；普通元素与空 false', async () => {
    const w = await mountGrid(READONLY, () => ({ rows: rows() }))
    expect(isTextEntryTarget(outerSink(w))).toBe(false)
    expect(isTextEntryTarget(document.createElement('input'))).toBe(true)
    expect(isTextEntryTarget(document.createElement('textarea'))).toBe(true)
    const editable = document.createElement('div')
    editable.contentEditable = 'true'
    expect(isTextEntryTarget(editable)).toBe(true)
    expect(isTextEntryTarget(document.createElement('div'))).toBe(false)
    expect(isTextEntryTarget(null)).toBe(false)
  })
})

describe('全局返回栈（useNavigationStack）', () => {
  it('选中只读表格的单元格后按 Backspace 照常返回上一跳', async () => {
    const push = vi.fn()
    initGlobalBackspace({ push } as unknown as Router)
    const Pusher = defineComponent({
      setup() {
        useNavigationStack().push({ source_view: '/projects/p1/trial-balance', query: { tab: 'detail' } })
        return () => h('div')
      },
    })
    const p = mount(Pusher)
    try {
      const w = await mountGrid(READONLY, () => ({ rows: rows() }))
      click(cell(w, 1, 1))
      key(outerSink(w), 'Backspace')
      expect(push).toHaveBeenCalledWith({ path: '/projects/p1/trial-balance', query: { tab: 'detail' } })
    } finally {
      p.unmount()
    }
  })
})
