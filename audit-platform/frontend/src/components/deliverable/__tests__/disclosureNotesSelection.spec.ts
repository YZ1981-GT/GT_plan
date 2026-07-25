import { describe, it, expect } from 'vitest'
import {
  buildGroupedTree,
  computePresetKeys,
  deriveSelectedSections,
  topLevelKey,
  GROUP_KEY_PREFIX,
  type NotesTreeNode,
} from '../disclosureNotesSelection'

const nodes: NotesTreeNode[] = [
  { id: '1', note_section: '一、1', section_title: '编制基础', has_data: true },
  { id: '2', note_section: '一、2', section_title: '会计政策', has_data: false },
  { id: '3', note_section: '五、1', section_title: '货币资金', has_data: true },
  { id: '4', note_section: '五、2', section_title: '应收账款', has_data: false },
  { id: '5', note_section: '五、22', section_title: '其他', has_data: true },
]

describe('topLevelKey', () => {
  it('取「、」前的中文序号；无「、」返回整串', () => {
    expect(topLevelKey('五、1')).toBe('五')
    expect(topLevelKey('三、7')).toBe('三')
    expect(topLevelKey('附注')).toBe('附注')
    expect(topLevelKey('')).toBe('')
  })
})

describe('buildGroupedTree', () => {
  it('按顶层中文序号分组，保持顺序，叶子带 label/has_data（Property 10 前缀原样）', () => {
    const groups = buildGroupedTree(nodes)
    expect(groups.map((g) => g.key)).toEqual([`${GROUP_KEY_PREFIX}一`, `${GROUP_KEY_PREFIX}五`])
    expect(groups[0].isGroup).toBe(true)
    expect(groups[0].children.map((c) => c.note_section)).toEqual(['一、1', '一、2'])
    expect(groups[1].children.map((c) => c.note_section)).toEqual(['五、1', '五、2', '五、22'])
    // 叶子 label = note_section + 标题；has_data 透传
    expect(groups[1].children[0].label).toBe('五、1 货币资金')
    expect(groups[1].children[0].has_data).toBe(true)
    expect(groups[1].children[1].has_data).toBe(false)
    // 前缀原样，不改写
    expect(groups[1].children[2].note_section).toBe('五、22')
  })

  it('section_title 为空时 label 仅 note_section', () => {
    const g = buildGroupedTree([{ id: 'x', note_section: '五、9', section_title: null }])
    expect(g[0].children[0].label).toBe('五、9')
  })
})

describe('computePresetKeys（Property 1：预设 = has_data=true 叶子集）', () => {
  it('只含 has_data=true 的 note_section，不含 has_data=false', () => {
    expect(computePresetKeys(nodes)).toEqual(['一、1', '五、1', '五、22'])
  })

  it('全无数据时预设为空', () => {
    const empty = nodes.map((n) => ({ ...n, has_data: false }))
    expect(computePresetKeys(empty)).toEqual([])
  })
})

describe('deriveSelectedSections（Property 3/7：叶子投影，剔除分组父节点）', () => {
  it('过滤 __group__ 前缀，仅保留叶子 note_section', () => {
    const checked = [`${GROUP_KEY_PREFIX}五`, '五、1', '五、2', '一、1']
    expect(deriveSelectedSections(checked)).toEqual(['五、1', '五、2', '一、1'])
  })

  it('纯投影：与勾选来源无关（预设后手动增删得到的当前集直接投影）', () => {
    // 模拟：预设 → 五、1/五、22/一、1；用户取消 五、22、补勾 五、2
    const afterEdit = [`${GROUP_KEY_PREFIX}五`, '五、1', '五、2', '一、1']
    // 最终 = 当前勾选叶子集（非预设原始集）
    expect(deriveSelectedSections(afterEdit)).toEqual(['五、1', '五、2', '一、1'])
  })

  it('空勾选 → 空集（Property 4 空选守卫的前置）', () => {
    expect(deriveSelectedSections([])).toEqual([])
    expect(deriveSelectedSections([`${GROUP_KEY_PREFIX}五`])).toEqual([])
  })
})
