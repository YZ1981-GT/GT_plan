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
// 注：原此处还有一个未被任何代码消费的 `SRC_ROOT = resolve(WORKPAPER_ROOT, '..')`，
// 取值是 components/ 而非 src/（名不副实）。已删除，真正的 src 根见下方 SRC_ROOT。

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

// ── 扫描域自身的完整性（2026-09-28 补，spec §十四）─────────────────────
//
// collectHosts() 有两条收窄：① 只走 WORKPAPER_ROOT 子树 ② 只认 `function` 形态。
// 两条都是静默脱管口 —— 新宿主若落在 components/workpaper/ 外，或写成
// `const syncToDisclosureNotes = async () => {}`，上面三条不变量会**全部通过**
// 而那个宿主根本没被看过。故把两条收窄各配一条反向断言钉住。

const SRC_ROOT = resolve(WORKPAPER_ROOT, '..', '..')

interface RawDefinition {
  rel: string
  form: 'function' | 'const'
  insideScanRoot: boolean
}

/** 全 src 扫描 syncToDisclosureNotes 的**任意**定义形态（排除测试文件） */
function collectAllDefinitions(): RawDefinition[] {
  const found: RawDefinition[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = resolve(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue
        walk(full)
        continue
      }
      const ext = extname(entry.name)
      if (ext !== '.ts' && ext !== '.vue') continue
      if (entry.name.includes('.spec.') || entry.name.includes('.test.')) continue
      const raw = readFileSync(full, 'utf-8')
      const hasFn = /function\s+syncToDisclosureNotes\b/.test(raw)
      const hasConst = /const\s+syncToDisclosureNotes\b/.test(raw)
      if (!hasFn && !hasConst) continue
      found.push({
        rel: relative(SRC_ROOT, full).replace(/\\/g, '/'),
        form: hasFn ? 'function' : 'const',
        insideScanRoot: full.startsWith(WORKPAPER_ROOT),
      })
    }
  }
  walk(SRC_ROOT)
  return found
}

const ALL_DEFINITIONS = collectAllDefinitions()

// ══════════════════════════════════════════════════════════════════════════

describe('全宿主披露同步接线（动态扫描）', () => {
  // ── 基线自检 ──────────────────────────────────────────────────────────

  it('自检：宿主数现算 ≥ 100（编写时 112，防扫描器被架空）', () => {
    expect(
      ALL_HOSTS.length,
      `宿主数 ${ALL_HOSTS.length} < 100，可能扫描路径错误`,
    ).toBeGreaterThanOrEqual(100)
  })

  // ── 扫描域完整性：两条收窄各配反向断言 ─────────────────────────────

  it('扫描域①：不存在落在 components/workpaper/ 外的生产宿主', () => {
    const outside = ALL_DEFINITIONS.filter((d) => !d.insideScanRoot).map((d) => d.rel)
    expect(
      outside,
      `以下文件定义了 syncToDisclosureNotes 但在本守卫扫描域（components/workpaper/）之外，` +
        `⇒ 上面的缺陷①②不变量对它们完全不生效（静默脱管）：\n${outside.join('\n')}\n` +
        `处置：要么把宿主移进 components/workpaper/，要么扩大本守卫的 WORKPAPER_ROOT。`,
    ).toEqual([])
  })

  it('扫描域②：不存在 const/箭头形态的 syncToDisclosureNotes 定义', () => {
    // collectHosts() 的收集条件是 /function\s+syncToDisclosureNotes\b/，
    // 写成 `const syncToDisclosureNotes = async () => {}` 会被整条跳过。
    const constForm = ALL_DEFINITIONS.filter((d) => d.form === 'const').map((d) => d.rel)
    expect(
      constForm,
      `以下宿主把 syncToDisclosureNotes 写成 const/箭头形态，本守卫的收集正则只认 ` +
        `function 形态 ⇒ 这些宿主不在任何不变量的视野内：\n${constForm.join('\n')}\n` +
        `处置：改回 function 声明（与既有 112 个宿主一致），或扩展 collectHosts 的正则与 ` +
        `extractFunctionBody 的花括号配平起点。`,
    ).toEqual([])
  })

  it('扫描域③：两个扫描器对「function 形态生产宿主」的口径一致', () => {
    // 防「改了一个扫描器忘了另一个」——两套收集逻辑必须数出同一个集合。
    const viaDefinitions = ALL_DEFINITIONS.filter(
      (d) => d.insideScanRoot && d.form === 'function',
    ).length
    expect(viaDefinitions, '两个扫描器口径漂移，其中一个已失效').toBe(ALL_HOSTS.length)
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

    // ── 扫描域完整性判据的变异（证明「现算为 0」不是恒绿）────────────

    it('反向③：域外宿主样本必须被判为 insideScanRoot=false', () => {
      // 模拟一个落在 src/composables/ 的宿主路径，不建真文件
      const fakeOutside = resolve(SRC_ROOT, 'composables', 'useFakeDisclosureHost.ts')
      expect(fakeOutside.startsWith(WORKPAPER_ROOT)).toBe(false)
      // 反证：真实宿主必须被判为域内
      expect(
        resolve(WORKPAPER_ROOT, 'e1', 'E1TabDisclosure.vue').startsWith(WORKPAPER_ROOT),
      ).toBe(true)
    })

    it('反向④：const/箭头形态样本必须被 form 判别器识别为 const', () => {
      const constSample = 'const syncToDisclosureNotes = async () => {\n  await post()\n}\n'
      const fnSample = 'async function syncToDisclosureNotes() {\n  await post()\n}\n'
      const hasFn = (s: string) => /function\s+syncToDisclosureNotes\b/.test(s)
      const hasConst = (s: string) => /const\s+syncToDisclosureNotes\b/.test(s)
      expect(hasFn(constSample), 'const 形态不应被 function 正则命中').toBe(false)
      expect(hasConst(constSample)).toBe(true)
      expect(hasFn(fnSample)).toBe(true)
      // 🔴 关键：const 形态在 collectHosts 的收集条件下会被**整条跳过**
      expect(hasFn(constSample)).toBe(false)
      // 且 extractFunctionBody 对 const 形态取不到函数体 ⇒ 不变量无从施加
      expect(extractFunctionBody(constSample, 'syncToDisclosureNotes')).toBeNull()
      expect(extractFunctionBody(fnSample, 'syncToDisclosureNotes')).not.toBeNull()
    })
  })
})
