/**
 * B60 子底稿结构化 schema —— 按源模板 docx 真实结构定义
 *
 * 覆盖问卷/表格型子底稿：B60-2-1 / B60-3 / B60A / B60B / B60C / B60D
 * （B60-2-2 IT进场前通知表 / B60-2-3 IT审计计划备忘录 结构复杂，暂保留 OnlyOffice-only）
 *
 * 持久化：每个 section 打包为一条 checklist_responses（item_id = {code}-{sectionId}，remark=JSON）
 *
 * Spec: b60-strategy-rework（直接修复）
 */

export type B60FieldType = 'text' | 'textarea' | 'date' | 'yesno' | 'yesnona' | 'select'

export interface B60Field {
  key: string
  label: string
  type: B60FieldType
  options?: string[]
  hint?: string
}

export interface B60Column {
  key: string
  label: string
  type?: 'text' | 'textarea' | 'yesno' | 'yesnona' | 'select' | 'date'
  options?: string[]
  minWidth?: number
}

export interface B60QuestionItem {
  key: string
  label: string
  type?: 'yesno' | 'yesnona'
}

export interface B60QuestionGroup {
  label?: string
  items: B60QuestionItem[]
}

export interface B60Section {
  id: string
  title: string
  /** 编制提示（琥珀块） */
  hint?: string
  kind: 'fields' | 'questionnaire' | 'table'
  /** kind=fields */
  fields?: B60Field[]
  /** kind=questionnaire */
  groups?: B60QuestionGroup[]
  /** kind=table */
  columns?: B60Column[]
  /** 固定预置行（首次加载时按此 seed，键对齐 columns.key） */
  fixedRows?: Record<string, string>[]
  /** 是否允许新增行 */
  addable?: boolean
  /** 新增行提示名 */
  rowLabel?: string
}

export interface B60SubSheetSchema {
  code: string
  title: string
  sections: B60Section[]
}

const YESNO = 'yesno'
const YESNONA = 'yesnona'

export const B60_SUBSHEET_SCHEMAS: Record<string, B60SubSheetSchema> = {
  // ─── B60-2-1 IT复杂性判断表 ───────────────────────────────────────────
  'B60-2-1': {
    code: 'B60-2-1',
    title: 'IT复杂性判断表',
    sections: [
      {
        id: 'applicability',
        title: '（一）是否适用 IT 审计的判断',
        hint:
          '结论须与 B60 第三章（六）IT 适用勾选一致；任一情况判断为「是」，须继续填写《B22A-4-1 IT概要》及下方（二）测试范围。' +
          '第三项判断详见《审计指引第42号-信息系统审计（2024年修订）》。',
        kind: 'questionnaire',
        groups: [
          {
            label: '一、必须执行 IT 审计的审计业务',
            items: [
              { key: 'ipo_listed', label: '1、IPO公司、上市公司整合审计业务', type: YESNO },
              { key: 'complex_finance', label: '2、复杂金融企业的财务报表审计业务（银行/保险/证券等，或合并报表中该类子公司收入或毛利占比>30%）', type: YESNO },
              { key: 'internet', label: '3、互联网企业的财务报表审计业务（A/B类，互联网收入或毛利占比>30%，或互联网业务净利润>50%）', type: YESNO },
            ],
          },
          {
            label: '二、被审计单位信息系统复杂的下列审计业务',
            items: [
              { key: 'bond_reits', label: '1、发行债券、新三板（含挂牌）、拟重大资产重组标的资产、基础设施公募REITs 的财务报表审计业务', type: YESNO },
              { key: 'important_sub', label: '2、非本所上市公司客户的重要子公司财务报表审计业务', type: YESNO },
              { key: 'intl', label: '3、重要国际业务', type: YESNO },
              { key: 'chain', label: '4、B类业务中被审计单位为超市、酒店、零售等连锁经营类企业的财务报表审计业务', type: YESNO },
            ],
          },
          {
            label: '三、其他',
            items: [
              { key: 'other_necessary', label: '项目合伙人或项目外复核人员认为必要进行 IT 审计的其他审计业务', type: YESNO },
            ],
          },
        ],
      },
      {
        id: 'scope',
        title: '（二）IT 审计测试范围（IT应用程序或基础设施清单）',
        hint:
          '需测试的系统范围应主要根据对财务报表的影响确定，除业务/财务系统外，一般应包括资金、清算、库存管理、成本分摊等相关应用。' +
          '本表为汇总内容，应与《B22A-4-1 IT概要》保持一致。',
        kind: 'table',
        addable: true,
        rowLabel: 'IT应用程序',
        columns: [
          { key: 'no', label: '编号', type: 'text', minWidth: 70 },
          { key: 'app', label: 'IT应用程序或基础设施', type: 'text', minWidth: 200 },
          { key: 'process', label: '涉及的重大业务流程', type: 'text', minWidth: 200 },
          { key: 'complexity', label: '复杂性', type: 'select', options: ['不复杂', '中等复杂', '复杂'], minWidth: 120 },
          { key: 'remark', label: '备注', type: 'textarea', minWidth: 160 },
        ],
      },
    ],
  },

  // ─── B60-3 评估专家工作计划 ───────────────────────────────────────────
  'B60-3': {
    code: 'B60-3',
    title: '评估专家工作计划',
    sections: [
      {
        id: 'basic',
        title: '一、基本信息',
        hint: '本模板以资产评估专家为主；税务/法律/精算等专家可复用本结构，注明专家类型。B60 三（四）利用评估专家时编制。',
        kind: 'fields',
        fields: [
          { key: 'date', label: '日期', type: 'date' },
          { key: 'to', label: '致', type: 'text' },
          { key: 'from', label: '发自', type: 'text' },
          { key: 'project', label: '项目名称', type: 'text' },
        ],
      },
      {
        id: 'expert_type',
        title: '二、专家类型（领域）',
        kind: 'questionnaire',
        groups: [
          {
            items: [
              { key: 'valuation', label: '资产评估 / 估值 / 减值（本模板默认）', type: YESNO },
              { key: 'tax', label: '税务', type: YESNO },
              { key: 'legal', label: '法律', type: YESNO },
              { key: 'actuary', label: '精算 / 其他（注明具体领域）', type: YESNO },
            ],
          },
        ],
      },
      {
        id: 'team',
        title: '三、专家团队角色',
        kind: 'table',
        columns: [
          { key: 'role', label: '角色', type: 'text', minWidth: 160 },
          { key: 'name', label: '姓名', type: 'text', minWidth: 200 },
        ],
        fixedRows: [
          { role: '合伙人/总监' }, { role: '高级经理' }, { role: '经理' },
          { role: '高级评估师' }, { role: '评估师' },
        ],
      },
      {
        id: 'plan',
        title: '四、工作计划',
        kind: 'fields',
        fields: [
          { key: 'purpose', label: '目的', type: 'textarea', hint: '概述与评估/专项事项有关的程序，作为总体审计策略的补充' },
          { key: 'background', label: '客户背景信息', type: 'textarea' },
          { key: 'scope', label: '利用专家工作的范围', type: 'textarea' },
          { key: 'timing', label: '时间安排', type: 'textarea' },
          { key: 'competence', label: '对专家能力、客观性和独立性的评价安排', type: 'textarea' },
        ],
      },
    ],
  },

  // ─── B60A 对内控审计的特殊考虑 ────────────────────────────────────────
  'B60A': {
    code: 'B60A',
    title: '对内控审计的特殊考虑',
    sections: [
      {
        id: 'basic',
        title: '一、基本信息',
        hint: '仅当 B60 适用性矩阵勾选整合审计/仅内控审计时编制。若仅承接内控审计，总体策略中与关键审计事项、其他信息、持续经营等相关内容可标注为「不适用」。',
        kind: 'fields',
        fields: [
          { key: 'base_date', label: '内控审计基准日', type: 'date' },
          { key: 'opinion_object', label: '意见对象', type: 'text', hint: '财务报告内部控制有效性' },
          { key: 'non_fin_defect', label: '非财务报告重大缺陷', type: 'text' },
          { key: 'integrated', label: '是否与财报审计整合执行', type: YESNO },
        ],
      },
      {
        id: 'entity_control',
        title: '二、企业层面控制识别出的相关风险因素',
        hint: '可从控制环境、管理层/治理层凌驾风险、风险评估过程、内部信息传递、内部监督、期末财务报告流程等方面描述。',
        kind: 'fields',
        fields: [
          { key: 'risk_factors', label: '识别出的相关风险因素', type: 'textarea' },
          { key: 'audit_impact', label: '对审计的影响', type: 'textarea' },
        ],
      },
      {
        id: 'it_consideration',
        title: '三、对企业利用信息技术的考虑',
        kind: 'fields',
        fields: [
          { key: 'it_info', label: '关于企业利用信息技术的信息', type: 'textarea' },
          { key: 'itgc_conclusion', label: '关于信息技术一般控制有效性的初步结论', type: 'textarea' },
        ],
      },
      {
        id: 'it_arrangement',
        title: '四、IT 结论与安排',
        kind: 'table',
        columns: [
          { key: 'item', label: '项目', type: 'text', minWidth: 240 },
          { key: 'conclusion', label: '结论/安排', type: 'textarea', minWidth: 220 },
          { key: 'index', label: '索引', type: 'text', minWidth: 120 },
        ],
        fixedRows: [
          { item: '是否适用 IT 审计（见 B60-2-1）', index: 'B60-2-1' },
          { item: 'ITGC/ITAC 对财务报告内控有效性的初步影响', index: 'B60-2-3 / B22A' },
          { item: '已知 IT 缺陷（如有）及对 ICFR 意见影响', index: '' },
        ],
      },
      {
        id: 'checklist',
        title: '五、管理层自评利用检查',
        kind: 'questionnaire',
        groups: [
          {
            items: [
              { key: 'got_self_eval', label: '已获取管理层内部控制自我评价报告', type: YESNONA },
              { key: 'elements_complete', label: '评价报告要素完整（按评价指引）', type: YESNONA },
              { key: 'defect_standard', label: '董事会缺陷评价标准符合《企业内部控制评价指引》', type: YESNONA },
              { key: 'consistent', label: '企审双方对重大缺陷结论是否一致', type: YESNONA },
              { key: 'inconsistent_impact', label: '不一致时对内控审计意见类型/报告内容的影响', type: YESNONA },
            ],
          },
        ],
      },
      {
        id: 'account_control',
        title: '六、重要账户与业务层控制范围',
        kind: 'table',
        addable: true,
        rowLabel: '重要账户',
        columns: [
          { key: 'account', label: '重要账户或披露', type: 'text', minWidth: 160 },
          { key: 'assertion', label: '相关认定', type: 'text', minWidth: 140 },
          { key: 'control', label: '拟测试的关键控制（简述）', type: 'textarea', minWidth: 220 },
          { key: 'index', label: '底稿索引', type: 'text', minWidth: 120 },
          { key: 'remark', label: '备注', type: 'text', minWidth: 120 },
        ],
      },
      {
        id: 'scope_diff',
        title: '七、与财报审计范围差异',
        kind: 'table',
        columns: [
          { key: 'item', label: '事项', type: 'text', minWidth: 180 },
          { key: 'has_diff', label: '是否存在差异', type: 'yesno', minWidth: 120 },
          { key: 'diff_desc', label: '差异说明', type: 'textarea', minWidth: 200 },
          { key: 'impact', label: '对程序/证据的影响', type: 'textarea', minWidth: 200 },
        ],
        fixedRows: [
          { item: '重要账户与披露范围' },
          { item: '业务层面控制测试范围' },
          { item: 'IT 一般控制/应用控制范围' },
          { item: '基准日与报告涵盖期间' },
          { item: '其他' },
        ],
      },
    ],
  },

  // ─── B60B 对IPO申报财务报表审计的特殊考虑 ─────────────────────────────
  'B60B': {
    code: 'B60B',
    title: '对IPO申报财务报表审计的特殊考虑',
    sections: [
      {
        id: 'reports',
        title: '一、其他鉴证结论或专项说明',
        hint: '并非每项都适用，项目组需根据业务约定书的委托范围确定需要出具报告或专项说明的内容。',
        kind: 'table',
        addable: true,
        rowLabel: '报告内容',
        columns: [
          { key: 'content', label: '报告内容', type: 'text', minWidth: 240 },
          { key: 'timing', label: '预计出具时间', type: 'text', minWidth: 140 },
          { key: 'applicable', label: '是否适用', type: 'yesno', minWidth: 100 },
        ],
      },
      {
        id: 'meeting',
        title: '二、时间安排的补充计划（中介协调会/技委会）',
        hint: '技委会资料应在预期审议日前至少三个工作日提交联络委员。',
        kind: 'table',
        addable: true,
        columns: [
          { key: 'stage', label: '审计工作阶段', type: 'text', minWidth: 180 },
          { key: 'timing', label: '预期时间', type: 'text', minWidth: 140 },
          { key: 'attendees', label: '计划参会人员', type: 'text', minWidth: 180 },
        ],
      },
      {
        id: 'extended_check',
        title: '三、延伸检查程序安排',
        kind: 'table',
        addable: true,
        columns: [
          { key: 'area', label: '延伸检查相关的领域或业务流程', type: 'text', minWidth: 220 },
          { key: 'category', label: '延伸检查类别', type: 'text', minWidth: 140 },
          { key: 'timing', label: '延伸检查时间', type: 'text', minWidth: 120 },
          { key: 'index', label: '底稿索引(S32/S33/S34)', type: 'text', minWidth: 160 },
        ],
      },
      {
        id: 'person_check',
        title: '四、首发专项人员核查',
        kind: 'table',
        addable: true,
        columns: [
          { key: 'scope', label: '拟核查的人员范围', type: 'text', minWidth: 180 },
          { key: 'focus', label: '重点关注内容', type: 'textarea', minWidth: 200 },
          { key: 'timing', label: '拟核查的时间', type: 'text', minWidth: 120 },
          { key: 'owner', label: '负责人/协调人', type: 'text', minWidth: 140 },
          { key: 'index', label: '底稿索引(S33)', type: 'text', minWidth: 120 },
        ],
      },
      {
        id: 'content_check',
        title: '五、首发专项内容核查',
        kind: 'table',
        addable: true,
        columns: [
          { key: 'content', label: '核查内容', type: 'text', minWidth: 200 },
          { key: 'timing', label: '拟核查的时间', type: 'text', minWidth: 120 },
          { key: 'account', label: '相关账户、交易或披露', type: 'text', minWidth: 200 },
          { key: 'index', label: '底稿索引(S32/S34)', type: 'text', minWidth: 140 },
        ],
      },
    ],
  },

  // ─── B60C 对国有企业年度财务报表审计的特殊考虑 ────────────────────────
  'B60C': {
    code: 'B60C',
    title: '对国有企业年度财务报表审计的特殊考虑',
    sections: [
      {
        id: 'reports',
        title: '一、其他鉴证结论或专项说明',
        hint: '并非每项都适用，项目组需根据业务约定书的委托范围确定需要出具报告或专项说明的内容。',
        kind: 'table',
        addable: true,
        rowLabel: '报告内容',
        columns: [
          { key: 'content', label: '报告内容', type: 'text', minWidth: 260 },
          { key: 'timing', label: '预计出具时间', type: 'text', minWidth: 160 },
        ],
        fixedRows: [
          { content: '财务决算专项说明审计报告' },
          { content: '内部控制审计报告或审核报告' },
          { content: '管理建议书' },
          { content: '审计情况说明' },
          { content: '财务总监履职评价报告' },
          { content: '资产减值准备核销专项审核报告' },
          { content: '金融衍生业务专项审核报告' },
          { content: '研究开发费用结构明细表的审计报告' },
        ],
      },
      {
        id: 'trigger',
        title: '二、国资沟通触发条件',
        hint: '出现任一「是」须安排与国资委沟通并填写沟通时间计划。',
        kind: 'table',
        columns: [
          { key: 'trigger', label: '触发情形', type: 'text', minWidth: 240 },
          { key: 'yesno', label: '是/否', type: 'yesno', minWidth: 90 },
          { key: 'timing', label: '计划沟通时点', type: 'text', minWidth: 140 },
          { key: 'attendees', label: '参与人', type: 'text', minWidth: 140 },
        ],
        fixedRows: [
          { trigger: '与管理层存在重大分歧' },
          { trigger: '主审所与参审所之间存在重大分歧' },
          { trigger: '影响审计意见类型或报告要素的重大事项' },
          { trigger: '审计范围受限或其他重大困难' },
          { trigger: '对审计计划的重大修改' },
          { trigger: '其他重大审计/会计/内控或违法事项' },
        ],
      },
      {
        id: 'communication',
        title: '三、与监管机构沟通的时间计划',
        kind: 'table',
        columns: [
          { key: 'stage', label: '审计工作阶段', type: 'text', minWidth: 160 },
          { key: 'timing', label: '预计沟通时间', type: 'text', minWidth: 140 },
          { key: 'attendees', label: '计划参与沟通人员', type: 'text', minWidth: 180 },
        ],
        fixedRows: [
          { stage: '审计计划阶段' }, { stage: '审计实施阶段' }, { stage: '报告阶段' },
        ],
      },
      {
        id: 'risk_response',
        title: '四、重点领域风险与应对',
        hint: '按「问题—账户—总体应对—程序索引」填写。',
        kind: 'table',
        addable: true,
        rowLabel: '风险/问题',
        columns: [
          { key: 'risk', label: '风险/问题', type: 'text', minWidth: 200 },
          { key: 'account', label: '相关账户、交易或披露', type: 'textarea', minWidth: 200 },
          { key: 'response', label: '拟采取的总体应对措施', type: 'textarea', minWidth: 220 },
          { key: 'index', label: '拟执行程序索引', type: 'text', minWidth: 130 },
        ],
        fixedRows: [
          { risk: '融资性贸易的相关收入' },
          { risk: 'BT、BOT等模式承接的地方政府公益性项目' },
          { risk: '重大投资、并购损失' },
          { risk: '成本费用列支（或潜亏挂账）' },
          { risk: '内部关联交易抵消不充分' },
          { risk: '境外业务管理、境外项目风险' },
          { risk: '担保事项' },
          { risk: '重大诉讼或监管调查事项' },
          { risk: '贪污、挪用企业资金事项' },
          { risk: '"小金库"等内控、合规问题' },
        ],
      },
    ],
  },

  // ─── B60D 向监管机构报送 ──────────────────────────────────────────────
  'B60D': {
    code: 'B60D',
    title: '向监管机构报送总体审计策略和具体审计计划',
    sections: [
      {
        id: 'filing',
        title: '报送存档信息（副本归档必填）',
        hint:
          '报送审计计划的函、审计计划（内容来源于总体审计策略）应作为审计工作底稿存档，索引号统一为 B60D。' +
          '项目组应确保报送内容与底稿相关内容一致，并以书面形式向证监局相关人员报送，项目合伙人签字（无须加盖本所章）。',
        kind: 'fields',
        fields: [
          { key: 'reach_date', label: '致达日期', type: 'date' },
          { key: 'recipient', label: '收件人（监管机构及人员）', type: 'text' },
          { key: 'method', label: '报送方式', type: 'select', options: ['当面', '邮寄', '系统'] },
          { key: 'b60_version', label: '对应 B60 版本日期', type: 'date' },
          { key: 'consistent', label: '是否与 B60 正文一致', type: 'yesno', hint: '否须说明' },
          { key: 'follow_up', label: '后续重大更新是否补充报送', type: 'yesnona' },
          { key: 'note', label: '备注/差异说明', type: 'textarea' },
        ],
      },
    ],
  },

  // ─── B60-2-2 IT审计进场前通知表 ───────────────────────────────────────
  'B60-2-2': {
    code: 'B60-2-2',
    title: 'IT审计进场前通知表',
    sections: [
      {
        id: 'basic',
        title: '一、项目基本信息',
        hint: 'IT 团队执行测试时编制；工时预算须与 B60-1 工时表、B60-2-3 计划备忘录保持一致。',
        kind: 'fields',
        fields: [
          { key: 'it_project_no', label: 'IT审计项目编号（如适用）', type: 'text' },
          { key: 'entrust_unit', label: '委托单位（部门/办公室/外部客户）', type: 'text' },
          { key: 'entity_name', label: '被审计单位名称（全称）', type: 'text' },
          { key: 'subsidiaries', label: '下属子公司', type: 'textarea' },
          { key: 'industry', label: '被审计单位所属行业', type: 'text' },
          { key: 'site_address', label: 'IT审计现场地址', type: 'text' },
          { key: 'period', label: '审计期间', type: 'text' },
          { key: 'report_time', label: '拟出具年审报告时间', type: 'text' },
        ],
      },
      {
        id: 'budget',
        title: '二、工时与费用预算',
        hint: '工时预算须与 B60-1、B60-2-3 一致。',
        kind: 'fields',
        fields: [
          { key: 'onsite_time', label: '期望IT审计进场-离场时间', type: 'text' },
          { key: 'consultant_hours', label: 'IT团队顾问工时预算', type: 'text' },
          { key: 'consultant_rate', label: '顾问工时费率', type: 'text' },
          { key: 'manager_hours', label: 'IT团队经理工时预算', type: 'text' },
          { key: 'manager_rate', label: '经理工时费率', type: 'text' },
          { key: 'director_hours', label: 'IT团队总监工时预算', type: 'text' },
          { key: 'director_rate', label: '总监工时费率', type: 'text' },
          { key: 'partner_hours', label: 'IT团队合伙人工时预算', type: 'text' },
          { key: 'partner_rate', label: '合伙人工时费率', type: 'text' },
          { key: 'total_hours', label: '工时预算合计', type: 'text' },
          { key: 'total_fee', label: 'IT团队费用合计', type: 'text' },
          { key: 'audit_fee', label: '财务审计收费金额（万元，含税）', type: 'text' },
        ],
      },
      {
        id: 'scope',
        title: '三、IT审计范围需求',
        kind: 'table',
        columns: [
          { key: 'item', label: 'IT审计范围需求', type: 'text', minWidth: 200 },
          { key: 'use_leap', label: '是否使用Leap', type: 'yesno', minWidth: 120 },
          { key: 'requirement', label: '对IT团队的要求或核查需求描述', type: 'textarea', minWidth: 260 },
        ],
        fixedRows: [
          { item: '信息技术一般控制（ITGC）' },
          { item: '信息技术应用控制测试（ITAC）' },
          { item: '会计分录测试' },
          { item: '数据提取' },
          { item: '数据分析' },
        ],
      },
      {
        id: 'client-contacts',
        title: '四、客户IT部门人员联系方式',
        kind: 'table',
        addable: true,
        rowLabel: '联系人',
        columns: [
          { key: 'name', label: '姓名', type: 'text', minWidth: 100 },
          { key: 'title', label: '职务', type: 'text', minWidth: 120 },
          { key: 'phone', label: '手机号/座机', type: 'text', minWidth: 140 },
          { key: 'email', label: '邮箱', type: 'text', minWidth: 160 },
        ],
      },
      {
        id: 'team-contacts',
        title: '四、项目组与IT团队联系方式',
        kind: 'fields',
        fields: [
          { key: 'partner_name', label: '项目合伙人', type: 'text' },
          { key: 'partner_phone', label: '项目合伙人手机号', type: 'text' },
          { key: 'partner_email', label: '项目合伙人邮箱', type: 'text' },
          { key: 'manager_name', label: '项目负责经理', type: 'text' },
          { key: 'manager_phone', label: '项目负责经理手机号', type: 'text' },
          { key: 'manager_email', label: '项目负责经理邮箱', type: 'text' },
          { key: 'it_lead', label: 'IT团队负责人', type: 'text' },
          { key: 'it_lead_phone', label: 'IT团队负责人手机号', type: 'text' },
        ],
      },
      {
        id: 'travel',
        title: '五、差旅与行程',
        kind: 'fields',
        fields: [
          { key: 'travel_cost', label: '差旅费用承担', type: 'select', options: ['客户', '项目组', 'IT团队'] },
          { key: 'itinerary', label: '建议IT团队行程（机票/航班信息）', type: 'textarea' },
          { key: 'biz_type', label: '业务类型', type: 'select', options: ['并购', '年审', 'IPO', '新三板', '其他'] },
        ],
      },
    ],
  },

  // ─── B60-2-3 IT审计计划备忘录 ─────────────────────────────────────────
  'B60-2-3': {
    code: 'B60-2-3',
    title: 'IT审计计划备忘录',
    sections: [
      {
        id: 'basic',
        title: '一、基本信息',
        hint: '本备忘录作为总体审计策略的 IT 安排补充；重大范围变更须回写 B60 第十五章。',
        kind: 'fields',
        fields: [
          { key: 'date', label: '日期', type: 'date' },
          { key: 'to', label: '致', type: 'text' },
          { key: 'from', label: '发自', type: 'text' },
          { key: 'subject', label: '主题', type: 'text' },
        ],
      },
      {
        id: 'team',
        title: '二、IT审计团队成员',
        kind: 'table',
        addable: true,
        rowLabel: '成员',
        columns: [
          { key: 'name', label: '姓名', type: 'text', minWidth: 140 },
          { key: 'level', label: '职级', type: 'text', minWidth: 160 },
        ],
      },
      {
        id: 'purpose',
        title: '三、目的与背景',
        kind: 'fields',
        fields: [
          { key: 'purpose', label: '目的', type: 'textarea', hint: '概述与IT审计团队参与有关的程序' },
          { key: 'background', label: '客户背景信息', type: 'textarea' },
          { key: 'discussion', label: '计划讨论（与项目合伙人确定IT团队参与程度）', type: 'textarea' },
        ],
      },
      {
        id: 'processes',
        title: '四、重大业务流程与涉及的信息系统',
        kind: 'table',
        addable: true,
        rowLabel: '业务流程',
        columns: [
          { key: 'process', label: '重大业务流程', type: 'text', minWidth: 160 },
          { key: 'systems', label: '涉及的信息系统', type: 'textarea', minWidth: 280 },
        ],
        fixedRows: [
          { process: '采购' }, { process: '销售' }, { process: '存货' }, { process: '财务报告' },
        ],
      },
      {
        id: 'risk-control',
        title: '五、财务报表科目风险与信息处理控制（A-E）',
        kind: 'table',
        addable: true,
        rowLabel: '科目',
        columns: [
          { key: 'account', label: 'A.财务报表科目', type: 'text', minWidth: 120 },
          { key: 'process', label: 'B.业务流程和交易', type: 'text', minWidth: 140 },
          { key: 'risk', label: 'C.潜在错报风险', type: 'textarea', minWidth: 180 },
          { key: 'control', label: 'D.信息处理控制及数据', type: 'textarea', minWidth: 240 },
          { key: 'system', label: 'E.涉及系统', type: 'text', minWidth: 140 },
        ],
      },
      {
        id: 'it-env',
        title: '六、IT环境',
        kind: 'fields',
        fields: [
          { key: 'app', label: '应用系统', type: 'textarea' },
          { key: 'db', label: '数据库', type: 'text' },
          { key: 'os', label: '操作系统', type: 'text' },
          { key: 'dc', label: '数据中心', type: 'text' },
          { key: 'network', label: '网络', type: 'text' },
        ],
      },
    ],
  },
}

/** 有结构化 schema 的子底稿编码 */
export const B60_STRUCTURED_CODES = Object.keys(B60_SUBSHEET_SCHEMAS)
