/**
 * useNoteTree — 主表注释章（上市 五、N / 国企 八、N）父节点分组归属测试
 *
 * 回归背景：分组区间原为「两变体共用一套硬编码」（asset 1-15 / liability 16-23 /
 * equity 24-28 / income 29-35），与两个模板的真实章节顺序完全错位，导致例如
 * 「五、29 长期待摊费用 / 五、30 递延所得税资产 / 五、31 其他非流动资产」被挂到
 * 「损益类」父节点下；且未命中任何区间的章节会在分组时静默消失。
 *
 * 断言依据：`backend/data/note_template_{listed,soe}.json` 的 section_number/section_title
 * 实证（非臆造）。
 */
import { describe, it, expect, vi } from 'vitest'
import { computed, ref } from 'vue'

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveIndex: vi.fn() }),
}))
vi.mock('@/services/auditPlatformApi', () => ({
  getDisclosureNoteTree: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn().mockResolvedValue({}) },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import { useNoteTree, type TreeNode } from '../useNoteTree'
import type { DisclosureNoteTreeItem } from '@/services/auditPlatformApi'

function makeTree(templateType: 'soe' | 'listed') {
  return useNoteTree({
    projectId: computed(() => 'p1'),
    year: computed(() => 2025),
    templateType: ref(templateType),
    isEqcrRole: computed(() => false),
  })
}

function item(section: string, title: string): DisclosureNoteTreeItem {
  return { id: section, note_section: section, section_title: title } as DisclosureNoteTreeItem
}

/** 造出 prefix + 1..count 的章节列表（>10 才触发分组分支） */
function seq(prefix: string, count: number): DisclosureNoteTreeItem[] {
  return Array.from({ length: count }, (_, i) => item(`${prefix}${i + 1}`, `节${i + 1}`))
}

/** 返回 section → 所属分组 label 的映射 */
function groupOf(nodes: TreeNode[], chapterId: string): Record<string, string> {
  const chapter = nodes.find((n) => n.id === chapterId)
  const out: Record<string, string> = {}
  for (const g of chapter?.children ?? []) {
    for (const leaf of g.children ?? []) {
      out[leaf.data?.note_section] = g.label
    }
  }
  return out
}

describe('主表注释章分组：上市版（五、N）', () => {
  const tree = makeTree('listed')
  tree.noteList.value = seq('五、', 74)
  const map = groupOf(tree.treeData.value, 'chapter_五')

  it.each([
    ['五、1', '流动资产 + 非流动资产'],   // 货币资金
    ['五、22', '流动资产 + 非流动资产'],  // 固定资产
    ['五、29', '流动资产 + 非流动资产'],  // 长期待摊费用（原误归损益类）
    ['五、30', '流动资产 + 非流动资产'],  // 递延所得税资产与递延所得税负债
    ['五、31', '流动资产 + 非流动资产'],  // 其他非流动资产
    ['五、32', '流动资产 + 非流动资产'],  // 所有权或使用权受到限制的资产
    ['五、33', '流动负债 + 非流动负债'],  // 短期借款
    ['五、47', '流动负债 + 非流动负债'],  // 租赁负债
    ['五、52', '流动负债 + 非流动负债'],  // 其他非流动负债
    ['五、53', '所有者权益'],             // 股本
    ['五、61', '所有者权益'],             // 未分配利润
    ['五、62', '损益类'],                 // 营业收入和营业成本
    ['五、70', '损益类'],                 // 净敞口套期收益
    ['五、71', '其他项目注释'],           // 现金流量表补充资料
    ['五、74', '其他项目注释'],           // 租赁
  ])('%s → %s', (section, label) => {
    expect(map[section]).toBe(label)
  })
})

describe('主表注释章分组：国企版（八、N）', () => {
  const tree = makeTree('soe')
  tree.noteList.value = seq('八、', 93)
  const map = groupOf(tree.treeData.value, 'chapter_八')

  it.each([
    ['八、1', '流动资产 + 非流动资产'],   // 货币资金
    ['八、30', '流动资产 + 非流动资产'],  // 长期待摊费用
    ['八、32', '流动资产 + 非流动资产'],  // 其他非流动资产
    ['八、33', '流动负债 + 非流动负债'],  // 短期借款
    ['八、52', '流动负债 + 非流动负债'],  // 租赁负债
    ['八、57', '流动负债 + 非流动负债'],  // 其他非流动负债
    ['八、58', '所有者权益'],             // 实收资本
    ['八、63', '所有者权益'],             // 未分配利润
    ['八、64', '损益类'],                 // 营业收入、营业成本
    ['八、74', '损益类'],                 // 资产减值损失
    ['八、78', '损益类'],                 // 所得税费用
    ['八、79', '其他项目注释'],           // 归属于母公司所有者的其他综合收益
    ['八、93', '其他项目注释'],           // 所有权和使用权受到限制的资产
  ])('%s → %s', (section, label) => {
    expect(map[section]).toBe(label)
  })
})

describe('分组不丢节点', () => {
  it('全部章节都归入某个父节点（含超模板编号与不可解析编号）', () => {
    const tree = makeTree('listed')
    const notes = [
      ...seq('五、', 74),
      item('五、120', '项目自建章节'),
      item('五、附加', '编号不可解析'),
    ]
    tree.noteList.value = notes
    const map = groupOf(tree.treeData.value, 'chapter_五')
    expect(Object.keys(map).length).toBe(notes.length)
    expect(map['五、120']).toBe('补充披露事项')
    expect(map['五、附加']).toBe('补充披露事项')
  })

  it('变体切换后归属随之变化（同一编号 33 在两版都属负债，58 在国企属权益/上市属负债后段）', () => {
    const listed = makeTree('listed')
    listed.noteList.value = seq('五、', 74)
    expect(groupOf(listed.treeData.value, 'chapter_五')['五、58']).toBe('所有者权益')

    const soe = makeTree('soe')
    soe.noteList.value = seq('八、', 93)
    expect(groupOf(soe.treeData.value, 'chapter_八')['八、58']).toBe('所有者权益')
    expect(groupOf(soe.treeData.value, 'chapter_八')['八、53']).toBe('流动负债 + 非流动负债')
  })
})
