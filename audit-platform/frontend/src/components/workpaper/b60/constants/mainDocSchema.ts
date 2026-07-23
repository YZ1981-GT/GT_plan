/**
 * B60 主底稿（总体审计策略及具体审计计划）结构化 schema
 *
 * 按源模板 docx 真实结构（15 章 / 38 表）忠实建模，取代原 26 章自由文本编辑器。
 * 关键：第七章 SCOT+ 路由表（Table 26/27）接 B50 风险 + 循环代码 + 程序索引 + B50 行号。
 *
 * 持久化：
 * - 普通 section → checklist_responses（主 B60 wp_id，item_id = B60-M-{sectionId}，remark=JSON）
 * - SCOT+ section（scot） → 复用 /api/projects/{pid}/b60/scot-rows 端点（wizard_state.b60_scot_rows）
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import type { B60Field, B60Column } from './subSheetSchemas'

export interface MainDocSection {
  id: string
  title: string
  hint?: string
  kind: 'fields' | 'questionnaire' | 'table'
  fields?: B60Field[]
  groups?: { label?: string; items: { key: string; label: string; type?: 'yesno' | 'yesnona' }[] }[]
  columns?: B60Column[]
  fixedRows?: Record<string, string>[]
  addable?: boolean
  rowLabel?: string
  /** 该 section 的 textarea 字段启用 🤖AI 辅助 */
  ai?: boolean
  /** 一键从 B50 带入：财报层次 / 认定层次 */
  b50Import?: 'fs' | 'assertion'
  /** SCOT+ 路由表（走 scot-rows 后端，非 checklist）：scot=Table26 / amount=Table27 */
  scot?: 'scot' | 'amount'
  /** 关联的下游/上游底稿编码（顶部显示 GtIndexChip） */
  refCodes?: string[]
}

const YESNO = 'yesno'
const YESNONA = 'yesnona'

export const B60_MAIN_SECTIONS: MainDocSection[] = [
  // ─── 责任人签名 ───
  {
    id: 'signatures',
    title: '责任人签名',
    kind: 'table',
    columns: [
      { key: 'role', label: '责任人', type: 'text', minWidth: 200 },
      { key: 'name', label: '姓名', type: 'text', minWidth: 140 },
      { key: 'sign', label: '签名（手签）', type: 'text', minWidth: 140 },
      { key: 'date', label: '日期', type: 'date', minWidth: 150 },
    ],
    fixedRows: [
      { role: '编制人：（项目负责经理）' },
      { role: '复核人：（项目合伙人）' },
      { role: '项目质量复核合伙人：（如适用）' },
      { role: '质量控制复核人：（如适用）' },
    ],
  },
  // ─── 业务特征与附件判断（T2，驱动子底稿适用性） ───
  {
    id: 'business-features',
    title: '业务特征与附件判断',
    hint: '本表判断决定须编制的附件子底稿（B60A~D / B60-2-* / B60-3）；与上方「适用性矩阵」一致。',
    kind: 'table',
    columns: [
      { key: 'item', label: '判断项', type: 'text', minWidth: 220 },
      { key: 'applicable', label: '是/否', type: 'yesno', minWidth: 90 },
      { key: 'attachment', label: '须编制附件', type: 'text', minWidth: 120 },
      { key: 'remark', label: '备注', type: 'text', minWidth: 140 },
    ],
    fixedRows: [
      { item: '整合审计', attachment: 'B60A' },
      { item: '仅内控审计', attachment: 'B60A' },
      { item: 'IPO / 申报财务报表审计', attachment: 'B60B' },
      { item: '国有企业年度财务报表审计', attachment: 'B60C' },
      { item: '需向证监局等报送审计计划', attachment: 'B60D' },
      { item: '适用 IT 审计（主稿三（六）任一勾选）', attachment: 'B60-2-1' },
      { item: '利用评估（或其他）专家', attachment: 'B60-3' },
      { item: '集团且利用组成部分注册会计师', attachment: 'B30' },
    ],
  },

  // ═══ 一、审计工作范围 ═══
  {
    id: 's1-engagement',
    title: '一、审计工作范围（一）委托事项',
    kind: 'fields',
    ai: true,
    fields: [
      { key: 'engagement', label: '委托事项', type: 'textarea', hint: '说明委托方、审计对象、审计期间及业务范围' },
    ],
  },
  {
    id: 's1-standards',
    title: '一（二）报告准则要求',
    kind: 'table',
    columns: [
      { key: 'item', label: '适用的准则或编制基础等', type: 'text', minWidth: 260 },
      { key: 'content', label: '具体内容', type: 'textarea', minWidth: 300 },
    ],
    fixedRows: [
      { item: '适用的财务报告编制基础' },
      { item: '与财务报告相关的行业特别规定' },
      { item: '适用的审计准则' },
      { item: '制定审计策略需考虑的其他事项' },
    ],
  },
  {
    id: 's1-reports',
    title: '一（三）报告时间要求',
    kind: 'table',
    columns: [
      { key: 'report', label: '拟出具的业务报告', type: 'text', minWidth: 320 },
      { key: 'time', label: '时间', type: 'text', minWidth: 160 },
    ],
    fixedRows: [
      { report: '202×年度财务报表审计报告' },
      { report: '202×年度控股股东及其他关联方占用资金情况的专项说明（如适用）' },
      { report: '202×年度内控制度鉴证报告（如适用）' },
      { report: '202×年度募集资金专项审核报告（如适用）' },
      { report: '202×年度营业收入扣除情况说明专项核查报告（如适用）' },
    ],
  },
  {
    id: 's1-components',
    title: '一（四）需单独出具审计报告的组成部分情况',
    kind: 'table',
    addable: true,
    rowLabel: '组成部分',
    columns: [
      { key: 'name', label: '组成部分名称', type: 'text', minWidth: 160 },
      { key: 'location', label: '注册地', type: 'text', minWidth: 120 },
      { key: 'relation', label: '与集团关系', type: 'text', minWidth: 120 },
      { key: 'cpa', label: '组成部分注册会计师', type: 'text', minWidth: 160 },
      { key: 'timing', label: '沟通初步时间安排', type: 'text', minWidth: 140 },
    ],
  },
  {
    id: 's1-prelim',
    title: '一（五）已开展的初步业务活动',
    kind: 'table',
    columns: [
      { key: 'proc', label: '初步业务活动程序', type: 'text', minWidth: 260 },
      { key: 'index', label: '索引号', type: 'text', minWidth: 140 },
    ],
    fixedRows: [
      { proc: '业务评价及风险评价' },
      { proc: '与前任注册会计师的沟通' },
      { proc: '独立性检查' },
      { proc: '已签订的业务约定书' },
    ],
  },

  // ═══ 二、被审计单位基本情况及本期重大变化 ═══
  {
    id: 's2-basic',
    title: '二、被审计单位基本情况及本期重大变化（一）基本情况',
    kind: 'table',
    columns: [
      { key: 'item', label: '要素', type: 'text', minWidth: 180 },
      { key: 'info', label: '经初步业务活动或以前年度审计了解的信息', type: 'textarea', minWidth: 320 },
    ],
    fixedRows: [
      { item: '所有权性质' }, { item: '母公司' }, { item: '实际控制人' },
      { item: '注册资本' }, { item: '经营范围' }, { item: '注册地址' }, { item: '办公地址' },
    ],
  },
  {
    id: 's2-listed',
    title: '二（一补充）上市公司相关情况（如适用）',
    kind: 'table',
    columns: [
      { key: 'item', label: '要素', type: 'text', minWidth: 220 },
      { key: 'info', label: '信息', type: 'textarea', minWidth: 320 },
    ],
    fixedRows: [
      { item: '上市日期' },
      { item: '上市后公司名称、控股股东和实际控制人的变化情况' },
      { item: '与现有主营业务相关的重大资产重组情况（业绩承诺、大额商誉等）' },
      { item: '证监会行业分类' },
    ],
  },
  {
    id: 's2-changes',
    title: '二（二）本期重大变化',
    kind: 'fields',
    ai: true,
    fields: [
      { key: 'changes', label: '本期重大变化说明', type: 'textarea', hint: '经营、组织结构、会计政策、重大交易等本期重大变化' },
    ],
  },
  {
    id: 's2-regulatory',
    title: '二（二）监管机构调查情况',
    kind: 'table',
    addable: true,
    rowLabel: '调查事项',
    columns: [
      { key: 'agency', label: '监管机构', type: 'text', minWidth: 140 },
      { key: 'matter', label: '调查事由', type: 'textarea', minWidth: 200 },
      { key: 'start', label: '开始调查时间', type: 'text', minWidth: 120 },
      { key: 'progress', label: '调查进展', type: 'textarea', minWidth: 180 },
      { key: 'impact', label: '对审计程序的影响', type: 'textarea', minWidth: 200 },
    ],
  },
]

// ═══ 三、审计安排 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's3-time',
    title: '三、审计安排（一）执行审计时间安排',
    kind: 'table',
    addable: true,
    rowLabel: '审计阶段',
    columns: [
      { key: 'stage', label: '执行审计阶段', type: 'text', minWidth: 240 },
      { key: 'plan', label: '初步时间计划', type: 'text', minWidth: 200 },
    ],
    fixedRows: [
      { stage: '审计计划阶段' }, { stage: '风险评估（现场了解与访谈）' },
      { stage: '控制测试（如适用）' }, { stage: '中期实质性程序（如适用）' },
      { stage: '存货监盘' }, { stage: '函证发出与回收' },
      { stage: '期末实质性程序' }, { stage: '期后事项审阅' },
      { stage: '审计报告与沟通' },
    ],
  },
  {
    id: 's3-team-core',
    title: '三（二）人员安排 — 项目组核心成员',
    kind: 'table',
    addable: true,
    rowLabel: '成员',
    columns: [
      { key: 'name', label: '姓名', type: 'text', minWidth: 120 },
      { key: 'level', label: '职级', type: 'text', minWidth: 120 },
      { key: 'role', label: '项目中角色', type: 'text', minWidth: 160 },
      { key: 'duty', label: '主要职责', type: 'textarea', minWidth: 220 },
    ],
  },
  {
    id: 's3-team-detail',
    title: '三（二）人员分工与时间安排',
    kind: 'table',
    addable: true,
    rowLabel: '成员',
    columns: [
      { key: 'name', label: '姓名', type: 'text', minWidth: 120 },
      { key: 'level', label: '职级', type: 'text', minWidth: 120 },
      { key: 'work', label: '工作分工', type: 'textarea', minWidth: 220 },
      { key: 'timing', label: '时间安排', type: 'text', minWidth: 160 },
    ],
  },
  {
    id: 's3-worktime',
    title: '三（三）审计项目工时预算与控制',
    kind: 'fields',
    refCodes: ['B60-1'],
    fields: [
      { key: 'note', label: '工时预算说明', type: 'textarea', hint: '详见 B60-1 审计项目工时预算与控制表' },
    ],
  },
  {
    id: 's3-expert',
    title: '三（四）利用注册会计师的专家',
    hint: '不适用时可留空。利用评估专家须编制 B60-3。',
    kind: 'table',
    addable: true,
    rowLabel: '专家',
    refCodes: ['B60-3'],
    columns: [
      { key: 'field', label: '利用专家的领域', type: 'text', minWidth: 140 },
      { key: 'name', label: '专家姓名或名称', type: 'text', minWidth: 140 },
      { key: 'scope', label: '主要职责及工作范围', type: 'textarea', minWidth: 200 },
      { key: 'reason', label: '利用专家工作的原因', type: 'textarea', minWidth: 180 },
      { key: 'source', label: '专家来源', type: 'select', options: ['内部', '外部'], minWidth: 100 },
      { key: 'remark', label: '备注', type: 'text', minWidth: 120 },
    ],
  },
  {
    id: 's3-internal-audit',
    title: '三（四）利用内部审计的工作',
    kind: 'table',
    columns: [
      { key: 'field', label: '主要利用领域', type: 'text', minWidth: 180 },
      { key: 'strategy', label: '利用内部审计的策略', type: 'textarea', minWidth: 200 },
      { key: 'content', label: '拟利用的内部审计工作内容', type: 'textarea', minWidth: 220 },
      { key: 'index', label: '索引号', type: 'text', minWidth: 100 },
    ],
    fixedRows: [
      { field: '对业务流程内控的测试' },
      { field: '了解业务流程的内部控制' },
      { field: '存货监盘程序' },
    ],
  },
  {
    id: 's3-other-cpa',
    title: '三（四）利用其他注册会计师的工作',
    kind: 'table',
    addable: true,
    rowLabel: '其他CPA',
    columns: [
      { key: 'name', label: '其他注册会计师名称', type: 'text', minWidth: 200 },
      { key: 'scope', label: '利用其工作的范围及程度', type: 'textarea', minWidth: 300 },
    ],
  },
  {
    id: 's3-service-org',
    title: '三（四）服务机构的考虑',
    kind: 'table',
    addable: true,
    rowLabel: '服务机构',
    columns: [
      { key: 'name', label: '服务机构名称', type: 'text', minWidth: 160 },
      { key: 'service', label: '提供的服务', type: 'textarea', minWidth: 180 },
      { key: 'cycle', label: '相关的循环', type: 'text', minWidth: 120 },
      { key: 'report', label: '服务机构CPA两类报告意见及日期', type: 'textarea', minWidth: 220 },
      { key: 'index', label: '索引号', type: 'text', minWidth: 100 },
    ],
  },
  {
    id: 's3-first-engagement',
    title: '三（五）对首次承接审计的考虑',
    kind: 'table',
    columns: [
      { key: 'item', label: '项目', type: 'text', minWidth: 240 },
      { key: 'executor', label: '执行人', type: 'text', minWidth: 120 },
      { key: 'timing', label: '拟执行时间', type: 'text', minWidth: 120 },
      { key: 'index', label: '索引号', type: 'text', minWidth: 100 },
    ],
    fixedRows: [
      { item: '就前期差错更正的沟通（如需要）' },
      { item: '与监管机构的沟通（如需要）' },
      { item: '期初余额审计' },
      { item: '本所质量控制制度规定的其他程序（如需要）' },
    ],
  },
  {
    id: 's3-it-consideration',
    title: '三（六）对被审计单位运用信息技术导致的风险的考虑',
    hint: '任一项判断为「是」→ 适用 IT 审计，须编制 B60-2-1 IT复杂性判断表 + B22A-4-1。',
    kind: 'questionnaire',
    refCodes: ['B60-2-1'],
    groups: [
      {
        items: [
          { key: 'ipo_integrated', label: 'IPO公司、上市公司整合审计（同时承接内控审计和财务报表审计）业务', type: YESNO },
          { key: 'complex_finance', label: '复杂金融企业的财务报表审计业务', type: YESNO },
          { key: 'internet', label: '互联网企业的财务报表审计业务（A/B类）', type: YESNO },
          { key: 'important_sub', label: '被认定为信息系统复杂的非本所上市公司客户的重要子公司', type: YESNO },
          { key: 'intl', label: '被认定为信息系统复杂的重要国际业务', type: YESNO },
          { key: 'other', label: '项目合伙人或项目外复核人员认为必要的其他业务', type: YESNO },
        ],
      },
    ],
  },
  {
    id: 's3-comm',
    title: '三（七）沟通的时间安排',
    kind: 'table',
    columns: [
      { key: 'matter', label: '沟通事项', type: 'text', minWidth: 220 },
      { key: 'people', label: '拟沟通的人员', type: 'text', minWidth: 140 },
      { key: 'content', label: '拟沟通的主要内容', type: 'textarea', minWidth: 200 },
      { key: 'owner', label: '负责沟通的项目组成员', type: 'text', minWidth: 140 },
      { key: 'timing', label: '计划沟通时间', type: 'text', minWidth: 120 },
    ],
    fixedRows: [
      { matter: '进场审计前，与独立董事（或审计委员会）的沟通' },
      { matter: '与管理层沟通' },
      { matter: '与治理层沟通' },
      { matter: '出具初步审计意见后，与独立董事（或审计委员会）的再次沟通' },
      { matter: '与审计委员会（或董事会）的沟通（出现需要沟通的情况时）' },
    ],
  },
  {
    id: 's3-reg-comm',
    title: '三（七）与监管机构的沟通',
    kind: 'table',
    columns: [
      { key: 'target', label: '沟通对象', type: 'text', minWidth: 160 },
      { key: 'content', label: '沟通事项或内容', type: 'textarea', minWidth: 200 },
      { key: 'method', label: '沟通方式', type: 'text', minWidth: 120 },
      { key: 'owner', label: '负责沟通的项目组成员', type: 'text', minWidth: 140 },
      { key: 'timing', label: '计划沟通时间', type: 'text', minWidth: 120 },
    ],
    fixedRows: [
      { target: '与所在地证监局的沟通' },
      { target: '与国资委的沟通' },
      { target: '与银保监管部门的沟通' },
    ],
  },
  {
    id: 's3-consult',
    title: '三（八）初步考虑拟执行业务咨询的事项',
    kind: 'table',
    addable: true,
    rowLabel: '咨询事项',
    columns: [
      { key: 'matter', label: '识别出的咨询事项', type: 'text', minWidth: 180 },
      { key: 'category', label: '咨询事项类别（会计/审计）', type: 'select', options: ['会计', '审计'], minWidth: 120 },
      { key: 'points', label: '咨询事项要点', type: 'textarea', minWidth: 220 },
      { key: 'timing', label: '拟咨询的时间', type: 'text', minWidth: 120 },
    ],
  },
)

// ═══ 四、未审财务报表的总体分析 ═══
B60_MAIN_SECTIONS.push({
  id: 's4-analysis',
  title: '四、未审财务报表的总体分析',
  kind: 'fields',
  ai: true,
  refCodes: ['B13'],
  fields: [
    { key: 'analysis', label: '未审财务报表横向、纵向分析', type: 'textarea', hint: '资产负债表/利润表主要项目横向纵向变动分析及异常关注；详见 B13 初步分析程序表' },
  ],
})

// ═══ 五、重要性水平的初步确定 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's5-materiality',
    title: '五、重要性水平的初步确定（一）初步确定重要性水平',
    hint: '计算过程见 B15；结论索引见 B19-1。',
    kind: 'table',
    refCodes: ['B15'],
    columns: [
      { key: 'item', label: '确定的重要性水平', type: 'text', minWidth: 240 },
      { key: 'current', label: '本期金额', type: 'text', minWidth: 160 },
      { key: 'prior', label: '上期金额', type: 'text', minWidth: 160 },
    ],
    fixedRows: [
      { item: '确定基准（如：税前利润、营业收入或资产总额）' },
      { item: '财务报表整体的重要性水平' },
      { item: '实际执行的重要性水平' },
      { item: '临界值（明显微小的错报）' },
    ],
  },
  {
    id: 's5-lower-mat',
    title: '五（二）为特定类别确定较低的重要性水平',
    kind: 'table',
    addable: true,
    rowLabel: '特定项目',
    columns: [
      { key: 'item', label: '交易、账户余额或披露', type: 'text', minWidth: 160 },
      { key: 'basis', label: '确定较低重要性的基准', type: 'textarea', minWidth: 180 },
      { key: 'reason', label: '选取较低重要性的原因', type: 'textarea', minWidth: 200 },
      { key: 'mat', label: '较低的重要性', type: 'text', minWidth: 120 },
      { key: 'pm', label: '较低的实际执行的重要性', type: 'text', minWidth: 140 },
    ],
    fixedRows: [
      { item: '关联交易' }, { item: '研发费用' }, { item: '信用减值损失' },
    ],
  },
)

// ═══ 六、识别的重大错报风险汇总 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's6-fs-risk',
    title: '六、识别的重大错报风险汇总（一）财务报表层次',
    hint: '可从 B50 一键带入财务报表层次风险（含舞弊风险）。',
    kind: 'table',
    addable: true,
    rowLabel: '风险因素',
    b50Import: 'fs',
    refCodes: ['B50'],
    columns: [
      { key: 'factor', label: '风险因素', type: 'text', minWidth: 160 },
      { key: 'desc', label: '风险描述', type: 'textarea', minWidth: 260 },
      { key: 'special', label: '是否属于特别风险', type: 'yesno', minWidth: 120 },
      { key: 'fraud', label: '是否与舞弊相关', type: 'yesno', minWidth: 120 },
    ],
  },
  {
    id: 's6-assertion-risk',
    title: '六（二）认定层次的重大错报风险汇总',
    hint: '可从 B50 一键带入认定层次风险。',
    kind: 'table',
    addable: true,
    rowLabel: '风险因素',
    b50Import: 'assertion',
    refCodes: ['B50'],
    columns: [
      { key: 'factor', label: '风险因素', type: 'text', minWidth: 140 },
      { key: 'desc', label: '风险描述', type: 'textarea', minWidth: 220 },
      { key: 'fsItem', label: '相关的财务报表项目或披露', type: 'text', minWidth: 160 },
      { key: 'assertion', label: '相关认定', type: 'text', minWidth: 120 },
      { key: 'special', label: '是否属于特别风险', type: 'yesno', minWidth: 110 },
      { key: 'fraud', label: '是否与舞弊相关', type: 'yesno', minWidth: 110 },
    ],
  },
)

// ═══ 七、相关交易类别、账户余额和披露及仅金额重大的项目（SCOT+ 路由，接 B50） ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's7-scot',
    title: '七、相关交易类别、账户余额和披露（SCOT+）',
    hint: '认定层次风险应对路由表：从 B50 带入科目→选综合性/实质性方案→填循环代码与程序底稿索引→关联 B50 风险行号。',
    kind: 'table',
    scot: 'scot',
    refCodes: ['B50'],
  },
  {
    id: 's7-amount',
    title: '七（二）仅金额重大的项目',
    hint: '仅金额重大（非风险驱动）的账户/交易/披露应对安排。',
    kind: 'table',
    scot: 'amount',
  },
)

// ═══ 八、对集团财务报表审计的特殊考虑 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's8-sig-components',
    title: '八、对集团财务报表审计的特殊考虑（一）重要组成部分',
    kind: 'table',
    addable: true,
    rowLabel: '重要组成部分',
    refCodes: ['B30'],
    columns: [
      { key: 'name', label: '重要组成部分', type: 'text', minWidth: 200 },
      { key: 'strategy', label: '审计策略', type: 'textarea', minWidth: 240 },
      { key: 'execution', label: '亲自执行/利用组成部分CPA工作', type: 'text', minWidth: 200 },
    ],
  },
  {
    id: 's8-insig-components',
    title: '八（二）不重要的组成部分',
    kind: 'table',
    addable: true,
    rowLabel: '不重要组成部分',
    columns: [
      { key: 'name', label: '不重要的组成部分', type: 'text', minWidth: 200 },
      { key: 'strategy', label: '审计策略', type: 'textarea', minWidth: 240 },
      { key: 'execution', label: '亲自执行/利用组成部分CPA工作', type: 'text', minWidth: 200 },
    ],
  },
  {
    id: 's8-comp-mat',
    title: '八（三）组成部分的重要性水平',
    kind: 'fields',
    fields: [
      { key: 'note', label: '组成部分重要性水平说明', type: 'textarea' },
    ],
  },
)

// ═══ 九、关键审计事项 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's9-kam',
    title: '九、关键审计事项（一）初步识别的关键审计事项',
    kind: 'table',
    addable: true,
    rowLabel: '关键审计事项',
    columns: [
      { key: 'kam', label: '识别为关键审计事项及其内容', type: 'textarea', minWidth: 240 },
      { key: 'basis', label: '识别为关键审计事项的判断依据', type: 'textarea', minWidth: 220 },
      { key: 'response', label: '计划采取的应对措施', type: 'textarea', minWidth: 220 },
    ],
  },
  {
    id: 's9-kam-comm',
    title: '九（二）关键审计事项的沟通',
    kind: 'table',
    addable: true,
    rowLabel: '沟通',
    columns: [
      { key: 'time', label: '沟通时间', type: 'text', minWidth: 120 },
      { key: 'kam', label: '沟通的关键审计事项', type: 'textarea', minWidth: 200 },
      { key: 'people', label: '参与沟通的被审计单位人员', type: 'text', minWidth: 160 },
      { key: 'index', label: '沟通函索引号', type: 'text', minWidth: 120 },
    ],
  },
)

// ═══ 十、对被审计单位持续经营的考虑 ═══
B60_MAIN_SECTIONS.push({
  id: 's10-going-concern',
  title: '十、对被审计单位持续经营的考虑',
  kind: 'table',
  addable: true,
  rowLabel: '事项',
  columns: [
    { key: 'matter', label: '对持续经营能力产生重大疑虑的事项或情况', type: 'textarea', minWidth: 300 },
    { key: 'response', label: '计划采取的应对措施', type: 'textarea', minWidth: 260 },
  ],
})

// ═══ 十一、对被审计单位适用法律法规的考虑 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's11-laws-fs',
    title: '十一、适用法律法规（一）对财务报表整体层面的影响',
    kind: 'table',
    columns: [
      { key: 'category', label: '风险类别', type: 'text', minWidth: 200 },
      { key: 'applicable', label: '是否适用', type: 'yesno', minWidth: 100 },
      { key: 'desc', label: '可能违法行为概述', type: 'textarea', minWidth: 240 },
      { key: 'response', label: '计划应对措施', type: 'textarea', minWidth: 240 },
    ],
    fixedRows: [
      { category: '管理层诚信和舞弊风险' },
      { category: '企业整体层面内部控制的缺陷' },
      { category: '持续经营的重大不确定性' },
    ],
  },
  {
    id: 's11-laws-assertion',
    title: '十一（二）对认定层次重大错报风险的影响',
    kind: 'table',
    addable: true,
    rowLabel: '相关领域',
    columns: [
      { key: 'area', label: '相关领域', type: 'text', minWidth: 200 },
      { key: 'applicable', label: '是否适用', type: 'yesno', minWidth: 100 },
      { key: 'impact', label: '对财务报表的影响', type: 'textarea', minWidth: 220 },
      { key: 'response', label: '计划应对措施', type: 'textarea', minWidth: 220 },
    ],
    fixedRows: [
      { area: '对经营范围的限定' }, { area: '环保相关的法律法规' },
      { area: '产品质量标准的规定' }, { area: '网络安全法规对产品提供内容的规定' },
      { area: '安全生产相关规定' }, { area: '税收相关法规' },
      { area: '劳动法等法规关于就业平等、社保缴纳的规定' },
      { area: '对监管指标的规定' }, { area: '反垄断法律法规' }, { area: '反洗钱法律法规' },
    ],
  },
)

// ═══ 十二、重大会计实务、职业判断及应对措施 ═══
B60_MAIN_SECTIONS.push({
  id: 's12-accounting',
  title: '十二、重大会计实务、职业判断及应对措施',
  kind: 'table',
  columns: [
    { key: 'category', label: '风险类别', type: 'text', minWidth: 180 },
    { key: 'matter', label: '事项描述', type: 'textarea', minWidth: 240 },
    { key: 'account', label: '相关账户余额和披露', type: 'text', minWidth: 160 },
    { key: 'response', label: '应对措施', type: 'textarea', minWidth: 220 },
  ],
  fixedRows: [
    { category: '财务报表层次的重大错报风险' },
    { category: '认定层次的重大错报风险' },
    { category: '仅金额重大的项目' },
  ],
})

// ═══ 十三、其他信息 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's13-other-info',
    title: '十三、其他信息（一）范围及计划公告时间',
    kind: 'fields',
    fields: [
      { key: 'scope', label: '其他信息的范围及计划公告的时间', type: 'textarea' },
    ],
  },
  {
    id: 's13-other-info-read',
    title: '十三（二）阅读其他信息的安排',
    kind: 'fields',
    fields: [
      { key: 'arrangement', label: '阅读其他信息的安排（时间计划、人员安排）', type: 'textarea' },
    ],
  },
)

// ═══ 十四、其他需要考虑的事项 ═══
B60_MAIN_SECTIONS.push({
  id: 's14-other',
  title: '十四、其他需要考虑的事项',
  kind: 'table',
  addable: true,
  rowLabel: '审计程序',
  columns: [
    { key: 'proc', label: '审计程序', type: 'textarea', minWidth: 280 },
    { key: 'executor', label: '执行人', type: 'text', minWidth: 120 },
    { key: 'timing', label: '初步计划执行的时间', type: 'text', minWidth: 140 },
  ],
  fixedRows: [
    { proc: '集团注册会计师的指示' },
    { proc: '其他事项……' },
  ],
})

// ═══ 十五、对审计计划的更新和修改 ═══
B60_MAIN_SECTIONS.push(
  {
    id: 's15-scot-recheck',
    title: '十五、对审计计划的更新和修改（一）对SCOT+完整性的再评估',
    kind: 'table',
    addable: true,
    rowLabel: 'SCOT+',
    columns: [
      { key: 'name', label: '交易、账户余额或披露名称', type: 'text', minWidth: 220 },
      { key: 'reason', label: '重新识别为SCOT+的判断理由', type: 'textarea', minWidth: 300 },
    ],
  },
  {
    id: 's15-plan-revision',
    title: '十五（二）其他对审计计划的修改',
    hint: '重大修改须在「适用性矩阵」面板递增计划版本（confirm_major_change + reason）。',
    kind: 'table',
    addable: true,
    rowLabel: '修改轮次',
    columns: [
      { key: 'round', label: '修改轮次', type: 'text', minWidth: 120 },
      { key: 'time', label: '修改时间', type: 'text', minWidth: 120 },
      { key: 'original', label: '原计划或安排', type: 'textarea', minWidth: 200 },
      { key: 'change', label: '更新和修改情况', type: 'textarea', minWidth: 200 },
      { key: 'reason', label: '更新和修改理由', type: 'textarea', minWidth: 180 },
      { key: 'after', label: '修改后的安排或实施的程序', type: 'textarea', minWidth: 200 },
    ],
    fixedRows: [
      { round: '第一次修改' },
      { round: '第二次修改' },
    ],
  },
)
