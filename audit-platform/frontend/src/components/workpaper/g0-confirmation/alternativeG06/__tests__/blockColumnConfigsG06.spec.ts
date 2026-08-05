/**
 * blockColumnConfigsG06.spec.ts — G0-6 四区块列定义守卫
 *
 * spec: g0-confirmation-source-alignment，Task 15/16
 * Property 16（与源模板两级表头交叉锁死）/ 17（数据零丢失）/ 18（编制指导文案与区块一致）
 *
 * 源侧事实由后端 `backend/tests/test_g0_source_template_facts.py::TestAlternativeProcedure`
 * 以 openpyxl 直读固化（区块锚点 + 三区两级表头 + block1 无凭证列）。本文件以同一批
 * 逐字常量作基准 —— 两侧独立录入同一份源模板，互为交叉验证；后端那份是裁决者。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  BLOCK_COLUMN_CONFIGS_G06,
  G06_SOURCE_EXTRA,
  G06_SOURCE_FIELDS,
  G0_ACCOUNT_SUBJECT_OPTIONS,
  getGroupsG06,
  getSumFieldsG06,
} from '../blockColumnConfigsG06'

// ─── 源模板逐字基准（与后端守卫同源） ────────────────────────────────────────

/** 源 A10:E10 —— 区块①，**无记账凭证列** */
const SRC_BLOCK1_LABELS = ['被投资单位', '投资比例', '投资金额', '投资条款', '索引号'] as const

/** 源 R17（组行）/ R18（叶子行）—— 区块②借贷两区共用 */
const SRC_BLOCK2_GROUPS = ['记账凭证', '支持性文件1', '支持性文件2'] as const
const SRC_BLOCK2_LEAVES = [
  '日期', '凭证编号', '业务内容', '对方科目', '金额',
  '识别特征', '信息1', '信息2',
  '识别特征', '信息1', '信息2',
] as const

/** 源 R33（组行）/ R34（叶子行）—— 区块③ */
const SRC_BLOCK3_GROUPS = ['记账凭证', '投资协议/交易确认单/交割单', '银行回单'] as const
const SRC_BLOCK3_LEAVES = [
  '日期', '凭证编号', '业务内容', '对方科目', '金额',
  '日期/编号', '被投资单位名称', '金额',
  '日期/编号', '付款方', '金额',
] as const

function labels(blockType: 'block1' | 'block2' | 'block3' | 'block4'): string[] {
  return BLOCK_COLUMN_CONFIGS_G06[blockType].columns.map((c) => c.label)
}
function fields(blockType: 'block1' | 'block2' | 'block3' | 'block4'): string[] {
  return BLOCK_COLUMN_CONFIGS_G06[blockType].columns.map((c) => c.field)
}

// ─── Property 16: 与源模板交叉锁死 ───────────────────────────────────────────

describe('Property 16: 区块① 对齐源 A10:E10（无记账凭证列）', () => {
  it('列 label 序列 == 源模板（序号列除外）', () => {
    expect(labels('block1').filter((l) => l !== '序号')).toEqual([...SRC_BLOCK1_LABELS])
  })

  it('🔴 不含记账凭证 5 列（源模板该区没有）', () => {
    const f = fields('block1')
    for (const banned of ['voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount']) {
      expect(f, `区块① 不该有 ${banned}`).not.toContain(banned)
    }
  })

  it('已补「投资条款」（源 D10）', () => {
    expect(fields('block1')).toContain('investment_term')
    expect(labels('block1')).toContain('投资条款')
  })

  it('区块① 源列集合与 G06_SOURCE_FIELDS 声明一致', () => {
    expect(fields('block1').filter((f) => f !== 'seq')).toEqual([...G06_SOURCE_FIELDS.block1])
  })
})

describe('Property 16: 区块② 对齐源 R17/R18 两级表头', () => {
  it('组名序列 == 源模板（无 group 的通用列除外）', () => {
    expect([...new Set(getGroupsG06('block2'))]).toEqual([...SRC_BLOCK2_GROUPS])
  })

  it('叶子 label 序列 == 源模板（序号/索引号/是否异常 除外）', () => {
    const leaf = BLOCK_COLUMN_CONFIGS_G06.block2.columns.filter((c) => c.group).map((c) => c.label)
    expect(leaf).toEqual([...SRC_BLOCK2_LEAVES])
  })

  it('🔴 支持性文件 1/2 各 3 列（此前被压成一个 support_doc 单列）', () => {
    const f = fields('block2')
    for (const k of ['support1_feature', 'support1_info1', 'support1_info2', 'support2_feature', 'support2_info1', 'support2_info2']) {
      expect(f, `缺 ${k}`).toContain(k)
    }
    expect(f, 'support_doc 不该再作为列渲染').not.toContain('support_doc')
  })

  it('`……` 占位列头不建列（永远收不到数据）', () => {
    expect(labels('block2')).not.toContain('……')
  })

  it('两个「识别特征」分属不同 group（否则界面出现两个同名列且无法区分）', () => {
    const cols = BLOCK_COLUMN_CONFIGS_G06.block2.columns.filter((c) => c.label === '识别特征')
    expect(cols).toHaveLength(2)
    expect(cols[0].group).not.toBe(cols[1].group)
  })
})

describe('Property 16: 区块③ 对齐源 R33/R34 + 源外增强并列', () => {
  it('源模板三个组名都在（且顺序在最前）', () => {
    const groups = [...new Set(getGroupsG06('block3'))]
    expect(groups.slice(0, 3)).toEqual([...SRC_BLOCK3_GROUPS])
  })

  it('源模板三组的叶子 label 序列逐字一致', () => {
    const srcGroupSet = new Set<string>(SRC_BLOCK3_GROUPS)
    const leaf = BLOCK_COLUMN_CONFIGS_G06.block3.columns
      .filter((c) => c.group && srcGroupSet.has(c.group))
      .map((c) => c.label)
    expect(leaf).toEqual([...SRC_BLOCK3_LEAVES])
  })

  it('已补两组证据列（投资协议/交易确认单/交割单 + 银行回单）', () => {
    const f = fields('block3')
    for (const k of ['deal_doc_no', 'deal_investee_name', 'deal_amount', 'bank_slip_no', 'bank_payer', 'bank_slip_amount']) {
      expect(f, `缺 ${k}`).toContain(k)
    }
  })

  it('裁决门 C：源外增强列全部保留且归入独立 group', () => {
    const extras = BLOCK_COLUMN_CONFIGS_G06.block3.columns.filter((c) => c.group === '源外增强·处置明细')
    expect(extras.map((c) => c.field)).toEqual([
      'disposal_amount', 'net_proceeds', 'trade_confirm_date', 'sell_qty', 'trade_price',
      'trade_amount', 'original_cost', 'fee', 'disposal_gain', 'bank_received',
    ])
  })

  it('区块③ 源列集合与 G06_SOURCE_FIELDS 声明一致', () => {
    const srcGroupSet = new Set<string>(SRC_BLOCK3_GROUPS)
    const srcFields = BLOCK_COLUMN_CONFIGS_G06.block3.columns
      .filter((c) => !c.group || srcGroupSet.has(c.group))
      .map((c) => c.field)
      .filter((f) => f !== 'seq')
    expect(srcFields).toEqual([...G06_SOURCE_FIELDS.block3])
  })
})

// ─── Property 16 续: 源外增强全部在册 ───────────────────────────────────────

describe('Property 16: 每个源外字段都在 G06_SOURCE_EXTRA 登记', () => {
  const registered = new Set(G06_SOURCE_EXTRA.map((e) => e.field))
  // 通用列（各区块共有、非源模板特有）不算源外增强
  const COMMON = new Set(['seq', 'ref_index', 'is_abnormal'])

  it.each(['block1', 'block2', 'block3'] as const)('%s 的每个渲染字段要么是源列要么已登记', (block) => {
    const src = new Set<string>(G06_SOURCE_FIELDS[block])
    for (const f of fields(block)) {
      if (COMMON.has(f) || src.has(f)) continue
      expect(registered, `${block}.${f} 既不是源列也未登记为源外增强`).toContain(f)
    }
  })

  it('block4 整区为源外增强 → 每个字段都已登记', () => {
    for (const f of fields('block4')) {
      if (COMMON.has(f)) continue
      // 记账凭证 5 列在 block4 是承接迁移数据用，登记在 block1 条目里说明了来由
      if (['voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount'].includes(f)) continue
      expect(registered, `block4.${f} 未登记`).toContain(f)
    }
  })

  it('每条登记都有 ≥10 字理由（防空话）', () => {
    for (const e of G06_SOURCE_EXTRA) {
      expect(e.reason.length, `${e.block}.${e.field} 理由过短`).toBeGreaterThanOrEqual(10)
    }
  })

  it('登记表无重复 (field, block) 组合', () => {
    const keys = G06_SOURCE_EXTRA.map((e) => `${e.block}.${e.field}`)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ─── Property 17: 数据零丢失 ─────────────────────────────────────────────────

describe('Property 17: 重构不丢字段', () => {
  /** 重构前的字段全集（从本次改动的 git 前态人工录入，作为零丢失基准） */
  const BEFORE_FIELDS: Readonly<Record<string, readonly string[]>> = {
    block1: ['seq', 'voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount', 'investment_amount', 'agreement_date', 'agreement_no', 'investee_name', 'invest_ratio', 'ref_index', 'is_abnormal'],
    block2: ['seq', 'voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount', 'trade_amount', 'trade_type', 'support_doc', 'ref_index', 'is_abnormal'],
    block3: ['seq', 'voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount', 'disposal_amount', 'net_proceeds', 'trade_confirm_date', 'sell_qty', 'trade_price', 'trade_amount', 'original_cost', 'fee', 'disposal_gain', 'bank_received', 'ref_index', 'is_abnormal'],
  }

  /** 有意不再渲染的字段 → 必须在 G06_SOURCE_EXTRA 或迁移映射里有落点 */
  const MIGRATED: Readonly<Record<string, string>> = {
    support_doc: 'support1_feature',
  }

  it.each(['block1', 'block2', 'block3'] as const)('%s：每个旧字段要么仍渲染、要么已登记、要么有迁移落点', (block) => {
    const now = new Set(fields(block))
    const registered = new Set(G06_SOURCE_EXTRA.filter((e) => e.block === block).map((e) => e.field))
    for (const f of BEFORE_FIELDS[block]) {
      if (now.has(f)) continue
      if (registered.has(f)) continue
      const target = MIGRATED[f]
      expect(target, `${block}.${f} 既不渲染、未登记、也无迁移落点 → 数据会丢`).toBeTruthy()
      expect(now, `${block}.${f} 的迁移落点 ${target} 不存在`).toContain(target)
    }
  })

  it('support_doc 的迁移在 composable 里实现且幂等（不删原值）', () => {
    const src = readFileSync(resolve(__dirname, '../composables/useAlternativeG06Data.ts'), 'utf-8')
    expect(src).toContain('migrateSupportDoc')
    expect(src).toContain('support1_feature')
    // 幂等前提：已填新字段则跳过
    expect(src).toMatch(/support1_feature\s*!=\s*null\s*&&\s*row\.support1_feature\s*!==\s*''/)
    // 不删原值（保留供导入导出/回溯）
    expect(src).not.toMatch(/delete\s+row\.support_doc/)
    expect(src).not.toMatch(/row\.support_doc\s*=\s*(''|undefined|null)/)
  })

  it('block4 仍持有全部旧四并列区块字段（承接 migrateLegacyBlocks）', () => {
    const f = fields('block4')
    for (const k of ['holding_variety', 'market_value', 'dividend_receivable', 'received_amount', 'net_received', 'dividend_diff', 'quote_source', 'valuation_model', 'fv_level', 'book_vs_quote_diff']) {
      expect(f, `block4 缺 ${k} → migrateLegacyBlocks 搬过来的数据无处显示`).toContain(k)
    }
  })
})

// ─── Property 18: 编制指导文案与现行区块一致 ────────────────────────────────

describe('Property 18: 编制指导文案不描述已废弃的四并列区块', () => {
  const vue = readFileSync(resolve(__dirname, '../GtConfirmationAlternativeG06.vue'), 'utf-8')

  it('不再把「持仓证明/投资收益股利/处置收益/公允价值佐证」当①②③④', () => {
    // 旧文案特征：①持仓证明 … ②投资收益/股利 … ③处置收益 … ④公允价值佐证
    expect(vue).not.toMatch(/①持仓证明/)
    expect(vue).not.toMatch(/②投资收益\/股利/)
    expect(vue).not.toMatch(/③处置收益/)
  })

  it('文案提到的三区名与源模板一致', () => {
    expect(vue).toContain('检查初始投资协议')
    expect(vue).toContain('检查本期发生额')
    expect(vue).toContain('检查期后是否被出售或赎回')
  })

  it('文案说明第四区是源外增强并指向登记表', () => {
    expect(vue).toContain('源外增强')
    expect(vue).toContain('G06_SOURCE_EXTRA')
  })

  it('补齐源模板两个表头字段（A5 会计科目 / D5 投资产品名称）', () => {
    expect(vue).toContain('account_subject')
    expect(vue).toContain('investment_product')
    expect(vue).toContain('会计科目')
    expect(vue).toContain('投资产品/名称')
  })

  it('会计科目下拉候选 = G 循环八个投资科目，且允许自定义', () => {
    expect(G0_ACCOUNT_SUBJECT_OPTIONS).toHaveLength(8)
    expect(G0_ACCOUNT_SUBJECT_OPTIONS[0]).toBe('交易性金融资产')
    expect(vue).toContain('allow-create')
  })

  it('反向自检：源码非空且含编制提示区（防读文件失败导致断言空转）', () => {
    expect(vue.length).toBeGreaterThan(1000)
    expect(vue).toContain('编制提示')
  })
})

// ─── 合计字段 ────────────────────────────────────────────────────────────────

describe('getSumFieldsG06', () => {
  it('区块① 合计投资金额', () => {
    expect(getSumFieldsG06('block1')).toEqual(['investment_amount'])
  })

  it('区块② 合计记账凭证金额', () => {
    expect(getSumFieldsG06('block2')).toEqual(['voucher_amount'])
  })

  it('区块③ 合计源三组金额 + 源外处置金额（不重复计同一列）', () => {
    const sums = getSumFieldsG06('block3')
    expect(sums).toContain('voucher_amount')
    expect(sums).toContain('deal_amount')
    expect(sums).toContain('bank_slip_amount')
    expect(new Set(sums).size).toBe(sums.length)
  })

  it('未知区块返空数组（不抛错）', () => {
    expect(getSumFieldsG06('blockX')).toEqual([])
  })
})
