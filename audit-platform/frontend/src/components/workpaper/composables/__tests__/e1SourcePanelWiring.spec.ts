/**
 * E1 取数溯源面板扩展守卫（Task 9）
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/
 * Requirements 1.8, 10.7
 *
 * 🔴 头号判据 = **prop 键集交叉锁死**。Vue 对「传了不存在的 prop」不报错（未知
 * 属性落到根元素当 HTML 属性）⇒ Volar 零诊断 / vitest 全绿 / Vite transform 200，
 * 四层验证全查不出，而组件内部读到 `undefined` ⇒ 整块静默不渲染。平台已踩过两次
 * （G5 溯源面板从未渲染过 / G6 传 `report-row` 而真实 prop 是 `fallback-row-code`）。
 *
 * 判据做法：从面板 SFC 的 `defineProps<{...}>()` **动态抽**合法 prop 名（转 kebab），
 * 与宿主调用点上的属性求差集；并断言必填 prop 确实传了。
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    try {
      readFileSync(resolve(dir, 'backend/app/services/four_table/e1_bank_accounts.py'))
      readFileSync(resolve(dir, 'audit-platform/frontend/package.json'))
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('定位不到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const read = (rel: string) => readFileSync(resolve(ROOT, rel), 'utf-8').replace(/\r\n/g, '\n')

const PANEL_REL = 'audit-platform/frontend/src/components/workpaper/e1/E1FourTableSourcePanel.vue'
const HOST_REL = 'audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue'
const PANEL = read(PANEL_REL)
const HOST = read(HOST_REL)

// ─────────────────────────── helper ─────────────────────────────────────────

function matchPair(src: string, from: number, open: string, close: string): number {
  let depth = 0
  for (let i = from; i < src.length; i += 1) {
    if (src[i] === open) depth += 1
    else if (src[i] === close) {
      depth -= 1
      if (depth === 0) return i
    }
  }
  return -1
}

/** 抽 `defineProps<{ ... }>()` 的类型体（花括号配对，容忍嵌套对象类型）。 */
function definePropsBody(src: string): string {
  const i = src.indexOf('defineProps<')
  if (i < 0) throw new Error('找不到 defineProps<')
  const brace = src.indexOf('{', i)
  const end = matchPair(src, brace, '{', '}')
  if (end < 0) throw new Error('defineProps 类型体不闭合')
  return src.slice(brace + 1, end)
}

function camelToKebab(s: string): string {
  return s.replace(/[A-Z]/g, m => `-${m.toLowerCase()}`)
}

/** 合法 prop 名（camelCase + kebab-case 两种写法都算）。 */
function legalProps(src: string): { camel: string[]; kebab: string[] } {
  const body = definePropsBody(src)
  const stripped = body
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(l => !l.trim().startsWith('//'))
    .join('\n')
  const camel = [...stripped.matchAll(/^\s*(\w+)\??\s*:/gm)].map(m => m[1])
  return { camel, kebab: camel.map(camelToKebab) }
}

/** 抽宿主里某组件调用点的属性名（去掉 `v-*` / `@` / 保留字）。 */
function callSiteAttrs(host: string, tag: string): { raw: string; attrs: string[] } {
  const m = new RegExp(`<${tag}[\\s\\S]*?/>`).exec(host)
  if (!m) throw new Error(`宿主里找不到 <${tag}`)
  const raw = m[0]
  const attrs = [...raw.matchAll(/(?:^|\s)(:?[a-zA-Z][\w-]*)=/g)]
    .map(x => x[1])
    .filter(a => !a.startsWith('v-') && !a.startsWith('@'))
    .map(a => (a.startsWith(':') ? a.slice(1) : a))
    .filter(a => !['key', 'ref', 'class', 'style', 'id'].includes(a))
  return { raw, attrs }
}

// ═══════════════════ helper 自检 ════════════════════════════════════════════

describe('helper 自检（防判据空转）', () => {
  it('definePropsBody 容忍嵌套对象类型', () => {
    const fake = 'const p = defineProps<{\n  a: { x: number }\n  b?: string\n}>()'
    const body = definePropsBody(fake)
    expect(body).toContain('a:')
    expect(body).toContain('b?:')
  })

  it('legalProps 抽出顶层键并剥注释', () => {
    const fake = [
      'const p = defineProps<{',
      '  /** doc: 注释里的 fake: 1 不算 */',
      '  realOne: string',
      '  // lineComment: 2',
      '  twoWords?: number',
      '}>()',
    ].join('\n')
    const { camel, kebab } = legalProps(fake)
    expect(camel).toEqual(['realOne', 'twoWords'])
    expect(kebab).toEqual(['real-one', 'two-words'])
  })

  it('callSiteAttrs 排除 v-if / @event / 保留字', () => {
    const fake = '<Foo v-if="ok" :bar="x" baz="y" @go="f" class="c" />'
    const { attrs } = callSiteAttrs(fake, 'Foo')
    expect(attrs.sort()).toEqual(['bar', 'baz'])
  })

  it('找不到目标时抛错', () => {
    expect(() => callSiteAttrs('<div/>', 'Nope')).toThrow()
    expect(() => definePropsBody('const x = 1')).toThrow()
  })
})

// ═══════════════════ prop 键集交叉锁死 ══════════════════════════════════════

describe('🔴 溯源面板 prop 键集交叉锁死（Requirements 1.8）', () => {
  it('宿主传的每个属性都是面板真实声明的 prop', () => {
    const { kebab, camel } = legalProps(PANEL)
    expect(kebab.length, 'prop 抽取失效').toBeGreaterThan(3)
    const { attrs } = callSiteAttrs(HOST, 'E1FourTableSourcePanel')
    const legal = new Set([...kebab, ...camel])
    const illegal = attrs.filter(a => !legal.has(a))
    expect(illegal, `宿主传了面板不存在的 prop：${illegal.join(', ')}`).toEqual([])
  })

  it('必填 prop（无 ?）必须真的传了', () => {
    const body = definePropsBody(PANEL)
    const required = [...body.matchAll(/^\s*(\w+)\s*:/gm)].map(m => camelToKebab(m[1]))
    const { attrs } = callSiteAttrs(HOST, 'E1FourTableSourcePanel')
    for (const r of required) {
      expect(attrs, `必填 prop ${r} 未传（整块会不渲染）`).toContain(r)
    }
  })

  it('accounts prop 已声明且宿主已传（否则账户级两块永不渲染）', () => {
    const { camel } = legalProps(PANEL)
    expect(camel).toContain('accounts')
    const { raw } = callSiteAttrs(HOST, 'E1FourTableSourcePanel')
    expect(raw).toContain(':accounts=')
  })
})

// ═══════════════════ 面板渲染内容 ═══════════════════════════════════════════

describe('账户级溯源块内容（Requirements 1.8, 10.7）', () => {
  it('渲染账户数 / parsed_level 分布 / 各槽勾稽 diff', () => {
    expect(PANEL).toContain('accountCount')
    expect(PANEL).toContain('levelRows')
    expect(PANEL).toContain('reconcileRows')
    // diff 列存在且按 ok 分色
    expect(PANEL).toMatch(/row\.diff/)
    expect(PANEL).toMatch(/row\.ok\s*\?\s*'success'\s*:\s*'danger'/)
  })

  it('勾稽不平时有 danger 提示（不是只在表格里显示数字）', () => {
    expect(PANEL).toContain('hasReconcileDiff')
    expect(PANEL).toMatch(/v-if="hasReconcileDiff"[\s\S]{0,200}?type="danger"/)
  })

  it('unassigned 告警块存在且列出账号与金额', () => {
    expect(PANEL).toContain('unassignedRows')
    expect(PANEL).toMatch(/v-if="unassignedRows\.length"/)
    expect(PANEL).toContain('unassignedTotalClosing')
    // 明确写出「aux 里有账户但科目定位未覆盖」的成因
    expect(PANEL).toContain('科目语义定位未覆盖')
  })

  it('parsed_level 作数据质量指标：level 3 占比高时提示', () => {
    expect(PANEL).toContain('level3Ratio')
    expect(PANEL).toContain('showLevelWarn')
    expect(PANEL).toMatch(/level3Ratio[\s\S]{0,80}?0\.5/)
  })

  it('「未传 accounts」与「传了但账户为空」是两种状态', () => {
    // accountsEmpty 只在 props.accounts 存在且账户数为 0 时为真
    expect(PANEL).toMatch(/accountsEmpty\s*=\s*computed\(\(\)\s*=>\s*!!props\.accounts\s*&&/)
    expect(PANEL).toMatch(/v-if="accountsEmpty"/)
    expect(PANEL).toContain('已退回叶子科目口径')
  })

  it('金额一律走 displayPrefs.fmtAmount（平台金额单一真源）', () => {
    const tpl = PANEL.slice(PANEL.indexOf('<template>'))
    // 账户级新增的金额单元格数（勾稽 3 + 明细 1 + 合计 1 + unassigned 2）
    const hits = (tpl.match(/displayPrefs\.fmtAmount\(/g) || []).length
    expect(hits).toBeGreaterThanOrEqual(11)
    expect(tpl, '禁用 toLocaleString（绕过平台金额偏好）').not.toContain('toLocaleString')
  })

  it('DisplayPrefs_Key 从 composables/displayPrefsKey 引入（不是 stores）', () => {
    expect(PANEL).toContain("import { DisplayPrefs_Key } from '../composables/displayPrefsKey'")
    expect(PANEL).not.toMatch(/import\s*\{[^}]*DisplayPrefs_Key[^}]*\}\s*from\s*'@\/stores\/displayPrefs'/)
  })

  it('中文标签集中在 SLOT_LABELS / LEVEL_LABELS（模板不写字面量）', () => {
    expect(PANEL).toContain('const SLOT_LABELS')
    expect(PANEL).toContain('const LEVEL_LABELS')
    for (const slot of ['bank', 'other', 'finance_co']) {
      expect(PANEL).toMatch(new RegExp(`${slot}:\\s*'`))
    }
  })
})

// ═══════════════════ 宿主侧只给该给的 sheet 传 ═══════════════════════════════

describe('宿主只在 E1-3 / E1-10 传 accounts（Requirements 1.8）', () => {
  it('ftAccountsForPanel 按 sheet 门控，其余 sheet 传 undefined', () => {
    const i = HOST.indexOf('const ftAccountsForPanel')
    expect(i).toBeGreaterThan(0)
    const seg = HOST.slice(i, i + 400)
    expect(seg).toContain("'E1-3'")
    expect(seg).toContain("'E1-10'")
    expect(seg).toContain('undefined')
    // E1-2 现金 / E1-4 数字货币没有账户维度 ⇒ 不得出现在门控清单里
    expect(seg).not.toContain("'E1-2'")
    expect(seg).not.toContain("'E1-4'")
  })

  it('叶子来源为空但账户级有数据时面板仍显示（否则溯源不可达）', () => {
    const { raw } = callSiteAttrs(HOST, 'E1FourTableSourcePanel')
    expect(raw).toContain('ftHasAccountSource')
    expect(HOST).toContain('const ftHasAccountSource')
  })
})
