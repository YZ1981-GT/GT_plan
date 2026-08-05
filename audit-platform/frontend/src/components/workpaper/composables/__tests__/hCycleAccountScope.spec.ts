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
    for (const cyc of ALL_CYCLES) {
      const py = stripPy(backendScopeSource(cyc))
      // 逐个 SemanticAccountSlot(...) 块取 key 与 fallback_standard_codes
      const blocks = py.split('SemanticAccountSlot(').slice(1)
      expect(blocks.length, `${cyc} 未切出槽块`).toBeGreaterThan(0)
      for (const block of blocks) {
        const keyM = block.match(/key\s*=\s*["'](\w+)["']/)
        if (!keyM) continue
        const key = keyM[1]
        const fbM = block.match(/fallback_standard_codes\s*=\s*\(([^)]*)\)/)
        const backendCodes = fbM
          ? [...fbM[1].matchAll(/["']([\w.-]+)["']/g)].map((m) => m[1])
          : []
        const feCodes = [...(H_CYCLE_SCOPES[cyc].def.slotFallbacks[key] ?? [])]
        expect(feCodes, `${cyc}.${key} 兜底码前后端不一致`).toEqual(backendCodes)
      }
    }
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
