import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const FILE = resolve(process.cwd(), 'src/views/LedgerPenetration.vue')
const SOURCE = readFileSync(FILE, 'utf-8')
const script = SOURCE.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)?.[1] || ''
const sf = ts.createSourceFile(FILE, script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

function calls(name: string): ts.CallExpression[] {
  const out: ts.CallExpression[] = []
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === name) out.push(node)
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return out
}

function functionBody(name: string): ts.Node | undefined {
  let found: ts.Node | undefined
  const visit = (node: ts.Node) => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node.body
    if (!found) ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

function bodyCalls(body: ts.Node | undefined, name: string): boolean {
  let found = false
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === name) found = true
    if (!found) ts.forEachChild(node, visit)
  }
  if (body) visit(body)
  return found
}

function propertyCalls(object: string): string[] {
  const names: string[] = []
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
      && ts.isIdentifier(node.expression.expression) && node.expression.expression.text === object) {
      names.push(node.expression.name.text)
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return names
}

describe('LedgerPenetration 窗口化接线', () => {
  it('四个互动区域各有独立 useLedgerWindow 实例和分页器', () => {
    expect(calls('useLedgerWindow')).toHaveLength(4)
    expect((SOURCE.match(/<LedgerWindowPager\b/g) || [])).toHaveLength(4)
  })

  it('生产组件不再调用旧 entries/opening/auxEntries，也没有20万行循环标识', () => {
    const legacy = new Set(['entries', 'openingBalance', 'auxEntries'])
    expect(propertyCalls('P_ledger').filter((name) => legacy.has(name))).toEqual([])
    const identifiers = new Set<string>()
    const visit = (node: ts.Node) => {
      if (ts.isIdentifier(node)) identifiers.add(node.text)
      ts.forEachChild(node, visit)
    }
    visit(sf)
    expect(identifiers.has('MAX_PAGES')).toBe(false)
    expect(identifiers.has('fetchAllLedgerEntries')).toBe(false)
    expect(identifiers.has('fetchAllLedgerEntriesForTab')).toBe(false)
  })

  it('四个原加载入口都调用窗口状态机', () => {
    for (const [fn, state] of [
      ['loadLedger', 'mainLedgerWindow'],
      ['loadTabLedger', 'tabLedgerWindow'],
      ['loadTabAuxLedger', 'tabAuxWindow'],
      ['loadAuxLedger', 'auxDrillWindow'],
    ]) {
      const body = functionBody(fn)
      expect(body, `缺函数 ${fn}`).toBeTruthy()
      expect(body?.getText(sf), fn).toContain(`${state}.loadFirst`)
    }
  })

  it('普通/顶部/辅助三类导出都走服务端完整导出', () => {
    for (const fn of ['exportLedgerExcel', 'exportTabLedgerExcel', 'exportTabAuxLedgerExcel', 'exportAuxLedgerExcel']) {
      expect(bodyCalls(functionBody(fn), 'exportWindowQuery'), fn).toBe(true)
    }
    expect(bodyCalls(functionBody('exportWindowQuery'), 'downloadLedgerWindow')).toBe(true)
  })

  it('序时账 / 辅助 Tab 默认展示全部（科目通配 *），未限定时不显示余额列', () => {
    // 序时账：不选科目也要发请求，accountCode 回落到 ALL_ACCOUNTS
    const ledgerQuery = functionBody('tabLedgerQuery')?.getText(sf) || ''
    expect(ledgerQuery).toContain('ALL_ACCOUNTS')
    expect(ledgerQuery).not.toContain('!tabLedgerAccount.value) return null')
    // 辅助明细：科目 / 类型都可省略，类型缺省传 null；浏览模式的余额由 onlyBusinessRows 隐去
    const auxQuery = functionBody('tabAuxQuery')?.getText(sf) || ''
    expect(auxQuery).toContain('ALL_ACCOUNTS')
    expect(auxQuery).not.toContain('!tabAuxType.value) return null')
    expect(SOURCE).toContain('onlyBusinessRows(')
  })

  it('辅助明细行（带 aux_type）凭证字为空时不按空串去查凭证，交给后端按号+日期定位', () => {
    const body = functionBody('rowVoucherType')?.getText(sf) || ''
    expect(body).toContain("'aux_type' in row")
    expect(body).toContain('return null')
  })
})
