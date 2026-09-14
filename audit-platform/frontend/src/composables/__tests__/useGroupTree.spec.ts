/**
 * useGroupTree.spec.ts — group-tree-architecture Task 1.3
 *
 * 测试 useGroupTree composable：
 * - fetchTree 调用 API + 更新 trees/independents ref
 * - loading 状态切换 + 错误处理
 * - filterTree / filterNode 搜索过滤正确性
 * - 视图模式 localStorage 持久化
 *
 * Validates: Requirements 1.1, 5.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import fc from 'fast-check'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
  },
}))

import {
  useGroupTree,
  nodeSelfMatches,
  nodeMatchesQuery,
  highlightSegments,
  consolMethodLabel,
  formatShareholding,
  countConsolMethods,
  VIEW_MODE_KEY,
  type TreeNode,
  type GroupTreeResponse,
  type ViewMode,
} from '../useGroupTree'

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeNode(partial: Partial<TreeNode> & { id: string; companyCode: string; companyName: string }): TreeNode {
  return {
    label: partial.companyName,
    parentCompanyCode: null,
    ultimateCompanyCode: null,
    consolLevel: 1,
    status: 'execution',
    reportScope: null,
    children: [],
    isDetached: false,
    isIndependent: false,
    isCycleBreak: false,
    hasNoCompanyCode: false,
    ...partial,
  }
}

function makeResponse(): GroupTreeResponse {
  const child = makeNode({ id: '2', companyCode: '91110000000000002X', companyName: '子公司甲' })
  const root = makeNode({
    id: '1',
    companyCode: '91110000000000001A',
    companyName: '母公司集团',
    reportScope: 'consolidated',
    children: [child],
  })
  return {
    trees: [
      {
        ultimateCode: '91110000000000001A',
        ultimateName: '母公司集团',
        rootProjectId: '1',
        children: [root],
      },
    ],
    independents: [makeNode({ id: '3', companyCode: '', companyName: '独立项目丙', hasNoCompanyCode: true, isIndependent: true })],
  }
}

beforeEach(() => {
  mockGet.mockReset()
  localStorage.clear()
})

// ─── fetchTree ───────────────────────────────────────────────────────────────

describe('useGroupTree.fetchTree', () => {
  it('拉取后端树形 JSON 并更新 trees/independents', async () => {
    mockGet.mockResolvedValueOnce(makeResponse())
    const { trees, independents, loading, error, fetchTree } = useGroupTree()

    await fetchTree()

    expect(mockGet).toHaveBeenCalledWith('/api/projects/tree', { params: {} })
    expect(trees.value).toHaveLength(1)
    expect(trees.value[0].ultimateName).toBe('母公司集团')
    expect(independents.value).toHaveLength(1)
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('传 year + scope 时作为 params 下发', async () => {
    mockGet.mockResolvedValueOnce({ trees: [], independents: [] })
    const year = ref<number | null>(2025)
    const { fetchTree } = useGroupTree(year)

    await fetchTree('consolidated')

    expect(mockGet).toHaveBeenCalledWith('/api/projects/tree', {
      params: { year: 2025, scope: 'consolidated' },
    })
  })

  it('API 失败时设置 error 并清空 trees', async () => {
    mockGet.mockRejectedValueOnce(new Error('网络错误'))
    const { trees, error, fetchTree } = useGroupTree()

    await fetchTree()

    expect(error.value).toBe('网络错误')
    expect(trees.value).toEqual([])
  })
})

// ─── 搜索过滤 ────────────────────────────────────────────────────────────────

describe('useGroupTree 搜索过滤', () => {
  it('nodeSelfMatches 匹配名称或代码（大小写不敏感），空串视为匹配', () => {
    const n = { companyName: '母公司集团', companyCode: '91110000000000001A', label: '母公司集团' }
    expect(nodeSelfMatches(n, '母公司')).toBe(true)
    expect(nodeSelfMatches(n, '0001a')).toBe(true) // 大小写不敏感
    expect(nodeSelfMatches(n, '不存在')).toBe(false)
    expect(nodeSelfMatches(n, '')).toBe(true)
  })

  it('nodeMatchesQuery：后代匹配则祖先也可见', () => {
    const resp = makeResponse()
    const root = resp.trees[0].children[0] // 母公司，含子公司甲
    // 搜索"子公司甲"——root 自身不含但后代含 → root 可见
    expect(nodeMatchesQuery(root, '子公司甲')).toBe(true)
    // 搜索完全不存在的串 → 不可见
    expect(nodeMatchesQuery(root, 'zzz不存在zzz')).toBe(false)
  })

  it('filterNode 适配 el-tree filter-node-method', () => {
    const { filterNode } = useGroupTree()
    const node = makeNode({ id: '9', companyCode: 'CODE123', companyName: '测试企业' })
    expect(filterNode('测试', node)).toBe(true)
    expect(filterNode('CODE', node)).toBe(true)
    expect(filterNode('其他', node)).toBe(false)
    expect(filterNode('', node)).toBe(true) // 空搜索全部可见
  })

  it('filterTree 设置 searchQuery；hasSearchMatch 反映命中', async () => {
    mockGet.mockResolvedValueOnce(makeResponse())
    const { fetchTree, filterTree, searchQuery, hasSearchMatch } = useGroupTree()
    await fetchTree()

    filterTree('子公司甲')
    expect(searchQuery.value).toBe('子公司甲')
    expect(hasSearchMatch.value).toBe(true)

    filterTree('完全不存在的企业')
    expect(hasSearchMatch.value).toBe(false)

    filterTree('')
    expect(hasSearchMatch.value).toBe(true) // 清空恢复
  })
})

// ─── 搜索高亮分段 ─────────────────────────────────────────────────────────────

describe('highlightSegments 搜索高亮分段', () => {
  it('空 query 返回单个非高亮分段（原文）', () => {
    expect(highlightSegments('母公司集团', '')).toEqual([{ text: '母公司集团', match: false }])
    expect(highlightSegments('母公司集团', '   ')).toEqual([{ text: '母公司集团', match: false }])
  })

  it('空 text 返回单个空非高亮分段', () => {
    expect(highlightSegments('', '母公司')).toEqual([{ text: '', match: false }])
    expect(highlightSegments(null, '母公司')).toEqual([{ text: '', match: false }])
    expect(highlightSegments(undefined, '母公司')).toEqual([{ text: '', match: false }])
  })

  it('无匹配返回单个非高亮分段（原文）', () => {
    expect(highlightSegments('母公司集团', 'zzz')).toEqual([{ text: '母公司集团', match: false }])
  })

  it('中间匹配切分为 前/命中/后 三段', () => {
    expect(highlightSegments('北京母公司集团有限', '母公司')).toEqual([
      { text: '北京', match: false },
      { text: '母公司', match: true },
      { text: '集团有限', match: false },
    ])
  })

  it('开头匹配（无前缀段）', () => {
    expect(highlightSegments('母公司集团', '母公司')).toEqual([
      { text: '母公司', match: true },
      { text: '集团', match: false },
    ])
  })

  it('结尾匹配（无后缀段）', () => {
    expect(highlightSegments('集团母公司', '母公司')).toEqual([
      { text: '集团', match: false },
      { text: '母公司', match: true },
    ])
  })

  it('大小写不敏感匹配，分段保留原始大小写', () => {
    expect(highlightSegments('91110000000000001A', '0001a')).toEqual([
      { text: '9111000000000', match: false },
      { text: '0001A', match: true },
    ])
  })

  it('多处匹配全部切分命中', () => {
    expect(highlightSegments('ABxABxAB', 'ab')).toEqual([
      { text: 'AB', match: true },
      { text: 'x', match: false },
      { text: 'AB', match: true },
      { text: 'x', match: false },
      { text: 'AB', match: true },
    ])
  })

  it('分段拼接后等于原文（不丢字符）', () => {
    const cases: Array<[string, string]> = [
      ['北京母公司集团有限', '母公司'],
      ['91110000000000001A', '0001a'],
      ['ABxABxAB', 'ab'],
      ['集团母公司', '母公司'],
      ['无匹配文本', 'zzz'],
    ]
    for (const [text, q] of cases) {
      const joined = highlightSegments(text, q).map((s) => s.text).join('')
      expect(joined).toBe(text)
    }
  })
})

// ─── Phase 2 持股/合并方式展示（Task 14.1 / 14.2）────────────────────────────

describe('consolMethodLabel 合并方式中文标签', () => {
  it('映射枚举值到中文', () => {
    expect(consolMethodLabel('full')).toBe('完全合并')
    expect(consolMethodLabel('equity')).toBe('权益法')
    expect(consolMethodLabel('proportional')).toBe('比例合并')
  })
  it('空值返回空串（不渲染 tag）', () => {
    expect(consolMethodLabel(null)).toBe('')
    expect(consolMethodLabel(undefined)).toBe('')
    expect(consolMethodLabel('')).toBe('')
  })
  it('未知值原样返回', () => {
    expect(consolMethodLabel('unknown_method')).toBe('unknown_method')
  })
})

describe('formatShareholding 持股比例格式化', () => {
  it('整数去掉小数尾零', () => {
    expect(formatShareholding(100)).toBe('100%')
    expect(formatShareholding(51)).toBe('51%')
  })
  it('保留有效小数', () => {
    expect(formatShareholding(66.67)).toBe('66.67%')
    expect(formatShareholding(66.7)).toBe('66.7%')
  })
  it('空值/NaN 返回空串（不渲染 badge）', () => {
    expect(formatShareholding(null)).toBe('')
    expect(formatShareholding(undefined)).toBe('')
    expect(formatShareholding(NaN)).toBe('')
  })
  it('0 仍渲染（0%）', () => {
    expect(formatShareholding(0)).toBe('0%')
  })
})

describe('countConsolMethods 合并方式统计', () => {
  it('递归统计森林节点的合并方式分布', () => {
    const leaf = makeNode({ id: 'a', companyCode: 'A', companyName: '子A', consolMethod: 'equity' })
    const root = makeNode({
      id: 'r',
      companyCode: 'R',
      companyName: '根',
      consolMethod: 'full',
      children: [
        leaf,
        makeNode({ id: 'b', companyCode: 'B', companyName: '子B', consolMethod: 'full' }),
        makeNode({ id: 'c', companyCode: 'C', companyName: '子C', consolMethod: 'proportional' }),
        makeNode({ id: 'd', companyCode: 'D', companyName: '子D' }), // 无 consolMethod
      ],
    })
    const counts = countConsolMethods([root])
    expect(counts.full).toBe(2)
    expect(counts.equity).toBe(1)
    expect(counts.proportional).toBe(1)
    expect(counts.total).toBe(4) // 无数据的子D 不计入
  })
  it('无任何合并方式数据 → 各项为 0', () => {
    const root = makeNode({ id: 'r', companyCode: 'R', companyName: '根' })
    const counts = countConsolMethods([root])
    expect(counts).toEqual({ full: 0, equity: 0, proportional: 0, total: 0 })
  })
})

// ─── 视图模式持久化 ───────────────────────────────────────────────────────────

describe('useGroupTree 视图模式持久化', () => {
  it('默认 list，写入后持久化到 localStorage', async () => {
    const { viewMode } = useGroupTree()
    expect(viewMode.value).toBe('list')

    viewMode.value = 'tree'
    await nextTick()
    expect(localStorage.getItem(VIEW_MODE_KEY)).toBe('tree')
  })

  it('从 localStorage 恢复已保存的视图模式', () => {
    localStorage.setItem(VIEW_MODE_KEY, 'client')
    const { viewMode } = useGroupTree()
    expect(viewMode.value).toBe('client')
  })
})

// ─── PBT (fast-check) ─────────────────────────────────────────────────────────
//
// Feature: group-tree-architecture
//   Property 8  (Task 3.2): Tree node data preservation
//   Property 15 (Task 4.2): View mode persistence round-trip
//   Property 9  (Task 5.2): Search filter correctness
//
// 项目约定：PBT 迭代次数低（hypothesis max_examples=5）→ fast-check numRuns: 5。

const FC_RUNS = { numRuns: 5 }

/** 小字母表（含中文+ASCII），高频碰撞以充分覆盖搜索命中分支 */
const NAME_CHARS = ['甲', '乙', '丙', 'A', 'B', 'a']
const CODE_CHARS = ['0', '1', '2', 'X', 'Y']

const arbName = fc.array(fc.constantFrom(...NAME_CHARS), { minLength: 1, maxLength: 4 }).map((cs) => cs.join(''))
const arbCode = fc.array(fc.constantFrom(...CODE_CHARS), { minLength: 1, maxLength: 5 }).map((cs) => cs.join(''))

/** 深度受限的递归树生成器（保证终止，不依赖 letrec 自动深度控制） */
function arbTreeNode(depth: number): fc.Arbitrary<TreeNode> {
  const leaf = fc.record({ companyName: arbName, companyCode: arbCode })
  if (depth <= 0) {
    return leaf.map(({ companyName, companyCode }) =>
      makeNode({ id: `n-${companyName}-${companyCode}`, companyName, companyCode }),
    )
  }
  return fc
    .record({
      companyName: arbName,
      companyCode: arbCode,
      children: fc.array(arbTreeNode(depth - 1), { maxLength: 3 }),
    })
    .map(({ companyName, companyCode, children }) =>
      makeNode({ id: `n-${companyName}-${companyCode}`, companyName, companyCode, children }),
    )
}

/**
 * 独立参考实现：节点可见 iff 自身或任一后代的 companyName/companyCode
 * 含搜索串（大小写不敏感）。空串 → 全部可见。
 */
function refNodeMatches(node: TreeNode, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const name = (node.companyName || node.label || '').toLowerCase()
  const code = (node.companyCode || '').toLowerCase()
  if (name.includes(q) || code.includes(q)) return true
  return (node.children || []).some((c) => refNodeMatches(c, q))
}

describe('PBT (fast-check) — group-tree-architecture', () => {
  // ─── Property 8 (Task 3.2): Tree node data preservation ──────────────────────
  // 树中节点的 companyName/companyCode/status 与源数据一致。
  // Validates: Requirements 3.4
  it('Property 8: fetchTree 保留每个节点的 companyName/companyCode/status（不丢失/不篡改）', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.record({
            companyName: arbName,
            companyCode: fc.oneof(arbCode, fc.constant('')),
            status: fc.constantFrom('created', 'planning', 'execution', 'completion', null),
          }),
          { minLength: 1, maxLength: 5 },
        ),
        async (specs) => {
          // 用生成的字段值构造后端返回的 GroupTreeResponse
          const children: TreeNode[] = specs.map((s, i) =>
            makeNode({
              id: `node-${i}`,
              companyCode: s.companyCode,
              companyName: s.companyName,
              status: s.status,
            }),
          )
          const root = makeNode({
            id: 'root',
            companyCode: '91110000000000001A',
            companyName: '根集团',
            reportScope: 'consolidated',
            children,
          })
          const response: GroupTreeResponse = {
            trees: [
              { ultimateCode: '91110000000000001A', ultimateName: '根集团', rootProjectId: 'root', children: [root] },
            ],
            independents: [],
          }

          mockGet.mockReset()
          mockGet.mockResolvedValue(response)

          const { trees, fetchTree } = useGroupTree()
          await fetchTree()

          // 源数据按 id 索引
          const sourceById = new Map<string, { companyName: string; companyCode: string; status: string | null }>()
          specs.forEach((s, i) =>
            sourceById.set(`node-${i}`, { companyName: s.companyName, companyCode: s.companyCode, status: s.status }),
          )

          // 遍历返回树形，逐节点核对 source 字段保留
          const walk = (nodes: TreeNode[]) => {
            for (const n of nodes) {
              const src = sourceById.get(n.id)
              if (src) {
                expect(n.companyName).toBe(src.companyName)
                expect(n.companyCode).toBe(src.companyCode)
                expect(n.status).toBe(src.status)
              }
              walk(n.children || [])
            }
          }
          walk(trees.value.flatMap((t) => t.children))
        },
      ),
      FC_RUNS,
    )
  })

  // ─── Property 15 (Task 4.2): View mode persistence round-trip ────────────────
  // 写入 localStorage 后读回值一致（'list' | 'client' | 'tree'）。
  // Validates: Requirements 4.5
  it('Property 15: viewMode 写入 localStorage 后读回一致（往返）', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constantFrom<ViewMode>('list', 'client', 'tree'), async (mode) => {
        localStorage.clear()

        // 先设一个与目标不同的"引子"值，保证后续设为 mode 时 ref 确实变化、
        // watch 触发写入（watch 非 immediate：值未变则不写）。
        const primer: ViewMode = mode === 'list' ? 'tree' : 'list'
        const { viewMode } = useGroupTree()
        viewMode.value = primer
        await nextTick()

        // 写入目标值 → watch 持久化
        viewMode.value = mode
        await nextTick()

        // localStorage 持有写入值
        expect(localStorage.getItem(VIEW_MODE_KEY)).toBe(mode)

        // 新实例从 localStorage 读回同值（往返）
        const fresh = useGroupTree()
        expect(fresh.viewMode.value).toBe(mode)
      }),
      FC_RUNS,
    )
  })

  // ─── Property 9 (Task 5.2): Search filter correctness ────────────────────────
  // 节点可见 iff 自身或后代的 companyName/companyCode 含搜索串（大小写不敏感）。
  // Validates: Requirements 5.1, 5.2
  it('Property 9: nodeMatchesQuery 等价于独立参考实现（自身或后代命中，大小写不敏感）', () => {
    const arbQuery = fc.oneof(
      fc.constant(''), // 空串 → 全部可见
      fc.array(fc.constantFrom(...NAME_CHARS), { minLength: 1, maxLength: 3 }).map((cs) => cs.join('')),
      fc.array(fc.constantFrom(...CODE_CHARS), { minLength: 1, maxLength: 3 }).map((cs) => cs.join('')),
      fc.array(fc.constantFrom(...NAME_CHARS, ...CODE_CHARS), { minLength: 1, maxLength: 3 }).map((cs) => cs.join('')),
    )

    fc.assert(
      fc.property(arbTreeNode(3), arbQuery, (root, query) => {
        expect(nodeMatchesQuery(root, query)).toBe(refNodeMatches(root, query))
      }),
      FC_RUNS,
    )
  })

  it('Property 9: 大小写不敏感——大写查询与小写查询结果一致', () => {
    fc.assert(
      fc.property(arbTreeNode(3), fc.array(fc.constantFrom('A', 'B', 'X', 'Y'), { minLength: 1, maxLength: 3 }).map((cs) => cs.join('')), (root, q) => {
        expect(nodeMatchesQuery(root, q.toUpperCase())).toBe(nodeMatchesQuery(root, q.toLowerCase()))
      }),
      FC_RUNS,
    )
  })
})
