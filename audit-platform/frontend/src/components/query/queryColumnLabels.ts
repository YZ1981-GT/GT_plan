/**
 * 高级查询列标签单一真源（advanced-query-consolidation Req1）
 *
 * 收敛自 CustomQueryDialog 内联 COLUMN_LABELS，补齐高级构建器/CustomQueryTab 常见列。
 * CustomQueryDialog / CustomQueryTab / AdvancedQueryBuilder 三方共用，消除硬编码孤本，
 * 并让 Tab/Builder 从此显示中文列名（此前显示后端英文 key）。
 *
 * 后端 execute 的 columns 仍为英文 string[]（不改契约）；中文标签属纯前端展示层。
 */

/** 列 key → 中文标签（单一真源） */
export const QUERY_COLUMN_LABELS: Record<string, string> = {
  // 报表 / 行次
  row_code: '行次', row_name: '项目', current_period_amount: '本期金额', prior_period_amount: '上期金额',
  report_type: '报表类型', applicable_standard: '适用准则', indent_level: '层级', is_total_row: '合计行', formula: '公式',
  // 试算 / 科目余额 / 序时账
  account_code: '科目编码', account_name: '科目名称', standard_account_code: '标准科目编码',
  opening_balance: '期初余额', closing_balance: '期末余额', debit_amount: '借方发生额', credit_amount: '贷方发生额',
  unadjusted: '未审数', audited: '审定数', unadjusted_amount: '未审数', aje_adjustment: '审计调整', audited_amount: '审定数',
  aje_dr: 'AJE借', aje_cr: 'AJE贷', rcl_dr: 'RCL借', rcl_cr: 'RCL贷',
  voucher_date: '凭证日期', voucher_no: '凭证号',
  // 调整分录
  entry_number: '分录号', adjustment_no: '分录号', description: '说明', review_status: '复核状态',
  // 附注
  section_id: '章节ID', note_section: '附注章节', section_title: '章节标题', table_name: '表名', headers: '表头',
  // 合并 / 工作底稿
  company_name: '企业名称', company_code: '企业代码', holding_type: '持股类型', non_common_ratio: '持股比例',
  direction: '借贷', subject: '科目', amount: '金额', desc: '说明', summary: '审定汇总',
  equity_dr: '权益抵消借', equity_cr: '权益抵消贷',
  // 底稿单元格 / 通用
  wp_code: '底稿编码', wp_name: '底稿名称', audit_cycle: '审计循环', sheet_name: 'sheet 名',
  cell_ref: '单元格', index: '序号', value: '值', status: '状态',
  indent: '层级', is_total: '合计行', row_count: '行数',
  // 工时
  work_date: '工作日期', hours: '工时', staff_id: '人员',
}

/**
 * 列标签三级兜底：共享映射 → 后端下发的 title（若存在且 ≠ key）→ key 原样。
 * @param key 列 key（英文）
 * @param title 后端 ColumnMeta.title（当前 execute 返回 string[] 时无此值）
 */
export function resolveColumnLabel(key: string, title?: string): string {
  if (!key) return title || ''
  const mapped = QUERY_COLUMN_LABELS[key]
  if (mapped) return mapped
  if (title && title !== key) return title
  return key
}
