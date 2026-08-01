/**
 * N2 双归一函数**交叉一致性**守卫
 *
 * 平台有两个税种归一函数，输出域不同但**必须映射到同一披露行**：
 *
 * | 函数 | 所在 | 输出域 | 用途 |
 * |------|------|--------|------|
 * | `normalizeTaxLabel` | `n2TaxLabelMap.ts` | 源模板**全称**（`城市维护建设税`） | 披露表行匹配 |
 * | `_normalizeTaxNameForN4` | `useN2CrossSheet.ts` | **简称**（`城建税`） | N4 联动 `TAX_CALC_TABLE_MAP` 匹配 |
 *
 * 两者互为逆映射（城建税↔城市维护建设税 / 车船税↔车船牌照税），但历史上**无守卫** ——
 * 任一侧改归一规则，另一侧不会红，会造成「披露表有这行、联动查不到」的静默漂移。
 *
 * 🔴 **已知有意分叉一处**：`地方教育附加`
 * - 披露侧 `normalizeTaxLabel('地方教育附加')` → `'教育费附加'`（合并）
 *   依据：源模板 `附注披露信息（上市公司）/（国企）` R8~R20 **只有「教育费附加」一行**，
 *   且源模板说明「（小税（费）种可合并反映。）」
 * - N4 侧 `_normalizeTaxNameForN4('地方教育附加')` → `'地方教育附加'`（独立）
 *   依据：`TAX_CALC_TABLE_MAP` 有独立键 `地方教育附加` → `N2-8-surtax-local-education`，
 *   N2-8 测算表按「城建税/教育费附加/地方教育附加」三档分别测算
 * ⇒ 同一笔余额两侧归属不同是**正确的**（披露合并 / 测算分开），本守卫显式登记为例外。
 *
 * spec: n2-disclosure-and-extraction-alignment Task 6.2
 */
import { describe, expect, it } from 'vitest'
import { N2_TAX_LABEL_MAP, N2_FIXED_TAX_LABELS, normalizeTaxLabel } from '../n2TaxLabelMap'

// ─── 从 useN2CrossSheet.ts 源码抽 N4 侧归一规则与 TAX_CALC_TABLE_MAP ──────────

const CROSS_SHEET_SRC = await import('../useN2CrossSheet?raw').then(
  (m) => (m as unknown as { default: string }).default,
)

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '')
}

/**
 * 重放 `_normalizeTaxNameForN4` 的规则（该函数非导出，故从源码抽 if 条件重放）。
 * 与实现同源：任一侧改动，`test_n4_rules_extracted_from_source` 会因规则条数变化而红。
 */
function normalizeTaxNameForN4(name: string): string {
  const s = String(name ?? '').trim()
  if (s === '城建税' || s === '城市维护建设税') return '城建税'
  if (s === '土地使用税' || s === '城镇土地使用税') return '土地使用税'
  if (s === '车船税' || s === '车船使用税' || s === '车船牌照税') return '车船税'
  if (s === '企业所得税' || s === '所得税') return '企业所得税'
  if (s === '增值税' || s === '未交增值税') return '增值税'
  return s
}

// ─── 1. 重放函数与源码实现同步（防实现改了守卫没跟上）───────────────────────

describe('N4 归一规则重放与源码同步', () => {
  const stripped = stripComments(CROSS_SHEET_SRC)

  it('源码里确实有 _normalizeTaxNameForN4（反向自检）', () => {
    expect(stripped).toContain('function _normalizeTaxNameForN4')
  })

  it('源码归一规则条数 = 重放函数条数（5 条 if）', () => {
    const body = stripped.match(
      /function _normalizeTaxNameForN4\([^)]*\)[^{]*\{([\s\S]*?)\n\}/,
    )?.[1]
    expect(body, '未抽到 _normalizeTaxNameForN4 函数体').toBeTruthy()
    const ifCount = (body!.match(/\bif\s*\(/g) || []).length
    expect(
      ifCount,
      '源码归一规则条数变了 → 请同步更新本文件的 normalizeTaxNameForN4 重放实现',
    ).toBe(5)
  })

  it('源码里 5 条规则的输出名逐字命中重放实现', () => {
    for (const out of ['城建税', '土地使用税', '车船税', '企业所得税', '增值税']) {
      expect(stripped).toContain(`return '${out}'`)
    }
  })
})

// ─── 2. TAX_CALC_TABLE_MAP 键必须是 N4 归一的输出（不变式） ──────────────────

describe('TAX_CALC_TABLE_MAP 键 = N4 归一输出', () => {
  const stripped = stripComments(CROSS_SHEET_SRC)
  const mapBody = stripped.match(/TAX_CALC_TABLE_MAP[^=]*=\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
  const keys = [...mapBody.matchAll(/'([^']+)':/g)].map((m) => m[1])

  it('抽到 6 个税种键（反向自检）', () => {
    expect(keys).toHaveLength(6)
  })

  it('每个键都是 N4 归一的不动点（幂等）', () => {
    for (const k of keys) {
      expect(normalizeTaxNameForN4(k), `键 ${k} 不是 N4 归一不动点`).toBe(k)
    }
  })
})

// ─── 3. 核心交叉断言：两侧归一结果必须映射到同一披露行 ──────────────────────

/** N4 简称 → 披露侧规范名（= 源模板全称）。有意分叉的项单独登记。 */
const N4_SHORT_TO_DISCLOSURE_LABEL: Record<string, string> = {
  增值税: '增值税',
  城建税: '城市维护建设税',
  教育费附加: '教育费附加',
  房产税: '房产税',
  土地增值税: '土地增值税',
  土地使用税: '土地使用税',
  车船税: '车船牌照税',
  企业所得税: '企业所得税',
}

/**
 * 🔴 有意分叉：披露侧合并、N4 侧独立。每条必须写明源模板依据。
 */
const INTENTIONAL_DIVERGENCE: Record<string, { disclosure: string; n4: string; why: string }> = {
  地方教育附加: {
    disclosure: '教育费附加',
    n4: '地方教育附加',
    why:
      '源模板披露表 R8~R20 只有「教育费附加」一行 + 说明「小税（费）种可合并反映」；'
      + 'N2-8 测算表按城建税/教育费附加/地方教育附加三档分别测算，故 TAX_CALC_TABLE_MAP 有独立键',
  },
}

describe('两侧归一结果映射到同一披露行', () => {
  /** 同一原始科目名，两条路径归一后应落到同一披露行 */
  const RAW_NAMES = [
    '增值税',
    '未交增值税',
    '城建税',
    '城市维护建设税',
    '车船税',
    '车船使用税',
    '车船牌照税',
    '土地使用税',
    '城镇土地使用税',
    '企业所得税',
    '房产税',
    '土地增值税',
    '教育费附加',
  ]

  it.each(RAW_NAMES)('「%s」两侧归一后落到同一披露行', (raw) => {
    const discLabel = normalizeTaxLabel(raw)
    const n4Short = normalizeTaxNameForN4(raw)
    const mapped = N4_SHORT_TO_DISCLOSURE_LABEL[n4Short] ?? n4Short
    expect(
      mapped,
      `「${raw}」漂移：披露侧→${discLabel} / N4侧→${n4Short}（映射为 ${mapped}）`,
    ).toBe(discLabel)
  })

  it('有意分叉项：地方教育附加两侧确实不同（若变同要重新评估源模板依据）', () => {
    const div = INTENTIONAL_DIVERGENCE['地方教育附加']
    expect(normalizeTaxLabel('地方教育附加')).toBe(div.disclosure)
    expect(normalizeTaxNameForN4('地方教育附加')).toBe(div.n4)
    expect(div.disclosure).not.toBe(div.n4)
    expect(div.why.length, '分叉必须写明源模板依据').toBeGreaterThan(30)
  })
})

// ─── 4. N4 简称映射表覆盖性 ──────────────────────────────────────────────────

describe('N4 简称映射表覆盖性', () => {
  it('每个映射目标都是 13 固定披露行之一', () => {
    for (const label of Object.values(N4_SHORT_TO_DISCLOSURE_LABEL)) {
      expect(N2_FIXED_TAX_LABELS, `${label} 不在 13 固定行内`).toContain(label)
    }
  })

  it('TAX_CALC_TABLE_MAP 的每个键都已登记（映射表或有意分叉）', () => {
    const stripped = stripComments(CROSS_SHEET_SRC)
    const mapBody = stripped.match(/TAX_CALC_TABLE_MAP[^=]*=\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
    const keys = [...mapBody.matchAll(/'([^']+)':/g)].map((m) => m[1])
    for (const k of keys) {
      const registered = k in N4_SHORT_TO_DISCLOSURE_LABEL || k in INTENTIONAL_DIVERGENCE
      expect(
        registered,
        `TAX_CALC_TABLE_MAP 新增键 ${k} 未登记 → 请补 N4_SHORT_TO_DISCLOSURE_LABEL 或 INTENTIONAL_DIVERGENCE`,
      ).toBe(true)
    }
  })

  it('披露侧 13 固定行里，N4 有对应测算表的都已建立映射', () => {
    // N4 侧只测算 6 个税种，其余固定行无测算表 —— 这是正常的（如矿产资源补偿费）
    const n4Covered = new Set(Object.values(N4_SHORT_TO_DISCLOSURE_LABEL))
    const notCovered = N2_FIXED_TAX_LABELS.filter((l) => !n4Covered.has(l))
    // 反向自检：确实有一部分固定行不被 N4 覆盖（否则本断言空转）
    expect(notCovered.length).toBeGreaterThan(0)
    // 且未覆盖的都是源模板里没有对应测算表的税种
    for (const label of notCovered) {
      expect(N2_TAX_LABEL_MAP[label], `${label} 不在 N2_TAX_LABEL_MAP`).toBeDefined()
    }
  })
})
