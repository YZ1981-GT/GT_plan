/**
 * 合并附注空表头不显示「列N」（spec note-pull-followup-closure R6.2）。
 *
 * 标签列表头 Word 本就留白：种子取单体同名表的首列表头，取不到留空（后端 `seed_consol_note_sections.fill_label_header`）。
 * 前端各列树 / 表头渲染照原样显示空，不兜底成「列N」—— 旧版就是兜底名被当成真表头写进了数据。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { buildColumnTree, columnLeaves } from '../composables/consolNoteColumns'
import { buildNoteColumnTree, noteColumnLeaves } from '@/views/composables/noteColumnTree'

const GROUPED = {
  headers: ['', '期末余额/账面余额', '期末余额/坏账准备'],
  multi_header: [['', '期末余额', ''], ['', '账面余额', '坏账准备']],
}

describe('空标签列表头照原样留空', () => {
  it('合并附注列树与编辑器列树：标签列叶子名为空', () => {
    expect(columnLeaves(buildColumnTree(GROUPED))[0]).toMatchObject({ label: '', headerIdx: 0 })
    expect(noteColumnLeaves(buildNoteColumnTree(GROUPED))[0]).toMatchObject({ label: '', headerIdx: 0 })
    expect(columnLeaves(buildColumnTree({ headers: ['', '期末'] })).map(n => n.label)).toEqual(['', '期末'])
    expect(noteColumnLeaves(buildNoteColumnTree({ headers: ['', '期末'] })).map(n => n.label)).toEqual(['', '期末'])
  })

  it('合并附注页、只读表格与两份列树不写「列N」兜底', () => {
    for (const rel of ['../ConsolNoteTab.vue', '../NoteTablesReadonly.vue', '../composables/consolNoteColumns.ts',
      '../../../views/composables/noteColumnTree.ts']) {
      const src = readFileSync(resolve(__dirname, rel), 'utf-8')
      expect(src, rel).not.toMatch(/`列\$\{/)
      expect(src, rel).not.toMatch(/['"]列['"]\s*\+/)
    }
  })
})
