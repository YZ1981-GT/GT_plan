/**
 * Property 6 — G0 孤儿 composable 已删除且无残留引用
 *
 * spec: confirmation-orphan-and-amount-format-closure（Requirement 3.1/3.2/3.3/3.7）
 *
 * ## 为什么这条守卫值得单独存在
 *
 * 删文件是「一次性动作」，但残留引用是**渐进复活**的：`components.d.ts` 由 unplugin
 * 自动生成，dev server 一跑就可能把已删符号写回；docstring 里提到旧名也会诱导后来者
 * 重建一份。故这里同时钉住三件事：
 * 1. 三个文件确实不存在（不是改名或移位置）；
 * 2. 全仓（含 `components.d.ts`）无残留引用；
 * 3. `useG0FormulaEngine.spec.ts` 在 `composables/__tests__/` 而非 `composables/`
 *    —— 测试文件混在生产目录里会被孤儿扫描器与打包器都当成生产模块。
 *
 * ## 三个被删文件与删除依据（勿据「名字看着有用」重建）
 *
 * - `useG0DualMode.ts`：G0 十张 sheet 在 `wp_code_overrides` 全部注册为
 *   `confirmation-*` HTML 组件，没有 OnlyOffice 双模式落点 → 该 composable 永不生效。
 * - `useG0ImportExport.ts`：页面级 `CycleImportExportDropdown` 直接用共享
 *   `useWorkpaperImportExport`，本包装是重复件。
 * - `useG0ReviewDialogProvide.ts`：`openReviewDialog` 已由 `GtWpRenderer` 统一 provide
 *   （docstring 声称「G0-3/G0-6 主入口调用」实测零调用）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    // 哨兵必须是具体文件：`backend/app/routers` 目录在 audit-platform 层也存在（历史空目录）
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'main.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未能向上定位仓库根（哨兵 backend/app/main.py 缺失）')
}

const REPO_ROOT = findRepoRoot()
const SRC = path.join(REPO_ROOT, 'audit-platform/frontend/src')
const G0 = path.join(SRC, 'components/workpaper/g0-confirmation')

/** 被删的三个 composable（符号名 = 文件名 stem = 导出函数名） */
const DELETED = ['useG0DualMode', 'useG0ImportExport', 'useG0ReviewDialogProvide'] as const

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = []
  if (!fs.existsSync(dir)) return out
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p, exts))
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p)
  }
  return out
}

/** 全仓 `.vue`/`.ts`（**含** `components.d.ts` —— 它正是自动复活的通道） */
const ALL_FILES = walk(SRC, ['.vue', '.ts']).map((p) => ({
  path: p,
  rel: path.relative(SRC, p).replace(/\\/g, '/'),
  text: fs.readFileSync(p, 'utf-8'),
}))

/**
 * 「残留引用」的扫描面 = 生产文件 + `components.d.ts`，**排除测试**。
 *
 * 🔴 排除测试是必需的，不是放宽：守卫与基线登记表本身就要**写出这些符号名**才能
 * 钉住「它们已被删除」（`orphanHostCoverage.spec.ts` 的「三个已删 composable 不在基线里」
 * 断言、`orphanHostBaseline.ts` 里「与已删的 useG0ImportExport 同族包装」这类 reason）。
 * 把它们算成残留引用会让守卫**互相打红**，且红的不是缺陷。
 *
 * 但 `components.d.ts` 必须留在扫描面 —— 它由 unplugin 自动生成，dev server 一跑
 * 就可能把已删组件写回，是「渐进复活」的真实通道。
 */
const PROD_FILES = ALL_FILES.filter(
  (f) => !f.rel.includes('/__tests__/') && !f.rel.endsWith('.spec.ts'),
)

describe('自检：扫描面非空（解析失效必须打红而非空转）', () => {
  it('扫到的文件数量锚定，且 components.d.ts 在扫描面内', () => {
    expect(ALL_FILES.length).toBeGreaterThan(1000)
    expect(
      ALL_FILES.some((f) => f.rel.endsWith('components.d.ts')),
      'components.d.ts 必须在扫描面内（它会自动写回已删组件）',
    ).toBe(true)
  })

  it('G0 目录存在且仍有生产文件（防路径写错导致断言恒真）', () => {
    expect(fs.existsSync(G0)).toBe(true)
    const prod = walk(G0, ['.vue', '.ts']).filter((p) => !p.includes('__tests__'))
    expect(prod.length).toBeGreaterThan(5)
  })
})

describe('Property 6: 三个 G0 孤儿 composable 已删除且无残留引用（Validates 3.1, 3.2, 3.3, 3.7）', () => {
  it.each(DELETED)('%s.ts 文件不存在（真删除，不是改名或移位）', (stem) => {
    const candidates = [
      path.join(G0, `composables/${stem}.ts`),
      path.join(G0, `${stem}.ts`),
    ]
    for (const c of candidates) {
      expect(fs.existsSync(c), `${c} 仍存在`).toBe(false)
    }
    // 全仓不得有同名文件（防被挪到别的目录继续当死代码）
    const anywhere = ALL_FILES.filter((f) => f.rel.endsWith(`/${stem}.ts`))
    expect(anywhere.map((f) => f.rel), `${stem}.ts 被挪到了别处`).toEqual([])
  })

  it.each(DELETED)('%s 在生产代码零引用（含 components.d.ts 自动复活通道）', (stem) => {
    const re = new RegExp(`\\b${stem}\\b`)
    const hits = PROD_FILES.filter((f) => re.test(f.text)).map((f) => f.rel)
    expect(
      hits,
      `${stem} 仍被生产代码引用（要么真删干净，要么说明它其实有用）：\n${hits.join('\n')}`,
    ).toEqual([])
  })

  it('useG0FormulaEngine.spec.ts 在 composables/__tests__/ 而非 composables/', () => {
    const wrong = path.join(G0, 'composables/useG0FormulaEngine.spec.ts')
    const right = path.join(G0, 'composables/__tests__/useG0FormulaEngine.spec.ts')
    expect(fs.existsSync(wrong), '测试文件仍混在生产目录 composables/ 下').toBe(false)
    expect(fs.existsSync(right), '未在 composables/__tests__/ 找到该测试').toBe(true)
  })

  it('composables/ 生产目录下不得有任何 .spec.ts（测试与生产分离）', () => {
    const dir = path.join(G0, 'composables')
    if (!fs.existsSync(dir)) return
    const strays = fs
      .readdirSync(dir, { withFileTypes: true })
      .filter((e) => e.isFile() && e.name.endsWith('.spec.ts'))
      .map((e) => e.name)
    expect(strays, `composables/ 下混入测试文件：${strays.join(', ')}`).toEqual([])
  })

  it('useG0ImportExport 的替代件存在（共享 useWorkpaperImportExport）', () => {
    const shared = path.join(SRC, 'components/workpaper/composables/useWorkpaperImportExport.ts')
    expect(
      fs.existsSync(shared),
      '共享 useWorkpaperImportExport 应存在（它是 useG0ImportExport 的替代）',
    ).toBe(true)
  })

  it('useG0ReviewDialogProvide 的替代件存在（平台 provide 链完整）', () => {
    /**
     * 🔴 真链条 = `useWorkpaperScaffold` → `useWorkpaperReviewProvide`
     *            → `useReviewDialogProvider.provide('openReviewDialog')`
     *
     * **与 `GtWpRenderer` 无关**：平台 40+ 个宿主的注释写着「openReviewDialog 由
     * Runtime Boundary(GtWpRenderer) 统一 provide」，但 `GtWpRenderer.vue` 全文
     * 不含 `ReviewDialog` 字样（实测 40512 字符零命中）→ 那批注释是过时说法。
     * 本断言按**代码实证**钉住真链，不按注释。
     */
    const providerSrc = fs.readFileSync(
      path.join(SRC, 'composables/useReviewDialogProvider.ts'),
      'utf-8',
    )
    expect(
      /provide\(\s*['"]openReviewDialog['"]/.test(providerSrc),
      'useReviewDialogProvider 应 provide openReviewDialog',
    ).toBe(true)

    const wpProvide = fs.readFileSync(
      path.join(SRC, 'components/workpaper/composables/useWorkpaperReviewProvide.ts'),
      'utf-8',
    )
    expect(
      wpProvide.includes('useReviewDialogProvider'),
      'useWorkpaperReviewProvide 应调用 useReviewDialogProvider（链条中段）',
    ).toBe(true)

    const scaffold = fs.readFileSync(
      path.join(SRC, 'components/workpaper/composables/useWorkpaperScaffold.ts'),
      'utf-8',
    )
    expect(
      scaffold.includes('useWorkpaperReviewProvide'),
      'useWorkpaperScaffold 应调用 useWorkpaperReviewProvide（链条上游，宿主由此获得 provide）',
    ).toBe(true)
  })

  it('反向自检：GtWpRenderer 确实不是 openReviewDialog 的 provider（钉住上面那条注释缺陷）', () => {
    const renderer = ALL_FILES.find((f) => f.rel.endsWith('GtWpRenderer.vue'))
    expect(renderer, 'GtWpRenderer.vue 应存在').toBeTruthy()
    expect(
      /provide\(\s*['"]openReviewDialog['"]/.test(renderer!.text),
      'GtWpRenderer 若哪天真的 provide 了，本断言会红 → 提醒同步修正 40+ 处宿主注释',
    ).toBe(false)
  })

  it('反向自检：对一个确实存在的 G0 符号，同款判据会命中（证明扫描非恒假）', () => {
    const re = /\buseAlternativeG06Data\b/
    const hits = ALL_FILES.filter((f) => re.test(f.text)).map((f) => f.rel)
    expect(hits.length, '存量符号应被扫到（否则上面的「零引用」全是空转）').toBeGreaterThan(0)
  })

  it('反向自检：对一个必然不存在的符号判为零引用', () => {
    const re = /\buseG0NoSuchComposableXyz\b/
    const hits = ALL_FILES.filter((f) => re.test(f.text) && !f.rel.endsWith('g0OrphanClosure.spec.ts'))
    expect(hits.map((f) => f.rel)).toEqual([])
  })
})
