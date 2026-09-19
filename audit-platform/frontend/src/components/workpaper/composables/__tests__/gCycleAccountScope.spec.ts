/**
 * G 循环科目定位守卫 —— **跨前后端交叉锁死**。
 *
 * 前端 `gCycleAccountScope.ts` 与后端 `four_table/g_cycle_specs.py` 是同一份声明的两侧，
 * 本守卫直接读**后端源码**比对槽键 / 报表行号 / 兜底码 —— 防「改一侧漏一侧」
 * （实证 G4 的 main 与 ecl/sppi 子策略、G6 的 main 与 service 层就是各写一份而分叉）。
 *
 * 另锁死实证结论：
 * - `report_config` 的 BS-022/025/026 连续偏移一位、IS-016↔IS-017 互换
 *   → 兜底码取实证真值 1506 / 1507 / 1519 / 6702
 * - `1102 衍生金融资产` / 衍生金融负债 任何项目科目表都没有 → **不得给兜底码**
 * - 跨循环科目互斥（这条正是抓住错位链的判据）
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
 *       Requirements 3 / Property 4, 7
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  G1_DERIVATIVE_FALLBACK_STANDARD,
  G1_GROSS_FALLBACK_STANDARD,
  G1_REPORT_ROW_CODE,
} from '../g1AccountScope'
import { G5_GROSS_FALLBACK_STANDARD, G5_REPORT_ROW_CODE } from '../g5AccountScope'
import { G6_GROSS_FALLBACK_STANDARD, G6_REPORT_ROW_CODE } from '../g6AccountScope'
import { G7_GROSS_FALLBACK_STANDARD, G7_REPORT_ROW_CODE } from '../g7AccountScope'
import {
  G_CYCLE_SCOPES,
  G_PL_CYCLES,
  gCycleBasisLabel,
  gCycleScope,
  isGPlCycle,
} from '../gCycleAccountScope'

// 本文件位于 audit-platform/frontend/src/components/workpaper/composables/__tests__/
// → 回到仓库根需 7 级（比 workpaper/__tests__ 下的守卫深一层，别照抄那边的 6 级）
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const BACKEND_SPEC = path.join(
  REPO_ROOT,
  'backend/app/services/four_table/g_cycle_specs.py',
)

const ALL_CYCLES = [
  'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7',
  'G8', 'G9', 'G10', 'G11', 'G12', 'G13', 'G14',
]

/** 实证真值（`account_chart` + `trial_balance.account_name` 双证） */
const TRUE_PRIMARY_CODE: Readonly<Record<string, string>> = {
  G1: '1101',
  G2: '1132',
  G3: '1131',
  G4: '1504',
  G5: '1531',
  G6: '1506',
  G7: '1511',
  G8: '1507',
  G9: '1519',
  G10: '2101',
  G11: '6111',
  G12: '6103',
  G13: '6101',
  G14: '6702',
}

/** `report_config` 实际写的（错的）码 —— 兜底码绝不能等于它们 */
const REPORT_CONFIG_WRONG_CODE: Readonly<Record<string, string>> = {
  G6: '1505', // 债权投资减值准备
  G8: '1506', // 其他债权投资
  G9: '1507', // 其他权益工具投资
  G14: '6701', // 资产减值损失
}

/** 实证任何项目科目表都不存在的码 —— 不得作兜底 */
const ABSENT_CODES = ['1102']

function backendSource(): string {
  return fs.readFileSync(BACKEND_SPEC, 'utf-8')
}

/** 剥 Python 注释与 docstring（缺陷说明里会写反例码，不剥必误判） */
function stripPy(src: string): string {
  return src
    .replace(/"""[\s\S]*?"""/g, '')
    .replace(/'''[\s\S]*?'''/g, '')
    .replace(/^\s*#.*$/gm, '')
}

/**
 * 剥 TS/JS 注释。
 *
 * 🔴 必须剥：薄壳文件的 docstring 里写着历史错值
 * （`G6_GROSS_FALLBACK_STANDARD = '1505'` 的纠错说明），不剥会让本守卫把注释当代码判红。
 */
function stripTs(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"\\])\/\/[^\n]*/g, '$1')
}

describe('自检：后端规格源码可读', () => {
  it('文件存在且非空', () => {
    expect(fs.existsSync(BACKEND_SPEC)).toBe(true)
    expect(backendSource().length).toBeGreaterThan(2000)
  })

  it('剥注释函数确实生效（docstring 里有反例码 1505）', () => {
    const raw = backendSource()
    expect(raw).toContain('1505')
    // 1505 是 G4 的备抵真值，剥注释后仍应存在于 G4_SPEC；但 docstring 里的
    // 「BS-022→1505」说明段必须被剥掉
    expect(raw).toContain('BS-022')
    expect(stripPy(raw)).not.toContain('连续偏移一位')
  })
})

describe('注册表完整性', () => {
  it('14 个循环全部登记', () => {
    expect(Object.keys(G_CYCLE_SCOPES).sort()).toEqual([...ALL_CYCLES].sort())
  })

  it('gCycleScope 大小写不敏感、未登记返 null', () => {
    expect(gCycleScope('g6')).toBe(G_CYCLE_SCOPES.G6)
    expect(gCycleScope(' G14 ')).toBe(G_CYCLE_SCOPES.G14)
    expect(gCycleScope('G99')).toBeNull()
    expect(gCycleScope('')).toBeNull()
  })

  it('槽键唯一且有中文展示名', () => {
    for (const cyc of ALL_CYCLES) {
      const slots = G_CYCLE_SCOPES[cyc].spec.slots
      const keys = slots.map((s) => s.key)
      expect(keys.length, `${cyc} 未声明槽`).toBeGreaterThan(0)
      expect(new Set(keys).size, `${cyc} 槽键重复`).toBe(keys.length)
      for (const s of slots) {
        expect(s.label.length, `${cyc}.${s.key} 无展示名`).toBeGreaterThan(0)
      }
    }
  })
})

describe('兜底码 = 实证真值（不是 report_config 的错码）', () => {
  it.each(ALL_CYCLES)('%s 主槽兜底码正确', (cyc) => {
    expect(G_CYCLE_SCOPES[cyc].primaryFallback).toBe(TRUE_PRIMARY_CODE[cyc])
  })

  it.each(Object.keys(REPORT_CONFIG_WRONG_CODE))(
    '🔴 %s 的兜底码不得等于 report_config 写的错码',
    (cyc) => {
      expect(G_CYCLE_SCOPES[cyc].primaryFallback).not.toBe(
        REPORT_CONFIG_WRONG_CODE[cyc],
      )
    },
  )

  it('🔴 实证不存在的科目不得有兜底码（否则「无此科目」被掩盖成 0）', () => {
    for (const cyc of ALL_CYCLES) {
      for (const slot of G_CYCLE_SCOPES[cyc].spec.slots) {
        if (slot.fallback) {
          expect(ABSENT_CODES, `${cyc}.${slot.key}`).not.toContain(slot.fallback)
        }
      }
    }
  })

  it('G1 / G10 的衍生品槽无兜底码', () => {
    for (const cyc of ['G1', 'G10']) {
      const slot = G_CYCLE_SCOPES[cyc].spec.slots.find((s) => s.key === 'derivative')
      expect(slot, `${cyc} 缺 derivative 槽`).toBeTruthy()
      expect(slot!.fallback, `${cyc}.derivative 不应有兜底码`).toBeUndefined()
    }
  })
})

describe('跨循环科目互斥（抓错位链的判据）', () => {
  it('任两个循环的兜底码互不相同', () => {
    const owner = new Map<string, string>()
    for (const cyc of ALL_CYCLES) {
      for (const slot of G_CYCLE_SCOPES[cyc].spec.slots) {
        if (!slot.fallback) continue
        const prev = owner.get(slot.fallback)
        expect(
          prev,
          `${slot.fallback} 被 ${prev} 与 ${cyc} 同时认领`,
        ).toBeUndefined()
        owner.set(slot.fallback, cyc)
      }
    }
  })

  it('🔴 G6/G8/G9 三者的码互不相同（错位链的三个受害者）', () => {
    const codes = ['G6', 'G8', 'G9'].map((c) => G_CYCLE_SCOPES[c].primaryFallback)
    expect(new Set(codes).size).toBe(3)
    expect(codes).toEqual(['1506', '1507', '1519'])
  })

  it('🔴 G14 与 K11 的码不同（IS-016 / IS-017 互换的两个受害者）', () => {
    expect(G_CYCLE_SCOPES.G14.primaryFallback).toBe('6702')
    expect(G_CYCLE_SCOPES.G14.primaryFallback).not.toBe('6701')
  })
})

describe('与后端 g_cycle_specs.py 交叉一致', () => {
  it('每个循环的报表行号与后端一致', () => {
    const src = stripPy(backendSource())
    for (const cyc of ALL_CYCLES) {
      const rowCode = G_CYCLE_SCOPES[cyc].spec.reportRowCode
      // 后端块形如 `G6_SPEC = SemanticAccountSpec(\n    row_code="BS-022",`
      const block = new RegExp(
        `${cyc}_SPEC\\s*=\\s*SemanticAccountSpec\\(([\\s\\S]{0,400}?)\\n\\)`,
      ).exec(src)
      expect(block, `后端缺 ${cyc}_SPEC`).toBeTruthy()
      const body = block![1]
      if (rowCode === null) {
        expect(
          /row_code\s*=\s*None/.test(body),
          `${cyc} 前端声明无报表行，后端应为 row_code=None`,
        ).toBe(true)
      } else {
        expect(body, `${cyc} 报表行号与后端不一致`).toContain(`row_code="${rowCode}"`)
      }
    }
  })

  it('每个循环的兜底码出现在后端同一循环的规格里', () => {
    const src = stripPy(backendSource())
    for (const cyc of ALL_CYCLES) {
      const block = new RegExp(
        `${cyc}_SPEC\\s*=\\s*SemanticAccountSpec\\(([\\s\\S]{0,900}?)\\n\\)`,
      ).exec(src)
      expect(block, `后端缺 ${cyc}_SPEC`).toBeTruthy()
      const body = block![1]
      for (const slot of G_CYCLE_SCOPES[cyc].spec.slots) {
        if (!slot.fallback) continue
        expect(body, `${cyc}.${slot.key} 兜底码 ${slot.fallback} 后端缺失`).toContain(
          `"${slot.fallback}"`,
        )
      }
    }
  })

  it('损益类循环集合两侧一致', () => {
    const src = stripPy(backendSource())
    const m = /G_PL_CYCLES\s*=\s*frozenset\(\{([^}]*)\}\)/.exec(src)
    expect(m, '后端缺 G_PL_CYCLES').toBeTruthy()
    const backendSet = new Set(
      [...m![1].matchAll(/"([^"]+)"/g)].map((x) => x[1]),
    )
    expect([...backendSet].sort()).toEqual([...G_PL_CYCLES].sort())
  })

  it('反向自检：不存在的循环名不会命中后端块（防正则空转）', () => {
    const src = stripPy(backendSource())
    const bogus = /G99_SPEC\s*=\s*SemanticAccountSpec\(/.exec(src)
    expect(bogus).toBeNull()
  })
})

describe('查询口径与「无此科目」判定', () => {
  const scope = G_CYCLE_SCOPES.G9

  it('render 下发时用下发值', () => {
    expect(scope.queryCodes({ gross_standard: ['1519', '1519.01'] })).toEqual([
      '1519',
      '1519.01',
    ])
  })

  it('render 未下发时回退兜底码', () => {
    expect(scope.queryCodes(null)).toEqual(['1519'])
    expect(scope.accountCode(undefined)).toBe('1519')
  })

  it('🔴 无兜底码声明的槽返空，绝不凭空造前缀', () => {
    const g1 = G_CYCLE_SCOPES.G1
    expect(g1.queryCodes(null, 'derivative')).toEqual([])
    expect(g1.accountCode(null, 'derivative')).toBe('')
  })

  it('found=false → 判定本项目无此科目', () => {
    const src = {
      slots: {
        gross: { key: 'gross', label: '其他非流动金融资产', found: false },
      },
    }
    expect(scope.isAccountAbsent(src)).toBe(true)
  })

  it('render 未下发 ≠ 无此科目', () => {
    expect(scope.isAccountAbsent(null)).toBe(false)
  })

  it('originalCodes 优先取客户原始码，缺失时退标准码', () => {
    const src = {
      slots: {
        gross: {
          key: 'gross',
          label: 'x',
          codes: ['1519.01'],
          standard_codes: ['1519'],
          found: true,
        },
      },
    }
    expect(scope.originalCodes(src)).toEqual(['1519.01'])
    expect(scope.originalCodes({ gross_standard: ['1519'] })).toEqual(['1519'])
  })

  it('🔴 matchesSlot 严格点号边界：1519 不得命中 15190', () => {
    const src = { gross_standard: ['1519'] }
    expect(scope.matchesSlot('1519', src)).toBe(true)
    expect(scope.matchesSlot('1519.01', src)).toBe(true)
    expect(scope.matchesSlot('15190', src)).toBe(false)
    expect(scope.matchesSlot('', src)).toBe(false)
  })

  it('兼容历史扁平形态与新 slots 形态', () => {
    expect(scope.queryCodes({ gross_standard: ['1519'] })).toEqual(['1519'])
    expect(
      scope.queryCodes({
        slots: { gross: { key: 'gross', label: 'x', standard_codes: ['1519'], found: true } },
      }),
    ).toEqual(['1519'])
  })
})

describe('既有 per-cycle 文件不得与单一真源漂移', () => {
  // G1 / G5 / G7 有历史遗留的 per-cycle scope 文件（各自导出自己的常量）。
  // 这里不重构它们（G7 有 29+ 既有测试），只锁死「常量必须与 gCycleAccountScope 一致」——
  // 否则就是双真源，改一处漏一处（实证 G6 的 main 与 service 层就这么分叉过）。
  //
  // 🔴 比对**运行时值**而不是源码正则：G5 写的是 `= G5_ACCOUNT_CODE`（常量间接引用），
  //    G6 是薄壳委托，G1/G7 是字面量 —— 三种形态用正则要写三个分支且易漏。
  it.each([
    ['G1', G1_GROSS_FALLBACK_STANDARD],
    ['G5', G5_GROSS_FALLBACK_STANDARD],
    ['G6', G6_GROSS_FALLBACK_STANDARD],
    ['G7', G7_GROSS_FALLBACK_STANDARD],
  ] as Array<[string, string]>)(
    '%s 的兜底码常量与 gCycleAccountScope 一致',
    (cyc, actual) => {
      expect(
        actual,
        `${cyc} per-cycle 常量为 ${actual}，与单一真源 ${G_CYCLE_SCOPES[cyc].primaryFallback} 漂移`,
      ).toBe(G_CYCLE_SCOPES[cyc].primaryFallback)
    },
  )

  it('各 per-cycle 报表行号与单一真源一致', () => {
    expect(G1_REPORT_ROW_CODE).toBe(G_CYCLE_SCOPES.G1.spec.reportRowCode)
    expect(G5_REPORT_ROW_CODE).toBe(G_CYCLE_SCOPES.G5.spec.reportRowCode)
    expect(G6_REPORT_ROW_CODE).toBe(G_CYCLE_SCOPES.G6.spec.reportRowCode)
    expect(G7_REPORT_ROW_CODE).toBe(G_CYCLE_SCOPES.G7.spec.reportRowCode)
  })

  it('🔴 G1 的衍生金融资产兜底码是实证不存在的科目 —— 单一真源刻意不给兜底', () => {
    // `1102` 在任何项目的 account_chart 里都没有（`2102` 是短期应付债券）。
    // per-cycle 文件保留该常量是历史形态，但单一真源不给兜底码 —— 否则
    // 「本项目无衍生金融工具」会被静默显示成 0。两者的差异在此显式登记。
    expect(G1_DERIVATIVE_FALLBACK_STANDARD).toBe('1102')
    const slot = G_CYCLE_SCOPES.G1.spec.slots.find((s) => s.key === 'derivative')
    expect(slot?.fallback).toBeUndefined()
    expect(G_CYCLE_SCOPES.G1.queryCodes(null, 'derivative')).toEqual([])
  })

  it('G6 已改为薄壳委托（不再写死码）', () => {
    const raw = fs.readFileSync(path.resolve(__dirname, '../g6AccountScope.ts'), 'utf-8')
    const src = stripTs(raw)
    expect(src).toContain('gCycleScope')
    expect(/G6_GROSS_FALLBACK_STANDARD\s*=\s*['"]/.test(src)).toBe(false)
  })

  it('反向自检：stripTs 确实剥掉了注释里的历史错值说明', () => {
    const raw = fs.readFileSync(path.resolve(__dirname, '../g6AccountScope.ts'), 'utf-8')
    // 纠错说明保留在注释里（供后人理解为何不是 1505）
    expect(raw).toContain('1505')
    expect(stripTs(raw)).not.toContain('1505')
  })
})

describe('损益类口径', () => {
  it('损益类为本期发生额，其余为期末余额', () => {
    for (const cyc of ALL_CYCLES) {
      const expected = G_PL_CYCLES.has(cyc) ? '本期发生额' : '期末余额'
      expect(gCycleBasisLabel(cyc), cyc).toBe(expected)
    }
  })

  it('isGPlCycle 大小写不敏感', () => {
    expect(isGPlCycle('g14')).toBe(true)
    expect(isGPlCycle('G1')).toBe(false)
    expect(isGPlCycle('')).toBe(false)
  })
})
