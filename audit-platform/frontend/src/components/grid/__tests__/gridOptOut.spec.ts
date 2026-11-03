/**
 * spec excel-style-table-editing R2.4：表格声明不启用表格交互（`data-gt-grid="off"`）必须登记理由。
 * 现算 0 处；新增一处就在 REGISTERED 里写「文件 → 理由」，删掉一处就删登记（两边逐条相等）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

/** 文件（相对 src，/ 分隔）→ 不启用的理由 */
const REGISTERED: Record<string, string> = {}

const OPT_OUT_RE = /data-gt-grid\s*(?:=\s*["']off["']|["']\s*:\s*["']off["'])/

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '__tests__') continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(vue|ts|tsx)$/.test(name) && !/\.(spec|test)\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

describe('表格交互退出开关登记', () => {
  it('识别三种写法（模板属性、渲染函数属性对象）', () => {
    expect(OPT_OUT_RE.test('<el-table data-gt-grid="off">')).toBe(true)
    expect(OPT_OUT_RE.test("<table data-gt-grid='off'>")).toBe(true)
    expect(OPT_OUT_RE.test("h(ElTable, { 'data-gt-grid': 'off' })")).toBe(true)
    expect(OPT_OUT_RE.test('<el-table data-gt-grid="on">')).toBe(false)
  })

  it('源码里的每一处都已登记理由，登记表里没有失效条目', () => {
    const found = walk(SRC)
      .filter((f) => !f.includes(`${sep}components${sep}grid${sep}`))
      .filter((f) => OPT_OUT_RE.test(readFileSync(f, 'utf-8')))
      .map((f) => relative(SRC, f).split(sep).join('/'))
      .sort()
    expect(found).toEqual(Object.keys(REGISTERED).sort())
    for (const [file, reason] of Object.entries(REGISTERED)) expect(reason.trim().length, file).toBeGreaterThan(4)
  })
})
