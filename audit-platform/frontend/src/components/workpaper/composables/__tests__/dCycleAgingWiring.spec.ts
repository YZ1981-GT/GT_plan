/**
 * D 循环账龄口径边界守卫 —— spec Task 24（Property 26 / 27）。
 *
 * 🔴🔴 **本守卫的结论与 Task 24 立项描述相反，是实证驱动的修正**（2026-08-06）
 *
 * 立项按「D3/D7 披露 Tab 里 grep 账龄信号 = 0」判定「未接账龄枚举」。**判据选错了** ——
 * 平台既定方案（用户 2026-07-30 定的**方案 A**）是「账龄口径映射放**同步层**
 * （`XNoteSectionMap.ts`），项目账龄配置继续只服务底稿内部」，组件层本来就不该有
 * 账龄真源的引用。逐个核实后：
 *
 * **① D3 的账龄贯通早已完整实现**（不是缺口）::
 *
 *     useD3DisclosureSoe.section1Rows   segment-driven：读 crossSheet.agingSegments，
 *                                        按 seg.dayFrom >= 366 聚合成两桶
 *     行带 rowKey = within1 / over1      供同步层做「底稿字面 → 附注口径」映射
 *     d3NoteSectionMap                   toDisclosureAgingLabel(r, SOE_AGING_OVERRIDES)
 *                                        把 `1年以内` 映射成模板字面 `1年以内（含1年）`
 *
 * 故项目账龄配置改 3 段 / 5 段 / 自定义时，聚合结果自动跟随，**无需改行集**。
 *
 * **② soe 八、38 主表源模板就是两档，不得按项目配置展开成 6 档**::
 *
 *     table '预收款项' rows=3:  '1年以内（含1年）' / '1年以上' / '合  计'
 *
 * 展开成 6 档 = 自造披露行（违反「源模板是裁决者」+「宁缺勿造」）。
 *
 * **③ D7 源模板没有账龄档位表** —— 上市 五、39 只有「账龄超过1年的重要合同负债」
 * **逐户明细表**（列 = 项目 / 期末余额 / 未偿还或未结转的原因），国企 八、39
 * 连这张都没有。故 D7 **不引入账龄枚举**，与平台已登记的「J2 到期分析 ≠ 账龄」
 * 「H 类不引入账龄枚举」同族裁决。
 *
 * ⇒ 本守卫**只钉死边界**，不新增功能：防后续会话按「信号数为 0」再判一次缺陷、
 * 把两档展开成 6 档、或给 D7 硬塞账龄档位。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('REPO_ROOT not found (双哨兵均未命中)')
}

const REPO_ROOT = findRepoRoot()
const WP_DIR = path.join(
  REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
)
const BE_DATA = path.join(REPO_ROOT, 'backend', 'data')

function read(rel: string): string {
  const p = path.join(WP_DIR, rel)
  if (!fs.existsSync(p)) throw new Error(`文件不存在：${rel}（路径已变？）`)
  return fs.readFileSync(p, 'utf-8')
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

interface TplRow { label?: string; row_type?: string }
interface TplTable { name?: string; rows?: TplRow[]; columns?: unknown[] }
interface TplSection { section_number?: string; section_title?: string; tables?: TplTable[] }

function sectionOf(tpl: 'listed' | 'soe', num: string): TplSection {
  const file = path.join(BE_DATA, `note_template_${tpl}.json`)
  const data = JSON.parse(fs.readFileSync(file, 'utf-8')) as { sections?: TplSection[] }
  const hit = (data.sections || []).find((s) => String(s.section_number) === num)
  if (!hit) throw new Error(`模板 ${tpl} 无章节 ${num}`)
  return hit
}

function tableOf(sec: TplSection, name: string): TplTable {
  const hit = (sec.tables || []).find((t) => String(t.name) === name)
  if (!hit) {
    throw new Error(
      `章节 ${sec.section_number} 无子表 ${name}（现有 ${(sec.tables || []).map((t) => t.name).join(' / ')}）`,
    )
  }
  return hit
}

// ══════════════════════════════════════════════════════════════════════════════
// Property 26: D3 账龄贯通已就位（方案 A：同步层映射 + segment-driven 聚合）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 26: D3 账龄口径贯通（方案 A）', () => {
  it('d3NoteSectionMap 从账龄真源 import（同步层做口径映射）', () => {
    const src = stripComments(read('composables/d3NoteSectionMap.ts'))
    // 只认 import 路径 —— 符号级匹配会被注释骗
    expect(src).toMatch(/from\s+'\.\/disclosureAgingLabels'/)
    expect(src).toMatch(/toDisclosureAgingLabel\s*\(/)
  })

  it('国企主表行标签经 SOE_AGING_OVERRIDES 映射，组件内不写死模板字面', () => {
    const src = stripComments(read('composables/d3NoteSectionMap.ts'))
    expect(src).toMatch(/toDisclosureAgingLabel\([^)]*SOE_AGING_OVERRIDES/)
    // 🔴 附注模板字面 `1年以内（含1年）` 只能由真源产出，不得在映射文件里硬编码
    expect(src).not.toMatch(/1年以内（含1年）/)
  })

  it('useD3DisclosureSoe 的按账龄两桶是 segment-driven（随项目账龄配置聚合）', () => {
    const src = stripComments(read('composables/useD3DisclosureSoe.ts'))
    // 读项目账龄段而非写死档位
    expect(src).toMatch(/agingSegments/)
    // 按天数边界归入「超 1 年」桶 —— 3 段 / 5 段 / 自定义都能正确聚合
    expect(src).toMatch(/dayFrom\s*>=\s*366/)
    // 两桶行带 rowKey 供同步层映射
    expect(src).toMatch(/rowKey:\s*'within1'/)
    expect(src).toMatch(/rowKey:\s*'over1'/)
  })

  it('国企主表源模板就是两档 —— 不得按项目账龄配置展开成 3/5 年段', () => {
    const sec = sectionOf('soe', '八、38')
    const main = tableOf(sec, '预收款项')
    const labels = (main.rows || []).map((r) => String(r.label))
    expect(labels).toEqual(['1年以内（含1年）', '1年以上', '合  计'])
    // 反向锁死：出现 `1至2年` / `2至3年` 这类档位即说明被展开成自造行
    const expanded = labels.filter((l) => /\d\s*[至到-]\s*\d\s*年/.test(l))
    expect(expanded, '八、38 主表被展开成多档账龄 = 自造披露行').toEqual([])
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 27: 反向锁死 —— 无账龄维度的循环不得引入账龄真源
// ══════════════════════════════════════════════════════════════════════════════

const AGING_SOURCE_SIGNALS = [
  'disclosureAgingLabels',
  'useAgingConfig',
  'toDisclosureAgingLabel',
  'DISCLOSURE_AGING_LABELS',
  'buildDisclosureAgingLabelMap',
] as const

/** 源模板确实无账龄维度的循环（每条带依据） */
const NO_AGING_CYCLES: ReadonlyArray<{ file: string; why: string }> = Object.freeze([
  {
    file: 'composables/d7NoteSectionMap.ts',
    why:
      'D7 源模板无账龄档位表：上市 五、39 只有「账龄超过1年的重要合同负债」逐户明细表' +
      '（列=项目/期末余额/未偿还或未结转的原因），国企 八、39 连这张都没有',
  },
  {
    file: 'composables/d1NoteSectionMap.ts',
    why: 'D1 应收票据按**票据种类**披露（银行承兑/商业承兑/信用证），无账龄维度',
  },
  {
    file: 'composables/d5NoteSectionMap.ts',
    why: 'D5 应收款项融资是票据类金融资产，按公允价值计量，无账龄维度',
  },
  {
    file: 'composables/d6NoteSectionMap.ts',
    why: 'D6 合同资产按**减值组合**披露（单项/组合），无账龄维度',
  },
])

describe('Property 27: 无账龄维度的循环不得引用账龄真源', () => {
  it.each(NO_AGING_CYCLES.map((c) => [c.file, c.why] as const))(
    '%s 不引用账龄真源',
    (file, why) => {
      const p = path.join(WP_DIR, file)
      if (!fs.existsSync(p)) return // 该循环无 map 文件则无需断言
      const src = stripComments(fs.readFileSync(p, 'utf-8'))
      const hits = AGING_SOURCE_SIGNALS.filter((s) => src.includes(s))
      expect(hits, `${file} 引用了账龄真源 ${hits.join('/')}；依据：${why}`).toEqual([])
    },
  )

  it('D7 源模板确实只有「超1年逐户明细」而无账龄档位表（判据非空自检）', () => {
    const listed = sectionOf('listed', '五、39')
    const lt = tableOf(listed, '账龄超过1年的重要合同负债')
    // 逐户明细表：数据行是**空白可扩行**（供审计师逐户填），不是账龄档位
    const labels = (lt.rows || []).map((r) => String(r.label || ''))
    const bands = labels.filter((l) => /\d\s*[至到-]\s*\d\s*年|1年以内/.test(l))
    expect(bands, '五、39 超1年表出现账龄档位行 = 被当成分档表了').toEqual([])
    // 国企侧连这张表都没有
    const soe = sectionOf('soe', '八、39')
    const names = (soe.tables || []).map((t) => String(t.name))
    expect(names).not.toContain('账龄超过1年的重要合同负债')
  })

  it('反向自检：D3 侧确实**有**账龄真源引用（证明上一组断言不是空转）', () => {
    const src = stripComments(read('composables/d3NoteSectionMap.ts'))
    const hits = AGING_SOURCE_SIGNALS.filter((s) => src.includes(s))
    expect(hits.length, 'D3 也没引用账龄真源 = 信号提取失效').toBeGreaterThan(0)
  })

  it('反向自检：账龄真源导出面齐备（防真源被改名后断言静默失效）', () => {
    const src = read('composables/disclosureAgingLabels.ts')
    for (const sym of [
      'DISCLOSURE_AGING_WITHIN1_SOE',
      'SOE_AGING_OVERRIDES',
      'toDisclosureAgingLabel',
      'DISCLOSURE_AGING_LABELS',
    ]) {
      expect(src, `账龄真源缺导出 ${sym}`).toMatch(
        new RegExp(`export (?:const|function)\\s+${sym}\\b`),
      )
    }
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 合计行字面：按各章节实证取值，禁全局套固定字面
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 26（续）: 合计行字面按章节实证', () => {
  it('D3 四张表的合计行字面互不相同 —— 禁统一', () => {
    // 实证：listed 主表/超1年 `合 计`（一空格）、soe 主表 `合  计`（两空格）、
    // soe 超1年 `合计`（无空格）—— 源模板如此，统一会让附注对不上行
    const listedSec = sectionOf('listed', '五、38')
    const soeSec = sectionOf('soe', '八、38')
    const totalOf = (t: TplTable) =>
      String((t.rows || []).find((r) => r.row_type === 'total')?.label ?? '')

    const listedMain = totalOf(tableOf(listedSec, '预收款项'))
    const soeMain = totalOf(tableOf(soeSec, '预收款项'))
    const soeLong = totalOf(tableOf(soeSec, '账龄超过1年的重要预收账款'))

    for (const [name, v] of [['listed 主表', listedMain], ['soe 主表', soeMain], ['soe 超1年', soeLong]] as const) {
      expect(v.replace(/\s+/g, ''), `${name} 合计行缺失`).toBe('合计')
    }
    // 至少存在两种不同字面 ⇒ 证明「不可统一」这一事实仍然成立
    expect(new Set([listedMain, soeMain, soeLong]).size).toBeGreaterThan(1)
  })

  it('d3NoteSectionMap 用 per-table 合计常量而非全局 DISCLOSURE_TOTAL_LABEL', () => {
    const src = stripComments(read('composables/d3NoteSectionMap.ts'))
    expect(src).toMatch(/D3_NOTE_TOTAL_LABEL/)
    // 🔴 该章节合计字面与平台默认不同，套全局常量会写错行
    expect(src).not.toMatch(/\bDISCLOSURE_TOTAL_LABEL\b/)
  })
})
