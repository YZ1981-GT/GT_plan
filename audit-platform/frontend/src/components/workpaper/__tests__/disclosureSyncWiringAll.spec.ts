/**
 * 全宿主披露同步接线守卫 —— 锁死 syncToDisclosureNotes 的两类已知缺陷
 *
 * 缺陷①：syncToDisclosureNotes 函数体内调用 useAuditContext()
 *   → useAuditContext 内部用 inject + onScopeDispose，必须 setup 顶层同步调用；
 *   写在 async 处理器里 inject 拿不到 route → TypeError → http.post 从未发出
 *   → last_sync_at 永远 NULL。2026-07-30 浏览器实测确认。
 *
 * 缺陷②：syncToDisclosureNotes 函数体内调用 scheduleAutoSync(syncToDisclosureNotes)
 *   → 调度自己 → 800ms 后重复 POST（自触发）→ 用户收到莫名"同步到附注失败"。
 *   自动同步只应由数据变更触发（增删行/从明细带入/AI 写入）。
 *
 * 宿主集合：动态扫描（现算），不写死清单 → 新增宿主自动纳入。
 * 双向变异：注入缺陷的样本必须被检出（扫描器非恒绿）。
 *
 * spec: disclosure-payload-authority-source Task 1.2 / Q3 Q4 Q5
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { resolve, relative, extname } from 'node:path'

// ── 递归收集宿主 ─────────────────────────────────────────────────────────

const WORKPAPER_ROOT = resolve(__dirname, '..')
const SRC_ROOT = resolve(WORKPAPER_ROOT, '..')

interface HostFile {
  /** 相对于 workpaper/ 的路径 */
  rel: string
  /** 文件全路径 */
  abs: string
  /** 去注释后的 <script setup> 内容（.vue）或整个 .ts 内容 */
  cleanBody: string
  /** syncToDisclosureNotes 函数体（去注释后） */
  syncFnBody: string | null
}

/** 去掉块注释与行注释（防注释中的示例文本被误判） */
function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 提取 <script setup> 体或整个 .ts 文件内容，去注释 */
function extractCleanBody(abs: string): string {
  const raw = readFileSync(abs, 'utf-8')
  if (abs.endsWith('.vue')) {
    const m = raw.match(/<script\s+setup[^>]*>([\s\S]*?)<\/script>/)
    return stripComments(m ? m[1] : '')
  }
  return stripComments(raw)
}

/** 花括号配平提取函数体 */
function extractFunctionBody(body: string, fnName: string): string | null {
  const pat = new RegExp(`(async\\s+)?function\\s+${fnName}\\s*\\(`)
  const m = pat.exec(body)
  if (!m) return null
  const openIdx = body.indexOf('{', m.index + m[0].length)
  if (openIdx < 0) return null
  let depth = 0
  for (let i = openIdx; i < body.length; i++) {
    if (body[i] === '{') depth++
    else if (body[i] === '}') {
      depth--
      if (depth === 0) return body.slice(openIdx, i + 1)
    }
  }
  return null
}

/** 递归收集所有含 syncToDisclosureNotes 定义的非测试文件 */
function collectHosts(): HostFile[] {
  const hosts: HostFile[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = resolve(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue
        walk(full)
      } else {
        const ext = extname(entry.name)
        if (ext !== '.ts' && ext !== '.vue') continue
        if (entry.name.includes('.spec.') || entry.name.includes('.test.')) continue
        const raw = readFileSync(full, 'utf-8')
        // 只要包含 syncToDisclosureNotes 函数定义
        if (!/function\s+syncToDisclosureNotes\b/.test(raw)) continue
        const cleanBody = extractCleanBody(full)
        const syncFnBody = extractFunctionBody(cleanBody, 'syncToDisclosureNotes')
        hosts.push({
          rel: relative(WORKPAPER_ROOT, full).replace(/\\/g, '/'),
          abs: full,
          cleanBody,
          syncFnBody,
        })
      }
    }
  }
  walk(WORKPAPER_ROOT)
  return hosts
}

const ALL_HOSTS = collectHosts()

// ══════════════════════════════════════════════════════════════════════════

describe('全宿主披露同步接线（动态扫描）', () => {
  // ── 基线自检 ──────────────────────────────────────────────────────────

  it('自检：宿主数现算 ≥ 100（编写时 112，防扫描器被架空）', () => {
    expect(
      ALL_HOSTS.length,
      `宿主数 ${ALL_HOSTS.length} < 100，可能扫描路径错误`,
    ).toBeGreaterThanOrEqual(100)
  })

  it('自检：所有宿主均能提取 syncToDisclosureNotes 函数体', () => {
    const noBody = ALL_HOSTS.filter((h) => h.syncFnBody === null).map((h) => h.rel)
    expect(
      noBody,
      `以下宿主无法提取函数体（可能是箭头函数或其他形态）：${noBody.join(', ')}`,
    ).toEqual([])
  })

  // ── 缺陷 ①：syncToDisclosureNotes 体内不得调 useAuditContext ────────

  it('缺陷①：全部宿主的 syncToDisclosureNotes 内无 useAuditContext 调用', () => {
    const hits = ALL_HOSTS.filter(
      (h) => h.syncFnBody && /\buseAuditContext\s*\(/.test(h.syncFnBody),
    ).map((h) => h.rel)
    expect(
      hits,
      `以下宿主在 syncToDisclosureNotes 内调 useAuditContext（inject 在 async 处理器里失效 → 同步是死的）：\n${hits.join('\n')}`,
    ).toEqual([])
  })

  // ── 缺陷 ②：syncToDisclosureNotes 体内不得自触发 ────────────────────

  it('缺陷②：全部宿主的 syncToDisclosureNotes 内无 scheduleAutoSync(自身)', () => {
    const hits = ALL_HOSTS.filter(
      (h) =>
        h.syncFnBody &&
        /scheduleAutoSync\s*\(\s*syncToDisclosureNotes\s*\)/.test(h.syncFnBody),
    ).map((h) => h.rel)
    expect(
      hits,
      `以下宿主在 syncToDisclosureNotes 内 scheduleAutoSync(syncToDisclosureNotes) = 自触发（800ms 后重复 POST）：\n${hits.join('\n')}`,
    ).toEqual([])
  })

  // ── 双向变异证明（扫描器非恒绿）──────────────────────────────────────

  describe('双向变异', () => {
    // 取第一个有函数体的宿主做变异基底
    const sampleHost = ALL_HOSTS.find((h) => h.syncFnBody !== null)

    it('正向：已正确的宿主不命中缺陷①', () => {
      expect(sampleHost).toBeTruthy()
      expect(/\buseAuditContext\s*\(/.test(sampleHost!.syncFnBody!)).toBe(false)
    })

    it('反向①：注入 useAuditContext 后必须命中', () => {
      expect(sampleHost).toBeTruthy()
      const mutated = '{ const ctx = useAuditContext()\n' + sampleHost!.syncFnBody!.slice(1)
      expect(/\buseAuditContext\s*\(/.test(mutated)).toBe(true)
    })

    it('正向：已正确的宿主不命中缺陷②', () => {
      expect(sampleHost).toBeTruthy()
      expect(
        /scheduleAutoSync\s*\(\s*syncToDisclosureNotes\s*\)/.test(sampleHost!.syncFnBody!),
      ).toBe(false)
    })

    it('反向②：注入自触发后必须命中', () => {
      expect(sampleHost).toBeTruthy()
      const mutated =
        '{ autoSync.scheduleAutoSync(syncToDisclosureNotes)\n' +
        sampleHost!.syncFnBody!.slice(1)
      expect(
        /scheduleAutoSync\s*\(\s*syncToDisclosureNotes\s*\)/.test(mutated),
      ).toBe(true)
    })
  })
})
