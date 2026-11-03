/**
 * 合并附注「前 N 名」表说明（spec note-pull-followup-closure R10）：后端 `_topn` → 界面写明近似 / 集团内单位 / 分母。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ElementPlus from 'element-plus'
import ConsolNoteTopnNotice from '../ConsolNoteTopnNotice.vue'
import { consolNoteTopnNotice } from '../consolNoteTopn'

describe('consolNoteTopnNotice', () => {
  it('没有 _topn 不提示', () => {
    expect(consolNoteTopnNotice(null)).toBeNull()
    expect(consolNoteTopnNotice({ rows: [] })).toBeNull()
  })

  it('汇总节点写明近似；集团内单位、分母、分母取不到的原因逐条列出', () => {
    const n = consolNoteTopnNotice({
      _topn: {
        limit: 5, approximate: true, excluded_group_units: ['B子公司'], denominator: '5000.00',
        denominator_source: '「（1）按账龄披露应收账款」期末账面余额合计', reasons: [],
      },
    })!
    expect(n.type).toBe('warning')
    expect(n.title).toContain('前 5 名')
    expect(n.lines[0]).toContain('近似')
    expect(n.lines).toContain('集团内单位不进排名：B子公司')
    expect(n.lines).toContain('比例列分母：「（1）按账龄披露应收账款」期末账面余额合计（5000.00）')
    const leaf = consolNoteTopnNotice({ _topn: { limit: 5, approximate: false, reasons: ['本节点还没有数，比例留空'] } })!
    expect(leaf.lines).toEqual(['本节点还没有数，比例留空'])
    expect(leaf.type).toBe('warning')
    expect(consolNoteTopnNotice({ _topn: { limit: 5, approximate: false, reasons: [] } })!.type).toBe('info')
  })

  it('组件渲染标题与各行；ConsolNoteTab 两个工具栏都挂了', () => {
    const w = mount(ConsolNoteTopnNotice, {
      props: { data: { _topn: { limit: 5, approximate: true, reasons: ['分母没有数'] } } },
      global: { plugins: [ElementPlus] },
    })
    expect(w.text()).toContain('前 5 名')
    expect(w.text()).toContain('分母没有数')
    const tab = readFileSync(resolve(__dirname, '../ConsolNoteTab.vue'), 'utf-8')
    expect(tab.match(/<ConsolNoteTopnNotice :data="selectedNoteSection\.savedData" \/>/g)?.length).toBe(2)
  })
})
