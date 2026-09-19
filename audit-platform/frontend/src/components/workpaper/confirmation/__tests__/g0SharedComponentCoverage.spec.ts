/**
 * g0SharedComponentCoverage.spec.ts — G0 无需共享组件分叉的守卫
 *
 * spec: g0-confirmation-source-alignment，Task 21
 * Property 25（G0-3 跟函 / F0-8 舞弊 与 D0 逐字相同 → 共享组件无需 G0 分叉）
 * Property 26（回函可靠性 14 列已被 `ReliabilityRow` 覆盖，逐列给出映射）
 *
 * ─── 为什么要有这份守卫 ──────────────────────────────────────────────────────
 * G0 的 `跟函函证过程控制G0-3` 与 `函证程序舞弊风险评价表F0-8` 正文与 D0 对应 sheet
 * **逐行相同**（后端 `test_g0_source_template_facts.py` 已 openpyxl 直读证明）。
 * 故这两块**不应**新增 G0 专属分叉 —— 本守卫把「无需分叉」变成可验证事实，防后来的会话
 * 因为「G0 没有 isG0 分支」误判成缺口而又抄一份（memory 已记「品种矩阵三份是有意范式，
 * 但跟函/舞弊不是」）。
 *
 * Property 26 同理：G0-7 的 14 个叶子列已全部落在共享 `ReliabilityRow` 上，逐列登记映射
 * 使「已覆盖」可复核；缺列即红。
 *
 * 本文件**不连库、不读 xlsx** —— 源模板事实经后端事实守卫的常量交叉取得。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { scenariosFor } from '../followup/memoTemplates'
import { PRESET_FRAUD_ITEMS } from '../fraudRisk/fraudRiskPresets'
import type { ReliabilityRow } from '../reliability/reliabilityTypes'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
const SENTINELS = [
  join('backend', 'tests', 'test_g0_source_template_facts.py'),
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const BACKEND_FACTS = readFileSync(
  join(REPO_ROOT, 'backend', 'tests', 'test_g0_source_template_facts.py'),
  'utf-8',
)
const CONFIRMATION_DIR = join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
  'confirmation',
)

function readConfirmation(rel: string): string {
  const p = join(CONFIRMATION_DIR, rel)
  if (!existsSync(p)) throw new Error(`共享组件文件不存在：${rel}`)
  return readFileSync(p, 'utf-8')
}

/** 去注释（块 + 行 + HTML）—— 被验证文件的注释里写着 'G0' 字样，不剥必假红 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

// ════════════════════════════════════════════════════════════════════════════
describe('Property 25 — 跟函备忘录与舞弊 19 条无需 G0 分叉', () => {
  it('后端已证明 G0-3 / F0-8 与 D0 对应 sheet 逐行相同（源侧前提）', () => {
    // 这两条断言在后端事实守卫里；此处交叉引用，源模板一旦分叉后端先红
    expect(BACKEND_FACTS).toContain('跟函函证过程控制G0-3')
    expect(BACKEND_FACTS).toContain('函证程序舞弊风险评价表F0-8')
    expect(BACKEND_FACTS).toMatch(/identical_to_d0/)
  })

  it('scenariosFor("G0") 返回通用场景集，与 D0/F0/H0/K0/L0 逐字节相同', () => {
    const g0 = scenariosFor('G0')
    expect(g0).toEqual(['immediate', 'later_follow', 'later_received', 'third_party_callback'])
    for (const cycle of ['D0', 'F0', 'H0', 'K0', 'L0'] as const) {
      expect(scenariosFor(cycle)).toEqual(g0)
    }
    // 只有 E0 是银行专属（唯一合法分叉）
    expect(scenariosFor('E0')).not.toEqual(g0)
  })

  it('memoTemplates 源码不含 G0 专属分支（防又抄一份）', () => {
    const src = stripComments(readConfirmation(join('followup', 'memoTemplates.ts')))
    expect(src).not.toMatch(/'G0'|"G0"/)
    // 反向自检：E0 分支确实存在 → 证明上面这条不是因为正则失效而空过
    expect(src).toMatch(/'E0'|"E0"/)
  })

  it('PRESET_FRAUD_ITEMS 是跨枢纽共用的 19 条，无 G0 分支', () => {
    expect(PRESET_FRAUD_ITEMS).toHaveLength(19)
    const src = stripComments(readConfirmation(join('fraudRisk', 'fraudRiskPresets.ts')))
    expect(src).not.toMatch(/'G0'|"G0"/)
    // 亦不得出现按枢纽切换的痕迹
    expect(src).not.toMatch(/\bcycle\b/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 26 — 回函可靠性 14 列已被 ReliabilityRow 覆盖', () => {
  /**
   * 源 `邮件传真回函可靠性验证G0-7` 的 14 个叶子列 → `ReliabilityRow` 字段映射。
   *
   * 🔴 列名取自后端 `RELIABILITY_LEAF_COLUMNS`（openpyxl 直读），本表只做「列 → 字段」
   *    的归属声明；缺列或字段不存在于类型上都会红。
   */
  const COLUMN_TO_FIELD: readonly { col: string; label: string; field: keyof ReliabilityRow }[] = [
    { col: 'A', label: '序号', field: 'seq' },
    { col: 'B', label: '函证索引号', field: 'confirm_index' },
    { col: 'C', label: '被询证单位名称', field: 'entity_name' },
    { col: 'D', label: '回函方式', field: 'reply_method' },
    { col: 'E', label: '是否由审计项目组直接接收', field: 'direct_received' },
    { col: 'F', label: '是否寄回原件', field: 'original_returned' },
    { col: 'G', label: '被函证者身份确认（注1）', field: 'identity_verified' },
    { col: 'H', label: '发函及回函传真信息及验证', field: 'fax_info_verify' },
    { col: 'I', label: '发函邮箱', field: 'send_email' },
    { col: 'J', label: '回函邮箱', field: 'reply_email' },
    { col: 'K', label: '邮箱可靠性验证（注2）', field: 'email_verified' },
    { col: 'L', label: '是否致电被函证者确认', field: 'phone_called' },
    { col: 'M', label: '对函证信息可靠性的考虑（注3）', field: 'reliability_consideration' },
    { col: 'N', label: '回函可靠性结论', field: 'conclusion_status' },
  ]

  /** 从后端事实守卫里抽 14 列真源（不读 xlsx） */
  function backendReliabilityColumns(): { col: string; label: string }[] {
    const m = BACKEND_FACTS.match(
      /RELIABILITY_LEAF_COLUMNS:\s*tuple\[tuple\[str,\s*str\],\s*\.\.\.\]\s*=\s*\(([\s\S]*?)\n\)/,
    )
    if (!m) throw new Error('未能在后端事实守卫里定位 RELIABILITY_LEAF_COLUMNS（正则失效）')
    const out: { col: string; label: string }[] = []
    for (const mm of m[1].matchAll(/\("([A-Z]+)",\s*"([^"]+)"\)/g)) {
      out.push({ col: mm[1], label: mm[2] })
    }
    return out
  }

  it('源侧 14 列抽取成功且数量为 14（抽取非空自检）', () => {
    const cols = backendReliabilityColumns()
    expect(cols.length).toBeGreaterThan(0)
    expect(cols).toHaveLength(14)
  })

  it('映射表与源 14 列逐列（列字母 + 标签）一一对应，双侧无剩余', () => {
    const cols = backendReliabilityColumns()
    expect(COLUMN_TO_FIELD.map((x) => [x.col, x.label])).toEqual(cols.map((c) => [c.col, c.label]))
  })

  it('每列映射的字段都真实存在于 ReliabilityRow 上（缺列即红）', () => {
    // 用一个显式对象承载全部映射字段：字段名写错 / 类型上不存在 → TS 编译期即红，
    // 运行期再断言键集完整（双保险）。
    const probe: Required<Pick<ReliabilityRow, (typeof COLUMN_TO_FIELD)[number]['field']>> = {
      seq: 1,
      confirm_index: 'G0-7-001',
      entity_name: '某被投资单位',
      reply_method: '电子邮件',
      direct_received: '是',
      original_returned: '否',
      identity_verified: '是',
      fax_info_verify: '传真号与公开信息一致',
      send_email: 'audit@firm.test',
      reply_email: 'cfo@investee.test',
      email_verified: '是',
      phone_called: '是',
      reliability_consideration: '结合工商公开信息核对',
      conclusion_status: '可靠',
    }
    for (const { field } of COLUMN_TO_FIELD) {
      expect(Object.prototype.hasOwnProperty.call(probe, field), `字段 ${field} 未覆盖`).toBe(true)
      expect(probe[field], `字段 ${field} 探针值为空`).toBeDefined()
    }
    expect(Object.keys(probe)).toHaveLength(14)
  })

  it('G0-7 的分组标题与 14 列同属一表（不需要 G0 专属组件）', () => {
    expect(BACKEND_FACTS).toContain('RELIABILITY_GROUP_G5')
    expect(BACKEND_FACTS).toContain('期末未收回原件函证可靠性验证')
    // 平台侧共享类型未按枢纽分叉
    const src = stripComments(readConfirmation(join('reliability', 'reliabilityTypes.ts')))
    expect(src).not.toMatch(/'G0'|"G0"/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('反向自检（防断言空转）', () => {
  it('stripComments 剥掉注释里的 G0 字样但保留代码字面', () => {
    const fixture = [
      "// G0 专属分支的说明注释",
      "/* 这里提到 'G0' 但只是注释 */",
      "<!-- 'G0' 在模板注释里 -->",
      "const cycles = ['E0']",
    ].join('\n')
    const out = stripComments(fixture)
    expect(out).not.toContain('G0')
    expect(out).toContain("['E0']")
    // 不得把 URL 的 `//` 当行注释
    expect(stripComments('const u = "https://x.test/g0"')).toContain('https://x.test/g0')
  })

  it('后端事实守卫确实被读到（非空 + 含锚点）', () => {
    expect(BACKEND_FACTS.length).toBeGreaterThan(1000)
    expect(BACKEND_FACTS).toContain('RELIABILITY_LEAF_COLUMNS')
  })
})
