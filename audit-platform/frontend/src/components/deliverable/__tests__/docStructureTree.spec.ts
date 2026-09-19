/**
 * 交付件文档结构树 / 生成守卫 —— fast-check 属性测试 + 单元测试
 * Spec: .kiro/specs/audit-report-deliverable-center/ Task 7.6-7.10
 *
 * 覆盖：
 *   Feature: audit-report-deliverable-center, Property 2: 导出弹窗默认全选 (7.6)
 *   Feature: audit-report-deliverable-center, Property 3: 附注层级选择联动 (7.7)
 *   Feature: audit-report-deliverable-center, Property 1: 选择性导出投影一致性 (7.8)
 *   单元测试：空选禁用确认、生成入口存在 (7.9)
 *   Feature: audit-report-deliverable-center, Property 37: 生成前置数据就绪守卫 (7.10)
 *
 * **Validates: Requirements 1.2, 1.3, 1.4, 1.6, 18.3, 21.1, 21.2, 21.3, 21.4**
 *
 * 实施方案：vitest + fast-check（默认 numRuns）。提取 docStructureTree.ts / generateGuard.ts
 * 纯逻辑直接测试，避免重度依赖完整组件挂载。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  buildDocStructure,
  collectLeafIds,
  collectAllIds,
  defaultCheckedKeys,
  applyToggle,
  projectedSections,
  findNode,
  type DocTreeNode,
} from '../docStructureTree'
import {
  GENERATE_ENTRIES,
  checkGenerateReady,
  type DataReadiness,
  type GenerateEntryKey,
} from '../generateGuard'

const DOC_TYPES = ['audit_report', 'financial_report', 'disclosure_notes'] as const

// ─── 随机结构树生成器（覆盖任意层级 + 叶子）──────────────────────────────
function leafArb(idPrefix: string): fc.Arbitrary<DocTreeNode> {
  return fc.string({ minLength: 1, maxLength: 6 }).map((s) => ({
    id: `${idPrefix}-${s}-${Math.random().toString(36).slice(2, 6)}`,
    label: `节点${s}`,
  }))
}

// 父节点带 1-4 个唯一叶子
function parentArb(idPrefix: string): fc.Arbitrary<DocTreeNode> {
  return fc.array(leafArb(`${idPrefix}c`), { minLength: 1, maxLength: 4 }).map((children) => {
    // 去重 id 保证唯一
    const seen = new Set<string>()
    const uniq = children.filter((c: DocTreeNode) => (seen.has(c.id) ? false : (seen.add(c.id), true)))
    return {
      id: `${idPrefix}-parent-${Math.random().toString(36).slice(2, 8)}`,
      label: '父',
      children: uniq,
    }
  })
}

const treeArb: fc.Arbitrary<DocTreeNode[]> = fc
  .array(fc.oneof(leafArb('L'), parentArb('P')), { minLength: 1, maxLength: 5 })
  .map((nodes) => {
    // 保证整棵树 id 全局唯一
    const seen = new Set<string>()
    const dedupe = (list: DocTreeNode[]): DocTreeNode[] =>
      list
        .filter((n) => (seen.has(n.id) ? false : (seen.add(n.id), true)))
        .map((n) => (n.children ? { ...n, children: dedupe(n.children) } : n))
    return dedupe(nodes)
  })

// ─── Property 2: 导出弹窗默认全选 (7.6) ──────────────────────────────────
describe('Feature: audit-report-deliverable-center, Property 2: 导出弹窗默认全选', () => {
  it('任意文档类型，默认选中键 == 全部叶子节点（Req 1.2）', () => {
    fc.assert(
      fc.property(fc.constantFrom(...DOC_TYPES), (docType) => {
        const tree = buildDocStructure(docType)
        const checked = defaultCheckedKeys(tree)
        const leaves = collectLeafIds(tree)
        expect([...checked].sort()).toEqual([...leaves].sort())
        // 非空：每种文档类型都有可选项
        expect(checked.length).toBeGreaterThan(0)
      }),
    )
  })

  it('任意随机结构树，默认全选覆盖且仅覆盖全部叶子（Req 1.2）', () => {
    fc.assert(
      fc.property(treeArb, (tree) => {
        const checked = new Set(defaultCheckedKeys(tree))
        const leaves = new Set(collectLeafIds(tree))
        expect(checked).toEqual(leaves)
      }),
    )
  })
})

// ─── Property 3: 附注层级选择联动 (7.7) ──────────────────────────────────
describe('Feature: audit-report-deliverable-center, Property 3: 附注层级选择联动', () => {
  it('勾选父节点→全部子叶被选中；取消父节点→全部子叶被取消（Req 1.6）', () => {
    fc.assert(
      fc.property(treeArb, (tree) => {
        const parents = collectAllIds(tree).filter((id) => {
          const node = findNode(tree, id)
          return node?.children && node.children.length > 0
        })
        fc.pre(parents.length > 0)

        for (const pid of parents) {
          const parent = findNode(tree, pid)!
          const childLeaves = collectLeafIds(parent.children!)

          // 从空集勾选父节点 → 其全部子叶被选中
          const afterCheck = applyToggle(tree, new Set<string>(), pid, true)
          for (const leaf of childLeaves) {
            expect(afterCheck.has(leaf)).toBe(true)
          }

          // 从全选取消父节点 → 其全部子叶被取消
          const allLeaves = new Set(collectLeafIds(tree))
          const afterUncheck = applyToggle(tree, allLeaves, pid, false)
          for (const leaf of childLeaves) {
            expect(afterUncheck.has(leaf)).toBe(false)
          }
        }
      }),
    )
  })

  it('附注真实结构：勾/取消第三章父节点联动其全部子项（Req 1.6）', () => {
    const tree = buildDocStructure('disclosure_notes')
    const itemsNode = findNode(tree, 'note_items')!
    const childLeaves = collectLeafIds(itemsNode.children!)
    expect(childLeaves.length).toBeGreaterThan(1)

    const checked = applyToggle(tree, new Set<string>(), 'note_items', true)
    childLeaves.forEach((l) => expect(checked.has(l)).toBe(true))

    const unchecked = applyToggle(tree, new Set(collectLeafIds(tree)), 'note_items', false)
    childLeaves.forEach((l) => expect(unchecked.has(l)).toBe(false))
  })
})

// ─── Property 1: 选择性导出投影一致性 (7.8) ──────────────────────────────
describe('Feature: audit-report-deliverable-center, Property 1: 选择性导出投影一致性', () => {
  it('投影集合 == 被勾选叶子子集，不遗漏不多余（Req 1.3, 18.3）', () => {
    fc.assert(
      fc.property(
        treeArb.chain((tree) => {
          const leaves = collectLeafIds(tree)
          return fc.record({
            tree: fc.constant(tree),
            // 随机勾选叶子子集
            picks: fc.subarray(leaves),
          })
        }),
        ({ tree, picks }) => {
          const checked = new Set(picks)
          const projected = projectedSections(tree, checked)
          const projectedSet = new Set(projected)

          // 不包含未勾选项
          for (const id of projected) {
            expect(checked.has(id)).toBe(true)
          }
          // 不遗漏勾选项（限定在叶子范围内）
          const leaves = new Set(collectLeafIds(tree))
          for (const id of picks) {
            if (leaves.has(id)) expect(projectedSet.has(id)).toBe(true)
          }
          // 投影规模 == 勾选叶子数
          const checkedLeafCount = picks.filter((p) => leaves.has(p)).length
          expect(projected.length).toBe(checkedLeafCount)
        },
      ),
    )
  })

  it('全选时投影 == 全部叶子（Req 1.3）', () => {
    fc.assert(
      fc.property(fc.constantFrom(...DOC_TYPES), (docType) => {
        const tree = buildDocStructure(docType)
        const allLeaves = collectLeafIds(tree)
        const projected = projectedSections(tree, new Set(allLeaves))
        expect([...projected].sort()).toEqual([...allLeaves].sort())
      }),
    )
  })
})

// ─── 单元测试：空选禁用确认、生成入口存在 (7.9) ──────────────────────────
describe('单元测试：空选禁用确认 + 生成入口存在', () => {
  it('空选时投影为空数组（确认按钮据此 disabled，Req 1.4）', () => {
    for (const docType of DOC_TYPES) {
      const tree = buildDocStructure(docType)
      expect(projectedSections(tree, new Set<string>())).toEqual([])
    }
  })

  it('三类核心生成入口齐全：报表 / 附注 / 报告正文（Req 21.1/21.2/21.3）', () => {
    const keys = GENERATE_ENTRIES.map((e) => e.key)
    expect(keys).toContain('reports')
    expect(keys).toContain('notes')
    expect(keys).toContain('report_body')
    // 每个入口都有中文显眼文案
    GENERATE_ENTRIES.forEach((e) => {
      expect(e.label).toMatch(/生成/)
      expect(e.requires.length).toBeGreaterThan(0)
    })
  })
})

// ─── Property 37: 生成前置数据就绪守卫 (7.10) ────────────────────────────
describe('Feature: audit-report-deliverable-center, Property 37: 生成前置数据就绪守卫', () => {
  const entryKeyArb = fc.constantFrom<GenerateEntryKey>('reports', 'notes', 'report_body')
  const readinessArb: fc.Arbitrary<DataReadiness> = fc.record({
    trialBalanceReady: fc.boolean(),
    reportsReady: fc.boolean(),
  })

  it('任一所需数据未就绪→被阻止且提示非空；全部就绪→放行（Req 21.4）', () => {
    fc.assert(
      fc.property(entryKeyArb, readinessArb, (entryKey, readiness) => {
        const entry = GENERATE_ENTRIES.find((e) => e.key === entryKey)!
        const anyMissing = entry.requires.some((flag) => !readiness[flag])
        const result = checkGenerateReady(entryKey, readiness)

        if (anyMissing) {
          expect(result.allowed).toBe(false)
          expect(result.message.length).toBeGreaterThan(0)
          expect(result.missing.length).toBeGreaterThan(0)
        } else {
          expect(result.allowed).toBe(true)
          expect(result.missing.length).toBe(0)
        }
      }),
    )
  })

  it('全部未就绪时三入口均被阻止（Req 21.4）', () => {
    const none: DataReadiness = { trialBalanceReady: false, reportsReady: false }
    for (const entry of GENERATE_ENTRIES) {
      const r = checkGenerateReady(entry.key, none)
      expect(r.allowed).toBe(false)
    }
  })

  it('全部就绪时三入口均放行（Req 21.4）', () => {
    const all: DataReadiness = { trialBalanceReady: true, reportsReady: true }
    for (const entry of GENERATE_ENTRIES) {
      const r = checkGenerateReady(entry.key, all)
      expect(r.allowed).toBe(true)
    }
  })
})
