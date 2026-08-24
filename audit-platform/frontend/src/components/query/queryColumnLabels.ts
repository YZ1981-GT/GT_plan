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
  // 2026-08-23 浏览器实测补：构建器默认列集里这三列仍显示英文（UI 全中文化缺口）
  account_category: '科目类别', rje_adjustment: '重分类调整', currency_code: '币种',
  aje_dr: 'AJE借', aje_cr: 'AJE贷', rcl_dr: 'RCL借', rcl_cr: 'RCL贷',
  voucher_date: '凭证日期', voucher_no: '凭证号',
  // 序时账 / 科目表补充
  accounting_period: '会计期间', voucher_type: '凭证类型', entry_seq: '分录序号',
  parent_code: '上级科目', level: '科目级次', category: '类别', source: '来源',
  year: '年度',
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
  start_time: '开始时间', end_time: '结束时间', purpose: '用途', ai_suggested: 'AI 建议',
  // ── 2026-08-23 补齐：以下键由守卫
  // `TestDefaultColumnsHaveChineseLabels` 强制（白名单默认列集必须全部有中文），
  // 缺映射时结果表会混排英文列名（UI 全中文化铁律）。
  // 调整分录
  adjustment_type: '调整类型',
  // 附注
  content_type: '内容类型', source_template: '源模板', sort_order: '排序号', is_stale: '需更新',
  // 重要性水平
  benchmark_type: '基准类型', benchmark_amount: '基准金额',
  overall_percentage: '整体重要性比例', overall_materiality: '整体重要性',
  performance_ratio: '实际执行比例', performance_materiality: '实际执行的重要性',
  trivial_ratio: '明显微小比例', trivial_threshold: '明显微小错报临界值',
  is_override: '手工覆盖',
  // 项目（name 为全局键，取通用「名称」以兼容多表）
  name: '名称', client_name: '客户名称',
  audit_period_start: '审计期间起', audit_period_end: '审计期间止',
  project_type: '项目类型', scenario: '业务场景',
  template_type: '模板类型', report_scope: '报表范围',
  manager_id: '项目经理', partner_id: '合伙人',
  parent_company_name: '母公司名称', parent_company_code: '母公司代码',
  ultimate_company_name: '最终控制方名称', ultimate_company_code: '最终控制方代码',
  consol_level: '合并层级', risk_level: '风险等级',
  budget_hours: '预算工时', contract_amount: '合同金额', archived_at: '归档时间',
  // 报表行次配置 / 映射
  row_number: '行号', parent_row_code: '上级行次',
  formula_category: '公式分类', formula_description: '公式说明', formula_source: '公式来源',
  report_line_code: '报表行次编码', report_line_name: '报表行次名称',
  report_line_level: '行次层级', parent_line_code: '上级行次编码',
  mapping_type: '映射类型', is_confirmed: '已确认',
  // 人员档案
  employee_no: '员工编号', department: '部门', title: '职称',
  role_level: '角色级别', specialty: '专长', join_date: '入职日期',
  partner_name: '合伙人姓名',
  // 未更正错报
  misstatement_description: '错报描述', misstatement_amount: '错报金额',
  misstatement_type: '错报类型',
  affected_account_code: '影响科目编码', affected_account_name: '影响科目名称',
  management_reason: '管理层未调整理由', auditor_evaluation: '审计师评价',
  // 底稿文件 / 索引
  wp_index_id: '底稿索引', file_path: '文件路径', source_type: '来源类型',
  file_version: '文件版本', assigned_to: '负责人', reviewer: '复核人',
  workflow_status: '流程状态', explanation_status: '说明状态',
  consistency_status: '一致性状态',
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
