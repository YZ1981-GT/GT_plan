/**
 * 抽凭科目码来源守卫 —— spec `voucher-sampling-account-scope-and-attach-closure` 阶段 1。
 *
 * 🔴 缺陷背景（2026-09-28 实证）
 *
 * 抽凭引擎的科目关联是在**查询阶段**完成的：宿主传 `account-code` → `config.accountCodes`
 * → `POST /voucher-extract` 的 `filters.account_codes` → 后端按科目查 `tb_ledger`。
 * 机制本身正确，但**前提是宿主传对了科目码**。现算 70 处静态字面量挂载点中 25 处与
 * 科目真源不一致，且双向都有错：
 *
 *   · 组件错：K5 `2701`（实为长期应付款，L5 循环的科目）/ G1 `1501`（持有至到期，G4）
 *             / I2 `1717`（真实库无此码）/ I6 `6602`（管理费用，K9）
 *   · `wp_account_mapping.json` 错：K10 `6301` / K12 `6001` / H5 `1606`
 *   · 真源判「宁缺勿造」：I5 / K4 的 FALLBACK 为空串
 *
 * 该缺陷长期存活的原因是两个已完成 spec 之间的缝隙：
 *   `semantic-account-resolver-full-rollout`(31/31) 主题就是「消除科目硬编码」但只管
 *   后端 render 策略（`抽凭`/`account-code`/`AccountScope` 关键词命中全为 0）；
 *   `voucher-sampling-hardening`(40/40) 管引擎本身但不管它拿到的科目码对不对。
 *
 * 本守卫的判据是**来源形态**（是否字面量），不是**取值对不对** —— 值偶然正确
 * （K10/K12/H5）也必须接真源，否则会再次漂移。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const WP_ROOT = path.resolve(__dirname, '..')
const COMPOSABLES = path.join(WP_ROOT, 'composables')

// ─── 剔注释 ──────────────────────────────────────────────────────────────────

/**
 * 剔除注释后的源码。
 *
 * 🔴 必须剔：说明「为什么不能用 2701」的注释里就含被禁字面量与 `account-code="2701"`
 * 这种原状引用。不剔会把已修好的文件判成违规 —— 本轮 K5 守卫首版即因此误报 3 个文件。
 */
export function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
    .replace(/([^:])\/\/[^\n'"`]*$/gm, '$1')
}

// ─── 扫描 ────────────────────────────────────────────────────────────────────

function collectVue(dir: string): string[] {
  const out: string[] = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...collectVue(p))
    else if (e.name.endsWith('.vue')) out.push(p)
  }
  return out
}

interface Host {
  file: string
  full: string
  raw: string
  src: string
}

const HOSTS: Host[] = collectVue(WP_ROOT)
  .map((f) => ({
    file: path.relative(WP_ROOT, f).replace(/\\/g, '/'),
    full: f,
    raw: fs.readFileSync(f, 'utf-8'),
    src: stripComments(fs.readFileSync(f, 'utf-8')),
  }))
  .filter((h) => h.src.includes('GtVoucherSamplingEngine'))

/** 静态字面量：account-code="1234"（非 : 绑定、值以数字开头） */
const RE_STATIC = /(?<!:)account-code\s*=\s*"(\d[^"]*)"/g
/** 动态绑定：:account-code="标识符或表达式" */
const RE_BIND = /:account-code\s*=\s*"([^"]+)"/g

function staticCodes(src: string): string[] {
  return [...src.matchAll(RE_STATIC)].map((m) => m[1].trim())
}
function boundExprs(src: string): string[] {
  return [...src.matchAll(RE_BIND)].map((m) => m[1].trim())
}

/** 循环前缀（从文件名首段推断，如 I2TabCutoffForward.vue → I2） */
function cycleOf(file: string): string {
  const base = path.basename(file)
  const m = base.match(/^([A-Za-z]\d+)/)
  return m ? m[1].toUpperCase() : ''
}

/** 循环 → 应使用的真源导出名（现算自 composables/*AccountScope.ts，2026-09-28） */
const SCOPE_HINT: Record<string, string> = {
  D4: 'd4AccountScope: d4RevenueQueryCodes / d4CostQueryCodes',
  F3: 'f3AccountScope: F3_GROSS_FALLBACK_STANDARD / f3GrossQueryCodes',
  F4: 'f4AccountScope: F4_GROSS_FALLBACK_STANDARD / f4GrossQueryCodes',
  F5: 'f5AccountScope: F5_GROSS_FALLBACK_STANDARD / f5GrossQueryCodes',
  G1: 'g1AccountScope: G1_GROSS_FALLBACK_STANDARD(1101) / G1_DERIVATIVE_FALLBACK_STANDARD(1102)',
  G7: 'g7AccountScope: G7_GROSS_FALLBACK_STANDARD / g7GrossQueryCodes',
  I1: 'i1AccountScope: I1_GROSS_FALLBACK_STANDARD / i1GrossQueryCodes',
  I2: 'i2AccountScope: I2_GROSS_FALLBACK_STANDARD(1704) / i2GrossQueryCodes',
  I3: 'i3AccountScope: I3_GROSS_FALLBACK_STANDARD / i3GrossQueryCodes',
  I4: 'i4AccountScope: I4_GROSS_FALLBACK_STANDARD / i4GrossQueryCodes',
  I5: "i5AccountScope: I5_GROSS_FALLBACK_STANDARD('' 宁缺勿造→须降级禁用)",
  I6: 'i6AccountScope: I6_GROSS_FALLBACK_STANDARD(6604 研发费用) / i6GrossQueryCodes',
  J1: 'jAccountScope: J1_GROSS_FALLBACK / j1GrossQueryCodes',
  K1: 'k1AccountScope: K1_GROSS_FALLBACK_STANDARD / k1GrossQueryCodes',
  K3: 'k3AccountScope: K3_FALLBACK_STANDARD / k3QueryCodes',
  K4: "k4AccountScope: K4_FALLBACK_STANDARD('' 宁缺勿造→须降级禁用)",
  K5: 'k5AccountScope: K5_FALLBACK_STANDARD(2801) / k5QueryCodes',
  K7: 'k7AccountScope: K7_FALLBACK_STANDARD / k7QueryCodes',
  K8: 'k8AccountScope: K8_FALLBACK_STANDARD / k8QueryCodes',
  K9: 'k9AccountScope: K9_FALLBACK_STANDARD / k9QueryCodes',
  K10: 'k10AccountScope: K10_FALLBACK_STANDARD(6117) / k10QueryCodes',
  K12: 'k12AccountScope: K12_FALLBACK_STANDARD(6301) / k12QueryCodes',
  K13: 'k13AccountScope: K13_FALLBACK_STANDARD / k13QueryCodes',
  H1: 'hCycleAccountScope: H1_ACCOUNT_DEF / h1Scope',
  H2: 'hCycleAccountScope: H2_ACCOUNT_DEF / h2Scope',
  H4: 'hCycleAccountScope: H4_ACCOUNT_DEF / h4Scope',
  H5: 'hCycleAccountScope: H5_ACCOUNT_DEF / h5Scope（油气资产 1631）',
  H6: 'hCycleAccountScope: H6_ACCOUNT_DEF / h6Scope',
  H10: 'hCycleAccountScope: H10_ACCOUNT_DEF / h10Scope',
  D1: 'dCycleAccountScope: dSlotQueryCodes',
  D2: 'dCycleAccountScope: dSlotQueryCodes',
  D3: 'dCycleAccountScope: dSlotQueryCodes',
  D5: 'dCycleAccountScope: dSlotQueryCodes',
  D6: 'dCycleAccountScope: dSlotQueryCodes',
  D7: 'dCycleAccountScope: dSlotQueryCodes',
  F1: 'f3/f4/f5AccountScope 同族（F1 见 dCycleAccountScope）',
  F2: 'f2NoteSectionMap: F2_INVENTORY_ACCOUNT_CODES（注意真实库无合同履约成本科目，见 spec R2）',
  G2: 'gCycleAccountScope',
  G3: 'gCycleAccountScope',
  G4: 'gCycleAccountScope',
  G6: 'g6AccountScope: g6GrossQueryCodes',
  M1: 'kCycle/mCycle 真源（见 composables 下对应 AccountScope）',
  M2: 'kCycle/mCycle 真源（见 composables 下对应 AccountScope）',
  N2: 'nCycle 真源（见 composables 下对应 AccountScope）',
  E1: '需新建 e1AccountScope（现算不存在，见 spec R1.3 / 任务 2.3）',
}

// ─── 1.1 静态字面量禁令 ──────────────────────────────────────────────────────

describe('抽凭挂载点：account-code 不得为内联数字字面量（spec R6.1）', () => {
  it('扫描面非空（否则全部断言空转）', () => {
    expect(HOSTS.length, '扫不到任何 GtVoucherSamplingEngine 宿主').toBeGreaterThan(20)
  })

  it('🔴 静态数字字面量一律违规（值正确也不例外，R1.5）', () => {
    const offenders: string[] = []
    for (const h of HOSTS) {
      const codes = staticCodes(h.src)
      if (codes.length === 0) continue
      const cyc = cycleOf(h.file)
      offenders.push(
        `${h.file}  传=${codes.join('|')}  应改用 → ${SCOPE_HINT[cyc] ?? `（${cyc} 循环真源待确认）`}`,
      )
    }
    expect(
      offenders,
      `以下抽凭挂载点把科目码写成内联字面量（共 ${offenders.length} 处）。\n` +
        '判据是**来源形态**不是取值：值偶然正确也必须接真源，否则会再次漂移。\n' +
        '范式：const code = computed(() => (props.tbSourceCodes ? xQueryCodes(props.tbSourceCodes) : [X_FALLBACK]).filter(Boolean).join(\',\'))\n\n  ' +
        offenders.join('\n  '),
    ).toEqual([])
  })

  it('🔴 反向自检：判据能抓到字面量（否则上一条是假绿）', () => {
    const bad = stripComments('<GtVoucherSamplingEngine account-code="1717" phase="final" />')
    expect(staticCodes(bad)).toEqual(['1717'])
  })

  it('🔴 反向自检：动态绑定不得被误判为静态', () => {
    const good = stripComments('<GtVoucherSamplingEngine :account-code="samplingCode" />')
    expect(staticCodes(good)).toEqual([])
    expect(boundExprs(good)).toEqual(['samplingCode'])
  })

  it('🔴 剔注释器自检：注释里的字面量被剔、代码保留', () => {
    const sample = [
      '// 原写 account-code="2701" —— 2701 是长期应付款',
      '<!-- 抽凭引擎（科目 2701 预计负债） -->',
      'const samplingAccountCode = K5_FALLBACK_STANDARD',
    ].join('\n')
    const out = stripComments(sample)
    expect(out).not.toContain('2701')
    expect(out, '剔过度会把代码吃掉 ⇒ 主断言变空转').toContain('K5_FALLBACK_STANDARD')
  })
})

// ─── 1.2 动态挂载点的标识符溯源（防「换地方硬编码」）────────────────────────

describe('抽凭挂载点：动态绑定的标识符必须溯源到真源（spec R6.6）', () => {
  it('🔴 绑定的标识符不得指向数字字面量常量', () => {
    const offenders: string[] = []
    for (const h of HOSTS) {
      for (const expr of boundExprs(h.src)) {
        // 只查裸标识符（含 .join()/.value 等后缀的表达式取其首段）
        const ident = expr.match(/^([A-Za-z_$][\w$]*)/)?.[1]
        if (!ident) continue
        // ① 来自 *AccountScope import ⇒ 合规
        const importedFromScope = new RegExp(
          `import\\s*\\{[^}]*\\b${ident}\\b[^}]*\\}\\s*from\\s*['"][^'"]*AccountScope['"]`,
        ).test(h.src)
        if (importedFromScope) continue
        // ② 本文件内赋值右侧是数字字面量 ⇒ 违规（换地方硬编码）
        const assignLiteral = new RegExp(
          `(?:const|let|var)\\s+${ident}\\s*(?::[^=]+)?=\\s*['"]\\d`,
        ).test(h.src)
        if (assignLiteral) {
          offenders.push(`${h.file}  :account-code="${expr}"  而 ${ident} = 数字字面量`)
        }
      }
    }
    expect(
      offenders,
      '以下挂载点把硬编码搬到了常量里（形态合规但来源仍是字面量）：\n  ' + offenders.join('\n  '),
    ).toEqual([])
  })

  it('🔴 反向自检：能抓到「换地方硬编码」', () => {
    const bad = stripComments(
      ['const X_ACCOUNT_CODE = \'1717\'', '<GtVoucherSamplingEngine :account-code="X_ACCOUNT_CODE" />'].join('\n'),
    )
    const ident = boundExprs(bad)[0].match(/^([A-Za-z_$][\w$]*)/)![1]
    expect(new RegExp(`(?:const|let|var)\\s+${ident}\\s*(?::[^=]+)?=\\s*['"]\\d`).test(bad)).toBe(true)
  })

  it('🔴 反向自检：来自真源 import 的标识符不算违规', () => {
    const good = stripComments(
      [
        "import { K5_FALLBACK_STANDARD } from '../../composables/k5AccountScope'",
        'const code = K5_FALLBACK_STANDARD',
        '<GtVoucherSamplingEngine :account-code="K5_FALLBACK_STANDARD" />',
      ].join('\n'),
    )
    const ident = boundExprs(good)[0].match(/^([A-Za-z_$][\w$]*)/)![1]
    expect(
      new RegExp(`import\\s*\\{[^}]*\\b${ident}\\b[^}]*\\}\\s*from\\s*['"][^'"]*AccountScope['"]`).test(good),
    ).toBe(true)
  })
})

// ─── 1.5 真源值断言（防有人改回错码）────────────────────────────────────────

describe('科目真源的取值必须正确（spec R1.4 / R2.3）', () => {
  /** 现算自真实库 tb_balance（6~10 个项目一致）+ report_config 公式 */
  const EXPECT: Array<[string, string, string, string]> = [
    // [真源文件, 导出名, 期望值, 该码的真实科目名 / 为何不是别的]
    ['k5AccountScope', 'K5_FALLBACK_STANDARD', '2801', '预计负债；2701 是长期应付款(L5)'],
    ['g1AccountScope', 'G1_GROSS_FALLBACK_STANDARD', '1101', '交易性金融资产；1501 是持有至到期投资(G4)'],
    ['i2AccountScope', 'I2_GROSS_FALLBACK_STANDARD', '1704', '开发支出；1717 真实库无此码'],
    // 🔴 6604 在 account_chart 里 7 条中 6 条为「研发费用」（与 wp_index 的 I6 底稿名一致）；
    //    只有 1 个项目把它用作「勘探费用」。科目定义权威源是 account_chart，
    //    不是某项目账套 tb_balance 的 MIN(account_name)（按后者取样会误判为勘探费用）。
    ['i6AccountScope', 'I6_GROSS_FALLBACK_STANDARD', '6604', '研发费用；6602 是管理费用(K9)'],
    ['k10AccountScope', 'K10_FALLBACK_STANDARD', '6117', '其他收益；wp_account_mapping.json 的 6301 是营业外收入(错)'],
    ['k12AccountScope', 'K12_FALLBACK_STANDARD', '6301', '营业外收入；wp_account_mapping.json 的 6001 是主营业务收入(错)'],
    ['l5AccountScope', 'L5_GROSS_FALLBACK_STANDARD', '2701', '长期应付款 —— 正是 K5 曾误用的那个码，保留此断言以固定归属'],
  ]

  for (const [file, name, want, why] of EXPECT) {
    it(`${file}.${name} === '${want}'（${why}）`, () => {
      const src = fs.readFileSync(path.join(COMPOSABLES, `${file}.ts`), 'utf-8')
      const m = src.match(new RegExp(`export const ${name}\\s*(?::[^=]+)?=\\s*'([^']*)'`))
      expect(m, `${file} 未导出 ${name}（真源改名会使宿主静默退回硬编码）`).toBeTruthy()
      expect(m![1]).toBe(want)
    })
  }

  const EMPTY: Array<[string, string, string]> = [
    ['i5AccountScope', 'I5_GROSS_FALLBACK_STANDARD', '其他非流动资产无标准独立码；1911/1901 均非'],
    ['k4AccountScope', 'K4_FALLBACK_STANDARD', '其他流动负债无标准独立码；2245 是持有待售负债'],
  ]

  for (const [file, name, why] of EMPTY) {
    it(`${file}.${name} 必须保持空串（宁缺勿造，${why}）`, () => {
      const src = fs.readFileSync(path.join(COMPOSABLES, `${file}.ts`), 'utf-8')
      const m = src.match(new RegExp(`export const ${name}\\s*(?::[^=]+)?=\\s*'([^']*)'`))
      expect(m, `${file} 未导出 ${name}`).toBeTruthy()
      expect(
        m![1],
        '空串表达「本循环无标准独立科目码」；被填上任何值即为臆造兜底，' +
          '会让抽凭以错科目查库。正确做法是降级禁用（spec R2）。',
      ).toBe('')
    })
  }
})

// ─── 1.6 契约存在性（防真源改名致静默降级）──────────────────────────────────

describe('科目真源导出契约（spec R1.1 / R1.2）', () => {
  const REQUIRED: Array<[string, string[]]> = [
    ['k5AccountScope', ['K5_FALLBACK_STANDARD', 'k5QueryCodes', 'K5_ACCOUNT_NAME']],
    ['g1AccountScope', ['G1_GROSS_FALLBACK_STANDARD', 'g1GrossQueryCodes']],
    ['i2AccountScope', ['I2_GROSS_FALLBACK_STANDARD', 'i2GrossQueryCodes']],
    ['i5AccountScope', ['I5_GROSS_FALLBACK_STANDARD', 'i5GrossQueryCodes']],
    ['i6AccountScope', ['I6_GROSS_FALLBACK_STANDARD', 'i6GrossQueryCodes']],
    ['k4AccountScope', ['K4_FALLBACK_STANDARD', 'k4QueryCodes', 'K4_ACCOUNT_NAME']],
    ['k10AccountScope', ['K10_FALLBACK_STANDARD', 'k10QueryCodes', 'K10_ACCOUNT_NAME']],
    ['k12AccountScope', ['K12_FALLBACK_STANDARD', 'k12QueryCodes', 'K12_ACCOUNT_NAME']],
    ['hCycleAccountScope', ['H5_ACCOUNT_DEF', 'h5Scope']],
  ]

  for (const [file, names] of REQUIRED) {
    it(`${file} 导出 ${names.join(' / ')}`, () => {
      const src = fs.readFileSync(path.join(COMPOSABLES, `${file}.ts`), 'utf-8')
      for (const n of names) {
        expect(
          new RegExp(`export\\s+(?:const|function)\\s+${n}\\b`).test(src),
          `${file} 缺导出 ${n}`,
        ).toBe(true)
      }
    })
  }
})
