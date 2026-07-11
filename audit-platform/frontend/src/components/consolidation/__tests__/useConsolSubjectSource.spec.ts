/**
 * useConsolSubjectSource 单测 — 合并模块科目名称真源 (Req 19.1 / 19.5 / 19.7)
 *
 * 证明：
 *  - TB 注册表为空 → 回退硬编码树（identity，无空白 picker）(Req 19.5)
 *  - TB 注册表可用 → 产出与硬编码 **同构** 的树（相同分组骨架 + 相同叶子科目名集合）(Req 19.1)
 *  - 叶子 value === label === 科目名字符串（subject 值契约不变，buildAutoEntries/Excel 不受影响）(Req 19.7)
 *  - 注册表未覆盖的叶子逐个降级保留硬编码字面量（绝不丢叶子）
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAddressRegistry } from '@/stores/addressRegistry'
import {
  useConsolSubjectSource,
  HARDCODED_SUBJECT_TREE,
  type SubjectTreeNode,
} from '../composables/useConsolSubjectSource'

// ─── helpers ────────────────────────────────────────────────────────────────
function collectLeafValues(nodes: SubjectTreeNode[]): string[] {
  const out: string[] = []
  for (const n of nodes) {
    if (n.children && n.children.length > 0) out.push(...collectLeafValues(n.children))
    else if (!n.disabled) out.push(n.value)
  }
  return out.sort()
}

function collectDisabledLabels(nodes: SubjectTreeNode[]): string[] {
  const out: string[] = []
  for (const n of nodes) {
    if (n.disabled) out.push(n.label)
    if (n.children) out.push(...collectDisabledLabels(n.children))
  }
  return out.sort()
}

function collectLeaves(nodes: SubjectTreeNode[]): SubjectTreeNode[] {
  const out: SubjectTreeNode[] = []
  for (const n of nodes) {
    if (n.children && n.children.length > 0) out.push(...collectLeaves(n.children))
    else if (!n.disabled) out.push(n)
  }
  return out
}

function makeTbEntry(label: string) {
  return {
    uri: `tb://${label}`,
    domain: 'tb',
    source: 'tb',
    path: '',
    cell: '',
    label,
    formula_ref: '',
    jump_route: '',
  }
}

describe('useConsolSubjectSource', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('回退硬编码树 when TB 注册表为空 (Req 19.5)', () => {
    const { subjectTree, isRegistryBacked, registrySubjectNames } = useConsolSubjectSource()
    expect(isRegistryBacked.value).toBe(false)
    expect(registrySubjectNames.value.size).toBe(0)
    // 空注册表时直接返回硬编码骨架（identity）
    expect(subjectTree.value).toBe(HARDCODED_SUBJECT_TREE)
  })

  it('注册表可用时产出与硬编码同构的树 (Req 19.1)', () => {
    const store = useAddressRegistry()
    // 注入部分 TB 域标准科目名（覆盖部分叶子）
    store.addresses = [
      makeTbEntry('货币资金'),
      makeTbEntry('应收账款'),
      makeTbEntry('营业收入'),
      makeTbEntry('资本公积'),
      // 非 TB 域应被忽略
      { ...makeTbEntry('报表行'), domain: 'report' },
    ] as any

    const { subjectTree, isRegistryBacked } = useConsolSubjectSource()
    expect(isRegistryBacked.value).toBe(true)

    // 分组骨架（disabled 父节点）与叶子科目名集合与硬编码完全一致 → 同构
    expect(collectDisabledLabels(subjectTree.value)).toEqual(
      collectDisabledLabels(HARDCODED_SUBJECT_TREE),
    )
    expect(collectLeafValues(subjectTree.value)).toEqual(
      collectLeafValues(HARDCODED_SUBJECT_TREE),
    )
  })

  it('叶子 value === label 且 subject 值契约不变 (Req 19.7)', () => {
    const store = useAddressRegistry()
    store.addresses = [makeTbEntry('货币资金'), makeTbEntry('存货')] as any

    const { subjectTree } = useConsolSubjectSource()
    for (const leaf of collectLeaves(subjectTree.value)) {
      expect(leaf.value).toBe(leaf.label)
      expect(leaf.value.startsWith('_')).toBe(false) // 叶子非内部占位码
    }
  })

  it('未覆盖叶子逐个降级保留硬编码字面量（绝不丢叶子）', () => {
    const store = useAddressRegistry()
    // 仅注册一个科目名，其余叶子应保留硬编码
    store.addresses = [makeTbEntry('货币资金')] as any

    const { subjectTree } = useConsolSubjectSource()
    const leaves = collectLeafValues(subjectTree.value)
    expect(leaves).toContain('货币资金')
    expect(leaves).toContain('存货') // 未在注册表 → 硬编码兜底仍在
    expect(leaves.length).toBe(collectLeafValues(HARDCODED_SUBJECT_TREE).length)
  })

  it('registrySubjectNames 仅收集 TB 域名称', () => {
    const store = useAddressRegistry()
    store.addresses = [
      makeTbEntry('货币资金'),
      { ...makeTbEntry('资产总计'), domain: 'report' },
      { ...makeTbEntry('附注1'), domain: 'note' },
    ] as any

    const { registrySubjectNames } = useConsolSubjectSource()
    expect(registrySubjectNames.value.has('货币资金')).toBe(true)
    expect(registrySubjectNames.value.has('资产总计')).toBe(false)
    expect(registrySubjectNames.value.has('附注1')).toBe(false)
  })
})
