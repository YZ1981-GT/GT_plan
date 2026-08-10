/**
 * H9 审定表消费 `tb_values` / `tb_source_codes` 的接线守卫。
 *
 * **缺陷背景**（2026-08-07 浏览器实测）
 *
 * 改造前 `H9TabAdjudication.vue` 里 `tb_values` / `tbValues` 计数**皆为 0**、
 * 连 `htmlData` prop 都没声明 ⇒ 后端按语义定位算出的租赁负债净额（94,219.84）
 * 在审定表界面**完全看不到**，科目码只能退到 `h9Scope` 兜底常量 = dead output；
 * 同时 `useAdjudicationBringIn` 的 `subjectPrefix`/`subjectCode` 写死 `'2601'`
 * ⇒ 该项目实际用 `2651` 族时「带入调整」一条分录都拉不到。
 *
 * 三层都要钉：
 * 1. 宿主 `GtH9LeaseLiabilities.vue` 必须传 `:html-data`（漏传即静默失效，Vue 不报错）
 * 2. 组件必须声明 `htmlData` prop 并从中取 `tb_source_codes` / `tb_values`
 * 3. 科目码必须走**运行态解析**（`h9Scope.grossCode(...)`），不得写死族字面量
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** 双哨兵向上找仓库根（单哨兵不够稳，见 memory 铁律） */
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'services', 'four_table', 'parent_check.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵均需存在）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper')

const HOST = path.join(FE, 'GtH9LeaseLiabilities.vue')
const TAB = path.join(FE, 'h9', 'core', 'H9TabAdjudication.vue')
const BRING_IN = path.join(FE, 'composables', 'useAdjudicationBringIn.ts')
const PULL = path.join(FE, 'composables', 'useAdjudicationAdjustmentPull.ts')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 剥注释（本守卫与被测源码的注释里都会写出被禁的反例） */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`\\])\/\/[^\n]*/g, '$1')
}

/** 截取某个开标签的完整属性区（按 `<` 到匹配的 `>`，不用固定字符窗口） */
function openTag(src: string, tagName: string): string {
  const re = new RegExp(`<${tagName}(?=[\\s/>])`)
  const m = re.exec(src)
  expect(m, `未找到 <${tagName} 标签（判据失效）`).toBeTruthy()
  const start = m!.index
  const end = src.indexOf('>', start)
  expect(end, `<${tagName} 开标签未闭合`).toBeGreaterThan(start)
  return src.slice(start, end + 1)
}

describe('自检：helper 不被相似标签名骗过', () => {
  it('openTag 按标签名边界匹配', () => {
    const fixture = '<FooREMOVED a="1"><Foo b="2">'
    expect(openTag(fixture, 'Foo')).toContain('b="2"')
    expect(openTag(fixture, 'Foo')).not.toContain('a="1"')
  })

  it('stripComments 确实剥掉了 HTML 注释里的反例', () => {
    const raw = read(HOST)
    expect(raw).toContain('漏传即静默失效')
    expect(stripComments(raw)).not.toContain('漏传即静默失效')
  })
})

describe('Property: 宿主必须给 H9 审定表传 :html-data', () => {
  const src = stripComments(read(HOST))

  it('H9TabAdjudication 开标签含 :html-data', () => {
    const tag = openTag(src, 'H9TabAdjudication')
    expect(tag, 'H9 审定表未收到 :html-data ⇒ 溯源面板与 TB 核对区永不渲染').toMatch(
      /:html-data\s*=/,
    )
  })

  it('传的是 props.htmlData 而非局部变量', () => {
    const tag = openTag(src, 'H9TabAdjudication')
    expect(tag).toMatch(/:html-data\s*=\s*"props\.htmlData"/)
  })

  it('其余必填 prop 未被漏掉', () => {
    const tag = openTag(src, 'H9TabAdjudication')
    for (const p of [':wp-id', ':project-id', ':all-responses', ':is-readonly']) {
      expect(tag, `缺 ${p}`).toContain(p)
    }
  })
})

describe('Property: 审定表消费 tb_source_codes 与 tb_values', () => {
  const raw = read(TAB)
  const src = stripComments(raw)

  it('声明了 htmlData prop', () => {
    expect(src).toMatch(/htmlData\?\s*:/)
  })

  it('tb_source_codes 顶层优先 + project_context 兼容', () => {
    expect(src).toContain('tb_source_codes')
    expect(
      src,
      '必须兼容 project_context 落点（平台两套并存，见 memory）',
    ).toMatch(/project_context\??\.tb_source_codes/)
  })

  it('读了 tb_values', () => {
    expect(src).toContain('tb_values')
  })

  it('渲染了共享溯源面板', () => {
    expect(src).toMatch(/<WpFourTableSourcePanel(?=[\s/>])/)
    const tag = openTag(src, 'WpFourTableSourcePanel')
    expect(tag).toMatch(/:source-codes\s*=/)
    expect(tag, '缺 gross-label（面板必填 prop）').toMatch(/gross-label\s*=/)
  })

  it('面板声明了备抵槽（多槽循环必需，否则未确认融资费用来源看不到）', () => {
    const tag = openTag(src, 'WpFourTableSourcePanel')
    expect(tag).toMatch(/:extra-slot-keys\s*=/)
    expect(src).toMatch(/H9_EXTRA_SLOT_KEYS\s*=\s*\[\s*'unearned_finance'/)
  })

  it('import 了面板组件（漏 import 时 get_diagnostics 查不出）', () => {
    expect(src).toMatch(/import\s+WpFourTableSourcePanel\s+from/)
  })
})

describe('Property: 三口径核对区可见性与「无此科目」区分', () => {
  const src = stripComments(read(TAB))

  it('render 未下发 tb_values 时整块不渲染（不显示一排 0）', () => {
    expect(src).toMatch(/hasTbValues/)
    expect(src, 'TB 核对区必须由 hasTbValues 门控').toMatch(
      /v-if\s*=\s*"hasTbValues"/,
    )
  })

  it('「本项目无此科目」与「余额为 0」分开表达', () => {
    expect(src).toContain('本项目无此科目')
    expect(src, '数值归一必须把 null/空串与 0 区分').toMatch(
      /=== null\s*\|\|[\s\S]{0,80}=== ''/,
    )
  })

  it('三口径列齐全（四表叶子 / 试算表 / 底稿审定）', () => {
    expect(src).toContain('四表叶子')
    expect(src).toContain('试算表')
    expect(src).toContain('底稿审定合计')
  })

  it('暴露了 trial_net_of 追溯（备抵扣减可见）', () => {
    expect(src).toContain('trial_net_of')
    expect(src).toMatch(/trialNetOf/)
  })

  it('差异为 null 时显示「无法比对」而不是 0', () => {
    expect(src).toContain('无法比对')
  })
})

describe('Property: 科目码走运行态解析，不写死族字面量', () => {
  const src = stripComments(read(TAB))

  it('leaseLiabilityCode 由 h9Scope.grossCode 派生', () => {
    expect(src).toMatch(/leaseLiabilityCode\s*=\s*computed\([\s\S]{0,120}h9Scope\.grossCode/)
  })

  it('unearnedFinanceCode 由 h9Scope.slotCodes 派生', () => {
    expect(src).toMatch(
      /unearnedFinanceCode\s*=\s*computed\([\s\S]{0,200}h9Scope\.slotCodes\(/,
    )
  })

  it.each([
    ['2205', '合同负债（D7 域），历史错码'],
    ['2651', '新族字面量'],
  ])('模板与逻辑里不得出现 %s 作科目码字面量', (code) => {
    // 允许出现在 h9Scope 的 wrongLegacyCodes 声明侧（那在别的文件），
    // 本组件源码里一律不得有
    const hits = [...src.matchAll(new RegExp(`'${code}'`, 'g'))]
    expect(hits.length, `发现 ${hits.length} 处 '${code}' 字面量`).toBe(0)
  })

  it('带入调整的 subjectPrefix/subjectCode 传 getter（延迟求值）', () => {
    expect(
      src,
      'subjectPrefix 传字符串快照会在「htmlData 后到」路径上永久锁死兜底码',
    ).toMatch(/subjectPrefix:\s*\(\)\s*=>/)
    expect(src).toMatch(/subjectCode:\s*\(\)\s*=>/)
    expect(src).toMatch(/subjectLabel:\s*\(\)\s*=>/)
  })

  it('禁用 as any 强转把 ref 塞进字符串入参', () => {
    expect(
      src,
      '`subjectPrefix: xxx as any` 会让请求参数变成 [object Object]',
    ).not.toMatch(/subject(?:Prefix|Code|Label):\s*\w+\s+as\s+any/)
  })
})

describe('Property: 共享 composable 的 Resolvable 放宽是 additive', () => {
  const pull = stripComments(read(PULL))
  const bring = stripComments(read(BRING_IN))

  it('导出了 Resolvable 与 unwrap', () => {
    expect(pull).toMatch(/export type Resolvable</)
    expect(pull).toMatch(/export function unwrap</)
  })

  it('subjectPrefix 在求值点经 unwrap（不是直接 Array.isArray）', () => {
    expect(pull).toMatch(/unwrap\(opts\.subjectPrefix\)/)
    expect(
      pull,
      '仍保留 `Array.isArray(opts.subjectPrefix)` 会让 getter 形态落空',
    ).not.toMatch(/Array\.isArray\(opts\.subjectPrefix\)/)
  })

  it('事件载荷里的 subjectCode 已求值（传 ref 会让 handler 匹配恒不成立）', () => {
    expect(bring).toMatch(/accountCode:\s*unwrap\(opts\.subjectCode\)/)
  })

  it('提示文案里的 subjectLabel 已求值', () => {
    expect(bring).toMatch(/unwrap\(opts\.subjectLabel\)/)
  })

  it('三个入参类型均为 Resolvable（additive，既有传字符串调用方不变）', () => {
    expect(bring).toMatch(/subjectPrefix:\s*Resolvable</)
    expect(bring).toMatch(/subjectCode:\s*Resolvable</)
    expect(bring).toMatch(/subjectLabel:\s*Resolvable</)
  })

  it('空前缀时不发请求（getter 未就绪的保护）', () => {
    expect(pull).toMatch(/if\s*\(!prefixes\.length\)\s*return/)
  })
})
