/**
 * alternativeBlockManifest.ts — 替代程序区块结构清单（契约守卫基准）
 *
 * confirmation-alternative-structure-alignment Task 1.1：
 * 对照各套源模板逐区块录入 BlockSpec，供契约守卫比对 blockColumnConfigs* 漂移。
 * 纯数据文件，不改生产行为。
 *
 * 【block 位映射核实依据】：
 * - K05: SUM_FIELDS 定义在 useAlternativeK05Data.ts (block3=本期发生额)
 * - K06: BLOCK_TITLES_K06 定义在 useAlternativeK06Data.ts:79 (block3=③本期发生额检查)
 * - L05: SUM_FIELDS 定义在 useAlternativeL05Data.ts:102 (block3=本期借款)
 * - G06: BLOCK_COLUMN_CONFIGS_G06 定义在 blockColumnConfigsG06.ts
 * - H05: getSumFieldsH05 定义在 blockColumnConfigsH05.ts
 * - D05/D06/F05/F06: blockColumnConfigs.ts (D05 共享) / F05/F06 各自单文件
 */

// ─── Types ──────────────────────────────────────────────────────────────────

export type AltCycleSheet = 'D05' | 'D06' | 'F05' | 'F06' | 'H05' | 'K05' | 'K06' | 'L05' | 'G06'

export interface BlockSpec {
  /** 工厂 block 位（block1-block4） */
  block: 'block1' | 'block2' | 'block3' | 'block4'
  /** 源模板区块标题 */
  title: string
  /** 源模板该区块的列字段（sumField 列） */
  columns: string[]
  /** 标记该 block 需要按 direction 拆借方/贷方两张表渲染 */
  splitByDirection?: boolean
  /** 标记该区块为源外增强（源模板无该区块或该区块留白） */
  sourceExtra?: boolean
  /** 源外增强依据说明 */
  sourceExtraReason?: string
}

// ─── Manifest ───────────────────────────────────────────────────────────────

/**
 * 全部九套替代程序的区块结构清单。
 * 契约守卫（Task 6.2）将以此为真源比对各套 blockColumnConfigs* 的区块集合与列集合。
 */
export const ALTERNATIVE_BLOCK_MANIFEST: Record<AltCycleSheet, BlockSpec[]> = {

  // ── D05 应收账款替代程序（不改结构，作 gold 标准） ─────────────────────────
  // columns = 各套 blockColumnConfigs* 的实际 sumField 列（Property 10 drift guard 真源，
  // 由 getSumFields* 实测校准；漂移即失败）。
  D05: [
    { block: 'block1', title: '①期后收款检查', columns: ['debit_amount', 'invoice_amount'] },
    { block: 'block2', title: '②发货单/运输凭证', columns: ['credit_amount', 'bank_amount'] },
    { block: 'block3', title: '③销售合同检查', columns: ['receipt_amount'] },
    { block: 'block4', title: '④其他支持性证据', columns: ['product_amount'] },
  ],

  // ── D06 应收账款-期后收款（镜像 D05，方向=贷方收款） ──────────────────────
  D06: [
    { block: 'block1', title: '①期后收款检查', columns: ['debit_amount', 'acceptance_amount', 'invoice_amount'] },
    { block: 'block2', title: '②发货/运输证据', columns: ['credit_amount', 'bank_amount'] },
    { block: 'block3', title: '③销售合同/订单', columns: ['product_amount'] },
    { block: 'block4', title: '④其他支持性证据', columns: ['receipt_amount'] },
  ],

  // ── F05 采购循环替代程序（不改结构，只拆子组件） ─────────────────────────────
  F05: [
    { block: 'block1', title: '①期后付款检查', columns: ['voucher_amount', 'invoice_amount'] },
    { block: 'block2', title: '②采购订单/合同', columns: ['voucher_amount', 'bank_amount'] },
    { block: 'block3', title: '③入库/验收凭证', columns: ['payment_amount', 'bank_amount', 'invoice_amount'] },
    { block: 'block4', title: '④其他支持性证据', columns: ['voucher_amount', 'contract_amount', 'invoice_amount'] },
  ],

  // ── F06 预付账款替代程序（镜像 F05） ───────────────────────────────────────
  F06: [
    { block: 'block1', title: '①期后付款检查', columns: ['voucher_amount', 'invoice_amount'] },
    { block: 'block2', title: '②采购合同/订单', columns: ['payment_amount', 'bank_amount', 'invoice_amount'] },
    { block: 'block3', title: '③入库/验收凭证', columns: ['voucher_amount', 'contract_amount', 'invoice_amount'] },
    { block: 'block4', title: '④其他支持性证据', columns: ['payment_amount', 'bank_amount', 'invoice_amount'] },
  ],

  // ── H05 固定资产替代程序（源模板留白，四区块全为源外增强） ─────────────────
  H05: [
    {
      block: 'block1', title: '①验收权属检查',
      columns: ['voucher_amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 H0-5「二、检查过程记录」为空白区，该区块由平台自建，非源模板要求',
    },
    {
      block: 'block2', title: '②采购证据检查',
      columns: ['voucher_amount', 'contract_amount', 'invoice_amount', 'payment_amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 H0-5 留白区，平台自建采购证据核查能力',
    },
    {
      block: 'block3', title: '③新增资产检查',
      columns: ['voucher_amount', 'cap_cost'],
      sourceExtra: true,
      sourceExtraReason: '源模板 H0-5 留白区，平台自建新增资产核查能力',
    },
    {
      block: 'block4', title: '④抵押/租赁证据',
      columns: ['voucher_amount', 'mortgage_amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 H0-5 留白区，平台自建抵押租赁核查能力',
    },
  ],

  // ── K05 其他应收款替代程序 ─────────────────────────────────────────────────
  K05: [
    { block: 'block1', title: '①期后收款检查', columns: ['voucher_amount', 'receipt_amount'] },
    { block: 'block2', title: '②期末余额支持性证据', columns: ['voucher_amount', 'agreement_amount'] },
    {
      block: 'block3', title: '③本期发生额检查',
      columns: ['voucher_amount', 'approval_amount'],
      splitByDirection: true, // 源模板 K0-5 第③区块为借方/贷方两张表
    },
    {
      block: 'block4', title: '④往来对账',
      columns: ['voucher_amount', 'other_balance', 'self_balance'],
      sourceExtra: true,
      sourceExtraReason: '源模板 K0-5 无往来对账区块，平台增强以提升覆盖率',
    },
  ],

  // ── K06 其他应付款替代程序 ─────────────────────────────────────────────────
  K06: [
    { block: 'block1', title: '①期后付款检查', columns: ['amount', 'paymentAmount'] },
    { block: 'block2', title: '②期末余额支持性证据', columns: ['amount', 'agreementAmount'] },
    {
      block: 'block3', title: '③本期发生额检查',
      columns: ['amount', 'approvalAmount'],
      splitByDirection: true, // 源模板 K0-6 第③区块为借方/贷方两张表
    },
    {
      block: 'block4', title: '④往来对账/协议证据',
      columns: ['amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 K0-6 无往来对账/协议区块，平台增强',
    },
  ],

  // ── L05 长期应付款/借款替代程序 ────────────────────────────────────────────
  // 注：L05 的 getSumFields 内联于 useAlternativeL05Data.ts（SUM_FIELDS，未导出），
  // 故不纳入 Property 10 的 getSumFields drift guard；仅校验其区块集合/splitByDirection/源外登记。
  L05: [
    { block: 'block1', title: '①期后还款检查', columns: ['voucher_amount', 'repayment_principal', 'repayment_interest'] },
    { block: 'block2', title: '②期末余额支持性证据', columns: ['voucher_amount', 'contract_amount', 'book_balance'] },
    {
      block: 'block3', title: '③本期借款检查',
      columns: ['voucher_amount', 'arrival_amount'],
      splitByDirection: true, // 源模板 L0-5 第③区块为借方(归还)/贷方(借入)两张表
    },
    {
      block: 'block4', title: '④抵质押/担保证据',
      columns: ['voucher_amount', 'mortgage_amount', 'guarantee_amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 L0-5 无抵质押/担保区块，平台增强',
    },
  ],

  // ── G06 投资循环替代程序（改造目标：对齐源三区） ─────────────────────────────
  // 【改造前现状】block1=持仓证明 / block2=股利 / block3=处置 / block4=公允价值
  // 【改造后目标】block1=①初始投资协议 / block2=②本期发生额(借贷拆表) / block3=③期后出售赎回 / block4=源外增强
  G06: [
    { block: 'block1', title: '①初始投资协议检查', columns: ['voucher_amount', 'investment_amount'] },
    {
      block: 'block2', title: '②本期发生额检查',
      columns: ['voucher_amount', 'trade_amount'],
      splitByDirection: true, // 源模板 G0-6 第②区块为借方/贷方两张表
    },
    { block: 'block3', title: '③期后出售/赎回检查', columns: ['voucher_amount', 'disposal_amount', 'trade_amount'] },
    {
      block: 'block4', title: '④源外增强（公允价值/持仓/股利）',
      columns: ['voucher_amount', 'market_value', 'dividend_receivable', 'trade_amount'],
      sourceExtra: true,
      sourceExtraReason: '源模板 G0-6 无公允价值/持仓/股利独立区块；现有四区块改造后语义迁移到block1-3或保留此block4',
    },
  ],
}

// ─── Source Extra 独立登记（满足 Requirement 4.4，可被守卫读取） ────────────

export interface SourceExtraEntry {
  /** 套别 */
  suite: AltCycleSheet
  /** 区块位 */
  block: 'block1' | 'block2' | 'block3' | 'block4'
  /** 区块标题 */
  title: string
  /** 依据说明 */
  reason: string
}

/**
 * 全部源外增强区块登记（从 ALTERNATIVE_BLOCK_MANIFEST 中 sourceExtra=true 的条目派生）。
 * 守卫（Task 6.2 Property 8）断言：每个 sourceExtra 区块在此有对应条目。
 */
export const SOURCE_EXTRA_MANIFEST: SourceExtraEntry[] = (() => {
  const entries: SourceExtraEntry[] = []
  for (const [suite, blocks] of Object.entries(ALTERNATIVE_BLOCK_MANIFEST)) {
    for (const spec of blocks) {
      if (spec.sourceExtra) {
        entries.push({
          suite: suite as AltCycleSheet,
          block: spec.block,
          title: spec.title,
          reason: spec.sourceExtraReason || '（未说明依据）',
        })
      }
    }
  }
  return entries
})()
