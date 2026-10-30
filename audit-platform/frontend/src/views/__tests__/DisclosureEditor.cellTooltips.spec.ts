/**
 * 附注单元格两层提示（spec note-chain-followup-optimizations R5）：校验提示包单元格容器、批注提示只包 GtGridCell。
 *
 * 原状（可打红）：`el-tooltip > CommentTooltip > div.gt-cell-wrapper` —— 没批注时 CommentTooltip 是片段根，接不住
 * 校验提示的触发器 ⇒ 校验提示永远不出现、每格一条 Vue 告警；有批注时两层提示嵌套，校验提示同样挂不上。
 * 按模板 AST 判结构（组件太大，挂载测不划算；运行时行为由 CommentTooltip.spec 与浏览器实测覆盖）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'

interface Node {
  type: number
  tag?: string
  content?: string
  props?: Array<{ type: number; name: string; value?: { content: string }; arg?: { content: string }; exp?: { content: string } }>
  children?: Node[]
}

const ELEMENT = 1
const TEXT = 2
const ATTRIBUTE = 6
const DIRECTIVE = 7

const SRC = readFileSync(resolve(__dirname, '../DisclosureEditor.vue'), 'utf-8')
const AST = parse(SRC, { filename: 'DisclosureEditor.vue' }).descriptor.template!.ast as unknown as Node

function walk(node: Node, visit: (n: Node, parent: Node | null) => void, parent: Node | null = null): void {
  visit(node, parent)
  for (const child of node.children ?? []) walk(child, visit, node)
}

const elementChildren = (n: Node) => (n.children ?? []).filter((c) => c.type === ELEMENT)
/** 除去空白文字后的全部子节点（注释也算：el-tooltip 里多一个注释节点开发环境就渲染不出触发元素）。 */
const meaningfulChildren = (n: Node) => (n.children ?? []).filter((c) => !(c.type === TEXT && !(c.content ?? '').trim()))
const staticClasses = (n: Node) =>
  ((n.props ?? []).find((p) => p.type === ATTRIBUTE && p.name === 'class')?.value?.content ?? '').split(/\s+/)
const bound = (n: Node, name: string) =>
  (n.props ?? []).find((p) => p.type === DIRECTIVE && p.name === 'bind' && p.arg?.content === name)?.exp?.content
const attr = (n: Node, name: string) => (n.props ?? []).find((p) => p.type === ATTRIBUTE && p.name === name)?.value?.content

describe('附注单元格：校验提示与批注提示各自挂到真实元素', () => {
  it('校验提示（el-tooltip）只包单元格容器，Enter / 空格不开合', () => {
    const found: Array<{ node: Node; parent: Node | null }> = []
    walk(AST, (n, parent) => { if (n.type === ELEMENT && staticClasses(n).includes('gt-cell-wrapper')) found.push({ node: n, parent }) })
    expect(found).toHaveLength(1)
    const { node, parent } = found[0]
    expect(parent?.tag).toBe('el-tooltip')
    expect(meaningfulChildren(parent!)).toEqual([node])
    expect(bound(parent!, 'content')).toContain('getCellValidationError')
    expect(bound(parent!, 'trigger-keys')?.replace(/\s/g, '')).toBe('[]')
    // 批注提示固定在上方（CommentTooltip）：同一格两种提示都有时，校验提示放下方才不互相遮住
    expect(attr(parent!, 'placement')).toBe('bottom')
  })

  it('批注提示在容器里、只包 GtGridCell', () => {
    let wrapper: Node | null = null
    walk(AST, (n) => { if (n.type === ELEMENT && staticClasses(n).includes('gt-cell-wrapper')) wrapper = n })
    const tips = elementChildren(wrapper!).filter((c) => c.tag === 'CommentTooltip')
    expect(tips).toHaveLength(1)
    expect(meaningfulChildren(tips[0]).map((c) => c.tag)).toEqual(['GtGridCell'])
  })

  it('全文件没有 el-tooltip 直接包 CommentTooltip（两层提示嵌套，外层挂不上）', () => {
    const nested: string[] = []
    walk(AST, (n) => {
      if (n.type === ELEMENT && n.tag === 'el-tooltip' && elementChildren(n).some((c) => c.tag === 'CommentTooltip')) {
        nested.push(bound(n, 'content') ?? '(无 content)')
      }
    })
    expect(nested).toEqual([])
  })
})
