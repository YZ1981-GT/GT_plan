/**
 * confirmationRiskPush.spec.ts — 函证两条风险推送通道守卫
 *
 * spec: f0-confirmation-linkage-and-structural-enhancement / Wave 8（Task 32~35）
 * Property 4（舞弊推送完整性）+ Property 8（A13 契约反验）+ Property 9（接线防孤儿）
 *
 * 🔴 本文件的核心价值 —— 上一版 `f0FraudRiskPush.ts` 是**零消费方 + 零测试**的孤儿模块，
 * 且两个载荷的契约都对不上平台真实通道（发明的事件名 / `source_wp_code` 键名不被 bridge 识别）。
 * 因此这里必须做三件单纯的单元测试做不到的事：
 *   1. 用**真实**的 `normalizeMisstatementPushPayload` 消费本模块的载荷（契约反验）
 *   2. 断言 `source` 落在 `GtB50RiskAssessment.SOURCE_OPTIONS` 白名单内（否则溯源被静默改写）
 *   3. 源码级断言两个宿主真的 import + emit 了（防再次退化成孤儿）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  B50_SOURCE_CONFIRMATION,
  buildB50RiskFactorPayload,
  buildDiffMisstatementPayload,
  buildMisstatementDescription,
  hasPresentFraudIndicators,
  isFraudIndicatorPresent,
  pickMisstatementAmount,
} from '../composables/confirmationRiskPush'
import { normalizeMisstatementPushPayload } from '@/composables/useA13MisstatementBridge'
import type { FraudRiskRow } from '../fraudRisk/fraudRiskTypes'
import type { DiffReconcileRow } from '../diffReconcile/diffReconcileTypes'

// ─── 源码读取（REPO_ROOT 走哨兵文件向上查找，禁写死回退级数） ─────────────────

const __dirname_ = dirname(fileURLToPath(import.meta.url))

/**
 * 🔴 memory 铁律：守卫的 REPO_ROOT 一律用**具体哨兵文件**向上查找。
 * 写死 `resolve(__dirname, '../../../../../../..')` 曾让整个 spec 文件 ENOENT
 * （表现为「文件级失败」而非断言失败，极易被当噪声跳过）。
 */
function findRepoRoot(start: string): string {
  let cur = start
  for (let i = 0; i < 12; i += 1) {
    if (
      existsSync(resolve(cur, '.gitattributes')) &&
      existsSync(resolve(cur, 'audit-platform/frontend/package.json'))
    ) {
      return cur
    }
    const parent = dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error(`未能从 ${start} 向上定位仓库根（哨兵 .gitattributes + frontend/package.json）`)
}

const REPO_ROOT = findRepoRoot(__dirname_)

function readSource(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
}

/** 去注释（防守卫自身/被查文件的说明文字被数成真实代码） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const WP = 'audit-platform/frontend/src/components/workpaper'
const B50_VUE = `${WP}/GtB50RiskAssessment.vue`
const FRAUD_HOST = `${WP}/confirmation/fraudRisk/GtConfirmationFraudRisk.vue`
const FRAUD_SUMMARY = `${WP}/confirmation/fraudRisk/FraudRiskSummary.vue`
const DIFF_HOST = `${WP}/confirmation/diffReconcile/GtConfirmationDiffReconcile.vue`
const DIFF_MASTER = `${WP}/confirmation/diffReconcile/DiffReconcileMaster.vue`
const PUSH_TS = `${WP}/confirmation/composables/confirmationRiskPush.ts`

// ─── Fixtures ────────────────────────────────────────────────────────────────

function fraudRow(over: Partial<FraudRiskRow> = {}): FraudRiskRow {
  return {
    _row_id: 'r1',
    seq: 1,
    description: '管理层不允许寄发询证函；',
    is_exist: '否',
    _preset: true,
    ...over,
  }
}

function diffRow(over: Partial<DiffReconcileRow> = {}): DiffReconcileRow {
  return {
    _row_id: 'd1',
    seq: 1,
    confirm_index: 'F0-001',
    entity_name: '某供应商有限公司',
    subject: '应付账款',
    sent_amount: 100000,
    reply_amount: 88000,
    difference: 12000,
    diff_type: 'unrecorded',
    diff_note: '货已收未记账',
    ...over,
  }
}

// ─── Property 4: 舞弊推送完整性 ──────────────────────────────────────────────

describe('Property 4: B50 载荷只含「是否存在=是」的迹象', () => {
  it('三态判定：只有「是」算存在', () => {
    expect(isFraudIndicatorPresent({ is_exist: '是' })).toBe(true)
    for (const v of ['否', 'NA', '待核实', '', undefined] as any[]) {
      expect(isFraudIndicatorPresent({ is_exist: v })).toBe(false)
    }
  })

  it('「否」/「NA」/「待核实」的行不进载荷', () => {
    const rows = [
      fraudRow({ seq: 1, is_exist: '是', description: 'A' }),
      fraudRow({ seq: 2, is_exist: '否', description: 'B' }),
      fraudRow({ seq: 3, is_exist: 'NA', description: 'C' }),
      fraudRow({ seq: 4, is_exist: '待核实', description: 'D' }),
    ]
    const { factors } = buildB50RiskFactorPayload(rows, 'F0-8')
    expect(factors).toHaveLength(1)
    expect(factors[0]).toContain('A')
    for (const excluded of ['：B', '：C', '：D']) {
      expect(factors.join('|')).not.toContain(excluded)
    }
  })

  it('描述为空的行跳过（B50 侧按文本去重，空文本会污染）', () => {
    const rows = [
      fraudRow({ is_exist: '是', description: '   ' }),
      fraudRow({ is_exist: '是', description: '真实迹象' }),
    ]
    expect(buildB50RiskFactorPayload(rows, 'F0-8').factors).toHaveLength(1)
  })

  it('文案含描述 + 应对措施 + 来源索引 + 来自底稿（对齐 B19-1 范式）', () => {
    const rows = [
      fraudRow({
        is_exist: '是',
        description: '从私人电子信箱发送的回函',
        countermeasure: '追加致电确认并取得原件',
        source_ref: 'F0-7',
      }),
    ]
    const [text] = buildB50RiskFactorPayload(rows, 'F0-8').factors
    expect(text).toBe(
      '函证舞弊风险迹象：从私人电子信箱发送的回函（应对措施：追加致电确认并取得原件）（来源：F0-7）（来自 F0-8）',
    )
  })

  it('应对措施/来源为空时不产生空括号', () => {
    const [text] = buildB50RiskFactorPayload(
      [fraudRow({ is_exist: '是', description: 'X' })],
      'L0-7',
    ).factors
    expect(text).toBe('函证舞弊风险迹象：X（来自 L0-7）')
    expect(text).not.toContain('（应对措施：）')
    expect(text).not.toContain('（来源：）')
  })

  it('七枢纽共享：wpCode 决定文案尾部标注，不写死 F0-8', () => {
    for (const code of ['D0-8', 'E0-8', 'F0-8', 'G0-8', 'H0-7', 'K0-8', 'L0-7']) {
      const [text] = buildB50RiskFactorPayload(
        [fraudRow({ is_exist: '是', description: 'X' })],
        code,
      ).factors
      expect(text).toContain(`（来自 ${code}）`)
    }
  })

  it('hasPresentFraudIndicators 与载荷非空一致（推送按钮 disabled 判据同源）', () => {
    const none = [fraudRow({ is_exist: '否' })]
    const some = [fraudRow({ is_exist: '是', description: 'X' })]
    const blank = [fraudRow({ is_exist: '是', description: '' })]
    expect(hasPresentFraudIndicators(none)).toBe(false)
    expect(hasPresentFraudIndicators(some)).toBe(true)
    expect(hasPresentFraudIndicators(blank)).toBe(false)
    expect(buildB50RiskFactorPayload(blank, 'F0-8').factors).toHaveLength(0)
  })

  it('空入参不抛异常', () => {
    expect(buildB50RiskFactorPayload([], 'F0-8').factors).toEqual([])
    expect(buildB50RiskFactorPayload(undefined as any, 'F0-8').factors).toEqual([])
  })
})

// ─── Property 8: B50 source 白名单交叉锁死 ───────────────────────────────────

describe('Property 8: source 必须在 B50 的 SOURCE_OPTIONS 白名单内', () => {
  const b50 = readSource(B50_VUE)

  it('反向自检：读到 B50 源码且含 SOURCE_OPTIONS 与静默改写逻辑', () => {
    expect(b50.length).toBeGreaterThan(1000)
    expect(b50).toContain('SOURCE_OPTIONS')
    // 正是这行把不在白名单的 source 改写成 b2_predecessor（本 Property 存在的理由）
    expect(stripComments(b50)).toMatch(/SOURCE_OPTIONS\.some\(\(o\)\s*=>\s*o\.value\s*===\s*rawSource\)/)
  })

  it(`SOURCE_OPTIONS 已登记 '${B50_SOURCE_CONFIRMATION}'`, () => {
    const block = stripComments(b50).match(/const SOURCE_OPTIONS = \[([\s\S]*?)\] as const/)
    expect(block, '未能定位 SOURCE_OPTIONS 声明').toBeTruthy()
    const values = [...block![1].matchAll(/value:\s*'([^']+)'/g)].map((m) => m[1])
    expect(values.length).toBeGreaterThan(5)
    expect(values).toContain(B50_SOURCE_CONFIRMATION)
  })

  it('载荷 source 恒等于该常量（不随 wpCode 变化，否则会落白名单外被改写）', () => {
    for (const code of ['D0-8', 'H0-7', 'K0-8']) {
      expect(buildB50RiskFactorPayload([], code).source).toBe(B50_SOURCE_CONFIRMATION)
    }
  })
})

// ─── Property 8b: A13 契约反验（用真实 normalizer 消费本模块载荷） ───────────

describe('Property 8b: A13 载荷经真实 normalizeMisstatementPushPayload 后字段正确落位', () => {
  it('wpCode / amount / accountName / description 全部落位', () => {
    const payload = buildDiffMisstatementPayload([diffRow()], 'F0-4')
    const drafts = normalizeMisstatementPushPayload(payload)
    expect(drafts).toHaveLength(1)
    const d = drafts[0]
    expect(d.wpCode).toBe('F0-4')
    expect(d.amount).toBe(12000)
    expect(d.accountName).toBe('应付账款')
    expect(d.description).toContain('某供应商有限公司')
    expect(d.description).toContain('未达账项')
    expect(d.description).toContain('（索引:F0-001）')
    expect(d.indexRef).toBe('F0-001')
  })

  it('accountCode 一律为 null（函证字典只给中文名，无科目码 → 宁缺勿造）', () => {
    const drafts = normalizeMisstatementPushPayload(
      buildDiffMisstatementPayload([diffRow()], 'F0-4'),
    )
    expect(drafts[0].accountCode).toBeNull()
  })

  it('🔴 反向自检：旧契约（source_wp_code + account_type 扁平单行）经同一 normalizer 会丢 wpCode', () => {
    // 这正是旧 `f0FraudRiskPush.buildDiffMisstatementPayload` 的形态。
    // 若本断言变绿失效（即旧形态也能带出 wpCode），说明 bridge 改了读取键，
    // 上面那条「wpCode 落位」的断言就失去判别力，需重新审视。
    const legacyShaped = {
      source_wp_code: 'F0',
      account_type: '应付账款',
      amount: 12000,
      reason: '未达账项',
      description: '函证差异：某供应商',
      misstatement_type: 'factual',
    }
    const drafts = normalizeMisstatementPushPayload(legacyShaped)
    expect(drafts).toHaveLength(1)
    expect(drafts[0].wpCode).toBe('') // ← 溯源丢失
    expect(drafts[0].accountName).toBeNull()
  })

  it('多行批量：逐行独立成 draft', () => {
    const rows = [
      diffRow({ _row_id: 'a', confirm_index: 'F0-001', difference: 100 }),
      diffRow({ _row_id: 'b', confirm_index: 'F0-002', difference: -250.555 }),
    ]
    const drafts = normalizeMisstatementPushPayload(buildDiffMisstatementPayload(rows, 'K0-4'))
    expect(drafts.map((d) => d.amount)).toEqual([100, 250.56])
    expect(drafts.every((d) => d.wpCode === 'K0-4')).toBe(true)
  })
})

// ─── Property 8c: 错报金额口径 ───────────────────────────────────────────────

describe('Property 8c: 错报金额取绝对值 + 两位精度 + 非法值剔除', () => {
  it('负差异取绝对值（bridge 对 amount<=0 直接丢弃；且源模板方向本身不一致）', () => {
    expect(pickMisstatementAmount({ difference: -12000 })).toBe(12000)
    expect(pickMisstatementAmount({ difference: 12000 })).toBe(12000)
  })

  it('两位精度（避免浮点漂移）', () => {
    expect(pickMisstatementAmount({ difference: -0.005 })).toBe(0.01)
    expect(pickMisstatementAmount({ difference: 1.23456 })).toBe(1.23)
  })

  it('NaN / Infinity / null / 0 → 0，且不进载荷', () => {
    for (const v of [NaN, Infinity, -Infinity, null, undefined, 0, '' as any]) {
      expect(pickMisstatementAmount({ difference: v as any })).toBe(0)
    }
    const rows = [diffRow({ difference: 0 }), diffRow({ difference: NaN as any })]
    expect(buildDiffMisstatementPayload(rows, 'F0-4').items).toHaveLength(0)
  })

  it('描述在缺字段时仍可读（不产出空括号 / 不写 undefined）', () => {
    const text = buildMisstatementDescription({ difference: 1 } as DiffReconcileRow)
    expect(text).toBe('函证差异：未填被询证单位，差异原因待查明')
    expect(text).not.toContain('undefined')
  })

  it('差异类型未登记时原样透出（allow-create 自定义值不被吞）', () => {
    const text = buildMisstatementDescription(
      diffRow({ diff_type: '自定义原因', diff_note: '' }),
    )
    expect(text).toContain('自定义原因')
  })
})

// ─── Property 9: 接线断言（防再次退化成零消费方孤儿模块） ────────────────────

describe('Property 9: 两条通道必须真的接线（源码级）', () => {
  const fraudHost = stripComments(readSource(FRAUD_HOST))
  const fraudSummary = stripComments(readSource(FRAUD_SUMMARY))
  const diffHost = stripComments(readSource(DIFF_HOST))
  const diffMaster = stripComments(readSource(DIFF_MASTER))

  it('反向自检：四份源码都读到了（防路径写错导致全部断言空转）', () => {
    for (const [name, src] of Object.entries({ fraudHost, fraudSummary, diffHost, diffMaster })) {
      expect(src.length, name).toBeGreaterThan(1000)
    }
  })

  it('F0-8 宿主 import 载荷构建函数并 emit b50:push-risk-factor', () => {
    expect(fraudHost).toContain('confirmationRiskPush')
    expect(fraudHost).toContain('buildB50RiskFactorPayload')
    expect(fraudHost).toMatch(/eventBus\.emit\(\s*'b50:push-risk-factor'/)
  })

  it('F0-8 汇总区有推送按钮且按 exist_count 禁用（不是永远可点的死按钮）', () => {
    expect(fraudSummary).toContain("'push-b50'")
    expect(fraudSummary).toMatch(/existCount/)
    expect(fraudSummary).toMatch(/:disabled="readonly \|\| existCount === 0"/)
  })

  it('推送成功后回填 b50_ref（Requirement 4.5，源模板 F0-8!H26 就写着 B50）', () => {
    expect(fraudHost).toMatch(/b50_ref\s*=\s*'B50'/)
  })

  it('X0-4 宿主 import 载荷构建函数并 emit a13:push-misstatement', () => {
    expect(diffHost).toContain('confirmationRiskPush')
    expect(diffHost).toContain('buildDiffMisstatementPayload')
    expect(diffHost).toMatch(/eventBus\.emit\('a13:push-misstatement'/)
  })

  it('X0-4 明细表同时提供单行推送与批量推送，且都携带行 ID', () => {
    expect(diffMaster).toContain("'push-a13'")
    expect(diffMaster).toMatch(/\$emit\('push-a13',\s*\[row\._row_id\]\)/)
    expect(diffMaster).toMatch(/\$emit\('push-a13',\s*\[\.\.\.overMaterialityRowIds\]\)/)
  })

  it('批量推送按超重要性行数禁用（无阈值时回落单行按钮，不是静默什么都不做）', () => {
    expect(diffMaster).toMatch(/overMaterialityRowIds\.length === 0/)
    expect(diffMaster).toContain('batchPushHint')
  })
})

// ─── Property 9b: 发明的事件名不得复活 ──────────────────────────────────────

describe('Property 9b: 不得使用零消费方的发明事件名', () => {
  it('confirmationRiskPush.ts 不再声明 event_type 字段', () => {
    const src = stripComments(readSource(PUSH_TS))
    expect(src).not.toContain('event_type')
  })

  it('全模块与两个宿主都不得出现 fraud-risk:push-to-b50（全库零消费方）', () => {
    for (const rel of [PUSH_TS, FRAUD_HOST, FRAUD_SUMMARY]) {
      expect(stripComments(readSource(rel)), rel).not.toContain('fraud-risk:push-to-b50')
    }
  })

  it('旧模块 f0FraudRiskPush.ts 已删（不得复活）', () => {
    expect(
      existsSync(resolve(REPO_ROOT, `${WP}/confirmation/composables/f0FraudRiskPush.ts`)),
    ).toBe(false)
  })

  it('自造的差异原因枚举 F0_DIFF_REASONS 已删（与后端字典 confirmation_diff_type 双真源）', () => {
    expect(stripComments(readSource(PUSH_TS))).not.toContain('F0_DIFF_REASONS')
    expect(stripComments(readSource(DIFF_HOST))).not.toContain('F0_DIFF_REASONS')
  })
})
