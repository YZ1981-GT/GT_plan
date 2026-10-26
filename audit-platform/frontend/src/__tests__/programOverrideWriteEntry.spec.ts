/**
 * 程序表字段覆盖（`procedure_table:*`）只能经两个入口写 —— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 *
 * 写读必须同一个 (scope, 年度)。scope / 年度的取法收在 `useProgramOverrideTarget`（控制台 / A1 / A2 / A3）与
 * `programStepOverrides`（循环底稿回填程序表）里；组件自己拼 `procedure_table:${sheetName}`、拿路由年度 / 今年写，
 * 正是「执行人改的状态刷新后看不到」的原因。任何别的源码文件出现 `procedure_table:` 字面量 ⇒ 红。
 * 注释行不计（与年度棘轮同一口径）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const SOURCE_EXT = /\.(?:ts|tsx|vue|js|mjs|cjs)$/
const TEST_FILE = /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/
const ALLOWED = [
  'composables/useProgramOverrideTarget.ts',
  'components/workpaper/composables/programStepOverrides.ts',
]

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (SOURCE_EXT.test(name) && !TEST_FILE.test(name)) out.push(full)
  }
  return out
}

function writers(): string[] {
  const hits: string[] = []
  for (const file of walk(SRC)) {
    const code = readFileSync(file, 'utf8').split('\n').filter(l => !COMMENT_LINE.test(l))
    if (code.some(l => l.includes('procedure_table:'))) hits.push(relative(SRC, file).replace(/\\/g, '/'))
  }
  return hits.sort()
}

describe('程序表字段覆盖写入入口', () => {
  it('只有两个收口模块出现 procedure_table: 字面量', () => {
    expect(writers()).toEqual([...ALLOWED].sort())
  })
})
