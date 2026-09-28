/**
 * K5 科目码防御守卫：禁止硬编码 `2701`（长期应付款）冒充预计负债。
 *
 * 🔴 背景（2026-09-28 实证）
 *
 * `2701` 在真实库**全部 6 个有该科目的项目**中一律是「长期应付款」（L5 循环，
 * 带 `.01 应付融资租赁款` / `.02 应付长期保证金` / `.03 应付长期借款` /
 * `.99 一年内到期` 四个子科目）；预计负债是 `2801`。底稿名亦为「预计负债」，
 * `report_config` 的 BS-068（上市）/ BS-094（国企）公式也是 `TB('2801','期末余额')`。
 *
 * 平台在修 `K5TabAdjudication` 时已确立单一真源 `k5AccountScope.ts`
 * （注释原文：「禁硬编码 2701 防污染 L5 长期应付款」），但那次只改了一个文件：
 * `K5TabLitigationCheck` 与 `K5TabProvisionCheck` 仍以 `account-code="2701"`
 * 驱动抽凭引擎 —— 抽回来的凭证属长期应付款，与预计负债/未决诉讼毫无关系，
 * 回填进底稿即错误样本；`K5TabLitigationCheck` 的 AJE 建议更是把
 * `creditAccountCode: '2701'` 与 `creditAccountName: '预计负债'` 写成码名矛盾，
 * 该分录会推给 K5-3 并进 A13 错报。
 *
 * 本守卫钉死两件事：
 *   1. K5 目录下不得出现驱动数据的 `2701` 字面量（含 account-code / accountCode）；
 *   2. 真源常量本身必须是 `2801`（防有人"顺手"把兜底改回去）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import { K5_FALLBACK_STANDARD, K5_ACCOUNT_NAME } from '../composables/k5AccountScope'

const K5_DIR = path.resolve(__dirname, '../k5')
const SCOPE_FILE = path.resolve(__dirname, '../composables/k5AccountScope.ts')

/** 递归收集 .vue 文件 */
function collectVue(dir: string): string[] {
  const out: string[] = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...collectVue(p))
    else if (e.name.endsWith('.vue')) out.push(p)
  }
  return out
}

/**
 * 剔除注释后的源码。
 *
 * 🔴 必须剔：本守卫要禁的字面量 `2701` 恰好也出现在「为什么不能用 2701」的
 * 说明性注释里（含 `account-code="2701"` 这种原状引用）。不剔注释会把正确修好的
 * 文件判成违规（首版即如此翻车）。判据只应落在可执行代码 / 真实模板绑定上。
 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')   // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')  // 块注释
    .replace(/^[ \t]*\/\/.*$/gm, '')   // 整行 // 注释
    .replace(/([^:])\/\/[^\n'"`]*$/gm, '$1') // 行尾 // 注释（避开 http://）
}

const FILES = collectVue(K5_DIR).map((f) => ({
  file: path.relative(K5_DIR, f).replace(/\\/g, '/'),
  raw: fs.readFileSync(f, 'utf-8'),
  src: stripComments(fs.readFileSync(f, 'utf-8')),
}))

describe('k5AccountScope 真源常量', () => {
  it('兜底标准码必须是 2801 预计负债（不是 2701 长期应付款）', () => {
    expect(K5_FALLBACK_STANDARD).toBe('2801')
  })

  it('科目名必须是预计负债', () => {
    expect(K5_ACCOUNT_NAME).toBe('预计负债')
  })

  it('真源文件必须留有 2701 的反面说明（防后人再次踩坑）', () => {
    const src = fs.readFileSync(SCOPE_FILE, 'utf-8')
    expect(src).toContain('2701')
    expect(src).toMatch(/长期应付款/)
  })
})

describe('K5 抽凭科目码不得硬编码 2701', () => {
  it('扫描面非空（否则断言空转）', () => {
    expect(FILES.length).toBeGreaterThan(5)
  })

  it('🔴 account-code / accountCode 不得绑定 2701 字面量', () => {
    const offenders: string[] = []
    // 匹配 account-code="2701" / :account-code="'2701'" / accountCode: '2701'
    const patterns = [
      /account-code\s*=\s*"2701"/,
      /:account-code\s*=\s*"'2701'"/,
      /accountCode\s*:\s*['"]2701['"]/,
      /creditAccountCode\s*:\s*['"]2701['"]/,
      /debitAccountCode\s*:\s*['"]2701['"]/,
      /K5_ACCOUNT_CODE\s*=\s*['"]2701['"]/,
    ]
    for (const { file, src } of FILES) {
      if (patterns.some((re) => re.test(src))) offenders.push(file)
    }
    expect(
      offenders,
      `以下 K5 组件把 2701（长期应付款）当作预计负债驱动数据：\n  ${offenders.join('\n  ')}\n` +
        '应改用 k5AccountScope 的 K5_FALLBACK_STANDARD / k5QueryCodes(props.tbSourceCodes)。',
    ).toEqual([])
  })

  it('🔴 反向自检：判据能抓到 2701 硬编码（否则上一条是假绿）', () => {
    const bad = '<GtVoucherSamplingEngine account-code="2701" phase="final" />'
    expect(/account-code\s*=\s*"2701"/.test(stripComments(bad))).toBe(true)
    const bad2 = "{ creditAccountCode: '2701', creditAccountName: '预计负债' }"
    expect(/creditAccountCode\s*:\s*['"]2701['"]/.test(stripComments(bad2))).toBe(true)
    const bad3 = "const K5_ACCOUNT_CODE = '2701'"
    expect(/K5_ACCOUNT_CODE\s*=\s*['"]2701['"]/.test(stripComments(bad3))).toBe(true)
  })

  it('🔴 剔注释器自检：注释里的 2701 说明必须被剔、代码必须保留', () => {
    const sample = [
      '// 原写 account-code="2701" —— 2701 是长期应付款',
      '<!-- 抽凭引擎（科目 2701 预计负债） -->',
      'const samplingAccountCode = K5_FALLBACK_STANDARD',
    ].join('\n')
    const out = stripComments(sample)
    expect(out).not.toContain('2701')
    expect(out, '剔过度会把代码吃掉 ⇒ 主断言变空转').toContain('K5_FALLBACK_STANDARD')
  })

  it('两个抽凭宿主必须从真源 import 科目码', () => {
    const hosts = ['contingency/K5TabLitigationCheck.vue', 'contingency/K5TabProvisionCheck.vue']
    for (const h of hosts) {
      const entry = FILES.find((f) => f.file === h)
      expect(entry, `${h} 不在扫描面内`).toBeTruthy()
      expect(
        entry!.src,
        `${h} 未从 k5AccountScope 取科目码 ⇒ 仍可能硬编码漂移`,
      ).toMatch(/from\s+['"].*k5AccountScope['"]/)
      expect(entry!.src).toContain('K5_FALLBACK_STANDARD')
    }
  })

  /**
   * 🔴 联动断裂守卫：`K5TabAdjudication` 已改用 `k5AccountCode()`（解析值/兜底 2801）
   * 发 `substantive:adjudicated` 事件，而两个 Disclosure 组件若仍按 `2701` 监听/发事件，
   * 事件永不匹配 ⇒ 附注自动同步静默失效（比金额错更难发现）。
   */
  it('附注同步与调整分录不得用 2701 作为事件/科目载荷', () => {
    const offenders: string[] = []
    for (const { file, src } of FILES) {
      if (/accountCode\s*:\s*['"]2701['"]/.test(src)) offenders.push(`${file}（事件载荷）`)
      if (/K5_ACCOUNT_CODE\s*=\s*['"]2701['"]/.test(src)) offenders.push(`${file}（模块常量）`)
      if (/\|\|\s*['"]2701['"]/.test(src)) offenders.push(`${file}（兜底值）`)
    }
    expect(
      offenders,
      '以下位置仍用 2701 驱动附注同步/调整分录科目，会与已改为 2801 的 ' +
        'K5TabAdjudication 事件口径不匹配（附注自动同步静默失效）：\n  ' +
        offenders.join('\n  '),
    ).toEqual([])
  })
})
