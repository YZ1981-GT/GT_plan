/**
 * K 循环前后端科目真源**交叉锁死**守卫（Property 10 / Requirement 3.5, 13.3）。
 *
 * **为什么需要这个文件**
 *
 * 既有 `kCycleAccountScope.spec.ts` 只做两件事：①禁止源码出现「错误科目码」
 * ②`tbSourceCodes` 有前端消费点。它**完全不校验 row_code** —— 于是
 * 2026-08-09 后端 `k_cycle_specs.py` 改正 9 处 row_code 后，前端 11 个
 * `kXAccountScope.ts` 仍留着旧的错码，而全部既有守卫（前端 vitest / 后端
 * pytest / `get_diagnostics`）**一条都不红**。
 *
 * 实测漂移（改造前）::
 *
 *     ==========  ==============  ==============  =============
 *     循环          前端 listed      前端 soe         后端（真值）
 *     ==========  ==============  ==============  =============
 *     K3          BS-053          BS-075          BS-050
 *     K4          BS-058          BS-081          BS-053
 *     K5          BS-068          BS-094          BS-065
 *     K6          BS-015          BS-024          BS-012
 *     K7          BS-069          BS-095          BS-066
 *     K8          IS-004          IS-022          IS-004
 *     K9          IS-005          IS-023          IS-005
 *     K10         IS-010          IS-030          IS-010
 *     K11         IS-017          IS-038          IS-017
 *     K12         IS-020          IS-041          IS-020
 *     K13         IS-021          IS-043          IS-021
 *     ==========  ==============  ==============  =============
 *
 * 这些常量当前只被**溯源展示**消费（`k5SourceLabel` 拼「报表行 BS-094」给审计师看），
 * 故漂移不改变取数金额 —— 但它是**审计追溯信息**：面板告诉审计师「本数取自报表行
 * BS-094」而后端实际用的是 BS-065，审计师按面板去核对 report_config 会找不到对应
 * 关系。平台铁律「审计 UI 必须有逻辑追溯能力」要求它准确。
 *
 * **判据形态**：直读后端 `k_cycle_specs.py` 源码抽声明值，与前端常量逐字比对。
 * 不用 fixture、不用冻结表 —— 后端改了这里必须跟着改，这正是「交叉锁死」的定义。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ (Task 7)
 */

import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ─── 路径解析（双哨兵向上查找，禁写死回退级数）─────────────────────────────

/**
 * 从当前文件向上找仓库根 —— 判据是**两个具体文件同时存在**。
 *
 * 🔴 哨兵必须是文件不能是目录：`audit-platform/backend/app/routers` 是历史遗留
 * 空目录，用目录做哨兵会在 `audit-platform` 层提前停下（memory 已记）。
 */
function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = path.join(dir, 'backend', 'app', 'services', 'four_table', 'k_cycle_specs.py')
    const b = path.join(dir, '.kiro', 'steering', 'memory.md')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('找不到仓库根（哨兵 backend/app/services/four_table/k_cycle_specs.py + .kiro/steering/memory.md）')
}

const REPO_ROOT = findRepoRoot()
const BACKEND_SPECS = path.join(REPO_ROOT, 'backend', 'app', 'services', 'four_table', 'k_cycle_specs.py')
const COMPOSABLES = path.resolve(__dirname, '..')

// ─── 后端声明抽取 ───────────────────────────────────────────────────────────

interface BackendSpec {
  wpCode: string
  rowCodeListed: string
  rowCodeSoe: string
  fallbackStandard: string
}

/**
 * 剥 python 注释与 docstring。
 *
 * 🔴 必须剥 —— 后端声明里 `row_code_evidence` 大量引用**旧错码**作留痕
 * （「原值 listed=BS-053…」），不剥会把留痕文字抽成声明值。
 */
function stripPy(src: string): string {
  let out = src.replace(/"""[\s\S]*?"""/g, '""')
  out = out.replace(/'''[\s\S]*?'''/g, "''")
  out = out.replace(/(?<!["'])#[^\n]*/g, '')
  return out
}

/** 取 `K_CYCLE_SPECS = { ... }` 的字典体（按方括号/花括号配对，不用固定窗口）。 */
function specTableBody(code: string): string {
  const anchor = code.indexOf('K_CYCLE_SPECS: dict[str, KCycleSpec] = {')
  if (anchor < 0) throw new Error('后端未找到 K_CYCLE_SPECS 声明（守卫自身缺陷或已改名）')
  const open = code.indexOf('{', anchor)
  let depth = 0
  for (let i = open; i < code.length; i += 1) {
    const ch = code[i]
    if (ch === '{') depth += 1
    else if (ch === '}') {
      depth -= 1
      if (depth === 0) return code.slice(open + 1, i)
    }
  }
  throw new Error('K_CYCLE_SPECS 花括号未配对')
}

function parseBackendSpecs(): Map<string, BackendSpec> {
  const code = stripPy(fs.readFileSync(BACKEND_SPECS, 'utf-8'))
  const body = specTableBody(code)
  const out = new Map<string, BackendSpec>()

  // 每个条目形如：  "K3": KCycleSpec(\n  wp_code="K3", ... \n ),
  const entryRe = /"(K\d+)"\s*:\s*KCycleSpec\s*\(/g
  let m: RegExpExecArray | null
  while ((m = entryRe.exec(body)) !== null) {
    const wp = m[1]
    // 从 `KCycleSpec(` 的左括号起做圆括号配对，取该条目的完整实参区
    const open = body.indexOf('(', m.index + m[0].length - 1)
    let depth = 0
    let end = -1
    for (let i = open; i < body.length; i += 1) {
      const ch = body[i]
      if (ch === '(') depth += 1
      else if (ch === ')') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) throw new Error(`${wp} 的 KCycleSpec(...) 圆括号未配对`)
    const args = body.slice(open + 1, end)
    const pick = (field: string): string => {
      const r = new RegExp(`\\b${field}\\s*=\\s*["']([^"']*)["']`)
      const hit = r.exec(args)
      return hit ? hit[1] : ''
    }
    out.set(wp, {
      wpCode: wp,
      rowCodeListed: pick('row_code_listed'),
      rowCodeSoe: pick('row_code_soe'),
      fallbackStandard: pick('fallback_standard'),
    })
  }
  return out
}

/** 后端 K6 负债侧 / 备抵侧独立常量（不在字典里）。 */
function parseBackendModuleConst(name: string): string {
  const code = stripPy(fs.readFileSync(BACKEND_SPECS, 'utf-8'))
  const r = new RegExp(`(?:^|\\n)${name}\\s*=\\s*["']([^"']+)["']`)
  const hit = r.exec(code)
  return hit ? hit[1] : ''
}

// ─── 前端常量抽取 ───────────────────────────────────────────────────────────

/** 剥 TS 注释（`//` 与 `/* *\/`），保留普通字符串字面量。 */
function stripTs(src: string): string {
  let out = src.replace(/\/\*[\s\S]*?\*\//g, '')
  out = out.replace(/(?<!:)\/\/[^\n]*/g, '')
  return out
}

function readScope(wp: string): string | null {
  const p = path.resolve(COMPOSABLES, `${wp.toLowerCase()}AccountScope.ts`)
  if (!fs.existsSync(p)) return null
  return stripTs(fs.readFileSync(p, 'utf-8'))
}

function frontConst(src: string, name: string): string | null {
  const r = new RegExp(`export\\s+const\\s+${name}\\s*(?::[^=]*)?=\\s*['"\`]([^'"\`]*)['"\`]`)
  const hit = r.exec(src)
  return hit ? hit[1] : null
}

// ─── 覆盖面声明（K1 无 scope 文件，单独一条断言）────────────────────────────

/** 有 `kXAccountScope.ts` 的循环（K1 是唯一例外，见 `test_k1_has_account_scope`）。 */
const SCOPED_CYCLES = ['K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9', 'K10', 'K11', 'K12', 'K13']

/**
 * K2 用单字段 `K2_REPORT_ROW_CODE`（两准则同码，早于双字段范式建立），
 * 其余用 `X_REPORT_ROW_CODE_LISTED` / `_SOE` 双字段。
 *
 * 两种形态都合法（K 循环实测两准则同号），故判据按形态分流而非强行统一。
 */
const SINGLE_FIELD_CYCLES = new Set(['K2'])

// ─── 类 A：判据自检（应当全绿）───────────────────────────────────────────────

describe('判据自检', () => {
  it('后端声明表可解析且覆盖 K1~K13', () => {
    const specs = parseBackendSpecs()
    const want = ['K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9', 'K10', 'K11', 'K12', 'K13']
    const missing = want.filter((w) => !specs.has(w))
    expect(missing, `后端声明表解析结果缺失：${missing.join(',')}`).toEqual([])
    for (const wp of want) {
      const s = specs.get(wp)!
      expect(s.rowCodeListed, `${wp} row_code_listed 抽取为空`).toMatch(/^(BS|IS|IMP|EQ|CFS)-\d+$/)
      expect(s.rowCodeSoe, `${wp} row_code_soe 抽取为空`).toMatch(/^(BS|IS|IMP|EQ|CFS)-\d+$/)
    }
  })

  it('剥 python 注释真的生效（否则会把 row_code_evidence 里的旧错码抽成声明值）', () => {
    // K3 的留痕文本含 `原值 listed=BS-053`，剥注释后不应出现在可解析区
    const raw = fs.readFileSync(BACKEND_SPECS, 'utf-8')
    expect(raw).toContain('row_code_evidence')
    const sample = '# row_code_listed="BS-999"\nrow_code_listed="BS-050"\n'
    const stripped = stripPy(sample)
    expect(stripped).not.toContain('BS-999')
    expect(stripped).toContain('BS-050')
  })

  it('剥 TS 注释真的生效', () => {
    const sample = `// export const X_REPORT_ROW_CODE_LISTED = 'BS-999'\nexport const Y = 'BS-050'`
    const stripped = stripTs(sample)
    expect(stripped).not.toContain('BS-999')
    expect(stripped).toContain('BS-050')
  })

  it('前端 scope 文件全部存在且非空', () => {
    for (const wp of SCOPED_CYCLES) {
      const src = readScope(wp)
      expect(src, `${wp.toLowerCase()}AccountScope.ts 不存在`).not.toBeNull()
      expect(src!.length, `${wp} scope 文件过短`).toBeGreaterThan(200)
    }
  })

  it('替身自检：漂移检测器对构造的不一致必须报出差异', () => {
    // 复现旧缺陷形态：前端 BS-094 vs 后端 BS-065
    const fe = "export const K5_REPORT_ROW_CODE_SOE = 'BS-094'"
    const got = frontConst(fe, 'K5_REPORT_ROW_CODE_SOE')
    expect(got).toBe('BS-094')
    expect(got).not.toBe('BS-065')
  })
})

// ─── 类 B：前后端交叉锁死 ───────────────────────────────────────────────────

describe('Property 10: 前端 row_code 与后端声明逐字一致', () => {
  const specs = parseBackendSpecs()

  it.each(SCOPED_CYCLES)('%s 的报表行常量与后端一致', (wp) => {
    const src = readScope(wp)!
    const be = specs.get(wp)!
    const diffs: string[] = []

    if (SINGLE_FIELD_CYCLES.has(wp)) {
      const single = frontConst(src, `${wp}_REPORT_ROW_CODE`)
      expect(single, `${wp} 未导出 ${wp}_REPORT_ROW_CODE`).not.toBeNull()
      if (single !== be.rowCodeListed) {
        diffs.push(`  ${wp}_REPORT_ROW_CODE: 前端=${single} 后端=${be.rowCodeListed}`)
      }
      // 单字段形态的前提是两准则同码 —— 后端哪天分变体，这条会强制先改前端形态
      if (be.rowCodeListed !== be.rowCodeSoe) {
        diffs.push(
          `  后端 ${wp} 两准则已分变体（listed=${be.rowCodeListed} soe=${be.rowCodeSoe}），` +
            `前端仍是单字段 ${wp}_REPORT_ROW_CODE ⇒ 必须改成双字段`,
        )
      }
    } else {
      const feListed = frontConst(src, `${wp}_REPORT_ROW_CODE_LISTED`)
      const feSoe = frontConst(src, `${wp}_REPORT_ROW_CODE_SOE`)
      expect(feListed, `${wp} 未导出 ${wp}_REPORT_ROW_CODE_LISTED`).not.toBeNull()
      expect(feSoe, `${wp} 未导出 ${wp}_REPORT_ROW_CODE_SOE`).not.toBeNull()
      if (feListed !== be.rowCodeListed) {
        diffs.push(`  ${wp}_REPORT_ROW_CODE_LISTED: 前端=${feListed} 后端=${be.rowCodeListed}`)
      }
      if (feSoe !== be.rowCodeSoe) {
        diffs.push(`  ${wp}_REPORT_ROW_CODE_SOE: 前端=${feSoe} 后端=${be.rowCodeSoe}`)
      }
    }

    expect(diffs, `${wp} 前后端报表行漂移 —— 后端已按 report_config 连库对账改正，前端未跟进：\n${diffs.join('\n')}`).toEqual([])
  })

  it.each(SCOPED_CYCLES)('%s 的兜底标准码与后端一致', (wp) => {
    const src = readScope(wp)!
    const be = specs.get(wp)!
    const feName = SINGLE_FIELD_CYCLES.has(wp) ? `${wp}_GROSS_FALLBACK_STANDARD` : `${wp}_FALLBACK_STANDARD`
    const fe = frontConst(src, feName)
    expect(fe, `${wp} 未导出 ${feName}`).not.toBeNull()
    expect(
      fe,
      `${wp} 兜底标准码漂移：前端=${fe} 后端=${be.fallbackStandard}（后端为空串表示宁缺勿造）`,
    ).toBe(be.fallbackStandard)
  })
})

describe('Property 10: K6 负债侧 / 备抵侧常量交叉锁死', () => {
  it('K6 前端须表达资产侧与负债侧两个报表行', () => {
    const src = readScope('K6')!
    const beAsset = parseBackendSpecs().get('K6')!.rowCodeListed
    const beLiab = parseBackendModuleConst('K6_LIABILITY_ROW_CODE')
    const beProv = parseBackendModuleConst('K6_PROVISION_ROW_CODE')

    expect(beLiab, '后端 K6_LIABILITY_ROW_CODE 抽取失败').toMatch(/^BS-\d+$/)
    expect(beProv, '后端 K6_PROVISION_ROW_CODE 抽取失败').toMatch(/^IMP-\d+$/)
    // 资产侧与负债侧必须是不同的行（同码即说明有一侧写错）
    expect(beAsset).not.toBe(beLiab)

    for (const code of [beAsset, beLiab, beProv]) {
      expect(
        src,
        `K6 scope 未提及后端声明的报表行 ${code} —— K6 一个循环管资产/负债/备抵三侧，` +
          `前端只表达一侧会让溯源面板漏报`,
      ).toContain(code)
    }
  })
})

describe('Requirement 3.5: K1 有前端科目真源', () => {
  it('k1AccountScope.ts 存在且与后端交叉锁死', () => {
    const p = path.resolve(COMPOSABLES, 'k1AccountScope.ts')
    expect(
      fs.existsSync(p),
      'k1AccountScope.ts 不存在 —— K1 是唯一无前端科目真源的 K 循环，' +
        '其 1221/1231 字面量散落在 useK1FormData / useK1Adjustment / K1TabAdjudication 等处',
    ).toBe(true)

    const src = stripTs(fs.readFileSync(p, 'utf-8'))
    const be = parseBackendSpecs().get('K1')!
    const feRow = frontConst(src, 'K1_REPORT_ROW_CODE')
    expect(feRow, 'k1AccountScope.ts 未导出 K1_REPORT_ROW_CODE').not.toBeNull()
    expect(feRow, `K1 报表行漂移：前端=${feRow} 后端=${be.rowCodeListed}`).toBe(be.rowCodeListed)

    const feFallback = frontConst(src, 'K1_GROSS_FALLBACK_STANDARD')
    expect(feFallback, `K1 兜底码漂移：前端=${feFallback} 后端=${be.fallbackStandard}`).toBe(
      be.fallbackStandard,
    )
  })

  it('K1 备抵兜底码与后端 fallback_provision 一致', () => {
    const p = path.resolve(COMPOSABLES, 'k1AccountScope.ts')
    if (!fs.existsSync(p)) {
      throw new Error('k1AccountScope.ts 不存在（上一条已报）')
    }
    const src = stripTs(fs.readFileSync(p, 'utf-8'))
    const beCode = stripPy(fs.readFileSync(BACKEND_SPECS, 'utf-8'))
    // 后端 K1 的 fallback_provision=("1231-03",)
    expect(beCode).toContain('"1231-03"')
    const fe = frontConst(src, 'K1_BAD_DEBT_FALLBACK_STANDARD')
    expect(
      fe,
      'K1 备抵兜底码必须是 1231-03（其他应收款专属备抵），不是宽口径 1231 —— ' +
        '宽口径会把应收账款坏账 1231-02 算进来',
    ).toBe('1231-03')
  })
})

// ─── 防回退：旧错码不得复活 ──────────────────────────────────────────────────

describe('Property 2 防回退: 前端不得复活旧错码', () => {
  /**
   * 改造前前端各 scope 里的**旧错码** → 该码实际指向的科目。
   *
   * 这些码都在 `report_config` 里真实存在（指向别的科目），故不能靠「码不存在」
   * 判断，只能按「该循环不得出现这些码」逐条锁死。
   */
  const REVIVED: Record<string, Array<[string, string]>> = {
    K3: [
      ['BS-053', '其他流动负债（K4 的行）'],
      ['BS-075', 'listed 侧是股本 / soe 侧 formula NULL'],
    ],
    K4: [
      ['BS-058', 'listed 侧非其他流动负债'],
      ['BS-081', '实收资本（或股本）'],
    ],
    K5: [
      ['BS-068', '其他非流动负债（L7 的行）'],
      ['BS-094', 'formula NULL'],
    ],
    K6: [
      ['BS-015', '流动资产合计（ROW 派生行）'],
      ['BS-024', '长期股权投资（G7 的行）'],
    ],
    K7: [
      ['BS-069', '非流动负债合计（ROW 派生行）'],
      ['BS-095', 'formula NULL'],
    ],
    K8: [['IS-022', '三、利润总额（ROW 派生行）']],
    K9: [['IS-023', '减：所得税费用']],
    K10: [['IS-030', '五、其他综合收益的税后净额']],
    K11: [['IS-038', '一码两义（5.其他 / 资产减值损失）']],
    K12: [['IS-041', 'listed 侧是基本每股收益']],
    K13: [['IS-043', 'listed 侧是其他债权投资信用减值准备']],
  }

  it('登记表非空且循环名合法（防判据空转）', () => {
    expect(Object.keys(REVIVED).length).toBeGreaterThanOrEqual(11)
    for (const wp of Object.keys(REVIVED)) {
      expect(SCOPED_CYCLES).toContain(wp)
      expect(REVIVED[wp].length).toBeGreaterThan(0)
      for (const [code, why] of REVIVED[wp]) {
        expect(code).toMatch(/^(BS|IS)-\d+$/)
        expect(why.length, `${wp}/${code} 的理由过短`).toBeGreaterThan(4)
      }
    }
  })

  it.each(Object.keys(REVIVED))('%s scope 不得出现旧错码', (wp) => {
    const src = readScope(wp)!
    const hits: string[] = []
    for (const [code, why] of REVIVED[wp]) {
      // 只查字符串字面量形态（剥注释后仍出现 = 真声明）
      for (const quoted of [`'${code}'`, `"${code}"`, `\`${code}\``]) {
        if (src.includes(quoted)) hits.push(`${code}（实为${why}）`)
      }
    }
    expect(
      hits,
      `${wp} scope 复活了旧错码：${hits.join(' / ')} —— ` +
        `这些码在 report_config 里指向别的科目，会让溯源面板给出错误的追溯路径`,
    ).toEqual([])
  })
})
