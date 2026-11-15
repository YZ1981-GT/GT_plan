/**
 * 试算表导出路径守卫（spec platform-global-display-settings-closure 任务 10 / AC-20）
 *
 * 🔴 背景：`useTbSummary.ts` 里曾有两个方法调**后端从未实现**的端点
 * （试算表汇总导出与它的模板导出）。该文件整个**从未被调用**
 * （`TrialBalance.vue` 有自己的 `loadTbSummary` / `exportTbSummary`，
 * 导出走纯前端 `exportMultiSheetData` 不经后端）⇒ 已于 2026-11-16 删除。
 *
 * 本守卫钉三件事：
 * 1. 那两个不存在的路径**不得**再作为**代码**出现（防有人从 git 历史抄回来）；
 * 2. 试算表真实导出路径 `/trial-balance/export`（后端已建）必须被前端调用；
 * 3. 导出必须走 `exportMultiSheetData`（纯前端生成）而不是「假设后端有文件」。
 *
 * 🔴 扫描口径：只扫**代码行**（剔除 `//`、`*`、`/*` 开头的注释行）。
 * 否则本文件自己的说明文字与源码里「说明这个路径不存在」的注释都会被判成违规
 * —— 这正是「注释未剔除致误报」（memory ⑰/T7 反向形态）的现场。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(HERE, '../../..')
const TRIAL_BALANCE = readFileSync(resolve(SRC, 'views/TrialBalance.vue'), 'utf-8')

/** 剔除注释行（`//` / `*` / `/*` 开头的行，以及行内 `//` 之后的部分）。 */
function stripComments(text: string): string {
  return text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) {
        return ''
      }
      const idx = line.indexOf('//')
      return idx >= 0 ? line.slice(0, idx) : line
    })
    .join('\n')
}

/** 递归收集 src 下所有非测试的 .ts / .vue 源码（只保留代码行）。 */
function collectSources(dir: string): Array<{ path: string; code: string }> {
  const out: Array<{ path: string; code: string }> = []
  const walk = (d: string) => {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const p = resolve(d, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '__tests__') continue
        walk(p)
      } else if (/\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith('.spec.ts')) {
        out.push({ path: p, code: stripComments(readFileSync(p, 'utf-8')) })
      }
    }
  }
  walk(dir)
  return out
}

const SOURCES = collectSources(SRC)

function offendersOf(needle: string): string[] {
  return SOURCES.filter((s) => s.code.includes(needle)).map((s) => s.path)
}

describe('试算表导出：已删除的死代码路径不得复活', () => {
  it('useTbSummary.ts 文件已删除', () => {
    expect(existsSync(resolve(SRC, 'views/composables/useTbSummary.ts'))).toBe(false)
  })

  it('代码里不再有试算表汇总导出端点', () => {
    expect(offendersOf('/trial-balance/summary/export')).toEqual([])
  })

  it('代码里不再有试算表汇总导出模板端点', () => {
    expect(offendersOf('/trial-balance/summary/export-template')).toEqual([])
  })

  it('代码里不再有试算表批量导出端点（后端注册表已标 retired）', () => {
    expect(offendersOf('/trial-balance/bulk-export')).toEqual([])
  })

  it('扫描器本身有非空分母（防空扫描恒绿）', () => {
    // 若 collectSources 因路径写错返回空数组，上面所有 toEqual([]) 都会恒绿。
    expect(SOURCES.length).toBeGreaterThan(200)
  })

  it('扫描器真的会命中（阳性对照：已知存在的真实路径）', () => {
    // 用一条确定存在的路径反证扫描器不是恒空。
    expect(offendersOf('/trial-balance/export').length).toBeGreaterThan(0)
  })
})

describe('试算表导出：真实路径必须被调用', () => {
  it('apiPaths 里的 trialBalance.export 指向真实存在的 /trial-balance/export', () => {
    const accounting = SOURCES.find((s) =>
      s.path.replace(/\\/g, '/').endsWith('services/apiPaths/accounting.ts'),
    )
    expect(accounting, 'accounting.ts 未找到').toBeDefined()
    expect(accounting!.code).toContain('/trial-balance/export')
    expect(accounting!.code).not.toContain('/trial-balance/summary/export')
  })

  it('TrialBalance.vue 的导出走 exportMultiSheetData（纯前端生成，不假设后端有文件）', () => {
    expect(TRIAL_BALANCE).toContain('exportMultiSheetData')
  })

  it('TrialBalance.vue 的 exportTbSummary 函数体不请求后端汇总导出', () => {
    const start = TRIAL_BALANCE.indexOf('async function exportTbSummary()')
    expect(start, 'exportTbSummary 未找到').toBeGreaterThan(-1)
    const body = stripComments(TRIAL_BALANCE.slice(start, start + 1200))
    expect(body).not.toContain('/trial-balance/summary/export')
  })

  it('TrialBalance.vue 不再 import 已删除的 useTbSummary', () => {
    expect(TRIAL_BALANCE).not.toContain("from '@/views/composables/useTbSummary'")
  })
})
