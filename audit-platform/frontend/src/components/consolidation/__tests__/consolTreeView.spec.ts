/**
 * 合并企业树展示工具（spec consol-tree-three-code-autobuild 任务 10.7）
 *
 * 树来自后端三码推导，节点身份是 node_key：同一企业代码可以不同角色出现（合并户 G:consol 与母公司户 G:parent），
 * 按企业代码作键会撞；工作底稿企业列的回退只取子公司类成员（排除合并差额、母公司、分公司）。
 */
import { describe, it, expect } from 'vitest'
import type { ConsolTreeNode } from '@/services/consolidationApi'
import {
  canEnterProject,
  directSubsidiaryMembers,
  findConsolNodeByProject,
  findNodeByCompany,
  findNodeByKey,
  flagTags,
  buildNameIndex,
  maxDepth,
  countNodes,
  modeLabel,
  relationTagLabel,
  sortDiagnostics,
  viaLabel,
  walkTree,
} from '../composables/consolTreeView'

function n(key: string, name: string, extra: Partial<ConsolTreeNode> = {}, children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  const kind = extra.kind ?? (role === 'consol_elim' || role === 'branch_elim' ? 'elim' : children.length ? 'aggregate' : 'data')
  return {
    project_id: null, company_code: code, company_name: name, parent_company_code: null, ultimate_company_code: null,
    consol_level: 1, children, node_key: key, role, kind, display_name: name, relation: null,
    host_project_id: null, flags: [], via: [], mode: null, ...extra,
  }
}

/** G（合并）⊃ 合并差额、母公司（有分公司 GB ⇒ 汇总：母分差额 + 本部 + GB）、子公司 A（合并）、经 M 间接持有的 S */
function sampleTree(): ConsolTreeNode {
  return n('G:consol', '某集团（合并）', { project_id: 'p-g', kind: 'aggregate' }, [
    n('G:consol_elim', '某集团（合并差额）', { host_project_id: 'p-g' }),
    n('G:parent', '某集团（母公司）', { kind: 'aggregate' }, [
      n('G:branch_elim', '某集团（母分差额）', { host_project_id: 'p-g' }),
      n('G:hq', '某集团（本部）', { project_id: 'p-gs' }),
      n('GB:branch', '北京分公司', { project_id: 'p-gb', relation: 'branch' }),
    ]),
    n('A:consol', '甲公司（合并）', { project_id: 'p-a', kind: 'aggregate', relation: 'subsidiary' }, [
      n('A:consol_elim', '甲公司（合并差额）', { host_project_id: 'p-a' }),
      n('A:parent', '甲公司（母公司）', { project_id: 'p-as' }),
    ]),
    n('M:subsidiary', '中间控股', { project_id: 'p-m', relation: 'subsidiary' }),
    n('S:subsidiary', '乙公司', { project_id: 'p-s', relation: 'subsidiary', via: ['M'], flags: ['standalone_missing'] }),
  ])
}

describe('consolTreeView', () => {
  it('先序遍历与按 node_key 查找：同一企业代码的合并户与母公司户是两个节点', () => {
    const tree = sampleTree()
    const keys = [...walkTree(tree)].map((x) => x.node_key)
    expect(keys.slice(0, 7)).toEqual([
      'G:consol', 'G:consol_elim', 'G:parent', 'G:branch_elim', 'G:hq', 'GB:branch', 'A:consol',
    ])
    expect(new Set(keys).size).toBe(keys.length)
    expect(keys.filter((k) => k.startsWith('G:')).length).toBe(5)
    expect(findNodeByKey(tree, 'G:parent')?.display_name).toBe('某集团（母公司）')
    expect(findNodeByKey(tree, 'NOPE:consol')).toBeNull()
    expect(findNodeByCompany(tree, 'G')?.node_key).toBe('G:consol')
    expect(findConsolNodeByProject(tree, 'p-a')?.node_key).toBe('A:consol')
    expect(countNodes(tree)).toBe(keys.length)
    expect(maxDepth(tree)).toBe(3)
  })

  it('工作底稿企业列回退：只取子公司类成员（合并子公司 + 单户子公司），排除合并差额 / 母公司 / 分公司', () => {
    expect(directSubsidiaryMembers(sampleTree()).map((c) => c.code)).toEqual(['A', 'M', 'S'])
    expect(directSubsidiaryMembers(null)).toEqual([])
  })

  it('进入项目只对有项目的节点；标记与间接持有文案为中文', () => {
    const tree = sampleTree()
    expect(canEnterProject(findNodeByKey(tree, 'G:consol_elim'))).toBe(false)
    expect(canEnterProject(findNodeByKey(tree, 'G:parent'))).toBe(false)
    expect(canEnterProject(findNodeByKey(tree, 'G:hq'))).toBe(true)
    const s = findNodeByKey(tree, 'S:subsidiary')!
    expect(flagTags(s).map((t) => t.label)).toEqual(['未建单户项目'])
    expect(viaLabel(s, buildNameIndex(tree))).toBe('经 中间控股 间接持有')
    expect(flagTags(n('X:subsidiary', 'x', { flags: ['unknown_flag'] }))[0].label).toBe('unknown_flag')
  })

  it('组织图关系标签与角色同文案时不重复：子公司/分公司数据节点只显示角色，下级合并企业显示「子公司」', () => {
    const tree = sampleTree()
    expect(relationTagLabel(findNodeByKey(tree, 'S:subsidiary')!)).toBe('')
    expect(relationTagLabel(findNodeByKey(tree, 'GB:branch')!)).toBe('')
    expect(relationTagLabel(findNodeByKey(tree, 'A:consol')!)).toBe('子公司')
    expect(relationTagLabel(findNodeByKey(tree, 'G:hq')!)).toBe('')
    // 数据节点的关系与角色不一致（如分公司被按子公司挂接）时如实显示关系
    expect(relationTagLabel(n('B:subsidiary', 'b', { relation: 'branch' }))).toBe('分公司')
  })

  it('合并方式标签优先用接口文案，缺失时按 mode 取；诊断警告在前', () => {
    expect(modeLabel('mixed')).toBe('母子合并＋总分汇总')
    expect(modeLabel('branch', '总分汇总')).toBe('总分汇总')
    expect(modeLabel(null)).toBe('')
    const sorted = sortDiagnostics([
      { code: 'via', message: 'i1', company_code: null, node_key: null, level: 'info' },
      { code: 'detached', message: 'w1', company_code: null, node_key: null, level: 'warning' },
      { code: 'orphan_entries', message: 'w2', company_code: null, node_key: null, level: 'warning' },
    ])
    expect(sorted.map((d) => d.message)).toEqual(['w1', 'w2', 'i1'])
  })
})
