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

  it('辅助 Tab 在选类型前不加载，避免跨维度重复累计', () => {
    const body = functionBody('tabAuxQuery')?.getText(sf) || ''
    expect(body).toContain('!tabAuxType.value')
    expect(SOURCE).toContain('请继续选择一个辅助类型，避免跨维度重复累计')
  })
})
