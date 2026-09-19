/**
 * J1 披露 Tab 导入导出接线守卫
 *
 * 后端多区块实现在 `backend/app/routers/wp_render_strategies/_j1_disclosure_import_export.py`
 * （复用 F2 的 `_Block` 表驱动范式），分派挂在**既有** J1 三路由上（不新建 router），
 * 入参名 `sheet`（共享前端组件发的）与历史 `sheet_type` 都认。
 *
 * 前端这一侧的失效形态都是"看不见的"（vitest 挂载测与 `get_diagnostics` 都查不出），
 * 故全部用**读 `.vue` 源码的正则契约**守：
 *
 * 1. **sheet 标识写错**：后端按 sheet 分派，写错会 400 或落到别的解析分支
 * 2. **导入后不重载 / 不 hydrate**：库里已改、界面还停在旧值（用户以为没导成功）
 * 3. **导入后不同步附注**：导进来的数据停在底稿，附注拿不到
 * 4. **只读态仍可导入**：绕过只读保护改数据
 * 5. **两套导入导出并存**：手写 el-dropdown 与共享组件同时在，用户点到哪个不确定
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 16.2
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const CORE = resolve(__dirname, '..', 'core')
const HOST = resolve(__dirname, '..', 'GtJ1EmployeeCompensation.vue')
const SRC = resolve(__dirname, '..', '..', '..', '..')
const REPO_ROOT = resolve(SRC, '..', '..', '..')
const SHARED_COMPOSABLE = resolve(
  SRC, 'components', 'workpaper', 'composables', 'useWorkpaperImportExport.ts',
)
const SHARED_DROPDOWN = resolve(
  SRC, 'components', 'workpaper', 'shared', 'CycleImportExportDropdown.vue',
)
const BACKEND_MODULE = resolve(
  REPO_ROOT, 'backend', 'app', 'routers', 'wp_render_strategies',
  '_j1_disclosure_import_export.py',
)

const TABS = [
  { name: 'J1TabDisclosureListed.vue', variant: 'listed', sheet: 'J1-note-listed' },
  { name: 'J1TabDisclosureSoe.vue', variant: 'soe', sheet: 'J1-note-soe' },
] as const

/**
 * 去掉块注释与行注释。
 *
 * 🔴 必需：本文件与被守卫源码的注释里都会写 `useJ1ImportExport` / `el-dropdown`
 * 等反例字样，不去注释会把说明文字数成真实调用（读源码型守卫的通用坑）。
 */
function stripComments(code: string): string {
  return code
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function src(file: string): string {
  return readFileSync(file, 'utf-8')
}

function scriptBody(file: string): string {
  const m = src(file).match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
  expect(m, `${file} 缺 <script setup>`).toBeTruthy()
  return stripComments(m![1])
}

function templateBody(file: string): string {
  const m = src(file).match(/<template>([\s\S]*)<\/template>/)
  expect(m, `${file} 缺 <template>`).toBeTruthy()
  return stripComments(m![1])
}

/** 从后端模块抽 sheet 标识常量（跨语言双真源守卫） */
function backendSheetIds(): Record<string, string> {
  const py = src(BACKEND_MODULE)
  const out: Record<string, string> = {}
  for (const m of py.matchAll(/^SHEET_(LISTED|SOE)\s*=\s*"([^"]+)"/gm)) {
    out[m[1].toLowerCase()] = m[2]
  }
  return out
}

describe('自检：正则与去注释没有空转', () => {
  it('stripComments 干掉 HTML / JS 注释', () => {
    expect(stripComments('<!-- 导入导出 ▾ -->a')).not.toContain('导入导出')
    expect(stripComments('// useJ1ImportExport\nb')).not.toContain('useJ1ImportExport')
    expect(stripComments('/* x */c')).toBe('c')
    // 不能把 URL 里的 `//` 当行注释
    expect(stripComments("const u = 'http://x/y'")).toContain('http://x/y')
  })

  it('后端 sheet 标识能被抽出', () => {
    expect(backendSheetIds()).toEqual({ listed: 'J1-note-listed', soe: 'J1-note-soe' })
  })
})

describe.each(TABS)('$name 导入导出接线', ({ name, sheet }) => {
  const file = resolve(CORE, name)

  it('工具栏复用共享组件 CycleImportExportDropdown（平台统一「导入导出 ▾」三项）', () => {
    const body = scriptBody(file)
    expect(body).toContain(
      "import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'",
    )
    const tpl = templateBody(file)
    expect(tpl).toMatch(/<CycleImportExportDropdown[\s\S]*?\/>/)
    expect(tpl).toContain('api-prefix="j1"')
  })

  it(`sheet 标识为 ${sheet}，与后端 SHEET_* 常量逐字一致`, () => {
    const tpl = templateBody(file)
    expect(tpl).toContain(`sheet="${sheet}"`)
    expect(Object.values(backendSheetIds())).toContain(sheet)
  })

  it('不得残留手写 el-dropdown 导入导出（两套并存 = 用户点到哪个不确定）', () => {
    const tpl = templateBody(file)
    expect(tpl).not.toContain('导出模板')
    expect(tpl).not.toContain('IMPORT_EXPORT_SHEET')
    expect(scriptBody(file)).not.toContain('useJ1ImportExport')
  })

  it('导入后重载 allResponses 再 hydrate（否则界面停留在旧值）', () => {
    const body = scriptBody(file)
    expect(templateBody(file)).toContain('@imported="onImported"')
    expect(body).toContain(
      "inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)",
    )
    const m = body.match(/async function onImported\(\)[\s\S]*?\n\}/)
    expect(m, '未找到 onImported').toBeTruthy()
    expect(m![0]).toMatch(/await reloadWorkpaperData\?\.\(\)\s*\n\s*hydrate\(\)/)
  })

  it('导入后触发一次自动同步（导入的数据也要进附注）', () => {
    const m = scriptBody(file).match(/async function onImported\(\)[\s\S]*?\n\}/)
    expect(m![0]).toContain('autoSync.scheduleAutoSync(syncToDisclosureNotes)')
  })

  it('只读态禁用导入导出（绕过只读保护改数据）', () => {
    const m = templateBody(file).match(/<CycleImportExportDropdown[\s\S]*?\/>/)
    expect(m![0]).toContain(':disabled="isReadonly"')
  })
})

describe('主入口与共享组件', () => {
  it('主入口 provide reloadWorkpaperData（子 Tab inject 才有值）', () => {
    expect(scriptBody(HOST)).toContain("provide('reloadWorkpaperData', selfLoad)")
  })

  it('共享组件只接受 .xlsx 并在导入完成后 emit imported', () => {
    const body = src(SHARED_DROPDOWN)
    expect(body).toContain('accept=".xlsx"')
    expect(stripComments(body)).toMatch(/if \(result\) emit\('imported'\)/)
  })

  it('共享 composable 走 POST + ?sheet=（与后端三路由入参名对齐）', () => {
    const body = stripComments(src(SHARED_COMPOSABLE))
    expect(body).toMatch(/export-template`,\s*null,\s*\{\s*\n?\s*params:\s*\{\s*sheet\s*\}/)
    expect(body).toMatch(/params:\s*\{\s*sheet\s*\}/)
    // 多区块返回 ok=false 时要把后端错误提示出来，并报导入行数
    expect(body).toMatch(/data\.ok === false/)
    expect(body).toContain('imported_count')
  })

  it('后端三路由同时接受 sheet 与 sheet_type，且披露 sheet 已登记', () => {
    const route = src(
      resolve(
        REPO_ROOT, 'backend', 'app', 'routers', 'wp_render_strategies', '_j1_import_export.py',
      ),
    )
    expect(route).toContain('_j1_disclosure_import_export')
    expect(route).toMatch(/methods=\["GET", "POST"\]/)
    expect(route).toMatch(/def _resolve_sheet_type\(/)
    // 三处分派：导出模板 / 导出数据 / 导入
    expect(route.match(/in _DISC_SHEET_TYPES/g)?.length).toBe(3)
  })
})
