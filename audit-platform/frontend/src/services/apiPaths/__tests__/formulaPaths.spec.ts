/**
 * 平台级守卫：公式端点登记表不可回退
 *
 * spec: formula-management-runtime-closure Task 16
 *   (Requirements 7.1, 7.2, 7.6, 8.4, 8.6 / Property 19, 20, 24)
 *
 * 🔴 **为什么需要这条守卫**：Task 14 把公式域端点从「18 个组件里硬编码模板字符串」
 * 收敛进 `apiPaths/formula.ts`。收敛本身是一次性的，**回退却是渐进的** ——
 * 下个会话加一个新端点时最省事的写法就是再写一个字面量 URL，于是登记表慢慢变成
 * 「只覆盖一半」的第二份真源，比完全不收敛更坏（改 prefix 时会漏掉未登记的那半）。
 *
 * 故这里钉死三件事：
 * 1. **未登记 URL 数只许减少**（`UNREGISTERED_BUDGET` 常量），新增字面量即打红；
 * 2. **登记表里的每条 URL 都必须命中后端真实路由**（交叉锁死，防「访问器名字对、
 *    URL 指到别处」的静默错误 —— 该形态已在 Task 14 的变异检验里复现过）；
 * 3. **`formula.py::execute` 的父子双算说明必须在位**（Task 15 的产出，
 *    它是「为什么 `/execute` 的 tb_map 与 four_table 语义定位脱节」的唯一书面依据，
 *    删掉后下个会话会把那段 `warnings` 当噪声清理）。
 *
 * 判据设计要点（踩过的坑）：
 * - 抽 URL 一律**先剥注释**：登记表与调用点的 JSDoc 里都会原样写出 URL 举例，
 *   不剥会把说明文字数成真实引用（memory 已登记该同族坑）。
 * - **BASE 前缀式引用按前缀关系判定**：`/api/formula-management/import-export`
 *   本身不是完整端点，真实请求是 `${BASE}/export-template`。
 * - **只统计生产代码**：`__tests__` 里的字面量是 mock 断言的判据，收敛它们没有意义
 *   （反而会让「测试断言 URL」与「生产实际 URL」失去独立性）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ── 仓库根定位：双哨兵具体文件向上查找（禁写死回退级数 / 禁用目录做哨兵） ──
function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const s1 = path.join(dir, 'backend', 'app', 'routers', 'wp_formula.py')
    const s2 = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(s1) && fs.existsSync(s2)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repo root not found (双哨兵均未命中)')
}

const REPO_ROOT = findRepoRoot()
const FE_SRC = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
const BE_ROUTERS = path.join(REPO_ROOT, 'backend', 'app', 'routers')
const PATHS_FILE = path.join(FE_SRC, 'services', 'apiPaths', 'formula.ts')

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

/** 剥块注释与行注释（保留字符串内容不做转义处理，够用且不会漏判）。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function walk(dir: string, ext: string[]): string[] {
  const acc: string[] = []
  if (!fs.existsSync(dir)) return acc
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const st = fs.statSync(full)
    if (st.isDirectory()) {
      if (name === '__pycache__' || name === 'node_modules') continue
      acc.push(...walk(full, ext))
    } else if (ext.some((e) => name.endsWith(e))) {
      acc.push(full)
    }
  }
  return acc
}

/**
 * URL 归一：把 `${...}` 与路径段里的 fastapi `{param}` 都折成 `{}`，
 * 并去掉查询串与末尾斜杠，使前后端可比。
 */
function normalizeUrl(u: string): string {
  let s = u.split('?')[0]
  s = s.replace(/\$\{[^}]*\}/g, '{}')
  s = s.replace(/\{[^}]*\}/g, '{}')
  s = s.replace(/\/+$/, '')
  return s
}

// ---------------------------------------------------------------------------
// 后端真实注册路由抽取（与 formulaEndpointExistence.spec.ts 同口径）
// ---------------------------------------------------------------------------

function collectBackendPaths(): Set<string> {
  const out = new Set<string>()
  for (const f of walk(BE_ROUTERS, ['.py'])) {
    const raw = fs.readFileSync(f, 'utf-8')
    // router = APIRouter(prefix="/api/xxx")
    const prefixes: string[] = []
    for (const m of raw.matchAll(/APIRouter\(([^)]*)\)/g)) {
      const pm = /prefix\s*=\s*["']([^"']*)["']/.exec(m[1])
      prefixes.push(pm ? pm[1] : '')
    }
    const prefix = prefixes.find((p) => p.startsWith('/api')) ?? prefixes[0] ?? ''
    for (const m of raw.matchAll(
      /@\w+\.(get|post|put|delete|patch)\(\s*["']([^"']*)["']/g,
    )) {
      const p = m[2]
      const full = p.startsWith('/api') ? p : `${prefix}${p}`
      if (!full.startsWith('/api')) continue
      out.add(normalizeUrl(full))
    }
  }
  return out
}

const backendNorm = collectBackendPaths()

function isBackendPrefix(norm: string): boolean {
  return [...backendNorm].some((b) => b.startsWith(`${norm}/`))
}

// ---------------------------------------------------------------------------
// 登记表里的 URL 抽取
// ---------------------------------------------------------------------------

const pathsSrc = fs.readFileSync(PATHS_FILE, 'utf-8')
const pathsCode = stripComments(pathsSrc)

/** 登记表代码区里出现的所有 `/api/...` 字面量（模板串与普通串都算）。 */
function registeredUrls(): string[] {
  const out = new Set<string>()
  for (const m of pathsCode.matchAll(/['"`](\/api\/[^'"`]*)['"`]/g)) {
    out.add(m[1])
  }
  return [...out].sort()
}

const registered = registeredUrls()

// ---------------------------------------------------------------------------
// 生产侧未登记 URL 统计
// ---------------------------------------------------------------------------

/**
 * 公式域生产文件集合。
 *
 * 与 Task 14 的搬迁范围一致：`components/formula/**` + `components/workpaper` 下的
 * 公式面板 + `composables/useFormula*.ts` + `components/workpaper/composables/useFormula*.ts`。
 */
function formulaProductionFiles(): string[] {
  const acc: string[] = []
  acc.push(...walk(path.join(FE_SRC, 'components', 'formula'), ['.ts', '.vue']))
  for (const dir of [
    path.join(FE_SRC, 'composables'),
    path.join(FE_SRC, 'components', 'workpaper'),
    path.join(FE_SRC, 'components', 'workpaper', 'composables'),
  ]) {
    for (const f of walk(dir, ['.ts', '.vue'])) {
      if (/Formula/.test(path.basename(f))) acc.push(f)
    }
  }
  return [...new Set(acc)].filter((f) => !f.includes('__tests__'))
}

/**
 * 与公式运行时相关的 URL 判据。
 *
 * 🔴 只统计**公式域自己的端点**：这些文件里也会请求试算表 / 附注树 / 底稿列表
 * （`/api/trial-balance`、`/api/working-papers`、`/api/report-config/types` 等），
 * 那些属别的域，登记它们会侵入其他 spec 的真源（R7.6 显式范围外）。
 */
function isFormulaEndpoint(u: string): boolean {
  return (
    /\/formulas?\b/.test(u) ||
    u.includes('/formula-management/') ||
    u.includes('/formula-scope/') ||
    u.includes('/formula/') ||
    u.includes('/validate-formula') ||
    u.includes('/draft-refresh') ||
    u.includes('/refresh-scopes')
  )
}

function collectUnregistered(): Array<{ url: string; file: string }> {
  const registeredNorm = new Set(registered.map(normalizeUrl))
  const out: Array<{ url: string; file: string }> = []
  for (const f of formulaProductionFiles()) {
    const code = stripComments(fs.readFileSync(f, 'utf-8'))
    for (const m of code.matchAll(/['"`](\/api\/[^'"`\s]*)['"`]/g)) {
      const url = m[1]
      if (!isFormulaEndpoint(url)) continue
      const norm = normalizeUrl(url)
      if (registeredNorm.has(norm)) continue
      out.push({ url, file: path.relative(FE_SRC, f).replace(/\\/g, '/') })
    }
  }
  return out
}

const unregistered = collectUnregistered()

/**
 * 未登记 URL 数上限。
 *
 * 🔴 **只许减少**。当前实测为 0（Task 14 + Task 16 已把生产侧公式端点全部收敛）。
 * 新增一个字面量 URL 就会打红，届时正确处置是**登记进 `apiPaths/formula.ts`**，
 * 不是把这个数字调大。
 */
const UNREGISTERED_BUDGET = 0

// ---------------------------------------------------------------------------
// Property 19: 公式端点收敛进 apiPaths
// ---------------------------------------------------------------------------

describe('Property 19: 公式端点收敛进 apiPaths（未登记数只许减少）', () => {
  it('提取器自检：登记表非空且含已知的三个端点', () => {
    expect(registered.length).toBeGreaterThan(10)
    const norm = new Set(registered.map(normalizeUrl))
    expect(norm.has('/api/workpapers/{}/formulas')).toBe(true)
    expect(norm.has('/api/workpapers/{}/user-formulas')).toBe(true)
    expect(norm.has('/api/formula-scope/{}/formulas')).toBe(true)
  })

  it('提取器自检：生产文件集合非空且不含测试文件', () => {
    const files = formulaProductionFiles()
    expect(files.length).toBeGreaterThan(5)
    expect(files.some((f) => f.includes('__tests__'))).toBe(false)
    // 已知的四个搬迁目标必须在扫描面内（防「扫描面缩小造成假绿」）
    const rel = files.map((f) => path.relative(FE_SRC, f).replace(/\\/g, '/'))
    expect(rel).toContain('components/formula/FormulaManagerDialog.vue')
    expect(rel).toContain('components/formula/GtRefreshScopeDialog.vue')
    expect(rel).toContain('components/workpaper/FormulaStatusPanel.vue')
    expect(rel).toContain('composables/useFormulaImportExport.ts')
  })

  it('生产侧未登记的公式 URL 数不超过预算', () => {
    expect(
      unregistered.map((u) => `${u.file}: ${u.url}`),
    ).toHaveLength(UNREGISTERED_BUDGET)
  })

  it('反向自检：替身未登记 URL 会被判据抓到（判据非空转）', () => {
    const fake = '/api/workpapers/fake-id/formulas-NOT-REGISTERED'
    expect(isFormulaEndpoint(fake)).toBe(true)
    const registeredNorm = new Set(registered.map(normalizeUrl))
    expect(registeredNorm.has(normalizeUrl(fake))).toBe(false)
  })

  it('反向自检：非公式域 URL 不被纳入统计（避免侵入其他 spec）', () => {
    for (const u of [
      '/api/trial-balance',
      '/api/working-papers',
      '/api/report-config/types',
      '/api/disclosure-notes/tree',
      '/api/address-registry',
    ]) {
      expect(isFormulaEndpoint(u)).toBe(false)
    }
  })
})

// ---------------------------------------------------------------------------
// Property 20: 登记表 ⊆ 后端真实路由
// ---------------------------------------------------------------------------

describe('Property 20: 登记表每条 URL 都命中后端真实路由（交叉锁死）', () => {
  /**
   * 已登记的豁免：后端确无实现的前瞻占位。
   *
   * 与 `formulaEndpointExistence.spec.ts` 的 `ENDPOINT_EXEMPTIONS` 同一条目
   * （`auto-generate`）。**两处不得各写一份判据** —— 这里只做「数量封顶 + 归一值一致」，
   * 理由与降级路径的实证归那份守卫。
   */
  const EXEMPT_NORM = Object.freeze(['/api/projects/{}/formula/auto-generate'])

  it('后端路由抽取非空（提取器自检）', () => {
    expect(backendNorm.size).toBeGreaterThan(500)
    expect(backendNorm.has('/api/workpapers/{}/formulas')).toBe(true)
  })

  it('登记表 URL 全部命中后端（或在豁免清单里）', () => {
    const missing: string[] = []
    for (const u of registered) {
      const norm = normalizeUrl(u)
      if (backendNorm.has(norm)) continue
      if (isBackendPrefix(norm)) continue
      if (EXEMPT_NORM.includes(norm)) continue
      missing.push(`${u}  (norm=${norm})`)
    }
    expect(missing).toEqual([])
  })

  it('豁免清单只许减少且与另一份守卫同值', () => {
    expect(EXEMPT_NORM.length).toBeLessThanOrEqual(1)
    // 与 formulaEndpointExistence.spec.ts 的登记值交叉锁死（防两处漂移）
    const other = fs.readFileSync(
      path.join(
        FE_SRC,
        'components',
        'workpaper',
        'composables',
        '__tests__',
        'formulaEndpointExistence.spec.ts',
      ),
      'utf-8',
    )
    for (const n of EXEMPT_NORM) {
      expect(other).toContain(n)
      // 豁免必须真的是后端零命中（否则豁免在掩盖已存在的路由）
      expect(backendNorm.has(n)).toBe(false)
    }
  })

  it('反向自检：替身 URL 既不命中后端也不在豁免 → 必被判 missing', () => {
    const fake = normalizeUrl('/api/workpapers/${id}/formulas-NOPE')
    expect(backendNorm.has(fake)).toBe(false)
    expect(isBackendPrefix(fake)).toBe(false)
    expect(EXEMPT_NORM.includes(fake)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Property 24: /execute 口径告警说明不可删
// ---------------------------------------------------------------------------

describe('Property 24: formula.py::execute 的父子双算说明与告警在位', () => {
  const enginePath = path.join(
    REPO_ROOT,
    'backend',
    'app',
    'services',
    'formula_engine.py',
  )
  const engineSrc = fs.readFileSync(enginePath, 'utf-8')

  /**
   * 截取 `FormulaEngine.execute` 的方法体。
   *
   * 🔴 **判据必须落在方法体内**：`four_table` / `warnings` / `startswith(` 在
   * 本文件别处（`_execute_regex` 的注释、`_check_prev_warnings`、`_TOKEN_PATTERNS`）
   * 都出现，全文断言会让「删掉整段告警」这个**核心变异静默逃逸**
   * （已在本轮变异检验 M4 复现：GREEN=守卫缺陷）。
   *
   * 定位方式：`async def execute(self, db, project_id, year, formula_type` 是
   * 该方法的唯一签名特征（模块级 `def execute(formula, ctx)` 与三个 Executor 的
   * `async def execute(db, project_id, ...)` 都不匹配它）；结束于下一个同缩进 `def`。
   */
  function engineExecuteBody(): string {
    const sigIdx = engineSrc.indexOf(
      'async def execute(self, db, project_id, year, formula_type',
    )
    expect(sigIdx).toBeGreaterThan(0)
    const rest = engineSrc.slice(sigIdx)
    // 下一个 `    async def ` / `    def ` （方法级缩进）即边界
    const endM = /\n {4}(?:async )?def /.exec(rest.slice(1))
    return endM ? rest.slice(0, endM.index + 1) : rest
  }

  const execBody = engineExecuteBody()

  it('提取器自检：方法体非空且不含相邻方法的内容', () => {
    expect(execBody.length).toBeGreaterThan(400)
    // batch_execute 是紧随其后的方法，不得被截进来
    expect(execBody).not.toContain('async def batch_execute')
    // 模块级 execute 的 parse 层注释也不得被截进来
    expect(execBody).not.toContain('_PARSE_MODE="parallel"')
  })

  it('execute 方法体内含父子双算口径说明（指向 four_table 叶子聚合）', () => {
    expect(execBody).toContain('four_table')
    expect(/父子|双算/.test(execBody)).toBe(true)
    // 必须点名共享件，否则「说明」退化成一句空话
    expect(execBody).toContain('leaf_aggregation')
  })

  it('execute 会在检出父子共存时产出运行时 warnings（不是只写注释）', () => {
    // 🔴 判据是**条件表达式形态**而不是标识符出现（memory 铁律：
    // 只断言标识符抓不住「把条件改成 if False」这类变异）
    expect(/if\s+_has_parent_child_overlap\(\s*tb_map\s*\)\s*:/.test(execBody)).toBe(
      true,
    )
    // 命中后必须真的把告警写进返回体（只 append 到本地变量却不返回 = dead output）
    expect(/warnings\.append\(/.test(execBody)).toBe(true)
    expect(/["']warnings["']\s*:\s*warnings/.test(execBody)).toBe(true)
  })

  it('父子共存检测函数真实存在且按前缀关系判定（非恒假）', () => {
    const m = /def\s+_has_parent_child_overlap\b[\s\S]*?(?=\ndef\s|\nclass\s|$)/.exec(
      engineSrc,
    )
    expect(m).not.toBeNull()
    const body = m![0]
    expect(/startswith\(/.test(body)).toBe(true)
    /**
     * 🔴 **不得退化成恒 False**（那样告警永不触发 = 又一个静默失效）。
     *
     * 判据是「存在能触发的 `return True` 路径」，**不是**「函数末尾没有
     * `return False`」—— 末尾的 `return False` 正是它的正常否定路径，
     * 按后者断言会把正确实现打红（本轮实测踩中一次）。
     */
    expect(/return\s+True\b/.test(body)).toBe(true)
    /**
     * 分隔符边界：标准码用 `-`（`1231-01`）、客户原始码用 `.`（`1002.001`），
     * memory 已记两套体系并存 —— 只认一种会漏判；裸 `startswith` 会把
     * `1231` 与 `12310` 误判成父子。
     */
    expect(body).toContain('"-"')
    expect(body).toContain('"."')
  })

  it('FormulaResult 声明了 warnings 字段（否则响应键被 pydantic 静默丢弃）', () => {
    const schemaPath = path.join(
      REPO_ROOT,
      'backend',
      'app',
      'models',
      'workpaper_schemas.py',
    )
    const schemaSrc = fs.readFileSync(schemaPath, 'utf-8')
    const m = /class\s+FormulaResult\b[\s\S]*?(?=\nclass\s|\Z)/.exec(schemaSrc)
    expect(m).not.toBeNull()
    expect(/warnings\s*:/.test(m![0])).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Property 25: apiPaths barrel 完整性（formula.ts 的导出必须全部进 index.ts）
//
// 🔴 为什么需要：`apiPaths/index.ts` 用**具名 re-export**（`export { a, b } from
// './formula'`）而不是 `export *` —— 新增一个 `export const` 若忘了加进这份清单，
// 从 barrel（`@/services/apiPaths`）取该对象会拿到 `undefined`，而按深路径
// （`@/services/apiPaths/formula`）导入的调用方仍然工作 ⇒ 一半路径可用、一半静默失败，
// TS 层不报错（barrel 无该名时是编译错，但调用方多用深路径故不触发）。
//
// 2026-08-07 归档复核实测：`draftRefresh` 已 `export` 但**未进 barrel**
// （其唯一消费方 GtRefreshScopeDialog.vue 走深路径故当前未暴露），已补齐。
// ---------------------------------------------------------------------------

describe('Property 25: apiPaths barrel 完整性', () => {
  const BARREL_FILE = path.join(FE_SRC, 'services', 'apiPaths', 'index.ts')

  /** 抽 formula.ts 的顶层 `export const <name>`。 */
  function formulaExports(): string[] {
    const code = stripComments(fs.readFileSync(PATHS_FILE, 'utf-8'))
    return [...code.matchAll(/^export\s+const\s+([A-Za-z_$][\w$]*)/gm)].map((m) => m[1])
  }

  /** 抽 barrel 中 `... } from './formula'` 这一段 re-export 的名字。 */
  function barrelNamesFromFormula(): string[] {
    const code = stripComments(fs.readFileSync(BARREL_FILE, 'utf-8'))
    const names: string[] = []
    for (const m of code.matchAll(/export\s*\{([^}]*)\}\s*from\s*['"]\.\/formula['"]/g)) {
      for (const raw of m[1].split(',')) {
        const n = raw.trim().split(/\s+as\s+/)[0].trim()
        if (n) names.push(n)
      }
    }
    return names
  }

  it('提取器自检：两侧都抽到非空结果，且 barrel 确实用具名 re-export（非 export *）', () => {
    const exp = formulaExports()
    const barrel = barrelNamesFromFormula()
    expect(exp.length).toBeGreaterThan(3)
    expect(barrel.length).toBeGreaterThan(3)
    // 若哪天改成 `export * from './formula'`，本组断言应整体退役而非静默放行
    const code = stripComments(fs.readFileSync(BARREL_FILE, 'utf-8'))
    expect(code).not.toMatch(/export\s+\*\s+from\s+['"]\.\/formula['"]/)
  })

  it('formula.ts 的每个导出都已进 barrel（漏一个 → 从 @/services/apiPaths 取到 undefined）', () => {
    const missing = formulaExports().filter((n) => !barrelNamesFromFormula().includes(n))
    expect(missing, `formula.ts 已导出但 index.ts 未 re-export: ${missing.join(', ')}`).toEqual([])
  })

  it('barrel 不得 re-export formula.ts 里不存在的名字（防清单陈旧）', () => {
    const extra = barrelNamesFromFormula().filter((n) => !formulaExports().includes(n))
    expect(extra, `index.ts re-export 了 formula.ts 不存在的名字: ${extra.join(', ')}`).toEqual([])
  })
})
