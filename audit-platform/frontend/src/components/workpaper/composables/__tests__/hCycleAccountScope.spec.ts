/**
 * H 循环科目定位守卫 —— **跨前后端交叉锁死 + 旧错码防复活**。
 *
 * 前端 `hCycleAccountScope.ts` 与后端 `four_table/h{N}_account_scope.py` 是同一份
 * 声明的两侧，本守卫直接读**后端源码**比对槽键 / 报表行号 / 兜底码，
 * 防「改一侧漏一侧」。
 *
 * 另锁死本 spec 实证的三个 P0：
 * - H3 原写 `1503`（可供出售金融资产 G6 域）/ `1504`（债权投资 G4 域）
 *   → 真族 `1521/1525/1526/1527`
 * - H8 原写 `1901`（待处理财产损溢，K2 `BS-014` 亦引用）/ `190101`（无点号平铺假码）
 *   → 真族 `1641/1642/1643`
 * - H9 原写 `2205`（合同负债，D7 域）→ 真族 `2601/2602`
 *
 * 🔴 旧错码不是「只显示错」：它同时用于 `writebackTB` 目标科目、
 * `substantive:adjudicated` 事件载荷、`/trial-balance?account_prefix=` 查询
 * → 把审定数写到别的循环科目名下。故本守卫扫 H8/H9 生产源码，
 * 禁止旧码以科目码形态出现。
 *
 * spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { H_CYCLE_SCOPES, createHCycleScope, type HCycleAccountDef } from '../hCycleAccountScope'
import { getHiExtractionSegments } from '../hiExtractionSegments'
import { H9_LEDGER_ACCOUNT_CODES } from '../h9LedgerPull'
import {
  H8_ADJ_ACCOUNT_OPTIONS,
  H8_ROU_COST_CODE,
  H8_ROU_DEP_CODE,
  H8_ROU_IMP_CODE,
} from '../useH8Adjustment'

// 本文件位于 .../workpaper/composables/__tests__/ → 回仓库根需 7 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const BACKEND_SCOPE_DIR = path.join(REPO_ROOT, 'backend/app/services/four_table')
const FRONTEND_WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

const ALL_CYCLES = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9', 'H10']

/** 实证真值（`report_config` + `account_chart` 双证） */
const TRUE_PRIMARY_CODE: Readonly<Record<string, string>> = {
  H1: '1601',
  H2: '1604',
  H3: '1521',
  H4: '1605',
  H5: '1631',
  H6: '1606',
  H7: '1621',
  H8: '1641',
  H9: '2601',
  H10: '6115',
}

/** 报表行次（`report_config` 实证；H5 油气资产无 BS 行） */
const TRUE_REPORT_ROW: Readonly<Record<string, string | null>> = {
  H1: 'BS-028',
  H2: 'BS-029',
  H3: 'BS-027',
  H4: 'BS-029',
  H5: null,
  H6: 'BS-028',
  H7: 'BS-030',
  H8: 'BS-031',
  H9: 'BS-063',
  H10: 'IS-018',
}

/** 历史错码 → 它实际归属的循环（防复活；也是「不得作兜底」清单） */
const LEGACY_WRONG_CODES: Readonly<Record<string, string>> = {
  '1901': '待处理财产损溢（K2 BS-014 亦引用）',
  '190101': '无点号平铺假码，非真实科目',
  '1902': 'H8 历史误写的累计折旧码（真值 1642）',
  '1903': 'H8 历史误写的减值准备码（真值 1643）',
  '2205': '合同负债（D7 循环 BS-047）',
  '220501': '无点号平铺假码，非真实科目',
  '1503': '可供出售金融资产（G6 域）',
  '1504': '债权投资（G4 域）',
  '1611': 'H5 历史误写的油气资产码（真值 1631）',
}

function backendScopeSource(cycle: string): string {
  const p = path.join(BACKEND_SCOPE_DIR, `${cycle.toLowerCase()}_account_scope.py`)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥 Python 注释与 docstring（缺陷说明里写着反例码，不剥必误判） */
function stripPy(src: string): string {
  return src
    .replace(/"""[\s\S]*?"""/g, '')
    .replace(/'''[\s\S]*?'''/g, '')
    .replace(/^\s*#.*$/gm, '')
}

/** 剥 TS/Vue 注释（生产源码的纠错说明里会写旧错码） */
function stripTs(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"\\])\/\/[^\n]*/g, '$1')
}

// ──────────────────────────────────────────────────────────────────────────────
// 双族真源解析（第三条边）
//
// 🔴 H8/H9 的后端兜底码不是字面量元组，而是模块级常量
// `_GROSS_CODES = codes_for_cycle_slot("H8", "gross")`。
// 只认 `fallback_standard_codes=(...)` 字面形态的判据会把它解析成 `[]`
// —— 于是「前端单族 vs 后端双族」这个真实缺陷会以「后端没声明」的形态出现，
// 更糟的是若前端也写成 `[]` 就双向静默通过。
//
// 故这里把 `dual_family_codes.py` 作为第三方真源一并解析，
// 形成「前端注册表 ↔ 后端 scope ↔ 双族真源」三向锁死。
// ──────────────────────────────────────────────────────────────────────────────

const DUAL_FAMILY_PY = path.join(BACKEND_SCOPE_DIR, 'dual_family_codes.py')

/** 解析 `dual_family_codes.py` → `{ '循环|槽键': ['码', ...] }` */
function parseDualFamilyCodes(): Record<string, string[]> {
  const raw = fs.readFileSync(DUAL_FAMILY_PY, 'utf-8')
  const py = stripPy(raw)

  // 1) DualFamilyGroup(...) 逐块取 slot_key / primary / alternate
  const bySlot: Record<string, string[]> = {}
  for (const block of py.split('DualFamilyGroup(').slice(1)) {
    const slotKey = block.match(/slot_key\s*=\s*["'](\w+)["']/)?.[1]
    const primary = block.match(/primary\s*=\s*["']([\w.-]+)["']/)?.[1]
    if (!slotKey || !primary) continue
    const altRaw = block.match(/alternate\s*=\s*(?:["']([\w.-]+)["']|None)/)
    const alternate = altRaw?.[1] ?? null
    bySlot[slotKey] =
      alternate && alternate !== primary ? [primary, alternate] : [primary]
  }

  // 2) CYCLE_SLOT_TO_DUAL_FAMILY 的 ("H8", "gross"): "gross" 映射
  const out: Record<string, string[]> = {}
  const mapBody = py.match(/CYCLE_SLOT_TO_DUAL_FAMILY[^=]*=\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
  for (const m of mapBody.matchAll(
    /\(\s*["'](\w+)["']\s*,\s*["'](\w+)["']\s*\)\s*:\s*["'](\w+)["']/g,
  )) {
    const [, cycle, slotKey, semanticKey] = m
    if (bySlot[semanticKey]) out[`${cycle}|${slotKey}`] = bySlot[semanticKey]
  }
  return out
}

const DUAL_FAMILY_CODES = parseDualFamilyCodes()

/**
 * 取后端某槽声明的兜底码。
 *
 * 支持两种形态：字面量元组 / 模块级常量引用（后者经双族真源解析）。
 * 返回 `null` 表示「解析不出」—— 调用方必须显式区分它与「确实声明为空」，
 * 否则解析器退化时会静默放行。
 */
function backendSlotFallbacks(
  cycle: string,
  py: string,
  block: string,
): { codes: string[]; via: 'literal' | 'constant' | 'absent' } | null {
  const literal = block.match(/fallback_standard_codes\s*=\s*\(([^)]*)\)/)
  if (literal) {
    return {
      codes: [...literal[1].matchAll(/["']([\w.-]+)["']/g)].map((m) => m[1]),
      via: 'literal',
    }
  }
  const ident = block.match(/fallback_standard_codes\s*=\s*([A-Za-z_]\w*)\s*,/)
  if (!ident) return { codes: [], via: 'absent' }

  // 模块级 `_X = codes_for_cycle_slot("H8", "gross")`
  const assign = py.match(
    new RegExp(`${ident[1]}\\s*=\\s*codes_for_cycle_slot\\(\\s*["'](\\w+)["']\\s*,\\s*["'](\\w+)["']\\s*\\)`),
  )
  if (!assign) return null
  const codes = DUAL_FAMILY_CODES[`${assign[1]}|${assign[2]}`]
  if (!codes) return null
  expect(assign[1], `${cycle} 的 ${ident[1]} 引用了别的循环的双族槽`).toBe(cycle)
  return { codes: [...codes], via: 'constant' }
}

// ──────────────────────────────────────────────────────────────────────────────
// 反向自检
// ──────────────────────────────────────────────────────────────────────────────

describe('自检：守卫本身没失效', () => {
  it('后端 10 个 scope 文件都能读到且非空', () => {
    for (const cyc of ALL_CYCLES) {
      const src = backendScopeSource(cyc)
      expect(src.length, `${cyc} scope 源码为空`).toBeGreaterThan(300)
      expect(src, `${cyc} 未声明 SemanticAccountSpec`).toContain('SemanticAccountSpec')
    }
  })

  it('stripPy 确实剥掉 docstring 里的反例码', () => {
    const raw = backendScopeSource('H8')
    expect(raw).toContain('1901') // docstring 里写着历史错码
    expect(stripPy(raw)).not.toContain('1901')
  })

  it('stripTs 确实剥掉 TS 注释里的反例码', () => {
    const sample = "// 历史写死 1901\nconst a = '1641' /* 不是 2205 */\n"
    const out = stripTs(sample)
    expect(out).not.toContain('1901')
    expect(out).not.toContain('2205')
    expect(out).toContain('1641')
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 注册表完整性
// ──────────────────────────────────────────────────────────────────────────────

describe('注册表完整性', () => {
  it('10 个循环全部登记', () => {
    expect(Object.keys(H_CYCLE_SCOPES).sort()).toEqual([...ALL_CYCLES].sort())
  })

  it('gross 兜底码 = 实证真值', () => {
    for (const cyc of ALL_CYCLES) {
      expect(H_CYCLE_SCOPES[cyc].def.grossFallback, `${cyc} gross 兜底码错`).toBe(
        TRUE_PRIMARY_CODE[cyc],
      )
    }
  })

  it('reportRowCode = report_config 实证值（H5 显式为 null）', () => {
    for (const cyc of ALL_CYCLES) {
      expect(H_CYCLE_SCOPES[cyc].def.reportRowCode, `${cyc} 报表行错`).toBe(
        TRUE_REPORT_ROW[cyc],
      )
    }
  })

  it('gross 槽兜底码首项与 grossFallback 一致（双真源不得分叉）', () => {
    for (const cyc of ALL_CYCLES) {
      const def = H_CYCLE_SCOPES[cyc].def
      expect(def.slotFallbacks.gross?.[0], `${cyc} slotFallbacks.gross 与 grossFallback 分叉`).toBe(
        def.grossFallback,
      )
    }
  })

  it('任何槽的兜底码都不得是历史错码', () => {
    const violations: string[] = []
    for (const cyc of ALL_CYCLES) {
      for (const [slot, codes] of Object.entries(H_CYCLE_SCOPES[cyc].def.slotFallbacks)) {
        for (const code of codes) {
          if (code in LEGACY_WRONG_CODES) {
            violations.push(`${cyc}.${slot} 兜底码 ${code} = ${LEGACY_WRONG_CODES[code]}`)
          }
        }
      }
    }
    expect(violations).toEqual([])
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 跨前后端交叉锁死
// ──────────────────────────────────────────────────────────────────────────────

describe('跨前后端交叉锁死', () => {
  it('槽键集合与后端 SemanticAccountSlot(key=...) 逐字一致', () => {
    for (const cyc of ALL_CYCLES) {
      const py = stripPy(backendScopeSource(cyc))
      const backendKeys = [...py.matchAll(/key\s*=\s*["']([\w]+)["']/g)].map((m) => m[1])
      expect(backendKeys.length, `${cyc} 后端未扫到槽键，正则失效`).toBeGreaterThan(0)
      const feKeys = Object.keys(H_CYCLE_SCOPES[cyc].def.slotFallbacks)
      expect([...feKeys].sort(), `${cyc} 前后端槽键不一致`).toEqual([...backendKeys].sort())
    }
  })

  it('后端 row_code 与前端 reportRowCode 一致', () => {
    for (const cyc of ALL_CYCLES) {
      const py = stripPy(backendScopeSource(cyc))
      const m = py.match(/row_code\s*=\s*(?:["']([\w-]+)["']|None)/)
      expect(m, `${cyc} 后端未声明 row_code`).not.toBeNull()
      const backendRow = m![1] ?? null
      expect(backendRow, `${cyc} 报表行前后端不一致`).toBe(
        H_CYCLE_SCOPES[cyc].def.reportRowCode,
      )
    }
  })

  it('后端 fallback_standard_codes 与前端 slotFallbacks 逐槽一致', () => {
    const viaConstant: string[] = []
    for (const cyc of ALL_CYCLES) {
      const py = stripPy(backendScopeSource(cyc))
      // 逐个 SemanticAccountSlot(...) 块取 key 与 fallback_standard_codes
      const blocks = py.split('SemanticAccountSlot(').slice(1)
      expect(blocks.length, `${cyc} 未切出槽块`).toBeGreaterThan(0)
      for (const block of blocks) {
        const keyM = block.match(/key\s*=\s*["'](\w+)["']/)
        if (!keyM) continue
        const key = keyM[1]
        const resolved = backendSlotFallbacks(cyc, py, block)
        expect(
          resolved,
          `${cyc}.${key} 后端兜底码解析不出（形态变了？解析器必须跟进而不是当成空）`,
        ).not.toBeNull()
        if (resolved!.via === 'constant') viaConstant.push(`${cyc}.${key}`)
        const feCodes = [...(H_CYCLE_SCOPES[cyc].def.slotFallbacks[key] ?? [])]
        expect(feCodes, `${cyc}.${key} 兜底码前后端不一致`).toEqual(resolved!.codes)
      }
    }
    // 反向自检：H8/H9 五个槽必须真的走了「常量 → 双族真源」这条解析路径。
    // 若哪天它们退回字面量元组，这条会打红提醒复核双族真源是否还是唯一真源。
    expect(viaConstant.sort(), '双族槽未经双族真源解析（解析器退化会静默放行）').toEqual([
      'H8.accum_dep',
      'H8.gross',
      'H8.impairment',
      'H9.gross',
      'H9.unearned_finance',
    ])
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 双族三向锁死（第三条边：dual_family_codes.py）
// ──────────────────────────────────────────────────────────────────────────────

describe('双族并存科目（H8 使用权资产 / H9 租赁负债）', () => {
  it('双族真源解析非空且覆盖 H8/H9 全部槽', () => {
    expect(Object.keys(DUAL_FAMILY_CODES).sort()).toEqual([
      'H8|accum_dep',
      'H8|gross',
      'H8|impairment',
      'H9|gross',
      'H9|unearned_finance',
    ])
  })

  it('前端双族兜底码含 alternate 族（只写 primary 只能取到 0.04%）', () => {
    expect(H_CYCLE_SCOPES.H8.def.slotFallbacks.gross).toEqual(['1641', '1651'])
    expect(H_CYCLE_SCOPES.H8.def.slotFallbacks.accum_dep).toEqual(['1642', '1652'])
    expect(H_CYCLE_SCOPES.H9.def.slotFallbacks.gross).toEqual(['2601', '2651'])
  })

  it('alternate 为 None 的槽不得臆造第二个码', () => {
    // 使用权资产减值准备：客户科目表未见 1653
    expect(H_CYCLE_SCOPES.H8.def.slotFallbacks.impairment).toEqual(['1643'])
    // 未确认融资费用：新族做成 2651.02 子科目，已含在 2651 父额内，再并取即双算
    expect(H_CYCLE_SCOPES.H9.def.slotFallbacks.unearned_finance).toEqual(['2602'])
  })

  it('grossFallback 取 primary（writebackTB / 请求参数用单码）', () => {
    expect(H_CYCLE_SCOPES.H8.def.grossFallback).toBe('1641')
    expect(H_CYCLE_SCOPES.H9.def.grossFallback).toBe('2601')
    for (const cyc of ['H8', 'H9']) {
      const def = H_CYCLE_SCOPES[cyc].def
      expect(def.slotFallbacks.gross[0], `${cyc} grossFallback 必须是 gross 首码`).toBe(
        def.grossFallback,
      )
    }
  })

  it('运行态 slotCodes 优先取 render 下发的码，兜底才用双族常量', () => {
    const scope = H_CYCLE_SCOPES.H8
    expect(scope.slotCodes(null, 'gross')).toEqual(['1641', '1651'])
    expect(
      scope.slotCodes({ slots: { gross: { codes: ['1651.01'] } } } as never, 'gross'),
    ).toEqual(['1651.01'])
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 旧错码防复活（扫 H3/H5/H8/H9 生产源码）
// ──────────────────────────────────────────────────────────────────────────────

function collectSources(dirNames: string[], filePredicate: (n: string) => boolean): string[] {
  const out: string[] = []
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue
        walk(p)
      } else if (
        (entry.name.endsWith('.ts') || entry.name.endsWith('.vue')) &&
        filePredicate(entry.name)
      ) {
        out.push(p)
      }
    }
  }
  for (const d of dirNames) walk(path.join(FRONTEND_WP_DIR, d))
  return out
}

/** 科目码形态：被引号包裹的裸 4~6 位数字（排除 `H8-3` 之类索引号） */
function accountCodeLiterals(src: string): string[] {
  return [...stripTs(src).matchAll(/['"](\d{4,6})['"]/g)].map((m) => m[1])
}

describe('旧错码防复活（H8/H9 生产源码）', () => {
  const H8_H9_LEGACY = ['1901', '190101', '1902', '1903', '2205', '220501']

  it('扫到了 H8/H9 源码文件（路径失效则打红）', () => {
    const files = collectSources(['composables', 'h8', 'h9'], (n) =>
      /h[89]/i.test(n),
    )
    expect(files.length, '未扫到 H8/H9 源码，路径或谓词失效').toBeGreaterThan(10)
  })

  it('H8/H9 生产源码不得出现旧错码作科目码', () => {
    const files = collectSources(['composables', 'h8', 'h9'], (n) => /h[89]/i.test(n))
    const violations: string[] = []
    for (const f of files) {
      const codes = new Set(accountCodeLiterals(fs.readFileSync(f, 'utf-8')))
      for (const wrong of H8_H9_LEGACY) {
        if (codes.has(wrong)) {
          violations.push(`${path.basename(f)}: ${wrong}（${LEGACY_WRONG_CODES[wrong]}）`)
        }
      }
    }
    expect(violations).toEqual([])
  })

  it('正向：H8/H9 真码确实出现在源码里（否则上一条在保护空集）', () => {
    const files = collectSources(['composables', 'h8', 'h9'], (n) => /h[89]/i.test(n))
    const all = new Set<string>()
    for (const f of files) {
      for (const c of accountCodeLiterals(fs.readFileSync(f, 'utf-8'))) all.add(c)
    }
    // 科目码集中在 hCycleAccountScope.ts，H8/H9 自身文件已改为委托 scope
    const scopeSrc = fs.readFileSync(
      path.join(FRONTEND_WP_DIR, 'composables/hCycleAccountScope.ts'),
      'utf-8',
    )
    const scopeCodes = new Set(accountCodeLiterals(scopeSrc))
    expect(scopeCodes.has('1641'), 'scope 未声明 H8 原值码 1641').toBe(true)
    expect(scopeCodes.has('2601'), 'scope 未声明 H9 租赁负债码 2601').toBe(true)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// useH8Adjustment 导出的三码来自 scope
// ──────────────────────────────────────────────────────────────────────────────

describe('useH8Adjustment 科目码委托 scope', () => {
  it('原值/折旧/减值三码 = h8Scope 声明', () => {
    const def = H_CYCLE_SCOPES.H8.def
    expect(H8_ROU_COST_CODE).toBe(def.slotFallbacks.gross[0])
    expect(H8_ROU_DEP_CODE).toBe(def.slotFallbacks.accum_dep[0])
    expect(H8_ROU_IMP_CODE).toBe(def.slotFallbacks.impairment[0])
  })

  it('录入下拉包含真族三码且不含旧错码', () => {
    const codes = H8_ADJ_ACCOUNT_OPTIONS.map((o) => o.code)
    expect(codes).toContain(H8_ROU_COST_CODE)
    expect(codes).toContain(H8_ROU_DEP_CODE)
    expect(codes).toContain(H8_ROU_IMP_CODE)
    for (const wrong of ['1901', '1902', '1903', '2205', '1802']) {
      expect(codes, `下拉仍含旧错码 ${wrong}`).not.toContain(wrong)
    }
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 工厂语义
// ──────────────────────────────────────────────────────────────────────────────

describe('createHCycleScope 语义', () => {
  const def: HCycleAccountDef = {
    cycle: 'XX',
    reportRowCode: 'BS-999',
    slotFallbacks: { gross: ['9001'], noFallback: [] },
    grossFallback: '9001',
  }
  const scope = createHCycleScope(def)

  it('溯源优先于兜底', () => {
    const src = { slots: { gross: { codes: ['8888'], found: true } } } as any
    expect(scope.slotCodes(src, 'gross')).toEqual(['8888'])
    expect(scope.grossCode(src)).toBe('8888')
  })

  it('未下发时回退兜底码', () => {
    expect(scope.slotCodes(null, 'gross')).toEqual(['9001'])
    expect(scope.grossCode(null)).toBe('9001')
  })

  it('无兜底码声明的槽返空，绝不凭空造前缀', () => {
    expect(scope.slotCodes(null, 'noFallback')).toEqual([])
    expect(scope.slotCodes(null, '不存在的槽')).toEqual([])
  })

  it('「本项目无此科目」与「render 未下发」区分开', () => {
    // render 未下发 = 未知，不能判定为无此科目
    expect(scope.isGrossAbsent(null)).toBe(false)
    expect(scope.isGrossAbsent({} as any)).toBe(false)
    // 显式 found=false 才是「本项目无此科目」
    expect(
      scope.isGrossAbsent({ slots: { gross: { codes: [], found: false } } } as any),
    ).toBe(true)
    // found=true 不算缺失
    expect(
      scope.isGrossAbsent({ slots: { gross: { codes: ['1'], found: true } } } as any),
    ).toBe(false)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 旧错码不得作**用户可见文案**出现（Task 18 浏览器实测挖出）
//
// 🔴 上面「旧错码防复活」只扫**引号包裹**的科目码形态，而浏览器实测看到的是
// 「一、使用权资产原值（科目1901）」「与试算平衡表核对 → 使用权资产原值(1901)」
// 「抽凭引擎（科目 1901 使用权资产-减少）」这类**模板文案** —— 引号判据一个都抓不到。
// 审定表把错科目号（1901 = 待处理财产损溢）直接展示给审计师，破坏逻辑追溯。
//
// 判据 = 剥注释后的**代码级**源码里不得出现这些数字（历史说明写在注释/docstring 里合法）。
// ──────────────────────────────────────────────────────────────────────────────

/** 历史说明允许留在注释里，故只扫剥注释后的代码 */
const LEGACY_DIGITS = ['1901', '190101', '1902', '1903', '2205', '220501'] as const

/**
 * 判「代码里出现了旧错码数字」。
 *
 * 🔴 **不能用 `\b`**：真实缺陷形态是 `cost1901`（形参键）与 `cost1901_unadjusted`
 * （render 键），`1901` 两侧都是词字符 ⇒ `\b1901\b` **恒不成立**，而这正是本轮
 * Task 18 修掉的东西（M14 变异实测 GREEN 抓出该盲区）。
 *
 * 正确判据 = 「不是更长数字串的一部分」，用数字前后瞻。这样：
 * - `cost1901` / `科目1901）` → 抓到
 * - `190101` / `11901` → 不误报（`190101` 是独立登记项，有自己的判据）
 */
function hasLegacyDigits(code: string, wrong: string): boolean {
  return new RegExp(`(?<![0-9])${wrong}(?![0-9])`).test(code)
}

/**
 * 两个**宿主** SFC 在 `workpaper/` 根目录，不在 `composables|h8|h9` 三个子目录里
 * ⇒ 按目录收集会把它们整个漏掉。而宿主正是渲染全局 TB 勾稽告警的地方：
 * `GtH8RightOfUseAssets.vue` 曾在告警文案里写死「试算平衡表(1901净额)」，
 * 靠子目录扫描的守卫**全绿**（Task 18 实测抓出）。
 */
const H_CYCLE_HOSTS = ['GtH8RightOfUseAssets.vue', 'GtH9LeaseLiabilities.vue'] as const

describe('旧错码不得作用户可见文案（H8/H9）', () => {
  const files = () => [
    ...collectSources(['composables', 'h8', 'h9'], (n) => /h[89]/i.test(n)),
    ...H_CYCLE_HOSTS.map((n) => path.join(FRONTEND_WP_DIR, n)),
  ]

  it('扫描面非空且含已知锚点文件（含两个宿主 SFC）', () => {
    const names = files().map((f) => path.basename(f))
    expect(names.length).toBeGreaterThan(10)
    expect(names).toContain('H8TabAdjudication.vue')
    expect(names).toContain('useH8Adjudication.ts')
    expect(names).toContain('h9LedgerPull.ts')
    expect(names).toContain('useH9FormData.ts')
    // 宿主必须在扫描面内（漏了它 = 全局 TB 告警文案里的错码永远抓不到）
    for (const h of H_CYCLE_HOSTS) {
      expect(names, `宿主 ${h} 不在扫描面`).toContain(h)
      expect(fs.existsSync(path.join(FRONTEND_WP_DIR, h)), `${h} 不存在`).toBe(true)
    }
  })

  it('H8 宿主的 TB 勾稽告警科目码由 scope 派生（不得写死）', () => {
    const code = stripTs(
      fs.readFileSync(path.join(FRONTEND_WP_DIR, 'GtH8RightOfUseAssets.vue'), 'utf-8'),
    )
    expect(code, '告警文案未由 scope 派生科目码').toContain('tbReconcileCodeText')
    expect(code).toContain("h8Scope.slotCodes(src, 'gross')")
    expect(code).toContain("h8Scope.slotCodes(src, 'accum_dep')")
    // 文案里不得残留任何写死的 4 位科目码字面量
    const banner = code.match(/试算平衡表\(([^)]*)\)/)
    expect(banner, '未找到 TB 告警文案（形态变了，解析器要跟进）').not.toBeNull()
    expect(banner![1], 'TB 告警文案仍写死科目码').not.toMatch(/\d{4}/)
  })

  it('useH9FormData 的 TB 字段名不得内嵌科目码（改码后名字会过期）', () => {
    const code = stripTs(
      fs.readFileSync(path.join(FRONTEND_WP_DIR, 'composables/useH9FormData.ts'), 'utf-8'),
    )
    // 旧名把 2205（合同负债 D7 域）嵌在标识符里，`\b` 判据抓不到
    for (const old of ['unadjusted2205', 'audited2205', 'ACCOUNT_CODE_2601']) {
      expect(code, `仍在用内嵌科目码的标识符 ${old}`).not.toContain(old)
    }
    expect(code).toContain('unadjustedLeaseLiability')
    expect(code).toContain('ACCOUNT_CODE_LEASE_LIABILITY')
  })

  it('剥注释后不得出现旧错码（含模板文案与标识符）', () => {
    const violations: string[] = []
    for (const f of files()) {
      const code = stripTs(fs.readFileSync(f, 'utf-8'))
      for (const wrong of LEGACY_DIGITS) {
        if (hasLegacyDigits(code, wrong)) {
          violations.push(`${path.basename(f)}: ${wrong}（${LEGACY_WRONG_CODES[wrong] ?? '旧错码'}）`)
        }
      }
    }
    // 用 join 而非 toEqual([])：vitest 对长数组会截断成 `[ …(5) ]`，看不到是哪几处
    expect(violations.join(' | ')).toBe('')
  })

  it('反向自检：标识符内嵌的错码也要抓到（`\\b` 判据抓不到 —— M14 变异实测）', () => {
    // 真实缺陷形态：形参键 `cost1901` / render 键 `cost1901_unadjusted`
    expect(hasLegacyDigits('const x = { cost1901: number }', '1901')).toBe(true)
    expect(hasLegacyDigits("cost: num('cost1901_unadjusted'),", '1901')).toBe(true)
    // 模板文案形态
    expect(hasLegacyDigits('<p>一、使用权资产原值（科目1901）</p>', '1901')).toBe(true)
    // 更长数字不误报（`190101` 是独立登记项，不该被 `1901` 抓走）
    expect(hasLegacyDigits("'190101'", '1901')).toBe(false)
    expect(hasLegacyDigits("'11901'", '1901')).toBe(false)
    expect(hasLegacyDigits("'220501'", '2205')).toBe(false)
    // 🔴 证明换判据是必要的：`\b` 版本对标识符内嵌形态恒漏
    expect(/\b1901\b/.test("num('cost1901_unadjusted')")).toBe(false)
  })

  it('反向自检：stripTs 确实保留模板文案、只剥注释', () => {
    const fixture = [
      '<template>',
      '  <p>科目1901 使用权资产</p>',
      '</template>',
      '<script setup lang="ts">',
      '// 历史实现写死 1902',
      '/* 以及 1903 */',
      'const a = 1',
      '</script>',
    ].join('\n')
    const code = stripTs(fixture)
    // 模板文案保留 ⇒ 上一条断言能抓到它
    expect(code).toContain('科目1901')
    // 注释被剥 ⇒ 历史说明不会被误判
    expect(code).not.toContain('1902')
    expect(code).not.toContain('1903')
  })

  it('H9 序时账取数走双族科目而非 2205（合同负债 D7 域）', () => {
    const src = fs.readFileSync(
      path.join(FRONTEND_WP_DIR, 'composables/h9LedgerPull.ts'),
      'utf-8',
    )
    const code = stripTs(src)
    // 不得写死任何 URL 段科目码
    expect(code, 'ledger 端点仍写死科目码').not.toMatch(/ledger\/entries\/\d+/)
    // 必须由 scope 派生
    expect(code).toContain('h9Scope.def.slotFallbacks.gross')
    expect(H9_LEDGER_ACCOUNT_CODES).toEqual(H_CYCLE_SCOPES.H9.def.slotFallbacks.gross)
  })

  it('HI 溯源面板 H8/H9 段取数公式覆盖双族', () => {
    const h8 = getHiExtractionSegments('H8')
    const h9 = getHiExtractionSegments('H9')
    expect(h8.length).toBe(3)
    expect(h9.length).toBe(2)
    // 原值 / 累计折旧 / 租赁负债三个双族槽的公式必须含两族
    const grossExpr = h8[0].expression
    expect(grossExpr).toContain("TB('1641','期末余额')")
    expect(grossExpr).toContain("TB('1651','期末余额')")
    expect(h8[1].expression).toContain("TB('1652','期末余额')")
    expect(h9[0].expression).toContain("TB('2651','期末余额')")
    // alternate 为 None 的两槽保持单码（不臆造第二个码）
    expect(h8[2].expression).toBe("TB('1643','期末余额')")
    expect(h9[1].expression).toBe("TB('2602','期末余额')")
    // 全部段的公式不得出现旧错码
    for (const seg of [...h8, ...h9]) {
      for (const wrong of LEGACY_DIGITS) {
        expect(seg.expression, `${seg.anchorKey} 公式含旧错码 ${wrong}`).not.toContain(wrong)
        expect(seg.label, `${seg.anchorKey} 标签含旧错码 ${wrong}`).not.toContain(wrong)
      }
    }
  })

  it('H8 审定表宿主必须给审定表 Tab 传 :html-data（否则 TB 核对拿不到真实数）', () => {
    const host = fs.readFileSync(path.join(FRONTEND_WP_DIR, 'GtH8RightOfUseAssets.vue'), 'utf-8')
    const m = host.match(/<H8TabAdjudication[\s\S]*?\/>/)
    expect(m, '宿主未渲染 H8TabAdjudication').not.toBeNull()
    expect(m![0], 'H8TabAdjudication 缺 :html-data').toContain(':html-data')

    // 🔴 必须剥注释：注释里写着「真实金额就在 tb_values.rou_asset_unadjusted 里」，
    //    裸 toContain 会被这段说明文字骗过（M14 变异实测 GREEN 抓出）。
    const tabCode = stripTs(
      fs.readFileSync(path.join(FRONTEND_WP_DIR, 'h8/core/H8TabAdjudication.vue'), 'utf-8'),
    )
    expect(tabCode, '审定表未声明 htmlData prop').toMatch(/htmlData\?\s*:/)
    // 必须真的把 TB 未审数喂给 composable（否则又是 dead prop）
    expect(tabCode, 'tbUnadjusted 未传给 composable（dead prop）').toMatch(/tbUnadjusted\s*,/)

    // 判据落在 computed **函数体内**：三个 render 键必须都被读到，
    // 少读一个就是某一层（原值/折旧/减值）的 TB 核对静默退化。
    const body = tabCode.match(/const tbUnadjusted = computed\(\(\) => \{([\s\S]*?)\n\}\)/)
    expect(body, '未找到 tbUnadjusted computed 函数体（形态变了，解析器要跟进）').not.toBeNull()
    for (const key of ['rou_asset_unadjusted', 'rou_dep_unadjusted', 'rou_imp_unadjusted']) {
      expect(body![1], `tbUnadjusted 未读 render 下发键 ${key}`).toContain(key)
    }
  })

  it('useH8Adjudication 的 TB 核对形参已改语义键（旧键名含错码）', () => {
    const src = fs.readFileSync(
      path.join(FRONTEND_WP_DIR, 'composables/useH8Adjudication.ts'),
      'utf-8',
    )
    const code = stripTs(src)
    for (const wrong of ['cost1901', 'dep1902', 'impair1903']) {
      expect(code, `仍在用旧键名 ${wrong}`).not.toContain(wrong)
    }
    expect(code).toMatch(/tbUnadjusted\?\s*:\s*Ref<\{\s*cost:/)
  })
})
