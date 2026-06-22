/**
 * alternativeD05Types.ts — D0-5 合同负债及销售替代程序 类型定义
 *
 * 核心设计：
 * - 多公司 master-detail：每公司一组 4 区块检查宽表
 * - 4 区块各自列结构不同（10-30 列），由 BLOCK_COLUMN_CONFIGS 驱动
 * - 检查比例自动计算：区块③④合计 / 本期销售额
 * - 从 D0-1 带入未回函公司，从 D0-4 带入未达账项
 * - 经理复核红线：异常行 / 区块空 / 比例低
 */

// ─── 检查行（通用结构，各区块共享） ─────────────────────────────────────────

export interface CheckRow {
  /** 内部行 ID（UUID，前端生成） */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 数据来源（auto/manual/import） */
  _source?: string
  /** 是否异常 */
  is_abnormal?: string  // '是'/'否'
  /** 索引号 */
  ref_index?: string
  /** 动态字段（各区块列结构不同，存为扁平 key-value） */
  [key: string]: any
}

// ─── 区块类型枚举 ───────────────────────────────────────────────────────────

export type BlockType = 'block1' | 'block2' | 'block3' | 'block4'

export const BLOCK_LABELS: Record<BlockType, string> = {
  block1: '①合同负债检查-检查期后结转',
  block2: '②合同负债检查-形成期末余额的合同、订单、银行收款凭单等支持性证据检查',
  block3: '③销售检查-本期收款检查',
  block4: '④销售检查-本期出库的合同、出库单、运输单、验收单等支持性证据检查',
}

// ─── 抽样配置 ───────────────────────────────────────────────────────────────

export interface SamplingConfig {
  /** 测试范围 */
  test_scope?: string
  /** 特定样本 */
  specific_samples?: string
  /** 抽样总体 */
  sampling_population?: string
  /** 确定的抽样样本量 */
  sample_size?: string
  /** 抽样方法（随机选样/系统选样/货币单元抽样/随意选样） */
  sampling_method?: string
  /** 抽样过程 */
  sampling_process?: string
}

// ─── 余额汇总 ───────────────────────────────────────────────────────────────

export interface BalanceSummary {
  /** 函证项目名称 */
  item_name?: string
  /** 年初余额 */
  opening_balance?: number
  /** 借方发生额 */
  debit_amount?: number
  /** 贷方发生额 */
  credit_amount?: number
  /** 期末余额（自动或手填） */
  closing_balance?: number
  /** 本期销售金额 */
  sales_amount?: number
  /** 本期收款检查比例（自动：block3合计/sales_amount） */
  receipt_check_ratio?: number | null
  /** 本期出库检查比例（自动：block4合计/sales_amount） */
  shipment_check_ratio?: number | null
}

// ─── 审计结论 ───────────────────────────────────────────────────────────────

export interface AuditConclusion {
  /** 审计说明 */
  audit_note?: string
  /** 结论类型 A/B/C */
  conclusion_type?: 'A' | 'B' | 'C'
  /** 结论文本 */
  conclusion_text?: string
}

// ─── 单个公司（master-detail 中的 detail） ──────────────────────────────────

export interface AlternativeCompany {
  /** 公司内部 ID */
  _company_id?: string
  /** 序号 */
  seq?: number
  /** 供应商/客户名称 */
  entity_name?: string
  /** 函证索引号（来自 D0-1） */
  confirm_index?: string
  /** 数据来源（auto/manual） */
  _source?: string

  /** 抽样配置 */
  sampling?: SamplingConfig
  /** 余额汇总 */
  balance?: BalanceSummary

  /** 4 区块行数据 */
  block1_rows?: CheckRow[]
  block2_rows?: CheckRow[]
  block3_rows?: CheckRow[]
  block4_rows?: CheckRow[]

  /** 审计结论 */
  conclusion?: AuditConclusion
}

// ─── 看板指标 ───────────────────────────────────────────────────────────────

export interface AlternativeD05Metrics {
  /** 总公司数 */
  total_companies: number
  /** 已完成公司数（4 区块均有记录） */
  completed_companies: number
  /** 有异常公司数 */
  abnormal_companies: number
  /** 检查比例分布（各公司收款/出库比例） */
  ratio_distribution: Array<{
    entity_name: string
    receipt_ratio: number | null
    shipment_ratio: number | null
  }>
  /** 完成率 */
  completion_rate: number
}

// ─── 持久化 payload ─────────────────────────────────────────────────────────

export interface AlternativeD05Payload {
  /** 格式版本标识 */
  _format: 'alternative-d05-v1'
  /** 公司列表 */
  companies: AlternativeCompany[]
}
