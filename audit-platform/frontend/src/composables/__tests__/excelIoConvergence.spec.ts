/**
 * 前端 Excel 调用单一入口守卫 —— Wave 1 Task 1
 * spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 1.1 / 1.2 / 1.4 / 1.6 / 5.1 / 6.6 · Property 1 / 2 / 4 / 25 / 37)
 *
 * ## 🔴 为什么需要这条守卫
 *
 * `xlsx@0.18.5` 是 SheetJS 在 npm 上的最后一版（SheetJS 已撤出 npm 改 CDN 分发），
 * 带 CVE-2023-30533（prototype pollution，上游 0.19.3 修复）与 CVE-2024-22363
 * （ReDoS，上游 0.20.2 修复），**这两个修复版永远不会进 npm**。
 *
 * 项目有 25 处 `read(buf, { type: 'array' })` 在读用户上传的 xlsx，散落 25 个文件，
 * 每处都是独立攻击面。收敛到 `useExcelIO` 单一入口后防护只需做一次 —— 但**收敛是
 * 一次性的，回退却是渐进的**：下次要导个 Excel 时最省事的写法就是再 `import('xlsx')`，
 * 于是慢慢退回 46 个散点。故这条守卫钉死「除单一入口外零裸 import」。
 *
 * ## 判据设计要点（踩过的坑）
 *
 * 1. **必须先剥注释**。`components/formula/exportFormulaTemplate.ts` 写的是
 *    `await import(/* ＠vite-ignore *\/ 'exceljs')` —— 注释夹在 `import(` 与字符串
 *    之间，`import\(\s*['"]` 的 `\s*` 匹配不到。立项第一轮扫描没剥注释，把 exceljs
 *    记成 3 个文件而真实是 4 个。同一原因让 `useExcelIO.ts` 自身被多算一处
 *    （它的文件头注释里写着「其余 18 处 `import('xlsx')` 调用不动」这句说明）。
 *
 * 2. **`import()` 与 `from` 两形态都要算**。项目里动态 `import('xlsx')` 占压倒多数，
 *    只扫 `from` 会漏掉绝大部分。
 *
 * 3. **豁免按路径不按符号名**。memory 铁律：符号级匹配只产生假阴性，且曾有 spec 因
 *    按符号名判定导致「只加一个 spec 文件的 import 就让基线缩短」的假绿。
 *
 * 4. **红消息必须可操作**（R1.6）。裸断言 `expect(n).toBe(0)` 只告诉你「有 46 个」，
 *    不告诉你是哪些文件、该改成什么。本守卫的红消息带文件路径与替代指引。
 *
 * ## 兜底扫描结论（防更奇特的漏网写法）
 *
 * 宽口径搜「提到三个库名但主正则未命中」的文件得 11 个，逐个核对**全是误报** ——
 * 均为把 `'xlsx'` 当文件扩展名用（`accept=".xlsx"`、后缀判断、图标映射）。
 * `require('xlsx')` 形态 0 命中。故主正则口径完备，无变量式/拼接式动态导入。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ═══════════════════════════════════════════════════════════════════════════
// 仓库根 —— 双哨兵具体文件向上查找（禁写死回退级数，memory 已记照抄必 ENOENT）
// ═══════════════════════════════════════════════════════════════════════════

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const s1 = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const s2 = path.join(dir, 'audit-platform', 'frontend', 'src', 'composables', 'useExcelIO.ts')
    if (fs.existsSync(s1) && fs.existsSync(s2)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未找到仓库根（双哨兵均未命中）—— 守卫必须打红而不是静默跳过')
}

const REPO_ROOT = findRepoRoot()
const FE_SRC = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
const BASELINE_PATH = path.join(FE_SRC, 'composables', '__tests__', '_baseline', 'excelIoConvergence.baseline.json')
const PKG_PATH = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'package.json')

/** 单一入口的相对路径（唯一允许 import 真实 Excel 库的生产文件） */
const ENTRY_REL = 'composables/useExcelIO.ts'

const EXCEL_LIBS = ['xlsx', 'xlsx-js-style', 'exceljs'] as const

/**
 * 主正则：`from 'xlsx'` 与 `import('xlsx')` 两形态。
 * 注意使用前必须先 stripComments()，否则会漏掉 `import(/* c *\/ 'exceljs')`。
 */
const BARE_IMPORT_RE = /(?:from|import\()\s*['"](xlsx|xlsx-js-style|exceljs)['"]/g

// ═══════════════════════════════════════════════════════════════════════════
// 工具
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 剥块注释与行注释。
 *
 * `[^:]` 前置是为了不把 `https://` 里的 `//` 当行注释（沿用 formulaPaths.spec.ts 的做法）。
 */
export function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function walk(dir: string, exts: string[]): string[] {
  const acc: string[] = []
  if (!fs.existsSync(dir)) return acc
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const st = fs.statSync(full)
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === 'dist' || name === '__pycache__') continue
      acc.push(...walk(full, exts))
    } else if (exts.some((e) => name.endsWith(e))) {
      acc.push(full)
    }
  }
  return acc
}

interface Baseline {
  bare_import_files: { initial: number; current: number; target: number }
  bare_import_calls: { initial: number; current: number; target: number }
  by_lib_files: Record<string, number>
  exempt: Array<{ path: string; reason: string; evidence: string }>
  _exempt_max: number
  _progress: Array<{ batch: string; files?: string[]; note?: string }>
  _files_deleted_not_migrated: string[]
}

function loadBaseline(): Baseline {
  expect(fs.existsSync(BASELINE_PATH), `基线文件缺失: ${BASELINE_PATH}`).toBe(true)
  return JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf-8')) as Baseline
}

const baseline = loadBaseline()
const exemptPaths = new Set(baseline.exempt.map((e) => e.path))

/** 是否为豁免文件（按路径判定，R1.2） */
function isExempt(rel: string): boolean {
  if (rel === ENTRY_REL) return true
  if (rel.includes('__tests__/')) return true
  if (rel.endsWith('.spec.ts') || rel.endsWith('.test.ts')) return true
  if (exemptPaths.has(rel)) return true
  return false
}

interface Hit {
  rel: string
  calls: number
  libs: string[]
}

/** 扫描全部生产文件，返回裸 import 命中 */
function scanBareImports(): { hits: Hit[]; totalCalls: number; byLibFiles: Record<string, number> } {
  const hits: Hit[] = []
  const byLibFiles: Record<string, number> = {}
  let totalCalls = 0

  for (const full of walk(FE_SRC, ['.vue', '.ts'])) {
    const rel = path.relative(FE_SRC, full).replace(/\\/g, '/')
    if (isExempt(rel)) continue
    const src = stripComments(fs.readFileSync(full, 'utf-8'))
    const libs = [...src.matchAll(BARE_IMPORT_RE)].map((m) => m[1])
    if (libs.length === 0) continue
    hits.push({ rel, calls: libs.length, libs: [...new Set(libs)].sort() })
    totalCalls += libs.length
    for (const lib of new Set(libs)) {
      byLibFiles[lib] = (byLibFiles[lib] || 0) + 1
    }
  }

  hits.sort((a, b) => b.calls - a.calls || a.rel.localeCompare(b.rel))
  return { hits, totalCalls, byLibFiles }
}

/**
 * 构造可操作的红消息（R1.6 / Property 37）。
 *
 * 必须含：违规文件路径 + 用了哪个库 + 替代指引。裸断言失败不满足 R1.6。
 */
function buildActionableMessage(hits: Hit[]): string {
  const lines = [
    `发现 ${hits.length} 个生产文件直接 import Excel 库（应统一走 composables/useExcelIO.ts）。`,
    '',
    '原因：xlsx@0.18.5 是 npm 上最后一版且带两个永不会修的 CVE（SheetJS 已撤出 npm），',
    '     每个直连点都是独立攻击面；收敛到单一入口后防护只需做一次。',
    '',
    '请改用（按用途选一）：',
    "  读文件      → import { parseFile } from '@/composables/useExcelIO'",
    "  导出模板    → import { exportTemplate } from '@/composables/useExcelIO'",
    "  导出数据    → import { exportData } from '@/composables/useExcelIO'",
    '  多 sheet    → exportMultiSheetData',
    '  要字节不下载 → exportToBytes',
    '',
    '⚠ 迁移须保持行为等价：原本无样式的产物请传 applyStyles:false，',
    '  原本只有表头行的请传 includeNoteRow:false，原本不弹提示的请传 successMessage:false。',
    '',
    '违规文件：',
    ...hits.map((h) => `  ${h.rel}  (${h.calls} 处, ${h.libs.join('/')})`),
    '',
    '确实无法收敛的，登记进 _baseline/excelIoConvergence.baseline.json 的 exempt[]（须含 reason + evidence）。',
  ]
  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════════════════
// 类 A：独立口径守卫 —— 与迁移进度无关，应恒绿
// ═══════════════════════════════════════════════════════════════════════════

describe('excelIo 收敛 · 类 A 独立口径（应恒绿）', () => {
  it('stripComments 剥掉注释里的 import 但保留真 import（反向自检，Property 25）', () => {
    const sample = [
      "import a from 'xlsx'",
      "// import b from 'exceljs'",
      "/* import c from 'xlsx-js-style' */",
      '/*',
      " * 说明文字里提到 import('xlsx') 也不该被算成真 import",
      ' */',
    ].join('\n')

    const after = stripComments(sample)
    const n = [...after.matchAll(BARE_IMPORT_RE)].length
    expect(
      n,
      `含 1 处真 import + 3 处注释内提及的样本，剥离后应只剩 1 处，实得 ${n}。` +
        '若 >1 说明 stripComments 没剥干净（会把注释里的说明数成真引用）；' +
        '若 =0 说明剥过头把真 import 也剥了。',
    ).toBe(1)
  })

  it('stripComments 不把 https:// 误当行注释（反向自检）', () => {
    const sample = ["const u = 'https://example.com/a'", "import x from 'xlsx'"].join('\n')
    const n = [...stripComments(sample).matchAll(BARE_IMPORT_RE)].length
    expect(n, 'https:// 的双斜杠被误判成行注释会导致其后整行被吞，进而漏掉真 import').toBe(1)
  })

  it('主正则能命中「注释夹在 import( 与字符串之间」的形态（真实漏网案例）', () => {
    // components/formula/exportFormulaTemplate.ts 的真实写法
    const sample = "const ExcelJS = await import(/* @vite-ignore */ 'exceljs')"
    const before = [...sample.matchAll(BARE_IMPORT_RE)].length
    const after = [...stripComments(sample).matchAll(BARE_IMPORT_RE)].length
    expect(before, '不剥注释时该形态匹配不到 —— 这正是第一轮扫描漏掉该文件的原因').toBe(0)
    expect(after, '剥注释后必须命中，否则守卫会漏掉这个真实存在的文件').toBe(1)
  })

  it('单一入口文件存在且确实 import 了真实库（否则收敛目标不成立）', () => {
    const entryFull = path.join(FE_SRC, ENTRY_REL)
    expect(fs.existsSync(entryFull), `单一入口缺失: ${ENTRY_REL}`).toBe(true)
    const src = stripComments(fs.readFileSync(entryFull, 'utf-8'))
    const libs = [...src.matchAll(BARE_IMPORT_RE)].map((m) => m[1])
    expect(
      libs.length,
      '单一入口自己都不 import 真实库，说明它不是真正的入口（可能已被改成 re-export 壳）',
    ).toBeGreaterThan(0)
  })

  it('三个库仍在 package.json（Property 5，防「看起来没人用了」而误删）', () => {
    const pkg = JSON.parse(fs.readFileSync(PKG_PATH, 'utf-8')) as {
      dependencies?: Record<string, string>
    }
    const deps = pkg.dependencies || {}
    for (const lib of EXCEL_LIBS) {
      expect(
        deps[lib],
        `${lib} 不在 dependencies。收敛后调用方看不到它了，但 useExcelIO 内部仍在用 —— 删掉会直接让导入导出全线崩。`,
      ).toBeDefined()
    }
  })

  it('豁免清单条目结构完整且不超上限（Property 4）', () => {
    expect(baseline.exempt.length, `豁免条目数 ${baseline.exempt.length} 超过上限 ${baseline._exempt_max}`).toBeLessThanOrEqual(
      baseline._exempt_max,
    )
    for (const e of baseline.exempt) {
      expect(e.path, '豁免条目缺 path').toBeTruthy()
      expect(e.reason && e.reason.trim().length > 0, `豁免条目 ${e.path} 的 reason 为空`).toBe(true)
      expect(e.evidence && e.evidence.trim().length > 0, `豁免条目 ${e.path} 的 evidence 为空`).toBe(true)
    }
  })

  it('豁免清单 stale 检测：已无裸 import 的文件必须移出（Property 30 / R5.6）', () => {
    const stale: string[] = []
    for (const e of baseline.exempt) {
      const full = path.join(FE_SRC, e.path)
      if (!fs.existsSync(full)) {
        stale.push(`${e.path}（文件已不存在）`)
        continue
      }
      const src = stripComments(fs.readFileSync(full, 'utf-8'))
      if ([...src.matchAll(BARE_IMPORT_RE)].length === 0) {
        stale.push(`${e.path}（已无裸 import）`)
      }
    }
    expect(
      stale,
      `以下豁免条目已失效，请从 exempt[] 移出（留着会让基线虚高、掩盖真实回退）：\n  ${stale.join('\n  ')}`,
    ).toEqual([])
  })

  it('基线自身口径自洽（initial ≥ current ≥ target）', () => {
    const f = baseline.bare_import_files
    const c = baseline.bare_import_calls
    expect(f.initial, 'files.initial 应 ≥ current').toBeGreaterThanOrEqual(f.current)
    expect(f.current, 'files.current 应 ≥ target').toBeGreaterThanOrEqual(f.target)
    expect(c.initial, 'calls.initial 应 ≥ current').toBeGreaterThanOrEqual(c.current)
    expect(c.current, 'calls.current 应 ≥ target').toBeGreaterThanOrEqual(c.target)
    expect(f.target, '收敛目标必须是 0').toBe(0)
    expect(c.target, '收敛目标必须是 0').toBe(0)
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 🔴 `_progress[].files` 的完整性 —— 补于 2026-08-14，起因是一次真实漏记
  //
  // `B2-14/14` 那批 13 个 confirmation 文件当时只写在 `note` 的自然语言里
  // （"其余 13 个：GtConfirmationSummary · alternativeD06/F05/…"），`files` 是空数组。
  // 提交前用「HEAD 反查裸 import」核对才发现，后果连锁三处：
  //   ① 按 files 精确 stage 的脚本漏掉它们 ⇒ 远端仍带裸 import，CI 零裸 import 守卫必红
  //   ② CI 的 Vite 编译扫描 `--from-baseline` 只覆盖 33/46
  //   ③「46 → 0」的成果在权威清单里只体现 33
  //
  // 教训：**写在 note 里等于没写** —— 机器读不到的记录不是单一真源。故把判据落到
  // `files` 数组本身，并且不止验数量（数量相等可能是巧合：实测曾出现「基线 46 / HEAD 46
  // 但各差一个元素」），还要验每个声明项**真的已经迁完**。
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * `_progress[].files` 并集，**排除单一入口自己**。
   *
   * 入口 `useExcelIO.ts` 会出现在「横切修复」那批的 files 里（那批确实改了它 ——
   * 修 `applyExcelStyleTemplate` 写非法 OOXML 枚举值 `vertical:'middle'` 的缺陷），
   * 但它是迁移的**目的地**而非待迁散点，既不该计入「迁移了 N 个文件」，也不该被
   * 「当前无裸 import」这条判据检查（它是唯一允许持有裸 import 的文件）。
   *
   * ⇒ 数量关系：`并集(不含入口) 45 + 已删 1 == initial 46`。
   */
  function progressFileUnion(): { union: Set<string>; dupes: string[] } {
    const union = new Set<string>()
    const dupes: string[] = []
    for (const entry of baseline._progress || []) {
      for (const f of entry.files || []) {
        if (f === ENTRY_REL) continue
        if (union.has(f)) dupes.push(`${f}（重复出现于 ${entry.batch}）`)
        union.add(f)
      }
    }
    return { union, dupes }
  }

  it('_progress[].files 覆盖完整：并集 + 已删文件 == initial（Property 38 / R6.7）', () => {
    const { union, dupes } = progressFileUnion()

    expect(dupes, `_progress[].files 有重复项，会让「迁移了 N 个文件」虚高：\n  ${dupes.join('\n  ')}`).toEqual([])

    const deleted = baseline._files_deleted_not_migrated || []
    const accounted = union.size + deleted.length
    expect(
      accounted,
      `已留痕 ${accounted} 个（_progress[].files 并集 ${union.size} + 已删 ${deleted.length}），` +
        `但 bare_import_files.initial 记 ${baseline.bare_import_files.initial}。\n` +
        '两者必须相等 —— 立项清点出的每个待处置文件都应在某一批的 files 里、或在已删清单里留痕。\n' +
        `差 ${Math.abs(accounted - baseline.bare_import_files.initial)} 个的常见原因：\n` +
        '  · 某批只把文件名写进了 note 的文字描述，files 数组忘了填（2026-08-14 真实发生过，B2 漏 13 个）\n' +
        '  · 处置为「删除」的文件既没进 files 也没进 _files_deleted_not_migrated\n' +
        `当前已删清单（${deleted.length} 项）：${deleted.join(', ') || '（空）'}`,
    ).toBe(baseline.bare_import_files.initial)

    // 已删文件不得同时出现在 files 里（否则删除被算成迁移成果）
    const both = deleted.filter((f) => union.has(f))
    expect(both, `以下文件既在 _files_deleted_not_migrated 又在 _progress[].files：\n  ${both.join('\n  ')}`).toEqual([])
  })

  it('_progress[].files 声明即已迁：每项都存在且当前无裸 import（Property 38 / R6.7）', () => {
    const { union } = progressFileUnion()

    const gone: string[] = []
    const stillBare: string[] = []
    for (const rel of union) {
      const full = path.join(FE_SRC, rel)
      if (!fs.existsSync(full)) {
        gone.push(rel)
        continue
      }
      const src = stripComments(fs.readFileSync(full, 'utf-8'))
      // 用新建正则而非复用带 /g 的 BARE_IMPORT_RE —— 共享 lastIndex 会让后续文件漏检
      const hits = [...src.matchAll(new RegExp(BARE_IMPORT_RE.source, 'g'))]
      if (hits.length > 0) stillBare.push(`${rel}（${hits.length} 处）`)
    }

    expect(
      gone,
      '以下文件在 _progress[].files 里声明迁移过，但磁盘上已不存在：\n  ' +
        gone.join('\n  ') +
        '\n若是有意删除，请移到 _files_deleted_not_migrated；若是路径写错，请修正。' +
        '\n（列了不存在的路径会让 CI 的 `--from-baseline` 编译扫描直接失败）',
    ).toEqual([])

    expect(
      stillBare,
      '以下文件声明「已迁移」但仍有裸 import —— 声明与实现不符：\n  ' + stillBare.join('\n  '),
    ).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：被测实现 —— Wave 1 阶段应全红（当前 46 个文件未迁移）
// ═══════════════════════════════════════════════════════════════════════════

describe('excelIo 收敛 · 类 B 被测实现', () => {
  const { hits, totalCalls, byLibFiles } = scanBareImports()

  it('进度基线未上调（Property 4 / R6.6 单调下降）', () => {
    expect(
      hits.length,
      `裸 import 文件数 ${hits.length} 超过基线 current ${baseline.bare_import_files.current}。` +
        '基线只许下调 —— 若确实新增了裸 import，请先迁移而不是抬基线。',
    ).toBeLessThanOrEqual(baseline.bare_import_files.current)
    expect(
      totalCalls,
      `裸 import 调用点 ${totalCalls} 超过基线 current ${baseline.bare_import_calls.current}`,
    ).toBeLessThanOrEqual(baseline.bare_import_calls.current)
  })

  it('基线 current 与实测一致（防基线漂移后无人察觉）', () => {
    expect(
      hits.length,
      `实测 ${hits.length} 个文件，基线 current 记 ${baseline.bare_import_files.current}。` +
        '两者不等说明有人改了代码没同步基线（或基线被抬高）。迁移后请把 current 改为实测值。',
    ).toBe(baseline.bare_import_files.current)
    expect(totalCalls, `实测 ${totalCalls} 个调用点，基线 current 记 ${baseline.bare_import_calls.current}`).toBe(
      baseline.bare_import_calls.current,
    )
  })

  it('按库文件数与基线一致（分库进度可见）', () => {
    for (const lib of EXCEL_LIBS) {
      const actual = byLibFiles[lib] || 0
      const expected = baseline.by_lib_files[lib] ?? 0
      expect(actual, `${lib} 实测 ${actual} 文件，基线记 ${expected}`).toBe(expected)
    }
  })

  it('🔴 生产文件零裸 import（尚未实现 —— Wave 3~4 Task 9~15 收口）', () => {
    expect(hits.length, buildActionableMessage(hits)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 元守卫：红消息必须可操作（Property 37 / R1.6）
// ═══════════════════════════════════════════════════════════════════════════

describe('excelIo 收敛 · 元守卫（红消息可操作性）', () => {
  const sampleHits: Hit[] = [
    { rel: 'components/foo/Bar.vue', calls: 2, libs: ['xlsx'] },
    { rel: 'utils/baz.ts', calls: 1, libs: ['exceljs'] },
  ]
  const msg = buildActionableMessage(sampleHits)

  it('红消息含每个违规文件的路径', () => {
    for (const h of sampleHits) {
      expect(msg, `红消息未提到违规文件 ${h.rel} —— 使用者无法定位`).toContain(h.rel)
    }
  })

  it('红消息含替代指引（useExcelIO 与具体 API 名）', () => {
    expect(msg, '红消息未指向 useExcelIO').toContain('useExcelIO')
    for (const api of ['parseFile', 'exportTemplate', 'exportData']) {
      expect(msg, `红消息未提到替代 API ${api}`).toContain(api)
    }
  })

  it('红消息含行为等价提醒（三个显式关闭）', () => {
    for (const flag of ['applyStyles', 'includeNoteRow', 'successMessage']) {
      expect(
        msg,
        `红消息未提醒 ${flag} —— 缺了它使用者会机械迁移并静默改变产物外观（applyStyles 默认 true 会给原本无样式的产物加三线表）`,
      ).toContain(flag)
    }
  })

  it('红消息含豁免出口说明', () => {
    expect(msg, '红消息未说明无法收敛时怎么办').toContain('exempt')
  })
})
