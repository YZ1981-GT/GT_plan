/**
 * 批注提示不得嵌在另一层提示里（spec note-chain-followup-optimizations R5）。
 *
 * 批注气泡（CommentTooltip，以及根是它的 GtAmountCell / ConsolNoteGridCell）有批注时根是 el-tooltip（片段根）：
 * 外层 el-tooltip / el-popover 的触发器挂不上去 ⇒ 外层提示不出现、Vue 告警。原状（可打红）：附注编辑页校验提示直接包
 * CommentTooltip、报表页公式提示直接包带 :comment 的 GtAmountCell。正确写法：外层提示包一个真实元素（span / div），
 * 批注组件放在里面（见 DisclosureEditor 单元格、ReportView 金额列）。
 */
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'
import { resolve } from 'node:path'
import { FRONTEND_SRC, readSource, toSrcRelative, walkSourceFiles } from './_helpers/frontendSourceScan'

interface Node {
  type: number
  tag?: string
  props?: Array<{ type: number; name: string; arg?: { content: string } }>
  children?: Node[]
  branches?: Node[]
  loc?: { start: { line: number } }
}

/** 根是 CommentTooltip 的组件（登记是可伪证声明：下面有一条检查它们的模板根真的是 CommentTooltip）。 */
const COMMENT_ROOTED: Record<string, string> = {
  GtAmountCell: 'components/common/GtAmountCell.vue',
  ConsolNoteGridCell: 'components/consolidation/ConsolNoteGridCell.vue',
}
const WRAPPERS = new Set(['el-tooltip', 'ElTooltip', 'el-popover', 'ElPopover'])

const slotName = (n: Node) =>
  (n.props ?? []).find((p) => p.type === 7 && p.name === 'slot')?.arg?.content ?? (n.tag === 'template' ? 'default' : null)
const hasComment = (n: Node) =>
  (n.props ?? []).some((p) => (p.type === 7 && p.name === 'bind' && p.arg?.content === 'comment') || (p.type === 6 && p.name === 'comment'))

/** 提示的触发节点：el-tooltip 取默认插槽第一个元素，el-popover 取 #reference 插槽第一个元素。 */
function triggerOf(n: Node): Node | undefined {
  const kids = (n.children ?? []).filter((c) => c.type === 1)
  const popover = /popover/i.test(n.tag ?? '')
  const slot = kids.find((k) => k.tag === 'template' && slotName(k) === (popover ? 'reference' : 'default'))
  const pool = slot ? (slot.children ?? []).filter((c) => c.type === 1) : popover ? [] : kids.filter((k) => k.tag !== 'template')
  return pool[0]
}

export function scanNested(filename: string, source: string): string[] {
  const ast = parse(source, { filename }).descriptor.template?.ast as unknown as Node | undefined
  const found: string[] = []
  const stack: Node[] = ast ? [ast] : []
  while (stack.length) {
    const n = stack.pop()!
    if (n.type === 1 && WRAPPERS.has(n.tag ?? '')) {
      const t = triggerOf(n)
      if (t && (t.tag === 'CommentTooltip' || (t.tag! in COMMENT_ROOTED && hasComment(t)))) {
        found.push(`${filename}:${t.loc?.start.line} ${n.tag} > ${t.tag}`)
      }
    }
    stack.push(...(n.children ?? []), ...(n.branches ?? []))
  }
  return found
}

describe('批注提示不嵌在另一层提示里', () => {
  it('src 下全部 .vue 没有这种写法', () => {
    const files = walkSourceFiles(FRONTEND_SRC).filter((f) => f.endsWith('.vue'))
    expect(files.length).toBeGreaterThan(1000) // 防空转：扫描范围失效时不能恒绿
    const hits = files.flatMap((f) => scanNested(toSrcRelative(f), readSource(f)))
    expect(hits).toEqual([])
  })

  it('扫描器自检：直接嵌套命中；外层包真实元素、没传批注、v-if 分开的不命中', () => {
    const tpl = (inner: string) => `<template><div>${inner}</div></template>`
    expect(scanNested('a.vue', tpl('<el-tooltip content="x"><GtAmountCell :value="v" :comment="c" /></el-tooltip>'))).toHaveLength(1)
    expect(scanNested('a.vue', tpl('<el-tooltip content="x"><CommentTooltip :comment="c"><span /></CommentTooltip></el-tooltip>'))).toHaveLength(1)
    expect(scanNested('a.vue', tpl('<el-popover><template #reference><ConsolNoteGridCell :comment="c" /></template></el-popover>'))).toHaveLength(1)
    expect(scanNested('a.vue', tpl('<el-tooltip content="x"><span><GtAmountCell :value="v" :comment="c" /></span></el-tooltip>'))).toEqual([])
    expect(scanNested('a.vue', tpl('<el-tooltip content="x"><GtAmountCell :value="v" /></el-tooltip>'))).toEqual([])
    expect(scanNested('a.vue', tpl('<el-tooltip v-if="a" content="x"><span /></el-tooltip><CommentTooltip v-else :comment="c"><span /></CommentTooltip>'))).toEqual([])
  })

  it('登记的组件模板根确实是 CommentTooltip（名单可伪证）', () => {
    for (const [name, rel] of Object.entries(COMMENT_ROOTED)) {
      const ast = parse(readSource(resolve(FRONTEND_SRC, rel)), { filename: rel }).descriptor.template?.ast as unknown as Node
      const roots = (ast.children ?? []).filter((c) => c.type === 1)
      expect(roots.map((r) => r.tag), name).toEqual(['CommentTooltip'])
    }
  })
})
