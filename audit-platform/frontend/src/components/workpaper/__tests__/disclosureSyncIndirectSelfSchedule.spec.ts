/**
 * 披露 Tab 同步函数不得经由别的函数调度自己（spec note-pull-followup-closure 复盘：间接自调度）。
 *
 * `disclosureAutoSyncCoverage.spec.ts` 已钉住「同步函数体内不得直接 `scheduleAutoSync(自己)`」，但漏了间接写法：
 *
 *   async function syncToNotes() { persistAll(); …POST… }
 *   function persistAll() { …save…; autoSync.scheduleAutoSync(syncToNotes) }
 *
 * 点一次「同步到附注」（或任何一次自动同步）之后，persistAll 又排下一次同步 ⇒ 每个防抖周期（800ms）再 POST 一次、再存一遍
 * 披露键，直到组件卸载（H2 实测 5 个周期 POST 1→6）。2026-10-28 扫出 G7 两版 / H1 上市 / H2 两版 / H6 共 6 处，已改为：
 * 同步前的保存走不排同步的保存函数，排同步只留在编辑触发的保存入口。
 *
 * 判据：同一文件里，同步函数（名为 sync…Note… / sync…Disclosure…）直接或经同文件函数间接调用到的函数体内，不得出现
 * `scheduleAutoSync(该同步函数)`。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ post: vi.fn(async () => ({ data: { rows_synced: 1 } })), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: h.post, put: h.put } }))
vi.mock('vue-router', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('vue-router')),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import H2TabDisclosureListed from '../h2/core/H2TabDisclosureListed.vue'
import H2TabDisclosureSoe from '../h2/core/H2TabDisclosureSoe.vue'

const WP_ROOT = resolve(__dirname, '..')

function walkVue(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue
      walkVue(p, out)
    } else if (entry.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const FUNC_RE = /\b(?:async\s+)?function\s+(\w+)\s*\(/g

/** 同文件具名函数 → 函数体（大括号配平；参数列表里的类型 / 默认值不影响定位） */
function functionBodies(src: string): Map<string, string> {
  const out = new Map<string, string>()
  const code = stripComments(src)
  let m: RegExpExecArray | null
  FUNC_RE.lastIndex = 0
  while ((m = FUNC_RE.exec(code))) {
    // 跳过参数列表（括号配平）再找函数体的左大括号
    let i = m.index + m[0].length
    let paren = 1
    while (i < code.length && paren) {
      if (code[i] === '(') paren += 1
      else if (code[i] === ')') paren -= 1
      i += 1
    }
    const open = code.indexOf('{', i)
    if (open < 0) continue
    let depth = 0
    for (let j = open; j < code.length; j += 1) {
      if (code[j] === '{') depth += 1
      else if (code[j] === '}') {
        depth -= 1
        if (depth === 0) {
          out.set(m[1], code.slice(open + 1, j))
          break
        }
      }
    }
  }
  return out
}

const SYNC_NAME = /^sync\w*(?:Note|Disclosure)\w*$/

/** 返回「同步函数 → 经哪个函数排了自己」的违规清单（传递调用，同文件内） */
function indirectSelfSchedules(src: string): Array<{ sync: string; via: string }> {
  const bodies = functionBodies(src)
  const found: Array<{ sync: string; via: string }> = []
  for (const [name, body] of bodies) {
    if (!SYNC_NAME.test(name)) continue
    const schedulesSelf = new RegExp(`scheduleAutoSync\\(\\s*${name}\\b`)
    const seen = new Set<string>([name])
    const queue = [...new Set([...body.matchAll(/\b(\w+)\s*\(/g)].map((x) => x[1]))]
    while (queue.length) {
      const callee = queue.shift() as string
      if (seen.has(callee) || !bodies.has(callee)) continue
      seen.add(callee)
      const calleeBody = bodies.get(callee) as string
      if (schedulesSelf.test(calleeBody)) {
        found.push({ sync: name, via: callee })
        break
      }
      for (const x of calleeBody.matchAll(/\b(\w+)\s*\(/g)) queue.push(x[1])
    }
  }
  return found
}

describe('披露 Tab 同步函数不得间接调度自己', () => {
  it('全部披露 Tab：同步前的保存不排同步（否则每 800ms 重复 POST，直到卸载）', () => {
    const offenders: string[] = []
    for (const p of walkVue(WP_ROOT)) {
      const src = readFileSync(p, 'utf8')
      if (!src.includes('scheduleAutoSync')) continue
      for (const { sync, via } of indirectSelfSchedules(src)) {
        offenders.push(`${p.slice(WP_ROOT.length + 1).replace(/\\/g, '/')}：${sync} → ${via} → scheduleAutoSync(${sync})`)
      }
    }
    expect(offenders).toEqual([])
  })

  it.each([
    ['listed', H2TabDisclosureListed, 'H2-listed-summary', { key: 'cip', endBalance: 5 }],
    ['soe', H2TabDisclosureSoe, 'H2-soe-summary', { key: 'cip', endBook: 5 }],
  ] as const)('行为：H2 %s 点一次「同步到附注」后 5 个防抖周期内不再自动重复同步（修复前 POST 1→6）', async (variant, Comp, key, row) => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const allResponses = new Map([[key, { item_id: key, conclusion: null, remark: JSON.stringify([row]) }]])
      const stubs = {
        'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
        'el-alert': true, 'el-tag': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-input-number': true,
        GtIndexChip: true, GtReviewTrigger: true, WpNoteTextArea: true, WpDisclosureConsistencyPanel: true, WpAmountInput: true,
      }
      const w = mount(Comp as any, { props: { wpId: 'w', projectId: 'p', allResponses, isReadonly: false }, global: { stubs } })
      await flushPromises()
      vi.advanceTimersByTime(5000)
      await flushPromises()
      h.post.mockClear()
      await w.find(`[data-testid="h2-disclosure-${variant}-sync"]`).trigger('click')
      await flushPromises()
      const counts: number[] = [h.post.mock.calls.length]
      for (let k = 0; k < 5; k += 1) {
        vi.advanceTimersByTime(800)
        await flushPromises()
        counts.push(h.post.mock.calls.length)
      }
      w.unmount()
      expect(counts[0]).toBeGreaterThan(0)
      expect(counts).toEqual(counts.map(() => counts[0]))
    } finally {
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('守卫自检：间接（含两层）自调度认得出，排同步只在编辑入口时不误报', () => {
    const bad = `
      async function syncToNotes() { persistAll(); await api.post('/x', {}) }
      function persistAll() { save(); autoSync.scheduleAutoSync(syncToNotes) }`
    expect(indirectSelfSchedules(bad)).toEqual([{ sync: 'syncToNotes', via: 'persistAll' }])
    const twoHops = `
      async function syncToDisclosureNotes(): Promise<void> { await persist() }
      async function persist(): Promise<void> { await write() }
      async function write(): Promise<void> { await api.put('/y'); autoSync.scheduleAutoSync(syncToDisclosureNotes) }`
    expect(indirectSelfSchedules(twoHops)).toEqual([{ sync: 'syncToDisclosureNotes', via: 'write' }])
    const good = `
      async function syncToNotes() { saveAll(); await api.post('/x', {}) }
      function saveAll() { save() }
      function persistAll() { saveAll(); autoSync.scheduleAutoSync(syncToNotes) }
      // function persistAll() { autoSync.scheduleAutoSync(syncToNotes) }`
    expect(indirectSelfSchedules(good)).toEqual([])
  })
})
