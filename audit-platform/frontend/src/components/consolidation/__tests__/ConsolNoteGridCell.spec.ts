/**
 * 合并附注单元格接入统一表格内核（spec excel-style-table-editing 5.6）。
 * 单向 model-value 保证 Esc 不写业务行，提交才由宿主接收。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ConsolNoteGridCell from '../ConsolNoteGridCell.vue'
import {
  activeInput, cell, click, key, mountGrid, settle, sink, typeInSink, unmountAll,
} from '../../grid/__tests__/gridHarness'

afterEach(() => unmountAll())

const TABLE = `
<el-table :data="rows">
  <el-table-column label="项目"><template #default="{ row }">{{ row[0] }}</template></el-table-column>
  <el-table-column label="期末数"><template #default="{ row }">
    <ConsolNoteGridCell :value="row[1]" label="期末数" :editable="true" :manual="row.manual"
      @commit="(value) => commit(row, value)" />
  </template></el-table-column>
</el-table>`

async function grid() {
  const onCommit = vi.fn()
  const w = await mountGrid(TABLE, () => ({
    rows: [{ 0: '货币资金', 1: '100', manual: false }],
  }), {
    commit(row: any, value: string) {
      row[1] = value
      row.manual = true
      onCommit(value)
    },
  } as never, { ConsolNoteGridCell })
  return {
    w,
    onCommit,
    row: (w.vm as any).rows[0] as any,
  }
}

describe('ConsolNoteGridCell', () => {
  it('平时只显示文字；编辑后按 Esc 不发 commit、业务值保持原样', async () => {
    const { w, row, onCommit } = await grid()
    expect(cell(w, 0, 1).textContent).toContain('100')
    expect(cell(w, 0, 1).querySelector('input')).toBeNull()

    click(cell(w, 0, 1))
    key(sink(w), 'F2')
    await settle()
    const input = activeInput(w)
    input.value = '999'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    key(input, 'Escape')
    await settle()

    expect(onCommit).not.toHaveBeenCalled()
    expect(row[1]).toBe('100')
    expect(cell(w, 0, 1).textContent).toContain('100')
  })

  it('Enter 提交一次，宿主才更新业务值并标为手工', async () => {
    const { w, row, onCommit } = await grid()
    click(cell(w, 0, 1))
    typeInSink(sink(w), '250')
    await settle()
    key(activeInput(w), 'Enter')
    await settle()

    expect(onCommit).toHaveBeenCalledOnce()
    expect(onCommit).toHaveBeenCalledWith('250')
    expect(row[1]).toBe('250')
    expect(row.manual).toBe(true)
  })
})

describe('ConsolNoteTab 编辑器接线', () => {
  it('普通与全屏的 8 种叶子格全部走 ConsolNoteGridCell，旧 useLazyEdit 已下线', () => {
    const source = readFileSync(resolve(__dirname, '../ConsolNoteTab.vue'), 'utf-8')
    expect(source.match(/<ConsolNoteGridCell\b/g)).toHaveLength(8)
    expect(source).not.toContain("from '@/composables/useLazyEdit'")
    expect(source).not.toContain('lazyEdit.')
    expect(source).toContain('@commit="onNoteCellCommit(row, col.colIndex, $event)"')
    expect(source).toContain('@commit="onNoteCellCommit(row, hi, $event)"')
  })
})
