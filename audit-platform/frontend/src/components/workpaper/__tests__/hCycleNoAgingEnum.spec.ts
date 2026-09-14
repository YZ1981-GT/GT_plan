/**
 * H 类禁引账龄枚举 + 禁写死骨架行数（spec `h-cycle-…` Task 15 / R9.1~R9.4 · R8.3~R8.5）
 *
 * ## 裁决 2：H 类不引入账龄枚举
 *
 * 长期资产**没有账龄维度**。H4「库龄」与应收账龄不同构（同 J2「到期分析」定论）：
 * 账龄是「已发生多久」的**过去**分段且平台有项目级配置（3/5 年段自定义），
 * 而库龄是工程物资的库存时长、H6 的「挂账关注」是「转入清理超 1 年」的风险标记。
 * 套用 `disclosureAgingLabels` / `useAgingConfig` 会把别的循环的分段口径带进来。
 *
 * 🔴 **本守卫当前是「防回退」性质**（实证命中数已是 0）⇒ 必须配
 * 「扫描面非空」与「注入一处引用必红」两条自检，否则它可能只是**空转**
 * （路径写错 / glob 失效 / 剥注释剥过头，都会让 0 命中变成假绿）。
 *
 * ## H4 库龄：保持自由输入（宁缺勿造）
 *
 * 源模板 `H4 工程物资.xlsx` 的 `明细表H4-2!AV8` 只有列头「库龄」二字 ——
 * **无数据验证、无区间字面量**（AV 列全列仅 3 个值：索引号 / 页次 / 库龄）
 * ⇒ 源模板未给出库龄的取值域，自造「1年以内/1-2年/…」等于绕过裁决 2 造一套账龄。
 * 故守卫只钉「不得接账龄枚举、不得自造区间常量」，不强制改成 `el-select`。
 *
 * ## 禁写死骨架行数
 *
 * `blankRows(p, 3|5|10)` 会让动态区**预置空占位行**，而空占位行会被同步推成
 * 「占位披露行」污染附注 ⇒ 骨架行数必须由 seed 行数派生（`max(seed 行数, 1)`）。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// 本文件位于 .../components/workpaper/__tests__/ → 回仓库根需 6 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../..')
const WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

/** 账龄枚举相关符号（平台单一真源 `composables/disclosureAgingLabels.ts` 及其消费入口） */
const AGING_SYMBOLS = [
  'disclosureAgingLabels',
  'useAgingConfig',
  'AGING_BANDS',
  'toDisclosureAgingLabel',
  'lookupDisclosureAgingLabel',
  'buildDisclosureAgingLabelMap',
  'DISCLOSURE_AGING_WITHIN1_SOE',
] as const

/**
 * H 类里唯一允许的本地分段选项：H4 工程物资**库龄**（库存时长）。
 *
 * 允许的三个前提（缺一即红）：
 * 1. 命名不含 `AGING`（原名 `AGING_OPTS` 会诱导后来者统一到平台账龄枚举）
 * 2. 就地声明 + 注释写明「与账龄无关 / 源模板无取值域」
 * 3. **不得进披露载荷**（实证 `h4NoteSectionMap.ts` / `h4DisclosureSyncPayload.ts` /
 *    两个 H4 披露 Tab 对「库龄」与 `aging` 字段命中数全为 0）—— 这条是防污染附注的真红线
 */
const H4_STOCK_AGE = {
  file: 'h4/core/H4TabDetail.vue',
  constName: 'STOCK_AGE_OPTS',
  /** 披露侧禁止出现库龄的文件 */
  disclosureFiles: [
    'composables/h4NoteSectionMap.ts',
    'composables/h4DisclosureSyncPayload.ts',
    'h4/core/H4TabDisclosureListed.vue',
    'h4/core/H4TabDisclosureSoe.vue',
  ],
} as const

export function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 收集 H 类源文件：`h1`~`h10` 目录 + `GtH*.vue` + `composables/h{n}*.ts` */
export function collectHFiles(): string[] {
  const out: string[] = []
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.(ts|vue)$/.test(e.name)) out.push(p)
    }
  }
  for (const e of fs.readdirSync(WP_DIR, { withFileTypes: true })) {
    const p = path.join(WP_DIR, e.name)
    if (e.isDirectory() && /^h(10|[1-9])$/.test(e.name)) walk(p)
    else if (e.isFile() && /^GtH\d+.*\.vue$/.test(e.name)) out.push(p)
  }
  const comp = path.join(WP_DIR, 'composables')
  for (const e of fs.readdirSync(comp, { withFileTypes: true })) {
    if (e.isFile() && /^h(10|[1-9])\w*\.ts$/.test(e.name)) out.push(path.join(comp, e.name))
  }
  return out.filter((p) => !p.includes('__tests__'))
}

const H_FILES = collectHFiles()

describe('H 类禁引账龄枚举（裁决 2 / R9.1~R9.4）', () => {
  it('扫描面非空自检：H 类文件数与目录覆盖都合理（防守卫空转）', () => {
    expect(H_FILES.length, `H 类文件数异常: ${H_FILES.length}（glob 失效？）`).toBeGreaterThan(200)
    // 每个循环目录都要被扫到，否则某循环可以偷偷引用账龄
    for (const n of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) {
      const sep = path.sep
      const hit = H_FILES.some((p) => p.includes(`${sep}h${n}${sep}`))
      expect(hit, `h${n} 目录未被扫到`).toBe(true)
    }
    // 已知内容锚点：证明读到的是真实源码而不是空串
    const h4detail = H_FILES.find((p) => p.endsWith('H4TabDetail.vue'))
    expect(h4detail, '未扫到 H4TabDetail.vue').toBeTruthy()
    expect(fs.readFileSync(h4detail!, 'utf-8')).toContain('库龄')
  })

  it.each(AGING_SYMBOLS)('H 类源码零引用 %s', (sym) => {
    const bad: string[] = []
    for (const p of H_FILES) {
      const src = stripComments(fs.readFileSync(p, 'utf-8'))
      if (src.includes(sym)) bad.push(path.relative(WP_DIR, p))
    }
    expect(
      bad,
      `长期资产无账龄维度（裁决 2）—— 以下文件引用了 ${sym}：${bad.join(', ')}`,
    ).toEqual([])
  })

  it('H4 库龄选项命名不得含 AGING（防被误统一到平台账龄枚举）', () => {
    const bad: string[] = []
    for (const p of H_FILES) {
      const src = stripComments(fs.readFileSync(p, 'utf-8'))
      for (const m of src.matchAll(/(?:const|let|var)\s+(\w*AGING\w*)\s*=/g)) {
        bad.push(`${path.relative(WP_DIR, p)}::${m[1]}`)
      }
    }
    expect(
      bad,
      '长期资产无账龄维度 —— 分段常量不得以 AGING 命名（库龄请用 STOCK_AGE_*）：'
        + bad.join(', '),
    ).toEqual([])
  })

  it('H4 库龄选项就地声明且注释写明「与账龄无关 / 源模板无取值域」', () => {
    const raw = fs.readFileSync(path.join(WP_DIR, H4_STOCK_AGE.file), 'utf-8')
    expect(raw, `缺 ${H4_STOCK_AGE.constName}`).toContain(`const ${H4_STOCK_AGE.constName} =`)
    // 注释（不剥）必须解释清语义边界，否则下个会话又会去接账龄
    expect(raw, '缺「与账龄无关」的语义说明').toMatch(/与「?账龄」?无关|禁接平台账龄/)
    expect(raw, '缺源模板无取值域的实证').toMatch(/AV8|无数据验证|无区间字面量/)
    // 持久化键仍是历史的 `aging`（改名会丢已录数据）→ 必须显式说明
    expect(raw, '未说明持久化键保持 aging 的理由').toMatch(/row\.aging[\s\S]{0,200}历史键|历史键[\s\S]{0,200}row\.aging/)
  })

  it('库龄不得进披露载荷（真红线：会污染附注）', () => {
    const bad: string[] = []
    for (const rel of H4_STOCK_AGE.disclosureFiles) {
      const p = path.join(WP_DIR, rel)
      if (!fs.existsSync(p)) throw new Error(`守卫路径失效: ${p}`)
      const src = stripComments(fs.readFileSync(p, 'utf-8'))
      if (src.includes('库龄')) bad.push(`${rel}::库龄`)
      if (/\baging\b/.test(src)) bad.push(`${rel}::aging`)
    }
    expect(
      bad,
      '库龄是底稿内部的减值迹象判断辅助（→ H4-7），进附注即造出源模板没有的披露列：'
        + bad.join(', '),
    ).toEqual([])
  })

  it('H6 的 aging 是「挂账关注」区段名，不是账龄段（语义登记，防被误改）', () => {
    const h6 = H_FILES.find((p) => p.endsWith(path.join('h6', 'core', 'H6TabDetail.vue')))
    expect(h6, '未找到 H6TabDetail.vue').toBeTruthy()
    const src = fs.readFileSync(h6!, 'utf-8')
    // 该取值是区段切换器的 value，语义 = 转入清理超 1 年
    expect(src).toMatch(/label:\s*'挂账关注'\s*,\s*value:\s*'aging'/)
    expect(src, 'H6 的判据是「超 1 年」而非账龄分段').toMatch(/isRowOverOneYear/)
  })
})

/**
 * 取 `fnName(` 的完整实参串（**按圆括号配对**）。
 *
 * 🔴 不能用 `\(([^)]*)\)` —— 它在遇到**第一个** `)` 就停，
 * `blankRows(p, Math.max(seed.length, 1))` 会被截成 `p, Math.max(seed.length, 1`，
 * 尾部恰是 `, 1` ⇒ 合法的派生写法被误判成「写死行数」（本守卫首版即踩此坑）。
 */
export function callArgs(src: string, fnName: string): string[] {
  const out: string[] = []
  const re = new RegExp(`\\b${fnName}\\s*\\(`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    let i = m.index + m[0].length
    let depth = 1
    let quote: string | null = null
    const start = i
    while (i < src.length && depth > 0) {
      const ch = src[i]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'" || ch === '`') {
        quote = ch
      } else if (ch === '(') depth++
      else if (ch === ')') depth--
      i++
    }
    out.push(src.slice(start, i - 1))
  }
  return out
}

/** 最后一个实参是否为字面数字（写死骨架行数） */
export function lastArgIsLiteralNumber(args: string): boolean {
  // 按顶层逗号切分（括号内的逗号不算）
  const parts: string[] = []
  let depth = 0
  let quote: string | null = null
  let buf = ''
  for (const ch of args) {
    if (quote) {
      if (ch === quote) quote = null
      buf += ch
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') quote = ch
    else if (ch === '(' || ch === '[' || ch === '{') depth++
    else if (ch === ')' || ch === ']' || ch === '}') depth--
    if (ch === ',' && depth === 0) {
      parts.push(buf)
      buf = ''
      continue
    }
    buf += ch
  }
  parts.push(buf)
  return parts.length > 1 && /^\s*\d+\s*$/.test(parts[parts.length - 1])
}

describe('H 类禁写死骨架行数（R8.3~R8.5）', () => {
  it('blankRows(x, 字面数字) 零命中', () => {
    const bad: string[] = []
    for (const p of H_FILES) {
      const src = stripComments(fs.readFileSync(p, 'utf-8'))
      for (const args of callArgs(src, 'blankRows')) {
        if (lastArgIsLiteralNumber(args)) {
          bad.push(`${path.relative(WP_DIR, p)}::blankRows(${args.trim()})`)
        }
      }
    }
    expect(
      bad,
      '预置空占位行会被同步推成「占位披露行」污染附注 ⇒ 骨架行数应由 seed 行数派生：'
        + bad.join(', '),
    ).toEqual([])
  })
})

describe('反向自检（证明上面的断言不是空转）', () => {
  it('注入一处账龄引用必被点名', () => {
    const fake = `import { toDisclosureAgingLabel } from '../composables/disclosureAgingLabels'`
    for (const sym of ['disclosureAgingLabels', 'toDisclosureAgingLabel']) {
      expect(stripComments(fake).includes(sym), `${sym} 应被检出`).toBe(true)
    }
  })

  it('注释里的账龄字样不参与判定（剥注释）', () => {
    const commented = `// 裁决 2：禁用 disclosureAgingLabels\nconst a = 1`
    expect(commented).toContain('disclosureAgingLabels')
    expect(stripComments(commented)).not.toContain('disclosureAgingLabels')
  })

  it('写死骨架行数会被检出，而派生形态不会（括号配对判据）', () => {
    const hit = (s: string) =>
      callArgs(s, 'blankRows').some((a) => lastArgIsLiteralNumber(a))
    expect(hit('const rows = blankRows(p, 5)'), '写死 5 行应被检出').toBe(true)
    expect(hit('const rows = blankRows(p, 3)')).toBe(true)
    // 🔴 关键：嵌套调用的合法派生形态**不得**误判
    expect(
      hit('const rows = blankRows(p, Math.max(seed.length, 1))'),
      '派生形态被误判 —— 说明实参提取又退回了 [^)]* 的写法',
    ).toBe(false)
    expect(hit('const rows = blankRows(p, rowCount)')).toBe(false)
    // 单参调用不算写死
    expect(hit('const rows = blankRows(p)')).toBe(false)
  })

  it('callArgs 尊重引号与嵌套括号', () => {
    const src = `blankRows(p, fn("a,b(c)", [1, 2]))`
    const args = callArgs(src, 'blankRows')
    expect(args).toHaveLength(1)
    expect(args[0]).toBe('p, fn("a,b(c)", [1, 2])')
    expect(lastArgIsLiteralNumber(args[0])).toBe(false)
  })

  it('以 AGING 命名的分段常量会被检出（库龄应用 STOCK_AGE_*）', () => {
    const fake = `const AGING_OPTS = ['1年以内', '1-2年']`
    const hits = [...stripComments(fake).matchAll(/(?:const|let|var)\s+(\w*AGING\w*)\s*=/g)]
    expect(hits.map((m) => m[1])).toEqual(['AGING_OPTS'])
    // 改名后不再命中
    const fixed = `const STOCK_AGE_OPTS = ['1年以内', '1-2年']`
    expect([...fixed.matchAll(/(?:const|let|var)\s+(\w*AGING\w*)\s*=/g)]).toHaveLength(0)
  })
})
