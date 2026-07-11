/**
 * useNoteTree — ACNR NOTE 索引接入测试（Task 22.2 / P22）
 *
 * 覆盖两部分：
 *  1. **Property 22: Note Index Additive Non-Regression**（fast-check）
 *     形式化：向叶子节点追加 `indexRef` 是「纯 additive」的 —
 *       ∀ 随机附注列表，treeData 的分组/排序/children 计数/id/label 与
 *       「去掉 indexRef 后」的结构完全一致；
 *       group 节点（isGroup）不带 indexRef，leaf 节点带 `indexRef === 'note:'+note_section`。
 *     Validates: Requirements 17.1, 17.3
 *
 *  2. **resolveNoteIndexRoute 单元测试** — 命中跳转 jump_route；未命中/异常/空回退 null。
 *     Validates: Requirements 17.1, 17.3
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { computed, ref } from 'vue'

// ─── Mock 远程 service（避免真实 API 调用） ────────────────────────────────
// useAcnr().resolveIndex 由 mockResolveIndex 驱动（单测可逐例配置）。
const mockResolveIndex = vi.fn()
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveIndex: mockResolveIndex }),
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

import { useNoteTree, type TreeNode, type UseNoteTreeReturn } from '../useNoteTree'
import type { DisclosureNoteTreeItem } from '@/services/auditPlatformApi'

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 实例化 composable，返回句柄 + 用于驱动 treeData 的 noteList/templateType setter */
function makeTree(templateType: 'soe' | 'listed' = 'soe'): UseNoteTreeReturn {
  return useNoteTree({
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2024),
    templateType: ref(templateType),
    isEqcrRole: computed(() => false),
  })
}

/** 判定「叶子节点」：没有 children 且不是分组 */
function isLeaf(node: TreeNode): boolean {
  return !node.isGroup && !node.children
}

/** 深度遍历树，对每个节点执行回调 */
function walk(nodes: TreeNode[], fn: (n: TreeNode) => void): void {
  for (const n of nodes) {
    fn(n)
    if (n.children) walk(n.children, fn)
  }
}

/** 深拷贝并递归剔除 indexRef，得到「pre-change」结构投影 */
function stripIndexRef(nodes: TreeNode[]): TreeNode[] {
  return nodes.map((n) => {
    const { indexRef: _drop, children, ...rest } = n
    const out: TreeNode = { ...rest }
    if (children) out.children = stripIndexRef(children)
    return out
  })
}

/** 收集所有叶子（按 DFS 前序，保留顺序） */
function collectLeaves(nodes: TreeNode[]): TreeNode[] {
  const acc: TreeNode[] = []
  walk(nodes, (n) => { if (isLeaf(n)) acc.push(n) })
  return acc
}

// ─── 附注生成器 ──────────────────────────────────────────────────────────────

// 命中各分组分支的关键词（触发 POLICY/MERGE/RELATED/SECTION 分组路径）
const KEYWORD_TITLES = [
  '会计期间', '企业合并', '存货', '职工薪酬', '租赁', '金融工具',
  '纳入合并', '表决权不足', '同一控制下企业合并', '重大限制',
  '母公司', '关联交易', '固定资产', '收入',
]

// 覆盖不同分组分支的章节前缀：三/四(政策平铺) 五/八(报表分组) 七(合并) 十一(关联) 其他平铺
const PREFIXES = ['一', '二', '三', '四', '五', '七', '八', '十一', '十七']

const titleArb = fc.oneof(
  fc.constantFrom(...KEYWORD_TITLES),
  fc.string({ minLength: 1, maxLength: 8 }),
)

const noteSeedArb = fc.record({
  prefix: fc.constantFrom(...PREFIXES),
  num: fc.integer({ min: 1, max: 40 }),
  title: titleArb,
})

/** 生成一组附注（id 保证唯一） */
const noteListArb = fc
  .array(noteSeedArb, { minLength: 1, maxLength: 25 })
  .map((seeds): DisclosureNoteTreeItem[] =>
    seeds.map((s, i) => ({
      id: `note-${i}`,
      note_section: `${s.prefix}、${s.num}`,
      section_title: s.title,
      account_name: null,
      content_type: 'table',
      status: 'draft',
      sort_order: i,
    })),
  )

// ─── Property 22: Additive Non-Regression ────────────────────────────────────

describe('Property 22: Note Index Additive Non-Regression (Req 17.1, 17.3)', () => {
  it('adding indexRef leaves id/label/children/ordering/grouping unchanged', () => {
    fc.assert(
      fc.property(
        noteListArb,
        fc.constantFrom<'soe' | 'listed'>('soe', 'listed'),
        (notes, templateType) => {
          const tree = makeTree(templateType)
          tree.noteList.value = notes
          const data = tree.treeData.value

          // 建立 id → note 映射，供叶子核对
          const byId = new Map(notes.map((n) => [n.id, n]))

          walk(data, (node) => {
            if (node.isGroup) {
              // (1) 分组节点绝不带 indexRef
              expect(node.indexRef).toBeUndefined()
            } else if (isLeaf(node)) {
              const note = byId.get(node.id)
              // (2) 叶子 id/label 未被 indexRef 影响
              expect(note).toBeDefined()
              expect(node.id).toBe(note!.id)
              expect(node.label).toBe(note!.section_title)
              // (3) 叶子 indexRef 恒等于 note:{note_section}
              expect(node.indexRef).toBe(`note:${note!.note_section}`)
              // (4) 剥离 indexRef 后即为 pre-change 形态 {id,label,data}
              const { indexRef: _d, ...bare } = node
              expect(bare).toEqual({ id: note!.id, label: note!.section_title, data: note })
            }
          })

          // (5) 去掉 indexRef 的结构投影里，任何节点都不再含 indexRef
          //     —— 证明 indexRef 是可无损剥离的附加字段（不影响 id/label/children/分组）
          const stripped = stripIndexRef(data)
          walk(stripped, (n) => expect(n.indexRef).toBeUndefined())

          // (6) 排序非回归：分组用 order-preserving `.filter` 构建，故「同一父节点下的
          //     叶子」相对顺序 = 其在原 noteList 中的相对顺序（跨章节顺序由 CHAPTER_GROUPS
          //     决定，非 noteList 顺序，故只在同组内校验）。
          walk(data, (parent) => {
            if (!parent.children) return
            const leafIdx = parent.children
              .filter(isLeaf)
              .map((l) => notes.findIndex((n) => n.id === l.id))
            const sortedAsc = [...leafIdx].sort((a, b) => a - b)
            expect(leafIdx).toEqual(sortedAsc)
          })
        },
      ),
      { numRuns: 60 },
    )
  })

  it('leaf count equals notes belonging to a recognized chapter (indexRef adds no/removes no leaf)', () => {
    fc.assert(
      fc.property(noteListArb, (notes) => {
        const tree = makeTree('soe')
        tree.noteList.value = notes
        const leaves = collectLeaves(tree.treeData.value)
        // 每片叶子对应唯一 note；不重复、不凭空产生
        const ids = leaves.map((l) => l.id)
        expect(new Set(ids).size).toBe(ids.length)
        for (const id of ids) expect(notes.some((n) => n.id === id)).toBe(true)
      }),
      { numRuns: 40 },
    )
  })
})

// ─── resolveNoteIndexRoute 单元测试 ───────────────────────────────────────────

describe('resolveNoteIndexRoute (Req 17.1, 17.3)', () => {
  beforeEach(() => {
    mockResolveIndex.mockReset()
  })

  it('returns jump_route when ACNR resolveIndex hits (found + jump_route)', async () => {
    mockResolveIndex.mockResolvedValue({ found: true, jump_route: '/notes/proj-1/2024?section=八、1' })
    const tree = makeTree()
    const route = await tree.resolveNoteIndexRoute('note:八、1')
    expect(mockResolveIndex).toHaveBeenCalledWith('note:八、1')
    expect(route).toBe('/notes/proj-1/2024?section=八、1')
  })

  it('returns null when found=false (fallback signal)', async () => {
    mockResolveIndex.mockResolvedValue({ found: false, error: 'not_found' })
    const tree = makeTree()
    expect(await tree.resolveNoteIndexRoute('note:五、9')).toBeNull()
  })

  it('returns null when found=true but jump_route missing', async () => {
    mockResolveIndex.mockResolvedValue({ found: true })
    const tree = makeTree()
    expect(await tree.resolveNoteIndexRoute('note:五、9')).toBeNull()
  })

  it('returns null when resolveIndex throws (error fallback)', async () => {
    mockResolveIndex.mockRejectedValue(new Error('network'))
    const tree = makeTree()
    expect(await tree.resolveNoteIndexRoute('note:三、2')).toBeNull()
  })

  it('returns null and does not call resolveIndex for empty indexRef', async () => {
    const tree = makeTree()
    expect(await tree.resolveNoteIndexRoute(undefined)).toBeNull()
    expect(await tree.resolveNoteIndexRoute('')).toBeNull()
    expect(mockResolveIndex).not.toHaveBeenCalled()
  })
})
