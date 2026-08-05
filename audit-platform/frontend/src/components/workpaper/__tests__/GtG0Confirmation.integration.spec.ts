/**
 * G0 投资循环函证 — 集成测试
 *
 * 验证各模块间的组合正确性（非 Vue 组件挂载）：
 * 1. wp_code_overrides 映射正确性（10 条 G0 → 对应 componentType）
 * 2. G0-3(证券) 差异三维公式（数量差异/公允价值差异/市值差异）+ Master-Detail CRUD
 * 3. G0-6 处置损益公式（成交-成本-手续费）+ 股利差异
 * 4. G0-6 四区块独立增删行 + 各区块合计
 * 5. G0-1 → G0-6 反向联动（未回函项目带入映射）
 * 6. 导入导出 round-trip（G0-3S 单 sheet / G0-6 四区块分 sheet 列定义一致性）
 * 7. 版本快照 autoSnapshot 触发（debounce）
 *
 * **Validates: Requirements 全部**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  calcQuantityDiff,
  calcFairValueDiff,
  calcMarketValueDiff,
  calcDisposalGain,
  calcDividendDiff,
  hasDifference,
} from '../g0-confirmation/composables/useG0FormulaEngine'
import { useDiffSecuritiesData } from '../g0-confirmation/diffSecurities/composables/useDiffSecuritiesData'
import { useAlternativeG06Data } from '../g0-confirmation/alternativeG06/composables/useAlternativeG06Data'
import {
  getSumFieldsG06,
  BLOCK_COLUMN_CONFIGS_G06,
  G06_SOURCE_EXTRA,
} from '../g0-confirmation/alternativeG06/blockColumnConfigsG06'
import type { BlockType } from '../confirmation/alternativeD05/alternativeD05Types'

// ---------------------------------------------------------------------------
// 1. wp_code_overrides 映射正确性（10 条 G0 映射）
// ---------------------------------------------------------------------------
describe('G0 集成: wp_code_overrides 10 条映射', () => {
  const overridesPath = path.resolve(
    __dirname,
    '../../../../../../backend/app/data/wp_code_overrides.json',
  )
  const overrides: Record<string, string> = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))

  const expected: [string, string][] = [
    ['G0', 'confirmation-hub'],
    ['G0A', 'a-program-console'],
    ['G0-1', 'confirmation-summary'],
    ['G0-2', 'confirmation-entity-verify'],
    ['G0-3', 'confirmation-followup'],
    ['G0-3S', 'confirmation-diff-securities'],
    // 🔴 G0-4（非证券投资差异）已由归档 spec `g0-investment-diff-model` 从 D0 通用
    //    `confirmation-diff-reconcile` 改为 G0 专属 `confirmation-diff-nonsecurities`
    //    （三维差异：持股比例 / 投资金额 / 投资条款）。本断言长期停留在旧值 = 陈旧镜像。
    ['G0-4', 'confirmation-diff-nonsecurities'],
    ['G0-6', 'confirmation-alternative-g06'],
    ['G0-7', 'confirmation-reliability'],
    ['G0-8', 'confirmation-fraud-risk'],
  ]

  it.each(expected)('wp_code "%s" → componentType "%s"', (code, ct) => {
    expect(overrides[code]).toBe(ct)
  })

  it('共有 10 条 G0 精确映射（G0/G0A/G0-数字/G0-3S）', () => {
    const g0Keys = Object.keys(overrides).filter((k) => /^G0(A|-[\dS]+)?$/.test(k))
    expect(g0Keys.sort()).toEqual(expected.map(([c]) => c).sort())
  })

  it('两张差异表各走 G0 专属 componentType，且与 D0 通用类型区分明确', () => {
    // 证券投资差异 / 非证券投资差异 各有专属组件（列集不同构：17 列 vs 15 列）
    expect(overrides['G0-3S']).toBe('confirmation-diff-securities')
    expect(overrides['G0-4']).toBe('confirmation-diff-nonsecurities')
    expect(overrides['G0-3S']).not.toBe(overrides['G0-4'])
    // 二者都不再退回 D0 通用差异调节组件
    expect(overrides['G0-3S']).not.toBe('confirmation-diff-reconcile')
    expect(overrides['G0-4']).not.toBe('confirmation-diff-reconcile')
  })

  it('两条含索引号笔误的**全名键**存在（裁决门 B：定位用 tab 名）', () => {
    // 定位一律走源模板真实 tab 名；`wp_render_config` 的 skip/componentType 判定
    // 顺序不同，全名键是唯一可靠的定位入口（详见 g0SheetRegistry.ts 文件头）
    expect(overrides['函证差异核对表G0-3（证券投资）']).toBe('confirmation-diff-securities')
    expect(overrides['函证差异核对表G0-4(非证券投资)']).toBe('confirmation-diff-nonsecurities')
  })
})

// ---------------------------------------------------------------------------
// 2. G0-3(证券) 差异三维公式 + Master-Detail CRUD
// ---------------------------------------------------------------------------
// 🔴 差异方向 = **账面 − 回函**（源模板 `函证差异核对表G0-3（证券投资）!K5` 表头逐字
//    `差异③=①-②`，①账面②回函；同组 `K7=E7-H7`/`L7=F7-I7` 亦如此）。
//    原用例镜像的「回函 − 账面」照抄了源 `M7=J7-G7` 的缺陷方向，已随
//    spec g0-confirmation-source-alignment Task 20（R10.2 / Property 27）纠正。
//    形参顺序同步改为 `(booked, reply)`。
describe('G0 集成: G0-3(证券) 三维差异公式（账面 − 回函）', () => {
  it('数量差异 = 账面持仓 − 回函持仓', () => {
    expect(calcQuantityDiff(10000, 9800)).toBe(200)
    expect(calcQuantityDiff(5000, 5000)).toBe(0)
  })

  it('市价（单价）差异 = 账面单价 − 回函单价', () => {
    expect(calcFairValueDiff(12.5, 12.0)).toBeCloseTo(0.5, 6)
  })

  it('公允价值差异 = 账面余额 − 回函公允价值（源 M 列方向写反，按表头意图统一）', () => {
    expect(calcMarketValueDiff(125000, 117600)).toBeCloseTo(7400, 6)
  })

  it('三维差异完整链路（持仓×单价=市值）', () => {
    const bookedQty = 10000
    const replyQty = 9800
    const bookedFv = 12.5
    const replyFv = 12.0
    const bookedMv = bookedQty * bookedFv // 125000
    const replyMv = replyQty * replyFv // 117600

    expect(calcQuantityDiff(bookedQty, replyQty)).toBe(200)
    expect(calcFairValueDiff(bookedFv, replyFv)).toBeCloseTo(0.5, 6)
    expect(calcMarketValueDiff(bookedMv, replyMv)).toBeCloseTo(7400, 6)
    // 有数量差异 → hasDifference 为真
    expect(hasDifference(calcQuantityDiff(bookedQty, replyQty), calcFairValueDiff(bookedFv, replyFv))).toBe(true)
  })

  it('无差异证券 → hasDifference 为假', () => {
    expect(hasDifference(calcQuantityDiff(5000, 5000), calcFairValueDiff(10, 10))).toBe(false)
  })
})

describe('G0 集成: useDiffSecuritiesData CRUD + 差异自动计算 + 汇总', () => {
  function makeData() {
    let htmlData: any = { _format: 'diff-securities-v1', rows: [], conclusion: '', audit_note: '' }
    return useDiffSecuritiesData({ htmlData: () => htmlData, readonly: false })
  }

  it('新增行 → updateRow 后差异列自动重算', () => {
    const d = makeData()
    const row = d.addRow()
    d.updateRow(row._row_id!, 'confirmed_qty', 10000)
    d.updateRow(row._row_id!, 'booked_qty', 9800)
    d.updateRow(row._row_id!, 'confirmed_unit_fv', 12.5)
    d.updateRow(row._row_id!, 'booked_unit_fv', 12.0)
    d.updateRow(row._row_id!, 'confirmed_market_value', 125000)
    d.updateRow(row._row_id!, 'booked_market_value', 117600)

    const updated = d.rows.value[0]
    // 🔴 差异 = 账面 − 回函 → 本 fixture 账面(9800/12.0/117600) 低于回函(10000/12.5/125000)
    //    故三列为**负**。原期望的 +200/+0.5/+7400 是旧方向（回函 − 账面）的镜像值。
    expect(updated.qty_diff).toBe(-200)
    expect(updated.fv_diff).toBeCloseTo(-0.5, 6)
    expect(updated.market_value_diff).toBeCloseTo(-7400, 6)
    expect(d.rowHasDiff(updated)).toBe(true)
  })

  it('metrics 汇总：核对笔数/有差异/无差异/最大单笔差异', () => {
    const d = makeData()
    // 行1：有数量差异 200
    const r1 = d.addRow()
    d.updateRow(r1._row_id!, 'confirmed_qty', 10000)
    d.updateRow(r1._row_id!, 'booked_qty', 9800)
    // 行2：完全相符
    const r2 = d.addRow()
    d.updateRow(r2._row_id!, 'confirmed_qty', 5000)
    d.updateRow(r2._row_id!, 'booked_qty', 5000)

    expect(d.metrics.value.total_count).toBe(2)
    expect(d.metrics.value.diff_count).toBe(1)
    expect(d.metrics.value.no_diff_count).toBe(1)
    // 汇总取绝对值 → 方向翻转不影响（下游 hasDifference / metrics / 推送阈值全走 Math.abs）
    expect(d.metrics.value.max_abs_diff).toBe(200)
  })

  it('deleteRow 后行数减少，buildPayload 格式正确', () => {
    const d = makeData()
    const r1 = d.addRow()
    d.addRow()
    expect(d.rows.value).toHaveLength(2)
    d.deleteRow(r1._row_id!)
    expect(d.rows.value).toHaveLength(1)

    const payload = d.buildPayload()
    expect(payload._format).toBe('diff-securities-v1')
    expect(payload.rows).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// 3. G0-6 处置损益公式 + 股利差异
// ---------------------------------------------------------------------------
describe('G0 集成: G0-6 处置损益/股利差异公式', () => {
  it('处置损益 = 成交金额 - 原始成本 - 手续费', () => {
    // 成交 150000，成本 120000，手续费 300 → 损益 29700
    expect(calcDisposalGain(150000, 120000, 300)).toBeCloseTo(29700, 2)
  })

  it('亏损处置 → 负值损益', () => {
    expect(calcDisposalGain(80000, 120000, 200)).toBeCloseTo(-40200, 2)
  })

  it('手续费为负时钳制为 0（不放大收益）', () => {
    expect(calcDisposalGain(150000, 120000, -50)).toBeCloseTo(30000, 2)
  })

  it('股利差异 = 应收股利 - 实收金额 - 红利税', () => {
    // 应收 10000，实收 8000，红利税 2000 → 差异 0
    expect(calcDividendDiff(10000, 8000, 2000)).toBeCloseTo(0, 2)
    // 应收 10000，实收 7500，红利税 2000 → 差异 500
    expect(calcDividendDiff(10000, 7500, 2000)).toBeCloseTo(500, 2)
  })
})

// ---------------------------------------------------------------------------
// 4. G0-6 四区块独立增删行 + 各区块合计
// ---------------------------------------------------------------------------
describe('G0 集成: useAlternativeG06Data 四区块 CRUD + 合计', () => {
  function makeData() {
    let htmlData: any = { _format: 'alternative-g06-v1', companies: [] }
    return useAlternativeG06Data({ htmlData: () => htmlData, readonly: false })
  }

  const blocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']

  it('四区块各自独立增删行互不影响', () => {
    const d = makeData()
    const c = d.addCompany()
    for (const bt of blocks) {
      d.addBlockRow(c._company_id!, bt)
      d.addBlockRow(c._company_id!, bt)
    }
    const company = d.companies.value[0]
    expect(company.block1_rows).toHaveLength(2)
    expect(company.block2_rows).toHaveLength(2)
    expect(company.block3_rows).toHaveLength(2)
    expect(company.block4_rows).toHaveLength(2)

    // 删 block1 的一行，其他区块不受影响
    d.deleteBlockRow(c._company_id!, 'block1', company.block1_rows![0]._row_id!)
    expect(company.block1_rows).toHaveLength(1)
    expect(company.block2_rows).toHaveLength(2)
  })

  it('block3 处置损益随 updateBlockField 自动计算', () => {
    const d = makeData()
    const c = d.addCompany()
    const row = d.addBlockRow(c._company_id!, 'block3')!
    d.updateBlockField(c._company_id!, 'block3', row._row_id!, 'trade_amount', 150000)
    d.updateBlockField(c._company_id!, 'block3', row._row_id!, 'original_cost', 120000)
    d.updateBlockField(c._company_id!, 'block3', row._row_id!, 'fee', 300)

    const updated = d.companies.value[0].block3_rows![0]
    expect(updated.disposal_gain).toBeCloseTo(29700, 2)
  })

  it('block4 股利差异随 updateBlockField 自动计算（源三区对齐后股利移入 block4 源外增强）', () => {
    const d = makeData()
    const c = d.addCompany()
    const row = d.addBlockRow(c._company_id!, 'block4')!
    d.updateBlockField(c._company_id!, 'block4', row._row_id!, 'dividend_receivable', 10000)
    d.updateBlockField(c._company_id!, 'block4', row._row_id!, 'net_received', 7500)
    d.updateBlockField(c._company_id!, 'block4', row._row_id!, 'dividend_tax', 2000)

    const updated = d.companies.value[0].block4_rows![0]
    expect(updated.dividend_diff).toBeCloseTo(500, 2)
  })

  // 🔴 以下三条断言原先要求 block1 含记账凭证列、block2 含 `trade_amount`，
  //    那是**源对齐前**的结构。g0 spec R7.2/R7.3 明确：源模板 `A10:E10` 区块①只有
  //    被投资单位/投资比例/投资金额/投资条款/索引号 5 列（无记账凭证），`trade_amount`
  //    属区块③处置口径 → 两者已移出渲染并逐列登记进 `G06_SOURCE_EXTRA`（字段不删）。
  it('getBlockTotal 按 sumField 累加金额列（block1 只有「投资金额」）', () => {
    const d = makeData()
    const c = d.addCompany()
    const r1 = d.addBlockRow(c._company_id!, 'block1')!
    const r2 = d.addBlockRow(c._company_id!, 'block1')!
    d.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'investment_amount', 5000)
    d.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'investment_amount', 3000)

    const total = d.getBlockTotal(d.companies.value[0], 'block1')
    expect(total.investment_amount).toBeCloseTo(8000, 2)
    // 记账凭证列已移出区块①（源 A10:E10 无此列）→ 不再产生 voucher_amount 合计
    expect(getSumFieldsG06('block1')).not.toContain('voucher_amount')
  })

  it('getBlockTotalByDirection 按借贷方向分组累加 block2 本期发生额', () => {
    const d = makeData()
    const c = d.addCompany()
    const rd = d.addBlockRow(c._company_id!, 'block2')!
    d.updateBlockField(c._company_id!, 'block2', rd._row_id!, 'direction', 'debit')
    d.updateBlockField(c._company_id!, 'block2', rd._row_id!, 'voucher_amount', 1200)
    const rc = d.addBlockRow(c._company_id!, 'block2')!
    d.updateBlockField(c._company_id!, 'block2', rc._row_id!, 'direction', 'credit')
    d.updateBlockField(c._company_id!, 'block2', rc._row_id!, 'voucher_amount', 800)

    const company = d.companies.value[0]
    // 区块② 的金额列是源 `E18 金额`（voucher_amount），不是自造的 trade_amount
    expect(d.getBlockTotalByDirection(company, 'block2', 'debit').voucher_amount).toBeCloseTo(1200, 2)
    expect(d.getBlockTotalByDirection(company, 'block2', 'credit').voucher_amount).toBeCloseTo(800, 2)
    // 全 block 合计 = 借+贷
    expect(d.getBlockTotal(company, 'block2').voucher_amount).toBeCloseTo(2000, 2)
  })

  it('每区块 sumField 定义与列配置一致（源三区对齐后新结构）', () => {
    // block1 = ①初始投资协议检查（源 A10:E10，无记账凭证列）
    expect(getSumFieldsG06('block1')).toEqual(['investment_amount'])
    // block2 = ②本期发生额检查（源 E18「金额」）
    expect(getSumFieldsG06('block2')).toEqual(['voucher_amount'])
    // block3 = ③期后出售/赎回检查（源三组证据金额 + 源外增强处置口径）
    expect(getSumFieldsG06('block3')).toContain('voucher_amount')
    expect(getSumFieldsG06('block3')).toContain('deal_amount')
    expect(getSumFieldsG06('block3')).toContain('bank_slip_amount')
    expect(getSumFieldsG06('block3')).toContain('disposal_amount')
    expect(getSumFieldsG06('block3')).toContain('trade_amount')
    // block4 = ④源外增强（保留原持仓/股利字段）
    expect(getSumFieldsG06('block4')).toContain('market_value')
    expect(getSumFieldsG06('block4')).toContain('dividend_receivable')
    // 🔴 原断言「4 区块均含记账凭证金额列」已作废：源模板区块①无记账凭证列（R7.2）。
    //    改为断言「除区块① 外均含」+ 区块① 显式不含（反向锁死，防又被塞回去）。
    for (const bt of blocks.filter((b) => b !== 'block1')) {
      expect(getSumFieldsG06(bt)).toContain('voucher_amount')
    }
    expect(getSumFieldsG06('block1')).not.toContain('voucher_amount')
  })

  it('metrics 完成度：四区块均有行才算完成', () => {
    const d = makeData()
    const c = d.addCompany()
    // 只填 2 个区块
    d.addBlockRow(c._company_id!, 'block1')
    d.addBlockRow(c._company_id!, 'block2')
    const status = d.getCompletionStatus(d.companies.value[0])
    expect(status.completed).toBe(2)
    expect(status.total).toBe(4)
    expect(d.metrics.value.completed_companies).toBe(0)

    // 补齐 4 区块
    d.addBlockRow(c._company_id!, 'block3')
    d.addBlockRow(c._company_id!, 'block4')
    expect(d.getCompletionStatus(d.companies.value[0]).completed).toBe(4)
    expect(d.metrics.value.completed_companies).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// 5. G0-1 → G0-6 反向联动（未回函项目带入映射）
// ---------------------------------------------------------------------------
describe('G0 集成: G0-1 → G0-6 反向联动', () => {
  /** 复制 GtConfirmationAlternativeG06.vue handleImportG01 的过滤+映射逻辑 */
  function filterUnreplied(rows: any[]) {
    return rows.filter(
      (r) => r.match_status === '未回函' || (r.is_replied === false && r.match_status !== '相符'),
    )
  }
  function mapToCompanies(unreplied: any[]) {
    return unreplied.map((r) => ({
      entity_name: r.entity_name || '',
      confirm_index: r.confirm_index,
      _source: 'auto',
      balance: {
        item_name: r.account_type || '交易性金融资产',
        investment_type: r.account_type || '交易性金融资产',
        closing_balance: Number(r.amount) || 0,
      },
    }))
  }

  const g01Rows = [
    { entity_name: '甲证券公司', match_status: '相符', is_replied: true, confirm_index: 'IDX-1', amount: 100000 },
    { entity_name: '乙基金', match_status: '未回函', is_replied: false, confirm_index: 'IDX-2', amount: 50000, account_type: '债权投资' },
    { entity_name: '丙投资', match_status: '不符', is_replied: false, confirm_index: 'IDX-3', amount: 30000 },
  ]

  it('只带入未回函/未回复且不相符的项目', () => {
    const unreplied = filterUnreplied(g01Rows)
    // 乙基金（未回函）+ 丙投资（is_replied=false 且非相符）
    expect(unreplied.map((r) => r.entity_name)).toEqual(['乙基金', '丙投资'])
  })

  it('映射为 G0-6 公司清单，携带投资类型与期末余额', () => {
    const companies = mapToCompanies(filterUnreplied(g01Rows))
    expect(companies).toHaveLength(2)
    expect(companies[0].entity_name).toBe('乙基金')
    expect(companies[0].balance.investment_type).toBe('债权投资')
    expect(companies[0].balance.closing_balance).toBe(50000)
    // 无 account_type → 默认交易性金融资产
    expect(companies[1].balance.investment_type).toBe('交易性金融资产')
  })

  it('importCompanies 按 confirm_index 去重导入', () => {
    let htmlData: any = { _format: 'alternative-g06-v1', companies: [] }
    const d = useAlternativeG06Data({ htmlData: () => htmlData, readonly: false })
    const companies = mapToCompanies(filterUnreplied(g01Rows))
    d.importCompanies(companies)
    expect(d.companies.value).toHaveLength(2)
    // 再次导入相同 confirm_index → 去重不重复添加
    d.importCompanies(companies)
    expect(d.companies.value).toHaveLength(2)
  })

  it('无未回函项目时不带入', () => {
    const allReplied = [{ entity_name: 'X', match_status: '相符', is_replied: true }]
    expect(filterUnreplied(allReplied)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// 6. 导入导出 round-trip（后端 spec + 前后端列定义一致性）
// ---------------------------------------------------------------------------
describe('G0 集成: 导入导出列定义前后端一致性', () => {
  const importExportPath = path.resolve(
    __dirname,
    '../../../../../../backend/app/routers/wp_render_strategies/_g0_confirmation_import_export.py',
  )
  const content = fs.readFileSync(importExportPath, 'utf-8')

  it('_g0_confirmation_import_export.py 三端点已注册', () => {
    expect(content).toContain('/g0/export-template')
    expect(content).toContain('/g0/export-data')
    expect(content).toContain('/g0/import-data')
  })

  it('G0-3S 单 sheet 17 列 + G0-6 四区块分 sheet', () => {
    // G0-3S 数据格式为 diff-securities-v1（单 sheet）
    expect(content).toContain('diff-securities-v1')
    // G0-6 数据格式为 alternative-g06-v1（4 区块）
    expect(content).toContain('alternative-g06-v1')
    // 4 区块 sheet 标题
    expect(content).toContain('①持仓证明检查')
    expect(content).toContain('②投资收益股利收入证据')
    expect(content).toContain('③投资处置收益证据')
    expect(content).toContain('④公允价值佐证')
  })

  // 🔴 原断言要求**四**区块都含记账凭证 5 列 —— 源对齐后区块①不含（源 A10:E10 只有
  //    5 列且无凭证信息，g0 spec R7.2）。改为「区块②③④含 + 区块①显式不含」双向锁死；
  //    区块①的 5 个凭证字段已逐列登记进 `G06_SOURCE_EXTRA`（字段保留、不再渲染）。
  it('G0-6 记账凭证 5 列：区块②③④ 前后端均含，区块① 已按源模板移出渲染', () => {
    const voucherFields = ['voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount']
    for (const bt of ['block2', 'block3', 'block4'] as BlockType[]) {
      const fields = BLOCK_COLUMN_CONFIGS_G06[bt].columns.map((c) => c.field)
      for (const vf of voucherFields) {
        expect(fields).toContain(vf)
        // 后端也定义同一批 field_key
        expect(content).toContain(`"${vf}"`)
      }
    }
    const block1Fields = BLOCK_COLUMN_CONFIGS_G06.block1.columns.map((c) => c.field)
    for (const vf of voucherFields) {
      expect(block1Fields).not.toContain(vf)
      // 移出渲染 ≠ 丢字段：必须在源外增强登记表里有落点（数据零丢失红线 R7.5）
      expect(G06_SOURCE_EXTRA.some((e) => e.block === 'block1' && e.field === vf)).toBe(true)
    }
  })

  it('G0-6 处置损益公式列（disposal_gain）前后端均存在', () => {
    const block3Fields = BLOCK_COLUMN_CONFIGS_G06.block3.columns.map((c) => c.field)
    expect(block3Fields).toContain('disposal_gain')
    expect(content).toContain('"disposal_gain"')
  })

  it('round-trip：G0-3S 导出列 field_key 与前端 SecuritiesDiffRow 字段对齐', () => {
    // 关键 field_key 后端定义存在
    const keyFields = ['security_name', 'security_code', 'confirmed_qty', 'booked_qty', 'qty_diff', 'fv_diff', 'market_value_diff']
    for (const f of keyFields) {
      expect(content).toContain(`"${f}"`)
    }
  })
})

// ---------------------------------------------------------------------------
// 7. 版本快照 autoSnapshot 触发（debounce）
// ---------------------------------------------------------------------------
const mockPost = vi.fn().mockResolvedValue({ data: {} })
vi.mock('@/utils/http', () => ({
  default: {
    post: (...args: any[]) => mockPost(...args),
    get: vi.fn(),
  },
}))

describe('G0 集成: 版本快照 autoSnapshot 触发', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPost.mockClear()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('scheduleAutoSnapshot debounce 后 POST 版本快照端点', async () => {
    const { ref } = await import('vue')
    const { useWorkpaperVersionToolbar } = await import('../composables/useWorkpaperVersionToolbar')
    const toolbar = useWorkpaperVersionToolbar({
      wpId: ref('wp-123'),
      projectId: ref('proj-456'),
      debounceMs: 3000,
    })

    toolbar.scheduleAutoSnapshot()
    // debounce 未到不触发
    expect(mockPost).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(3000)
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-456/workpapers/wp-123/versions')
    expect(body.snapshot_type).toBe('auto')
  })

  it('连续多次调度只触发一次（debounce 合并）', async () => {
    const { ref } = await import('vue')
    const { useWorkpaperVersionToolbar } = await import('../composables/useWorkpaperVersionToolbar')
    const toolbar = useWorkpaperVersionToolbar({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      debounceMs: 3000,
    })

    toolbar.scheduleAutoSnapshot()
    await vi.advanceTimersByTimeAsync(1000)
    toolbar.scheduleAutoSnapshot()
    await vi.advanceTimersByTimeAsync(1000)
    toolbar.scheduleAutoSnapshot()
    await vi.advanceTimersByTimeAsync(3000)

    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('缺少 wpId/projectId 时不发请求', async () => {
    const { ref } = await import('vue')
    const { useWorkpaperVersionToolbar } = await import('../composables/useWorkpaperVersionToolbar')
    const toolbar = useWorkpaperVersionToolbar({
      wpId: ref(''),
      projectId: ref('proj-1'),
      debounceMs: 3000,
    })
    toolbar.scheduleAutoSnapshot()
    await vi.advanceTimersByTimeAsync(3000)
    expect(mockPost).not.toHaveBeenCalled()
  })
})
