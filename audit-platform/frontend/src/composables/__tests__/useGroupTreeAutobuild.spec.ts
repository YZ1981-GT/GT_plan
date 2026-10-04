import { describe, expect, it } from 'vitest'
import { formatShareholding, nodeMatchesQuery } from '../useGroupTree'
import type { GroupTree, TreeNode } from '../useGroupTree'

function node(overrides: Partial<TreeNode> = {}): TreeNode {
  return {
    id: 'p-g', label: '集团', companyCode: 'G', companyName: '集团', parentCompanyCode: null,
    ultimateCompanyCode: 'G', consolLevel: 1, status: 'execution', reportScope: 'consolidated',
    children: [], isDetached: false, isIndependent: false, isCycleBreak: false, hasNoCompanyCode: false,
    nodeKey: 'G@2025', relation: null, year: 2025,
    projects: [{ id: 'p-g', reportScope: 'consolidated' }, { id: 'p-gs', reportScope: 'standalone' }],
    consolidatedProjectId: 'p-g', standaloneProjectId: 'p-gs', ...overrides,
  }
}

describe('集团架构森林前端契约', () => {
  it('消费 tree.key/year 与企业实体 nodeKey，保留合并/单户双口径', () => {
    const tree: GroupTree = {
      key: 'G@2025', year: 2025, ultimateCode: 'G', ultimateName: '集团', rootProjectId: 'p-g', children: [node()],
    }
    expect(tree.key).toBe('G@2025')
    expect(tree.year).toBe(2025)
    expect(tree.children[0].nodeKey).toBe('G@2025')
    expect(tree.children[0].projects?.map((p) => p.reportScope)).toEqual(['consolidated', 'standalone'])
  })

  it('关系、间接持有和年度都属于节点可渲染契约', () => {
    const child = node({ id: 'p-b', nodeKey: 'B@2025', companyCode: 'B', companyName: '分公司B', relation: 'branch', year: 2025, via: [{ companyCode: 'A', companyName: '中间企业A' }] })
    expect(child.relation).toBe('branch')
    expect(child.via?.[0].companyName).toBe('中间企业A')
    expect(child.year).toBe(2025)
  })

  it('搜索继续递归匹配新节点字段的企业名称/代码', () => {
    const root = node({ children: [node({ nodeKey: 'B@2025', companyCode: 'B', companyName: '分公司B' })] })
    expect(nodeMatchesQuery(root, '分公司B')).toBe(true)
    expect(nodeMatchesQuery(root, 'B')).toBe(true)
    expect(formatShareholding(100)).toBe('100%')
  })
})


describe('P11 前端消费面守卫', () => {
  it('生产类型声明保留年度森林、关系、项目口径与间接路径字段', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(path.resolve(__dirname, '../useGroupTree.ts'), 'utf-8')
    const treeNode = src.slice(src.indexOf('export interface TreeNode'), src.indexOf('export interface GroupTree'))
    const groupTree = src.slice(src.indexOf('export interface GroupTree {'), src.indexOf('export interface GroupTreeResponse'))
    for (const field of ['nodeKey?', 'forestKey?', 'relation?', 'flags?', 'via?', 'year?', 'projects?', 'consolidatedProjectId?', 'standaloneProjectId?']) {
      expect(treeNode, `TreeNode 缺少 ${field}`).toContain(field)
    }
    expect(groupTree).toContain('key?: string')
    expect(groupTree).toContain('year?: number | null')
  })

  it('项目森林与合并架构视图使用实体 nodeKey/forest key，不再固定使用项目 id', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const projects = fs.readFileSync(path.resolve(__dirname, '../../views/Projects.vue'), 'utf-8')
    const hub = fs.readFileSync(path.resolve(__dirname, '../../views/ConsolidationHub.vue'), 'utf-8')
    expect(projects).toContain('node-key="nodeKey"')
    expect(projects).toContain('registerTreeRef(tree.key || `${tree.ultimateCode}@${tree.year || \'\'}`, el)')
    expect(hub).toContain('node-key="nodeKey"')
    expect(hub).toContain('registerTreeRef(tree.key || `${tree.ultimateCode}@${tree.year || \'\'}`, el)')
  })
})
