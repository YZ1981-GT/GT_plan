/**
 * G6 其他债权投资披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * 🔴 背景：旧 `G6TabDisclosureListed.vue` 是自造的 7 个虚构小节 + 137 行
 * `成本项目N`，接同步会污染附注。本组测试锁死重写后的 14 张表与
 * `note_template_listed.json §五、15` 逐字一致。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G6_DISCLOSURE_SHEET_NAME,
  G6_LISTED_STAGE_SUBTABLE,
  G6_LISTED_SUBTABLE,
  G6_NOTE_SECTION,
  G6_SOE_SUBTABLE,
  isG6DisclosureApplicable,
  resolveG6CurrentStandard,
} from '../g6NoteSectionMap'
import {
  buildG6ImportantRows,
  buildG6ListedColumns,
  buildG6ListedSubTableData,
  buildG6ListedSyncPayload,
  buildG6StageMoveRows,
  buildG6StageRows,
  buildG6WriteoffDetailRows,
  buildG6WriteoffRows,
  G6_INDIVIDUAL_LABEL,
  G6_PORTFOLIO_LABEL,
  G6_WHICH_LABEL,
} from '../g6DisclosureSyncPayload'
import {
  buildDefaultG6ListedState,
  G6_STAGE_MOVE_ROWS,
  G6_WRITEOFF_ROW_LABEL,
  recomputeBalanceRows,
  recomputeFairValueRows,
  recomputeImportantRows,
  recomputeProvisionRows,
  stageTransferImbalances,
  type G6ListedDisclosureState,
} from '../g6ListedDisclosureRows'

// ─────────────────────── 通用子表契约（5 条 Property） ───────────────────────

runDisclosureSubtableContract({
  cycle: 'G6',
  variants: [
    {
      variant: 'listed',
      section: G6_NOTE_SECTION.listed,
      subtables: {
        ...G6_LISTED_SUBTABLE,
        ...Object.fromEntries(G6_LISTED_STAGE_SUBTABLE.map((n, i) => [`stage${i + 1}`, n])),
      },
      columns: buildG6ListedColumns(buildDefaultG6ListedState().stageBlocks),
    },
  ],
})

// ─────────────────────── 章节 / sheet 名 ───────────────────────

describe('G6 章节映射与 sheet_name', () => {
  it('章节号取自 variant_matrix（qi_ta_zhai_quan_tou_zi）', () => {
    expect(G6_NOTE_SECTION.listed).toBe('五、15')
    expect(G6_NOTE_SECTION.soe).toBe('八、16')
  })

  it('sheet 名为源 xlsx 真实中文 tab 名，不是 wp_code 形态合成标识', () => {
    for (const name of Object.values(G6_DISCLOSURE_SHEET_NAME)) {
      expect(name).toMatch(/^附注披露信息/)
      expect(name).not.toMatch(/G6/)
      expect(name).not.toMatch(/note-(listed|soe)/)
    }
  })

  it('国企侧只 2 张表（减值准备在国企附注里是交叉引用、无表）', () => {
    expect(Object.keys(G6_SOE_SUBTABLE)).toHaveLength(2)
  })

  it('未声明适用准则时两个变体都放行', () => {
    expect(isG6DisclosureApplicable('listed', [])).toBe(true)
    expect(isG6DisclosureApplicable('soe', null)).toBe(true)
  })

  it('声明上市时国企变体被拦下，反之亦然', () => {
    expect(isG6DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isG6DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(isG6DisclosureApplicable('soe', ['soe_standalone'])).toBe(true)
    expect(isG6DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })

  it('合并口径映射到 *_consolidated', () => {
    expect(resolveG6CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveG6CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveG6CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })
})

// ─────────────────────── 阶段表末列口径 ───────────────────────

describe('G6 三阶段表列口径', () => {
  const cols = buildG6ListedColumns(buildDefaultG6ListedState().stageBlocks)

  it('只有「期末第一阶段」末列是「理由」，其余五张是「划分依据」', () => {
    const last = (name: string) => cols[name][cols[name].length - 1].label
    expect(last(G6_LISTED_STAGE_SUBTABLE[0])).toBe('理由')
    for (const name of G6_LISTED_STAGE_SUBTABLE.slice(1)) {
      expect(last(name)).toBe('划分依据')
    }
  })

  it('第一阶段用 12 个月 ECL 率，第二三阶段用整个存续期', () => {
    const rate = (name: string) => cols[name][2].label
    expect(rate(G6_LISTED_STAGE_SUBTABLE[0])).toContain('未来12个月')
    expect(rate(G6_LISTED_STAGE_SUBTABLE[1])).toContain('整个存续期')
    expect(rate(G6_LISTED_STAGE_SUBTABLE[3])).toContain('未来12个月')
    expect(rate(G6_LISTED_STAGE_SUBTABLE[5])).toContain('整个存续期')
  })

  it('两级表头只有 3 张表（期末重要 / 续表 / 阶段迁移），其余显式 flat', () => {
    const grouped = Object.entries(cols)
      .filter(([, defs]) => defs.some((c) => c.group))
      .map(([name]) => name)
      .sort()
    expect(grouped).toEqual(
      [
        G6_LISTED_SUBTABLE.importantEnd,
        G6_LISTED_SUBTABLE.importantPrior,
        G6_LISTED_SUBTABLE.stageMove,
      ].sort(),
    )
  })
})

// ─────────────────────── 载荷构建器 ───────────────────────

/** 造一份有数的状态：主表 2 行明细 + 一年内到期扣减；（1）（2）表各 1 行 */
function seededState(): G6ListedDisclosureState {
  const s = buildDefaultG6ListedState()
  const detail = s.balanceRows.filter((r) => r.kind === 'data')
  detail[0].label = 'AA 企业债'
  detail[0].endBalance = 1000
  detail[0].priorBalance = 900
  detail[1].label = 'BB 金融债'
  detail[1].endBalance = 500
  detail[1].priorBalance = 400
  const ded = s.balanceRows.find((r) => r.kind === 'deduction')!
  ded.endBalance = 300
  ded.priorBalance = 200
  s.balanceRows = recomputeBalanceRows(s.balanceRows)

  const fv = s.fairValueRows.filter((r) => r.kind === 'data')
  fv[0].label = 'AA 企业债'
  fv[0].openingFv = 900
  fv[0].accruedInterest = 60
  fv[0].fvChangeCurrent = 40
  fv[0].cost = 880
  fv[0].fvChangeCumulative = 120
  fv[0].ociImpairment = 30
  s.fairValueRows = recomputeFairValueRows(s.fairValueRows)

  const prov = s.provisionRows.filter((r) => r.kind === 'data' && !r.fixed)
  prov[0].label = 'AA 企业债'
  prov[0].opening = 20
  prov[0].increase = 15
  prov[0].decrease = 5
  s.provisionRows = recomputeProvisionRows(s.provisionRows)

  const imp = s.importantEndRows.filter((r) => r.kind === 'data')
  imp[0].label = 'AA 企业债'
  imp[0].faceValue = 1000
  imp[0].couponRate = '3.50%'
  imp[0].effectiveRate = '3.62%'
  imp[0].maturityDate = '2027-06-30'
  imp[0].overduePrincipal = 0
  s.importantEndRows = recomputeImportantRows(s.importantEndRows)

  const block = s.stageBlocks[0]
  block.individual.details[0].name = 'AA 企业债'
  block.individual.details[0].bookBalance = 1000
  block.individual.details[0].impairment = 30
  block.individual.details[0].reason = '发行人评级下调'
  block.portfolio.details[0].name = '低风险组合'
  block.portfolio.details[0].bookBalance = 500
  block.portfolio.details[0].impairment = 5

  s.stageMoveRows = s.stageMoveRows.map((r) =>
    r.rowKey === 'closing' ? { ...r, stage1: 20, stage2: 10, stage3: 5 } : r,
  )
  s.writeoffRows[0] = {
    ...s.writeoffRows[0],
    label: 'CC 城投债',
    nature: '企业债',
    amount: 80,
    reason: '发行人破产清算',
    procedure: '经董事会决议批准',
    relatedParty: false,
  }
  return s
}

describe('G6 上市载荷装配', () => {
  const data = buildG6ListedSubTableData(seededState())

  it('推送 14 张表，键与模板表名逐字一致', () => {
    const expected = [
      ...Object.values(G6_LISTED_SUBTABLE),
      ...G6_LISTED_STAGE_SUBTABLE,
    ]
    expect(expected).toHaveLength(14)
    for (const name of expected) {
      expect(Array.isArray(data[name])).toBe(true)
    }
  })

  it('主表小计 / 合计行带 is_total（源模板写作「小 计」「合 计」，先去空白再判型）', () => {
    const rows = data[G6_LISTED_SUBTABLE.balance] as Record<string, unknown>[]
    const sub = rows.find((r) => String(r.label).replace(/\s+/g, '') === '小计')!
    const total = rows.find((r) => String(r.label).replace(/\s+/g, '') === '合计')!
    expect(sub.row_type).toBe('subtotal')
    expect(sub.is_total).toBe(true)
    expect(sub.end_balance).toBe(1500)
    expect(total.row_type).toBe('total')
    // 合计 = 小计 − 减：一年内到期
    expect(total.end_balance).toBe(1200)
    expect(total.prior_balance).toBe(1100)
  })

  it('（1）表期末公允价值 D = A + B + C，合计行按列求和', () => {
    const rows = data[G6_LISTED_SUBTABLE.fairValue] as Record<string, unknown>[]
    const detail = rows.find((r) => r.label === 'AA 企业债')!
    expect(detail.closing_fv).toBe(1000)
    const total = rows.find((r) => String(r.label).replace(/\s+/g, '') === '合计')!
    expect(total.closing_fv).toBe(1000)
    expect(total.oci_impairment).toBe(30)
  })

  it('（2）表期末余额 = 期初 + 增加 − 减少', () => {
    const rows = data[G6_LISTED_SUBTABLE.provision] as Record<string, unknown>[]
    expect(rows.find((r) => r.label === 'AA 企业债')!.closing).toBe(30)
    expect(rows.find((r) => String(r.label).replace(/\s+/g, '') === '合计')!.closing).toBe(30)
  })

  it('重要投资表合计行的利率 / 到期日写 null（源模板列示为「--」，不加总）', () => {
    const rows = buildG6ImportantRows(seededState().importantEndRows, 'end')
    const total = rows.find((r) => String(r.label).replace(/\s+/g, '') === '合计')!
    expect(total.end_face_value).toBe(1000)
    expect(total.end_coupon_rate).toBeNull()
    expect(total.end_effective_rate).toBeNull()
    expect(total.end_maturity_date).toBeNull()
  })

  it('续表列键带 prior_ 前缀，与期末表不撞键', () => {
    const prior = buildG6ImportantRows(seededState().importantPriorRows, 'prior')
    expect(Object.keys(prior[0])).toContain('prior_face_value')
    expect(Object.keys(prior[0])).not.toContain('end_face_value')
  })
})

describe('G6 三阶段行序与「其中：」结构行', () => {
  const rows = buildG6StageRows(seededState().stageBlocks[0])

  it('行序 = 按单项 → 其中： → 明细 → 按组合 → 其中： → 明细 → 合计', () => {
    expect(rows.map((r) => r.label)).toEqual([
      G6_INDIVIDUAL_LABEL,
      G6_WHICH_LABEL,
      'AA 企业债',
      G6_PORTFOLIO_LABEL,
      G6_WHICH_LABEL,
      '低风险组合',
      '合计',
    ])
  })

  it('「其中：」结构行列键齐备但值为 null（不破坏 columns 键集）', () => {
    const which = rows[1]
    expect(Object.keys(which).sort()).toEqual(
      ['gross', 'label', 'loss_rate', 'net', 'provision', 'reason', 'row_type'].sort(),
    )
    expect(which.gross).toBeNull()
    expect(which.provision).toBeNull()
  })

  it('父行汇总明细、损失率按 减值准备/账面余额 计算，账面价值取差额', () => {
    expect(rows[0].gross).toBe(1000)
    expect(rows[0].provision).toBe(30)
    expect(rows[0].loss_rate).toBe(3)
    expect(rows[0].net).toBe(970)
  })

  it('合计行 = 单项 + 组合，并带 is_total', () => {
    const total = rows[rows.length - 1]
    expect(total.gross).toBe(1500)
    expect(total.provision).toBe(35)
    expect(total.is_total).toBe(true)
    expect(total.row_type).toBe('total')
  })

  it('分母为 0 时损失率写 null，不写 0（避免「0% 损失率」误读）', () => {
    const empty = buildG6StageRows(buildDefaultG6ListedState().stageBlocks[1])
    expect(empty[0].loss_rate).toBeNull()
  })

  it('🔴 空白骨架明细行不推（否则附注多出一行全零、名字也叫「其中：」的幽灵行）', () => {
    // 浏览器实测中招：结构行 whichRow + 默认名为「其中：」的空明细行并存
    const rows = buildG6StageRows(buildDefaultG6ListedState().stageBlocks[0])
    expect(rows.map((r) => r.label)).toEqual([
      G6_INDIVIDUAL_LABEL,
      G6_WHICH_LABEL,
      G6_PORTFOLIO_LABEL,
      G6_WHICH_LABEL,
      '合计',
    ])
    // 唯一的两行「其中：」都是结构行（列值为 null），不是数据行
    for (const r of rows.filter((x) => x.label === G6_WHICH_LABEL)) {
      expect(r.gross).toBeNull()
      expect(r.provision).toBeNull()
    }
  })

  it('明细行只要有名字或有金额就推（不误杀真实明细）', () => {
    const byAmount = buildDefaultG6ListedState()
    byAmount.stageBlocks[0].individual.details[0].impairment = 12
    const rows = buildG6StageRows(byAmount.stageBlocks[0])
    // 单项父行 + 其中： + 1 条明细 + 组合父行 + 其中： + 合计 = 6 行
    expect(rows).toHaveLength(6)
    expect(rows[2]).toMatchObject({ label: '', provision: 12, row_type: 'data' })

    const byName = buildDefaultG6ListedState()
    byName.stageBlocks[0].portfolio.details[0].name = '低风险组合'
    const rows2 = buildG6StageRows(byName.stageBlocks[0])
    expect(rows2.map((r) => r.label)).toContain('低风险组合')
  })
})

describe('G6 阶段迁移表（5）', () => {
  it('12 行固定行序取自源模板 R152~R163', () => {
    const rows = buildG6StageMoveRows(seededState().stageMoveRows)
    expect(rows).toHaveLength(12)
    expect(rows.map((r) => r.row_key)).toEqual(G6_STAGE_MOVE_ROWS.map((r) => r.rowKey))
  })

  it('合计列 = 三阶段之和；期末余额行带 is_total', () => {
    const rows = buildG6StageMoveRows(seededState().stageMoveRows)
    const closing = rows.find((r) => r.row_key === 'closing')!
    expect(closing.total).toBe(35)
    expect(closing.is_total).toBe(true)
  })

  it('阶段间转移行三阶段代数和应为 0，不平时被 stageTransferImbalances 揪出', () => {
    const base = buildDefaultG6ListedState().stageMoveRows
    expect(stageTransferImbalances(base)).toEqual([])
    const bad = base.map((r) =>
      r.rowKey === 'to_stage2' ? { ...r, stage1: -100, stage2: 90, stage3: 0 } : r,
    )
    expect(stageTransferImbalances(bad)).toEqual(['to_stage2'])
    const good = base.map((r) =>
      r.rowKey === 'to_stage2' ? { ...r, stage1: -100, stage2: 100, stage3: 0 } : r,
    )
    expect(stageTransferImbalances(good)).toEqual([])
  })
})

describe('G6 核销（6）', () => {
  it('手工填的核销总额优先，未填时回退明细之和', () => {
    const s = seededState()
    expect(buildG6WriteoffRows(s.writeoffRows, 0)[0].writeoff_amount).toBe(80)
    expect(buildG6WriteoffRows(s.writeoffRows, 120)[0].writeoff_amount).toBe(120)
    expect(buildG6WriteoffRows(s.writeoffRows, 0)[0].label).toBe(G6_WRITEOFF_ROW_LABEL)
  })

  it('明细表过滤空行并追加合计行，关联交易列输出中文是/否', () => {
    const rows = buildG6WriteoffDetailRows(seededState().writeoffRows)
    expect(rows).toHaveLength(2)
    expect(rows[0].related_party).toBe('否')
    expect(rows[1].row_type).toBe('total')
    expect(rows[1].amount).toBe(80)
  })
})

describe('G6 同步载荷', () => {
  it('sheet_name / section_id / current_standard 齐备', () => {
    const p = buildG6ListedSyncPayload('wp-1', ['listed_standalone'], seededState())!
    expect(p.sheet_name).toBe(G6_DISCLOSURE_SHEET_NAME.listed)
    expect(p.section_id).toBe(G6_NOTE_SECTION.listed)
    expect(p.current_standard).toBe('listed_standalone')
    expect(Object.keys(p.columns)).toHaveLength(14)
  })

  it('缺 wpId 或变体不适用时返回 null（宁缺勿造）', () => {
    expect(buildG6ListedSyncPayload('', [], seededState())).toBeNull()
    expect(buildG6ListedSyncPayload('wp-1', ['soe_standalone'], seededState())).toBeNull()
  })

  it('三段说明文本走 _note_texts，空文本不推', () => {
    const s = seededState()
    expect((buildG6ListedSubTableData(s) as any)._note_texts).toBeUndefined()
    s.fvNote = '合计与 G6-3 期末审定数勾稽'
    s.judgementBasisNote = '逾期 30 天以上视为信用风险显著增加'
    const texts = (buildG6ListedSubTableData(s) as any)._note_texts as Array<Record<string, string>>
    expect(texts.map((t) => t.section)).toEqual([
      'listed-fair-value-note',
      'listed-judgement-basis',
    ])
  })
})
