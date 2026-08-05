/**
 * g0ColumnSpec.spec.ts — G0-1 列集与源模板 28 列的一一映射守卫
 *
 * spec: g0-confirmation-source-alignment，Task 12（Property 2 / 3）
 *
 * 源侧事实由后端 `backend/tests/test_g0_source_template_facts.py::TestSummaryUpperZone`
 * 以 openpyxl 直读固化；前端侧以 `CONFIRMATION_SOURCE_COLUMN_LABELS.G0`（28 条，
 * 与 openpyxl 读值逐字一致）作比对基准 —— 两侧独立录入同一份源模板，互为交叉验证。
 *
 * 🔴 平台 29 列 vs 源模板 28 列的**唯一**差额是 `confirmation_method`
 *    （准则 1312 的积极式/消极式，源模板无此列；源模板的「函证方式」是**渠道**，
 *     由 variant 列 `send_channel` 承载）。除此之外必须一一对应。
 */
import { describe, expect, it } from 'vitest'
import {
  BASE_CONFIRMATION_COLUMNS,
  CYCLE_COLUMN_LABEL_OVERRIDES,
  CYCLE_EXCLUDED_COLUMNS,
  CYCLE_VARIANT_COLUMNS,
  resolveConfirmationColumns,
  type ConfirmCycle,
} from '../../confirmation/confirmationColumnSpec'
import { CONFIRMATION_SOURCE_COLUMN_LABELS } from '../../confirmation/confirmationColumnSourceManifest'

/** 源模板 G0-1 无此三列（联系人/联系电话在 G0-2 的 F/G 列；源模板无币种列） */
const G0_EXCLUDED = ['contact_person', 'contact_phone', 'currency'] as const

/**
 * 平台列 label 与源模板 label 的**已登记差异**（每条须有理由）。
 * key = 平台 label，value = { source, reason }
 */
const LABEL_DELTAS: Record<string, { source: string; reason: string }> = {
  '是否收到回函': {
    source: '是否收到回函（√）',
    reason: '源模板用勾号标记，而 G0-1!L8:L17 的数据有效性实测为 `是,否` → 平台按 DV 取值不带勾号',
  },
  '是否采取替代程序': {
    source: '是否采取替代程序（√）',
    reason: '同上，G0-1!X8:X17 的 DV 实测为 `是,否`',
  },
  '差异调节表索引': {
    source: '调节索引（G0-3）',
    reason:
      '源字面含 tab 名索引号笔误（底稿目录裁决为 G0-4）→ 该列 label 的处置归 Task 10/11（裁决门 B），' +
      '此处保持 BASE label 不先落，避免把笔误当正解固化',
  },
}

/** 平台有而源模板无的列（准则概念，非源列） */
const PLATFORM_ONLY_LABELS = ['函证类型（积极式/消极式）'] as const

describe('Property 2: G0-1 列集与源模板 28 列一一映射', () => {
  const cols = resolveConfirmationColumns('G0')
  const labels = cols.map((c) => c.label)
  const keys = cols.map((c) => c.key)
  const sourceLabels = CONFIRMATION_SOURCE_COLUMN_LABELS.G0

  it('源模板基准恰 28 列且无重复', () => {
    expect(sourceLabels).toHaveLength(28)
    expect(new Set(sourceLabels).size).toBe(28)
  })

  it('平台列数 = 28 源列 + 1 平台专属列', () => {
    expect(cols).toHaveLength(sourceLabels.length + PLATFORM_ONLY_LABELS.length)
  })

  it('平台列 key 无重复', () => {
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('归一后平台 label 集合 == 源模板 label 集合（双向无剩余）', () => {
    const normalized = labels
      .filter((l) => !PLATFORM_ONLY_LABELS.includes(l as (typeof PLATFORM_ONLY_LABELS)[number]))
      .map((l) => LABEL_DELTAS[l]?.source ?? l)

    expect([...normalized].sort()).toEqual([...sourceLabels].sort())
  })

  it('每条 label 差异都已登记理由（≥20 字，防空话）', () => {
    for (const [platformLabel, delta] of Object.entries(LABEL_DELTAS)) {
      expect(labels, `已登记差异 ${platformLabel} 未出现在平台列集中（登记已过期）`).toContain(platformLabel)
      expect(sourceLabels, `${platformLabel} 的源侧对应 ${delta.source} 不在源基准内`).toContain(delta.source)
      expect(delta.reason.length, `${platformLabel} 的理由过短`).toBeGreaterThanOrEqual(20)
    }
  })

  it('平台专属列确实不在源模板内（否则应改为 override 而非专属）', () => {
    for (const l of PLATFORM_ONLY_LABELS) {
      expect(sourceLabels).not.toContain(l)
      expect(labels).toContain(l)
    }
  })
})

describe('Property 2: G0 列集组成', () => {
  it('三个空列噪声已剔除', () => {
    const keys = resolveConfirmationColumns('G0').map((c) => c.key)
    for (const k of G0_EXCLUDED) expect(keys, `${k} 应被剔除`).not.toContain(k)
    expect(CYCLE_EXCLUDED_COLUMNS.G0).toEqual([...G0_EXCLUDED])
  })

  it('AB 列审计结论已补齐，且复用 row_conclusion 字段 + row_summary 段', () => {
    const col = resolveConfirmationColumns('G0').find((c) => c.key === 'row_conclusion')
    expect(col, 'G0 缺 AB 列「审计结论」').toBeDefined()
    expect(col!.label).toBe('审计结论')
    expect(col!.group).toBe('row_summary')
    expect(col!.source).toContain('G0-1')
  })

  it('源模板「函证方式」由 send_channel 承载（渠道），confirmation_method 显式区分', () => {
    const cols = resolveConfirmationColumns('G0')
    const channel = cols.find((c) => c.key === 'send_channel')
    const method = cols.find((c) => c.key === 'confirmation_method')
    expect(channel, 'G0 缺渠道列').toBeDefined()
    expect(channel!.label).toBe('函证方式')
    expect(method!.label).toBe('函证类型（积极式/消极式）')
    // 两列不得同名，否则界面出现两个「函证方式」
    expect(channel!.label).not.toBe(method!.label)
  })

  it('G0 未启用其它枢纽的专属列（无跨枢纽噪声）', () => {
    const keys = resolveConfirmationColumns('G0').map((c) => c.key)
    for (const k of ['term_book', 'term_reply', 'term_match', 'term_note', 'send_memo', 'account_no', 'amount_orig', 'fx_rate']) {
      expect(keys, `G0 不该有 ${k}`).not.toContain(k)
    }
  })

  it('variant 声明与解析结果一致', () => {
    expect(CYCLE_VARIANT_COLUMNS.G0).toEqual(['send_channel', 'g0_row_conclusion'])
  })
})

describe('Property 3: 标签覆盖不污染 BASE，其余循环零回归', () => {
  it('BASE 常量本体未被 mutate（G0 用词未泄漏到 BASE）', () => {
    const baseByKey = new Map(BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c.label]))
    // 抽三条 G0 有覆盖的列，断言 BASE 仍是原用词
    expect(baseByKey.get('account_type')).toBe('科目')
    expect(baseByKey.get('amount')).toBe('函证金额')
    expect(baseByKey.get('is_replied')).toBe('是否已回函')
  })

  it('D0/F0/K0/L0 不受 G0 覆盖影响（未声明覆盖的循环仍取 BASE 用词）', () => {
    for (const cycle of ['D0', 'F0', 'K0', 'L0'] as ConfirmCycle[]) {
      expect(CYCLE_COLUMN_LABEL_OVERRIDES[cycle]).toBeUndefined()
      const byKey = new Map(resolveConfirmationColumns(cycle).map((c) => [c.key, c.label]))
      expect(byKey.get('account_type')).toBe('科目')
      expect(byKey.get('amount')).toBe('函证金额')
    }
  })

  it('覆盖表只含 G0 / H0 两个 key', () => {
    expect(Object.keys(CYCLE_COLUMN_LABEL_OVERRIDES).sort()).toEqual(['G0', 'H0'])
  })

  it('G0 与 H0 的覆盖各自独立（同 key 可不同用词，互不影响）', () => {
    const g0 = new Map(resolveConfirmationColumns('G0').map((c) => [c.key, c.label]))
    const h0 = new Map(resolveConfirmationColumns('H0').map((c) => [c.key, c.label]))
    // amount：G0「账面期末余额」/ H0「金额或合同条款」—— 源模板用词不同不强行统一
    expect(g0.get('amount')).toBe('账面期末余额')
    expect(h0.get('amount')).toBe('金额或合同条款')
    // reply_from_addr：G0「回函地址」/ H0 保持 BASE「回函发出地址」
    expect(g0.get('reply_from_addr')).toBe('回函地址')
    expect(h0.get('reply_from_addr')).toBe('回函发出地址')
  })
})

describe('反向自检', () => {
  it('归一表若为空则一一映射断言必失败（证明归一确有必要）', () => {
    const labels = resolveConfirmationColumns('G0')
      .map((c) => c.label)
      .filter((l) => !PLATFORM_ONLY_LABELS.includes(l as (typeof PLATFORM_ONLY_LABELS)[number]))
    // 不做 LABEL_DELTAS 归一 → 与源基准必不相等
    expect([...labels].sort()).not.toEqual([...CONFIRMATION_SOURCE_COLUMN_LABELS.G0].sort())
  })

  it('若不剔除三列则列数必超（证明剔除确有必要）', () => {
    const withoutExclusion = BASE_CONFIRMATION_COLUMNS.length + CYCLE_VARIANT_COLUMNS.G0.length
    expect(withoutExclusion).toBeGreaterThan(resolveConfirmationColumns('G0').length)
  })

  it('源基准非空且含 G0 特征用词（防 manifest 被清空导致断言空转）', () => {
    expect(CONFIRMATION_SOURCE_COLUMN_LABELS.G0).toContain('账面期末余额')
    expect(CONFIRMATION_SOURCE_COLUMN_LABELS.G0).toContain('调节索引（G0-3）')
  })
})
