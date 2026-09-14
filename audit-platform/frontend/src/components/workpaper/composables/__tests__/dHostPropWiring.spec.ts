/**
 * dHostPropWiring.spec.ts — D 循环宿主传参 & 溯源面板属性名守卫
 *
 * **Validates: Requirements 3.5, 4.2, 4.4, 4.6**
 * Properties: 13, 14
 *
 * 为什么必须有这个守卫
 * --------------------
 * 平台已实证两类「四层验证全绿、只有浏览器能发现」的静默失效：
 *
 * 1. **宿主漏传 prop = 静默锁死** —— 子组件声明了 `htmlData` 而宿主不传，
 *    `props.htmlData` 恒 `undefined` ⇒ 溯源面板永不渲染、带入按钮恒灰。
 *    实测本 spec 开工前 **6 个 D 宿主全部没传**（只有 D4 传了），
 *    即 `dCycleAccountScope.ts` 在接线前是 dead output。
 * 2. **传「不存在的 prop」= 静默失效** —— 未知属性会落到根元素当 HTML 属性，
 *    Volar 零诊断 / vitest 全绿 / Vite 200。G5 溯源面板曾因此从未渲染过。
 *
 * 故本守卫从 SFC 的 `defineProps` **动态抽取**合法属性名再比对，不写死清单。
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/ (Task 17)
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

// `composables/__tests__/` 下回退 7 级到仓库根（照抄 gCycleAccountScope.spec.ts 的
// 既有范式；层数写错会 ENOENT，表现为「文件级失败」而非断言失败 —— 极易被当噪声跳过）
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const WP_DIR = path.join(
  REPO_ROOT,
  'audit-platform/frontend/src/components/workpaper',
)
const PANEL = path.join(WP_DIR, 'shared/WpFourTableSourcePanel.vue')

/** 7 个 D 循环的宿主 SFC 与其审定表子组件标签名 */
const HOSTS: ReadonlyArray<{ wp: string; host: string; tag: string }> = [
  { wp: 'D1', host: 'GtD1NotesReceivable.vue', tag: 'D1TabAdjudication' },
  { wp: 'D2', host: 'GtD2AccountsReceivable.vue', tag: 'D2TabAdjudication' },
  { wp: 'D3', host: 'GtD3PrepaidAccounts.vue', tag: 'D3TabAdjudication' },
  { wp: 'D4', host: 'GtD4OperatingRevenue.vue', tag: 'D4TabAdjudication' },
  { wp: 'D5', host: 'GtD5ReceivablesFinancing.vue', tag: 'D5TabAdjudication' },
  { wp: 'D6', host: 'GtD6ContractAssets.vue', tag: 'D6TabAdjudication' },
  { wp: 'D7', host: 'GtD7ContractLiabilities.vue', tag: 'D7TabAdjudication' },
]

function read(p: string): string {
  return fs.readFileSync(p, 'utf-8')
}

/** 剥 HTML 注释与 JS 行/块注释（模板里的注释会藏反例文字） */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/**
 * 截出某个组件标签的完整属性区（从 `<Tag` 到配对的 `>`）。
 *
 * 🔴 不能用 `/<Tag[^>]*>/` —— 属性值里可能含 `>`（如 `:x="a > b"`）。
 * 也不能只按标签名前缀匹配：`<D1TabAdjudicationFoo` 会被 `<D1TabAdjudication` 命中，
 * 故要求标签名后紧跟空白或 `/>`（memory 已登记的「标签存在性断言必须带边界」）。
 */
function tagAttrBlock(src: string, tag: string): string | null {
  const re = new RegExp(`<${tag}(?=[\\s/>])`)
  const m = re.exec(src)
  if (!m) return null
  let i = m.index + m[0].length
  let quote = ''
  while (i < src.length) {
    const ch = src[i]
    if (quote) {
      if (ch === quote) quote = ''
    } else if (ch === '"' || ch === "'") {
      quote = ch
    } else if (ch === '>') {
      return src.slice(m.index, i + 1)
    }
    i += 1
  }
  return null
}

/** 从 `defineProps<{...}>()` 抽属性名（含 withDefaults 包裹形态） */
function definePropNames(src: string): string[] {
  const code = stripComments(src)
  const at = code.indexOf('defineProps<')
  if (at < 0) return []
  const open = code.indexOf('{', at)
  if (open < 0) return []
  let depth = 0
  let end = -1
  for (let i = open; i < code.length; i += 1) {
    if (code[i] === '{') depth += 1
    else if (code[i] === '}') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) return []
  const body = code.slice(open + 1, end)
  const names: string[] = []
  for (const line of body.split('\n')) {
    const m = /^\s*([A-Za-z_$][\w$]*)\s*\??\s*:/.exec(line)
    if (m) names.push(m[1])
  }
  return names
}

const kebab = (s: string) => s.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()

/** 抽某标签属性区里出现的属性名（去掉 `:` / `v-bind:` 前缀，忽略指令） */
function usedAttrNames(block: string): string[] {
  const out: string[] = []
  const re = /(?:^|\s)(v-bind:|:|@)?([A-Za-z][\w.-]*)\s*=/g
  let m: RegExpExecArray | null
  while ((m = re.exec(block))) {
    const prefix = m[1] || ''
    const name = m[2]
    if (prefix === '@') continue
    if (/^v-/.test(name)) continue
    if (['key', 'ref', 'class', 'style', 'is'].includes(name)) continue
    out.push(name)
  }
  return out
}

// ───────────────── Property 13：宿主已传 `:html-data` ─────────────────

describe('Property 13: 宿主向审定表透传 html-data', () => {
  it('7 个宿主文件都存在（防路径写错导致断言空转）', () => {
    for (const h of HOSTS) {
      expect(fs.existsSync(path.join(WP_DIR, h.host)), h.host).toBe(true)
    }
  })

  it.each(HOSTS)('$wp 宿主向 $tag 传了 :html-data', ({ host, tag }) => {
    const src = stripComments(read(path.join(WP_DIR, host)))
    const block = tagAttrBlock(src, tag)
    expect(block, `${host} 未渲染 <${tag}>`).toBeTruthy()
    const hasBind =
      /(?::|v-bind:)html-data\s*=/.test(block!) || /v-bind\s*=\s*"\$props"/.test(block!)
    expect(
      hasBind,
      `🔴 ${host} 未向 <${tag}> 传 :html-data —— 子组件 props.htmlData 恒 undefined，` +
        `溯源面板永不渲染、带入按钮恒灰，而 Volar/vitest/Vite 四层全绿`,
    ).toBe(true)
  })

  it('反向自检：标签名边界生效（<Tag 不得被 <TagFoo 命中）', () => {
    const fake = '<D1TabAdjudicationFoo :wp-id="x" />'
    expect(tagAttrBlock(fake, 'D1TabAdjudication')).toBeNull()
    expect(tagAttrBlock('<D1TabAdjudication :wp-id="x" />', 'D1TabAdjudication')).toBeTruthy()
  })

  it('反向自检：属性值含 > 时不提前截断', () => {
    const s = '<Foo :cond="a > b" :html-data="hd" />'
    const block = tagAttrBlock(s, 'Foo')!
    expect(block).toContain(':html-data')
  })

  it('反向自检：不传时判据确实为假（证明上面的断言不是空话）', () => {
    const s = '<D2TabAdjudication :wp-id="x" :project-id="y" />'
    const block = tagAttrBlock(s, 'D2TabAdjudication')!
    expect(/(?::|v-bind:)html-data\s*=/.test(block)).toBe(false)
  })
})

// ────── Property 14：溯源面板属性名与 defineProps 一致 ──────

describe('Property 14: WpFourTableSourcePanel 调用点属性名合法', () => {
  it('面板文件存在且能抽出 props（防解析失效空转）', () => {
    expect(fs.existsSync(PANEL)).toBe(true)
    const names = definePropNames(read(PANEL))
    expect(names.length).toBeGreaterThanOrEqual(5)
    // 锚点：这几个必填/常用 prop 必须被抽到，否则解析器坏了
    expect(names).toContain('sourceCodes')
    expect(names).toContain('grossLabel')
    expect(names).toContain('provisionLabel')
  })

  it('全仓调用点的属性名都在 defineProps 里（含 D 类新接入点）', () => {
    const legal = new Set(definePropNames(read(PANEL)).map(kebab))
    const bad: string[] = []
    for (const file of walkVue(WP_DIR)) {
      const src = stripComments(read(file))
      if (!/<WpFourTableSourcePanel(?=[\s/>])/.test(src)) continue
      const block = tagAttrBlock(src, 'WpFourTableSourcePanel')
      if (!block) continue
      for (const attr of usedAttrNames(block)) {
        if (!legal.has(kebab(attr))) {
          bad.push(`${path.relative(WP_DIR, file)} → ${attr}`)
        }
      }
    }
    expect(
      bad,
      '🔴 传了 WpFourTableSourcePanel 不存在的属性 —— Vue 会静默落到根元素当 HTML 属性，' +
        '该功能永不生效且四层验证全绿：\n' + bad.join('\n'),
    ).toEqual([])
  })

  it('反向自检：不存在的属性名会被判非法', () => {
    const legal = new Set(definePropNames(read(PANEL)).map(kebab))
    expect(legal.has('source-codes')).toBe(true)
    // G5 曾真实踩过的四个错名
    for (const wrong of ['gross-standard', 'resolved-from', 'report-row-code', 'hint']) {
      expect(legal.has(wrong), `${wrong} 不该是合法 prop`).toBe(false)
    }
  })

  it('反向自检：扫描面非空（防 walk 失效让断言恒绿）', () => {
    let n = 0
    for (const f of walkVue(WP_DIR)) {
      if (/<WpFourTableSourcePanel(?=[\s/>])/.test(stripComments(read(f)))) n += 1
    }
    expect(n, '一个调用点都没扫到 —— walk 或正则失效').toBeGreaterThanOrEqual(20)
  })
})

function* walkVue(dir: string): Generator<string> {
  for (const name of fs.readdirSync(dir)) {
    if (name === 'node_modules' || name === '__snapshots__') continue
    const p = path.join(dir, name)
    const st = fs.statSync(p)
    if (st.isDirectory()) yield* walkVue(p)
    else if (name.endsWith('.vue')) yield p
  }
}

// ────── Property 15：带入操作的三态语义（纯函数层面锁死） ──────

describe('Property 15: 带入语义（手工优先 / 只覆盖命中 / 清零有提示）', () => {
  it('dCycleAccountScope 暴露了区分「无科目」与「余额为 0」的判据', async () => {
    const m = await import('../dCycleAccountScope')
    expect(typeof m.isDAccountAbsent).toBe('function')
    expect(typeof m.dSlotClosing).toBe('function')
    // 无科目 → absent 为真、金额为 null
    const absent = { slots: { gross: { found: false, state: 'no_account' } } } as never
    expect(m.isDAccountAbsent(absent)).toBe(true)
    expect(m.dSlotClosing(absent)).toBeNull()
    // 余额为 0 → absent 为假、金额为 0（**不是 null**）
    const zero = {
      slots: { gross: { found: true, state: 'ok', closing: 0, tb_rows_count: 2 } },
    } as never
    expect(m.isDAccountAbsent(zero)).toBe(false)
    expect(m.dSlotClosing(zero)).toBe(0)
  })

  it('反向自检：Number(null)===0 这种写法会混淆两态', () => {
    // 复现被禁的写法 —— 证明上面的断言不是空话
    expect(Number(null) === 0).toBe(true)
    expect(Number(null)).toBe(0)
  })
})
