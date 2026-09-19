/**
 * `FormulaStatusPanel.vue` 四字段展示守卫
 *
 * spec: formula-management-runtime-closure Task 3
 *   (Requirements 2.1–2.6 / Property 6 of design §Correctness Properties 对应 R2)
 *
 * 🔴 **为什么独立成文件**：同目录 `FormulaStatusPanel.spec.ts` 属并发 spec
 * `d-cycle-four-table-extraction-formulas`（Task 4.1/4.2 的端点与 Tier A 编辑断言），
 * 两个 spec 同时编辑一个文件会互相回退（memory 已记 4 次实测）。本文件只断言
 * 本 spec R2 的展示不变式，与那份互不重叠。
 *
 * 判据一律**源码级**（读 `.vue` 原文），理由两条：
 * 1. 四字段是「模板里有没有引用」的结构性问题，挂载测试要造 17 键 fixture 且
 *    受 element-plus stub 影响，反而更脆；
 * 2. R2.5 要求「复用单一真源 `FORMULA_TYPE_LABEL`，禁自建第二份标签表」——
 *    这本身只能靠源码断言（挂载测试看不出标签是哪来的）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

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
const PANEL = path.join(FE_SRC, 'components', 'workpaper', 'FormulaStatusPanel.vue')
const INVENTORY = path.join(
  FE_SRC,
  'components',
  'workpaper',
  'composables',
  'formulaEngineInventory.ts',
)
const WP_FORMULA_PY = path.join(REPO_ROOT, 'backend', 'app', 'routers', 'wp_formula.py')

const raw = fs.readFileSync(PANEL, 'utf-8')

/** 取 `<template>` 段（最外层，含内层 `<template #footer>` 也无妨）。 */
function templateBlock(src: string): string {
  const i = src.indexOf('<template>')
  const j = src.lastIndexOf('</template>')
  if (i < 0 || j < 0) throw new Error('template block not found')
  return src.slice(i, j)
}

/** 取 `<script setup>` 段。 */
function scriptBlock(src: string): string {
  const m = /<script setup[^>]*>([\s\S]*?)<\/script>/.exec(src)
  if (!m) throw new Error('script block not found')
  return m[1]
}

/** 剥 HTML 注释（模板里会写「为什么这么渲染」的说明，含被禁写法的反例）。 */
function stripHtmlComments(s: string): string {
  return s.replace(/<!--[\s\S]*?-->/g, ' ')
}

/** 剥 JS 注释（带字符串状态机，避免被 `https://` 骗）。 */
function stripJsComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '*') {
      const e = src.indexOf('*/', i + 2)
      i = e < 0 ? src.length : e + 2
      out += ' '
      continue
    }
    if (c === '/' && n === '/') {
      const e = src.indexOf('\n', i)
      i = e < 0 ? src.length : e
      out += ' '
      continue
    }
    out += c
    i += 1
  }
  return out
}

const tmpl = stripHtmlComments(templateBlock(raw))
const script = stripJsComments(scriptBlock(raw))

describe('提取器自检', () => {
  it('三个提取器都拿到非空内容', () => {
    expect(tmpl.length).toBeGreaterThan(1000)
    expect(script.length).toBeGreaterThan(1000)
    expect(raw.length).toBeGreaterThan(5000)
  })

  it('stripHtmlComments 确实剥掉注释', () => {
    const f = '<div>a</div><!-- 反例：{{ it.formula_type }} 裸英文 -->'
    const s = stripHtmlComments(f)
    expect(s).toContain('<div>a</div>')
    expect(s).not.toContain('裸英文')
  })

  it('stripJsComments 确实剥掉注释且不被 URL 骗', () => {
    const f = "// 反例 FORBIDDEN_TOKEN\nconst u = 'https://a/b'"
    const s = stripJsComments(f)
    expect(s).not.toContain('FORBIDDEN_TOKEN')
    expect(s).toContain('https://a/b')
  })
})

describe('R2.1: issue_description 与 hint_text 在模板中真实渲染', () => {
  it('两字段都出现在模板（不是仅在接口声明里）', () => {
    expect(tmpl).toContain('issue_description')
    expect(tmpl).toContain('hint_text')
  })

  it('R2.1 后半：为空时不渲染该区域（v-if 门控）', () => {
    expect(/v-if="it\.issue_description"/.test(tmpl)).toBe(true)
    expect(/v-if="it\.hint_text"/.test(tmpl)).toBe(true)
  })

  it('接口 RawFormulaItem 已声明四字段（否则 TS 层就丢弃了）', () => {
    for (const f of ['issue_description', 'hint_text', 'last_computed_at', 'refs']) {
      expect(new RegExp(`${f}\\??:`).test(script)).toBe(true)
    }
  })
})

describe('R2.2 / R2.5: formula_type 显示中文标签且复用单一真源', () => {
  it('模板不得渲染裸 formula_type', () => {
    // 允许 `formulaTypeLabel(it.formula_type)` / `formulaTypeTagType(it.formula_type)`，
    // 禁止 `{{ it.formula_type }}` 这种直出英文值
    expect(/\{\{\s*\w+\.formula_type\s*\}\}/.test(tmpl)).toBe(false)
  })

  it('模板经中文标签函数渲染', () => {
    expect(/formulaTypeLabel\(\s*it\.formula_type\s*\)/.test(tmpl)).toBe(true)
  })

  it('中文标签真源 = formulaEngineInventory.FORMULA_TYPE_LABEL（import 且被使用）', () => {
    expect(
      /import\s*\{[^}]*FORMULA_TYPE_LABEL[^}]*\}\s*from\s*['"][^'"]*formulaEngineInventory['"]/s.test(
        script,
      ),
    ).toBe(true)
    expect(/FORMULA_TYPE_LABEL\s*\[/.test(script)).toBe(true)
  })

  it('禁本文件内自建第二份三类型标签表（R2.5）', () => {
    // 自建形态：`Record<FormulaType, string>` 或字面量里同时含三个中文标签
    expect(/Record<\s*FormulaType\s*,\s*string\s*>/.test(script)).toBe(false)
    const selfBuilt =
      script.includes('自动运算') && script.includes('逻辑判断') && script.includes('合理性提示')
    expect(selfBuilt).toBe(false)
  })

  it('真源本身三类型齐备（交叉锁死：真源缺键则标签会退化成英文）', () => {
    const inv = fs.readFileSync(INVENTORY, 'utf-8')
    const m = /FORMULA_TYPE_LABEL[^=]*=\s*\{([\s\S]*?)\}/.exec(inv)
    expect(m).not.toBeNull()
    const body = m![1]
    expect(body).toContain('auto_calc')
    expect(body).toContain('logic_check')
    expect(body).toContain('reasonability')
    expect(body).toContain('自动运算')
    expect(body).toContain('逻辑判断')
    expect(body).toContain('合理性提示')
  })
})

describe('R2.3: last_computed_at 可读时间，为空显示「未计算」', () => {
  it('模板经 computedAtText 渲染', () => {
    expect(/computedAtText\(\s*it\.last_computed_at\s*\)/.test(tmpl)).toBe(true)
  })

  it('script 里空值分支返回「未计算」', () => {
    const i = script.indexOf('function computedAtText')
    expect(i).toBeGreaterThan(-1)
    const body = script.slice(i, i + 400)
    expect(body).toContain('未计算')
    // 判据是**条件形态**不是「出现了某个标识符」（memory 铁律：
    // 字符串存在性判据挡不住把条件改成恒假）
    expect(/if\s*\(\s*!\s*iso\s*\)\s*return\s*'未计算'/.test(body)).toBe(true)
  })
})

describe('R2.4: refs 数量展示且可展开', () => {
  it('模板展示引用数量', () => {
    expect(/refsCount\(\s*it\.refs\s*\)/.test(tmpl)).toBe(true)
    expect(tmpl).toContain('引用')
  })

  it('模板有展开/收起交互与列表渲染', () => {
    expect(/toggleRefs\(\s*it\.id\s*\)/.test(tmpl)).toBe(true)
    expect(/v-for="\(r, ri\) in \(it\.refs \|\| \[\]\)"/.test(tmpl)).toBe(true)
  })

  it('引用列表的 v-if 条件确实绑在 expandedRefs 上（判据 = 条件形态，非标识符存在）', () => {
    // 🔴 变异检验抓出的守卫缺陷：`expandedRefs.has(it.id)` 在展开箭头
    // `{{ expandedRefs.has(it.id) ? '▴' : '▾' }}` 处也出现 ⇒ 只断言
    // 「该标识符在模板里出现过」时，把 `<ul v-if="false">` 也放行 =
    // 最核心的变异（删掉展开能力）静默逃逸。判据必须落在 v-if 条件本身。
    expect(/<ul\s+v-if="expandedRefs\.has\(\s*it\.id\s*\)"/.test(tmpl)).toBe(true)
  })

  it('refsCount 对非数组返回 0（不崩）', () => {
    const i = script.indexOf('function refsCount')
    expect(i).toBeGreaterThan(-1)
    const body = script.slice(i, i + 260)
    expect(/Array\.isArray\(\s*refs\s*\)/.test(body)).toBe(true)
  })
})

describe('R2.6 交叉锁死: 展示的字段必须在后端 _formula_to_dict 下发', () => {
  const py = fs.readFileSync(WP_FORMULA_PY, 'utf-8')
  const i = py.indexOf('def _formula_to_dict')
  const seg = py.slice(i, i + 1600)

  it('后端 _formula_to_dict 存在且含四字段', () => {
    expect(i).toBeGreaterThan(-1)
    for (const f of ['issue_description', 'hint_text', 'last_computed_at', 'refs', 'formula_type']) {
      expect(seg).toContain(`"${f}"`)
    }
  })

  it('反向自检：抽到的函数体确实是 dict 构造（防切片失效空转）', () => {
    expect(seg).toContain('return {')
    expect(seg).toContain('"target_cell"')
  })
})

describe('R2.2 补强: lifecycle_state 中文标签的取值域必须与后端实际写入值一致', () => {
  // 🔴 **2026-08-07 浏览器实测抓出的第 14 处缺陷**：`FORMULA_LIFECYCLE_LABEL`
  // 首版按推测写 `draft / active / archived`，而后端**这三个值一个都不写** ——
  // 真实取值只有 `saved`（迁移 V104 的列默认值 + `wp_formula_service.save()`
  // 两条分支显式赋值 + 真实库 `SELECT lifecycle_state` 全为 `saved`）。
  // 首版映射恰好漏掉唯一真实存在的值 ⇒ 面板走 `?? state` 兜底显示裸英文 `saved`，
  // 正是 R2.2 要消除的「裸英文值」，只是换了个字段。
  //
  // 判据 = **读后端源码抽实际写入值**再比对前端标签表键集（交叉锁死），
  // 而不是把期望值写死在守卫里 —— 写死等于把同一个推测抄第二遍。
  const SERVICE_PY = path.join(
    REPO_ROOT,
    'backend',
    'app',
    'services',
    'wp_formula_service.py',
  )
  const MIGRATION = path.join(
    REPO_ROOT,
    'backend',
    'migrations',
    'V104__formula_runtime_outbox.sql',
  )

  /** 从后端源码抽 `lifecycle_state = "xxx"` 的赋值字面量。 */
  function backendWrittenStates(): string[] {
    const src = fs.readFileSync(SERVICE_PY, 'utf-8')
    const out = new Set<string>()
    for (const m of src.matchAll(/lifecycle_state\s*=\s*["']([\w-]+)["']/g)) {
      out.add(m[1])
    }
    return [...out]
  }

  /** 从迁移抽列默认值（新行未经 save 时的初值）。 */
  function migrationDefaultState(): string | null {
    const sql = fs.readFileSync(MIGRATION, 'utf-8')
    const m = /lifecycle_state\s+VARCHAR\(\d+\)\s+DEFAULT\s+'([\w-]+)'/i.exec(sql)
    return m ? m[1] : null
  }

  function labelKeys(): string[] {
    const inv = fs.readFileSync(INVENTORY, 'utf-8')
    const m = /FORMULA_LIFECYCLE_LABEL[^=]*=\s*\{([\s\S]*?)\n\}/.exec(inv)
    expect(m).not.toBeNull()
    return [...m![1].matchAll(/(?:^|\n)\s*([\w-]+)\s*:/g)].map((x) => x[1])
  }

  it('抽取器自检：后端确实写了 lifecycle_state，迁移确实有默认值', () => {
    const written = backendWrittenStates()
    expect(written.length).toBeGreaterThan(0)
    expect(migrationDefaultState()).toBeTruthy()
  })

  it('标签表键集 ⊇ 后端实际写入的全部取值', () => {
    const keys = new Set(labelKeys())
    const missing = backendWrittenStates().filter((s) => !keys.has(s))
    expect(missing, `标签表缺后端实际写入的取值 ${JSON.stringify(missing)} → 面板显示裸英文`).toEqual([])
  })

  it('标签表必须包含迁移的列默认值（新建行的初值）', () => {
    const def = migrationDefaultState()!
    expect(labelKeys()).toContain(def)
  })

  it('反向自检：`draft`/`active`/`archived` 后端零写入（证明首版是推测）', () => {
    const written = new Set([...backendWrittenStates(), migrationDefaultState()])
    for (const guess of ['draft', 'active', 'archived']) {
      expect(written.has(guess)).toBe(false)
    }
  })

  it('面板经 formulaLifecycleLabel 渲染，不直出裸值', () => {
    expect(/formulaLifecycleLabel\(\s*it\.lifecycle_state\s*\)/.test(tmpl)).toBe(true)
    expect(/\{\{\s*\w+\.lifecycle_state\s*\}\}/.test(tmpl)).toBe(false)
  })
})

describe('R10.4 可达性: FormulaStatusPanel 的宿主链必须完整（已登记的已知缺口）', () => {
  // 🔴🔴 **2026-08-07 浏览器实测发现的第 15 处缺陷（本轮最重要的一条）**
  //
  // R2 把面板的 issue / hint / 计算时间 / 中文类型标签都补齐了，且后端实测确实下发
  // （真实库往返：3 条公式逐条带 `issue_description` / `hint_text` / `formula_type`），
  // 但**用户在 HTML 渲染器路径下打不开这个面板**：
  //
  //   FormulaStatusPanel
  //     └─ 唯一宿主 WorkpaperSidePanel.vue（质量检查组 → 「公式」内层 Tab）
  //          └─ 唯一宿主 WorkpaperEditor.vue，靠 `showSidePanel` 控制抽屉
  //               ├─ 「📋 面板」按钮 —— **只在非 HTML 渲染器分支的工具栏里**
  //               │   （HTML 路径下该工具栏整段不渲染；浏览器实测 D1 与 A1 两个
  //               │    底稿全页 DOM 里 `面板` 字样命中 **0**）
  //               └─ `onOpenAttachment`（`@open-attachment`）—— HTML 路径唯一 setter
  //
  // 而 `open-attachment` 的**发射方只有 2 个组件**（`GtAProgramConsole` 程序表 /
  // `GtEControlTest` E 类控制测试）⇒ 审定表 / 明细表 / 披露表这些**公式真正所在的
  // sheet 一个都不发** ⇒ 面板对这些 sheet 完全不可达。
  //
  // 浏览器实测记录（项目 0ec33ac9 / 底稿 D1 68c7740e）：
  //   - 底稿目录 sheet：无 📎 行级元素；「关联附件」工具栏按钮发的是 `open-attachments`
  //     （**复数**）→ 只开 GtWpRenderer 自己的「本底稿关联附件（D1）」抽屉，与侧面板无关
  //   - D1-13 检查表的 📎 是**上传触发器**（点开是 file chooser）
  //   - D1A 程序表有 18 个 📎 按钮，点击后 DOM 里 9 个 el-drawer 无一是侧面板
  //     （`.gt-wp-side-group-tabs` 命中 0、`.formula-status-panel` 命中 0）
  //
  // ⇒ **本 spec 不修**：修它要动 `WorkpaperEditor` 的工具栏渲染条件或给 HTML 路径
  // 加入口，属渲染器/侧面板的宿主接线（半径覆盖 40+ HTML componentType），
  // 与本 spec 的「公式运行层闭环」不同半径。故按 memory「孤儿三选一」登记为
  // **已知缺口 + 守卫钉死**，并让它**修好后自动打红**提醒摘掉登记（防永久盲区）。
  const EDITOR = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'views', 'WorkpaperEditor.vue')
  const SIDE_PANEL = path.join(FE_SRC, 'components', 'workpaper', 'WorkpaperSidePanel.vue')

  const editorSrc = fs.readFileSync(EDITOR, 'utf-8')
  const sideSrc = fs.readFileSync(SIDE_PANEL, 'utf-8')

  it('宿主链前两段完好：面板 → 侧面板 → 编辑器', () => {
    expect(sideSrc).toContain('FormulaStatusPanel')
    expect(/<FormulaStatusPanel\b/.test(sideSrc)).toBe(true)
    expect(editorSrc).toContain('WorkpaperSidePanel')
    expect(/<WorkpaperSidePanel\b/.test(editorSrc)).toBe(true)
  })

  it('侧面板确有「公式」内层 Tab（否则即使抽屉打开也看不到面板）', () => {
    expect(/label="公式"\s+name="formulas"/.test(sideSrc)).toBe(true)
  })

  it('已登记缺口：HTML 路径下 showSidePanel 的唯一 setter 仍是 onOpenAttachment', () => {
    // 抽所有 setter 的上下文。
    // 🔴 正则必须容忍 `.value` —— 模板里是 `showSidePanel = !showSidePanel`（ref 自动解包），
    //    而 `<script setup>` 里是 `showSidePanel.value = true`。首版漏了 `.value`
    //    ⇒ 只抽到工具栏按钮那一处，把「附件事件也是 setter」这条判据打成假红。
    const setters = [
      ...editorSrc.matchAll(/showSidePanel(?:\.value)?\s*=\s*(?:!showSidePanel(?:\.value)?|true)/g),
    ].map((m) => editorSrc.slice(Math.max(0, m.index! - 320), m.index!))
    expect(setters.length).toBeGreaterThanOrEqual(2)
    const hasToolbarButton = setters.some((ctx) => /面板/.test(ctx))
    const hasAttachmentSetter = setters.some((ctx) =>
      /onOpenAttachment|open-attachment|附件/.test(ctx),
    )
    expect(hasAttachmentSetter, '`onOpenAttachment` 不再置 showSidePanel → 面板彻底无入口').toBe(true)

    // 🔴 stale 检测：「📋 面板」按钮仍在 **非 HTML** 分支里 ⇒ 缺口仍在。
    //    哪天有人把它移到 HTML 分支（或另加入口），下面这条会打红，
    //    提醒把本 describe 的「已知缺口」登记一并摘掉。
    const htmlBranchStart = editorSrc.indexOf('v-if="useHtmlRenderer && wpDetail"')
    const nonHtmlBranchStart = editorSrc.indexOf('toolbarButtons.filter')
    expect(hasToolbarButton).toBe(true)
    expect(htmlBranchStart).toBeGreaterThan(-1)
    expect(nonHtmlBranchStart).toBeGreaterThan(htmlBranchStart)
    const panelBtnIdx = editorSrc.indexOf('showSidePanel = !showSidePanel')
    expect(
      panelBtnIdx > nonHtmlBranchStart,
      '「📋 面板」按钮已不在非 HTML 分支 —— 若已给 HTML 路径加入口，'
        + '请摘掉本 describe 的「已知缺口」登记（它已成为盲区）',
    ).toBe(true)
  })

  it('已登记缺口：open-attachment 只源自程序表与 E 类控制测试两条链', () => {
    // 🔴 实测发射方 **6 个**，其中只有两条**到 GtWpRenderer 的链**：
    //   - `GtAProgramConsole.vue`（程序表，直接发给 GtWpRenderer）
    //   - `GtEControlTest.vue`（E 类控制测试，直接发给 GtWpRenderer）
    //   其余 3 个是 E 类内部的**再发射**（`EControlEvalStepper` / `EControlSingleForm`
    //   / `EControlSummaryTable` → `GtEControlTest`），`GtWpRenderer.vue` 自己是
    //   **向上转发**给编辑器。首版把它们一并当「发射方」并断言集合为 2 ⇒ 假红。
    //   本条要钉住的不变量是：**审定表 / 明细表 / 披露表这些公式所在的 sheet 一个都不发**。
    const roots = [path.join(FE_SRC, 'components', 'workpaper')]
    const emitters = new Set<string>()
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) {
          if (e.name === '__tests__' || e.name === 'node_modules') continue
          walk(p)
          continue
        }
        if (!/\.(vue|ts)$/.test(e.name)) continue
        const s = fs.readFileSync(p, 'utf-8')
        if (/emit\(\s*['"]open-attachment['"]/.test(s)) emitters.add(e.name)
      }
    }
    roots.forEach(walk)
    // 反向自检：扫描面非空（否则本断言恒真 = 空转）
    expect(emitters.size, '扫描面为空 —— 遍历器失效').toBeGreaterThan(0)

    //: 2026-08-07 实测的发射方全集（含 E 类内部再发射与 GtWpRenderer 向上转发）
    const BASELINE_EMITTERS = [
      'EControlEvalStepper.vue',
      'EControlSingleForm.vue',
      'EControlSummaryTable.vue',
      'GtAProgramConsole.vue',
      'GtEControlTest.vue',
      'GtWpRenderer.vue',
    ]
    expect([...emitters].sort()).toEqual(BASELINE_EMITTERS)

    // 核心不变量：公式所在的 sheet 组件（审定表 / 明细表 / 披露表）一个都不发 ⇒
    // 面板对它们不可达。这些组件名一旦出现在发射方里，说明缺口已被收窄，
    // 请复核并摘掉本 describe 的「已知缺口」登记。
    const formulaSheetHosts = [...emitters].filter((n) =>
      /Adjudication|Detail|Disclosure|AuditSheet|GtGridSheet/i.test(n),
    )
    expect(
      formulaSheetHosts,
      '公式所在 sheet 已能打开侧面板 —— 缺口已收窄，请摘掉「已知缺口」登记',
    ).toEqual([])
  })
})
