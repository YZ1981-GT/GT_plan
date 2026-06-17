/**
 * wpPopupDocxConfigs — A 循环 docx 子底稿弹窗配置（单一数据源）
 *
 * 新增 docx 弹窗只需在此文件加条目，WpPopupDocxEditor / WpInlinePopup /
 * GtAProgramConsole.INLINE_POPUP_WP_CODES 自动消费。
 */

export interface DocxPopupLink {
  label: string
  routeName?: string
  wpCode?: string
}

export interface DocxPopupConfig {
  title: string
  guidance: string[]
  applicableNote: string
  templatePath: string
  relatedLinks: DocxPopupLink[]
}

export const DOCX_POPUP_CONFIGS: Record<string, DocxPopupConfig> = {
  'A8-1': {
    title: '管理层关于审计报告日后公布其他信息的书面声明',
    guidance: [
      '本声明书系根据《中国注册会计师审计准则第1521号》的相关规定编制，针对只能在审计报告日后获取的其他信息时，注册会计师应从管理层获取的书面声明。',
      '红色字体显示的内容，由项目组根据企业或约定项目的具体情况填入适当的内容或删除不适用之处。蓝色字体显示的内容，是对相关内容的提示，使用时删除。',
      '注册会计师应在审计计划阶段通过与管理层讨论，确定哪些文件组成年度报告，以及被审计单位计划公布这些文件的方式和时间安排。',
      '对于注册会计师在审计报告日前未获取的其他信息，应要求管理层提供本书面声明，包括拟编制并发布这些其他信息，以及预计发布的时间。',
      '本书面声明的签署日期通常应与审计报告日一致，不得晚于审计报告日。',
      '本书面声明可单独要求管理层出具，也可以整合在《A16 管理层声明书》中。',
    ],
    applicableNote: '当被审计单位的年度报告（含其他信息）在审计报告日后才能获取时适用',
    templatePath: 'wp_templates/A/A8-1 管理层对审计报告日后公布其他信息的书面声明201707.docx',
    relatedLinks: [
      { label: 'A16 管理层声明书', wpCode: 'A16' },
      { label: 'A8 其他信息程序表', wpCode: 'A8' },
    ],
  },
  'A8-2': {
    title: '其他信息比对记录',
    guidance: [
      '本底稿用于记录注册会计师将其他信息中的金额或其他项目与财务报表进行比对的过程和结论。',
      '比对内容包括：关键财务业绩摘要、经营数据、特殊项目、流动性信息、资本支出、表外安排、担保及或有事项、财务比率等金额类信息。',
      '以及：会计估计解释、关联方识别、风险管理政策、法律监管变化、新准则影响、业务环境描述、战略概述等其他项目类信息。',
      '对于识别出的不一致或可能的重大错报，应记录与管理层讨论的结果及后续处理。',
    ],
    applicableNote: '所有审计项目均适用，在获取年度报告其他信息后编制',
    templatePath: 'wp_templates/A/A8-2 其他信息比对记录20170725.docx',
    relatedLinks: [
      { label: 'A8 其他信息程序表', wpCode: 'A8' },
      { label: '财务报表（试算表）', routeName: 'trial-balance' },
    ],
  },
  'A9-1': {
    title: '向管理层通报内部控制缺陷沟通函',
    guidance: [
      '本函用于向管理层通报审计过程中识别出的内部控制缺陷（含重大缺陷和重要缺陷）。',
      '红色字体内容需根据项目实际情况填写或删除，蓝色提示性文字导出前应删除。',
      '通报内容应包括缺陷描述、影响及管理层已采取或拟采取的整改措施。',
    ],
    applicableNote: '识别出内部控制缺陷且需向管理层书面通报时适用',
    templatePath: 'wp_templates/A/A9-1向管理层通报内部控制缺陷-沟通函.docx',
    relatedLinks: [
      { label: 'A9 内部控制建议程序表', wpCode: 'A9' },
      { label: 'A14 内控缺陷程序表', wpCode: 'A14' },
    ],
  },
  'A9-2': {
    title: '向治理层通报内部控制缺陷沟通函',
    guidance: [
      '本函用于向治理层通报审计过程中识别出的内部控制缺陷。',
      '当存在重大缺陷时，必须以书面形式及时通报治理层。',
      '红色字体内容需根据项目实际情况填写，蓝色提示性文字导出前应删除。',
    ],
    applicableNote: '识别出内部控制缺陷且需向治理层书面通报时适用',
    templatePath: 'wp_templates/A/A9-2向治理层通报内部控制缺陷-沟通函.docx',
    relatedLinks: [
      { label: 'A9 内部控制建议程序表', wpCode: 'A9' },
      { label: 'A10 与治理层沟通程序表', wpCode: 'A10' },
    ],
  },
  'A10-1': {
    title: '与治理层沟通函',
    guidance: [
      '本函根据《中国注册会计师审计准则第1151号——与治理层的沟通》（2022年12月修订）编制。',
      '沟通对象为公司董事会、监事会或审计委员会。',
      '本函仅供治理层参考，不应被用于其他目的。',
      '红色字体内容需根据项目具体情况填写或删除，蓝色/【注】提示内容为编制指引，导出正式文件前应删除。',
      '沟通事项包括：审计责任、质量管理体系、独立性、审计范围和时间安排、重大发现等。',
    ],
    applicableNote: '所有审计项目均适用，审计完成阶段与治理层沟通时使用',
    templatePath: 'wp_templates/A/A10-1 与治理层沟通函.docx',
    relatedLinks: [
      { label: 'A10 与治理层沟通程序表', wpCode: 'A10' },
      { label: 'A13 错报汇总', wpCode: 'A13' },
    ],
  },
  'A11-1': {
    title: '期后事项问询函',
    guidance: [
      '本问询函根据《中国注册会计师审计准则第1332号——期后事项》编制。',
      '问询日期应在资产负债表日之后，且尽量接近审计报告日。',
      '问询对象为公司管理层，内容涵盖期后已发生或计划中的重大事项。',
      '【注】标记的内容为编制提示，导出正式文件前应删除。红字示例为参考，需根据实际替换。',
      '受访对象答复栏由管理层填写，审计人员记录并评估是否需要调整或披露。',
    ],
    applicableNote: '所有审计项目均适用，审计完成阶段发送给管理层',
    templatePath: 'wp_templates/A/A11-1 期后事项问询函.docx',
    relatedLinks: [
      { label: 'A11 期后事项程序表', wpCode: 'A11' },
      { label: 'A5-3 或有事项', wpCode: 'A5-3' },
    ],
  },
  'A12-1': {
    title: '法律事务确认函及律师回复函',
    guidance: [
      '本确认函根据审计准则要求，向被审计单位聘请的律师询证未决诉讼等法律事务。',
      '函件由被审计单位盖章后发送给律师事务所，律师直接回函至致同会计师事务所。',
      '需确认的内容包括：未决诉讼说明、损失可能性及金额估计、律师费结算情况。',
      '公司名称、年度、律师事务所名称等信息需根据项目实际填写。',
      '若无未决诉讼事项，律师可直接填写复函并签章寄回。',
    ],
    applicableNote: '所有审计项目均适用，审计完成阶段发送给律师事务所',
    templatePath: 'wp_templates/A/A12-1 法律事务确认函及律师回复函.docx',
    relatedLinks: [
      { label: 'A12 律师回复程序表', wpCode: 'A12' },
      { label: 'A5-3 或有事项', wpCode: 'A5-3' },
    ],
  },
  'A16-1': {
    title: '管理层声明书（企业会计准则）',
    guidance: [
      '适用于执行企业会计准则的一般财务报表审计项目。',
      '声明书应由被审计单位管理层签署，签署日期不得早于审计报告日。',
      '红色字体为需根据项目情况填写或删除的内容，蓝色提示导出前应删除。',
    ],
    applicableNote: '一般财务报表审计项目（企业会计准则）',
    templatePath: 'wp_templates/A/A16-1 管理层声明书-财务报表审计（企业会计准则）.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-2': {
    title: '管理层声明书（整合审计）',
    guidance: [
      '适用于财务报表审计与内部控制审计整合项目。',
      '声明内容涵盖财务报表责任及内部控制相关声明事项。',
    ],
    applicableNote: '整合审计项目适用',
    templatePath: 'wp_templates/A/A16-2 管理层声明书-整合审计.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-3': {
    title: '管理层声明书（IPO申报报表审计）',
    guidance: [
      '适用于 IPO 申报财务报表审计项目。',
      '声明书应涵盖申报报表期间及关键声明事项。',
    ],
    applicableNote: 'IPO 申报报表审计项目适用',
    templatePath: 'wp_templates/A/A16-3 管理层声明书-财务报表审计（IPO申报报表审计）.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-4': {
    title: '管理层声明书（IPO季度财务报表审阅）',
    guidance: [
      '适用于 IPO 季度财务报表审阅项目。',
      '声明事项应涵盖审阅报告所针对的财务信息。',
    ],
    applicableNote: 'IPO 季度财务报表审阅项目适用',
    templatePath: 'wp_templates/A/A16-4 管理层声明书（IPO季度财务报表审阅）20170206.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-5': {
    title: '管理层声明书（新三板申报报表审计）',
    guidance: [
      '适用于新三板申报财务报表审计项目。',
      '声明书内容应涵盖申报报表及相关声明事项。',
    ],
    applicableNote: '新三板申报报表审计项目适用',
    templatePath: 'wp_templates/A/A16-5 管理层声明书-财务报表审计（新三板申报报表审计）.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-6': {
    title: '管理层声明书（企业债：会计准则）',
    guidance: [
      '适用于企业债发行相关的财务报表审计项目（企业会计准则）。',
    ],
    applicableNote: '企业债发行相关财务报表审计适用',
    templatePath: 'wp_templates/A/A16-6 管理层声明书-财务报表审计（企业债：会计准则）.docx',
    relatedLinks: [{ label: 'A16 管理层声明书程序表', wpCode: 'A16' }],
  },
  'A16-7': {
    title: '管理层关联交易声明书',
    guidance: [
      '适用于需要管理层单独就关联交易事项出具声明的项目。',
      '声明应涵盖关联关系识别、交易完整性及披露充分性等内容。',
    ],
    applicableNote: '存在重大关联交易且需单独声明时适用',
    templatePath: 'wp_templates/A/A16-7 管理层关联交易声明书201910.docx',
    relatedLinks: [
      { label: 'A16 管理层声明书程序表', wpCode: 'A16' },
      { label: 'A7 关联方程序表', wpCode: 'A7' },
    ],
  },
  'A17-1': {
    title: '重大事项概要汇总',
    guidance: [
      '重大事项概要是审计完成阶段的核心综合性底稿，涵盖审计业务约定、独立性、审计计划更新、职业判断、错报风险、KAM 等章节。',
      '红色字体为需填写内容，蓝色提示导出前应删除。',
      '各章节可从关联底稿模块拉取数据填充。',
    ],
    applicableNote: 'A 类业务（上市公司/IPO 等）强制编制',
    templatePath: 'wp_templates/A/A17-1 重大事项概要汇总.docx',
    relatedLinks: [{ label: 'A17 重大事项概要程序表', wpCode: 'A17' }],
  },
  'A17-2-1': {
    title: '重大事项概要—关键审计事项（KAM）',
    guidance: [
      '本底稿用于记录关键审计事项的识别、应对及结论。',
      'KAM 内容应与审计报告中"关键审计事项"部分保持一致。',
    ],
    applicableNote: 'A 类业务且审计报告包含 KAM 时适用',
    templatePath: 'wp_templates/A/A17-2-1 重大事项概要—关键审计事项.docx',
    relatedLinks: [{ label: 'A17 重大事项概要程序表', wpCode: 'A17' }],
  },
  'A17-3': {
    title: '业务咨询记录',
    guidance: [
      '记录审计过程中向所内或外部专家进行的业务咨询事项。',
      '应包括咨询问题、咨询对象、咨询结论及执行情况。',
    ],
    applicableNote: '发生业务咨询时适用',
    templatePath: 'wp_templates/A/A17-3 业务咨询记录-XX公司-XXX事项.docx',
    relatedLinks: [{ label: 'A17 重大事项概要程序表', wpCode: 'A17' }],
  },
  'A17-3-1': {
    title: '业务咨询结果执行情况记录',
    guidance: [
      '记录业务咨询结论在审计项目中的执行情况。',
      '应说明咨询结论是否已落实及具体执行证据。',
    ],
    applicableNote: '存在业务咨询且需记录执行情况时适用',
    templatePath: 'wp_templates/A/A17-3-1 业务咨询结果执行情况记录.docx',
    relatedLinks: [
      { label: 'A17-3 业务咨询记录', wpCode: 'A17-3' },
      { label: 'A17 重大事项概要程序表', wpCode: 'A17' },
    ],
  },
  'A17-4': {
    title: '重大专业分歧事项记录',
    guidance: [
      '记录项目组与项目质量控制复核人员（或其他专业人员）之间的重大专业分歧。',
      '应包括分歧事项、各方观点、最终结论及依据。',
    ],
    applicableNote: '存在重大专业分歧时适用',
    templatePath: 'wp_templates/A/A17-4 重大专业分歧事项记录.docx',
    relatedLinks: [{ label: 'A17 重大事项概要程序表', wpCode: 'A17' }],
  },
  'A17-6': {
    title: '总结会会议纪要',
    guidance: [
      '记录审计总结会的时间、参与人员、讨论事项及结论。',
      '总结会应在审计报告日前召开，讨论重大事项及审计结论。',
    ],
    applicableNote: 'A 类业务推荐在签发前召开总结会',
    templatePath: 'wp_templates/A/A17-6  总结会会议记要.docx',
    relatedLinks: [{ label: 'A17 重大事项概要程序表', wpCode: 'A17' }],
  },
  'A18-1': {
    title: '向监管部门报送审计小结的函',
    guidance: [
      '适用于需要向证券监管部门报送审计小结的项目。',
      '函件内容应涵盖审计范围、主要审计程序及结论摘要。',
    ],
    applicableNote: '上市公司等需向监管部门报送审计小结时适用',
    templatePath: 'wp_templates/A/A18-1 向监管部门报送审计小结的函.docx',
    relatedLinks: [{ label: 'A18 监管沟通程序表', wpCode: 'A18' }],
  },
  'A18-2': {
    title: '与监管层沟通函（通用）',
    guidance: [
      '适用于与证券监管部门的常规沟通。',
      '红色字体需根据项目情况填写，蓝色提示导出前应删除。',
    ],
    applicableNote: '需与监管层进行书面沟通时适用',
    templatePath: 'wp_templates/A/A18-2 与监管层沟通函 (通用)2019.docx',
    relatedLinks: [{ label: 'A18 监管沟通程序表', wpCode: 'A18' }],
  },
  'A26-1': {
    title: '专业技术委员会业务报告审核提交资料清单',
    guidance: [
      '列出提交专业技术委员会审核所需的资料清单。',
      '项目组应逐项核对并勾选已备齐的资料。',
    ],
    applicableNote: 'A 类业务需专委会审批时适用',
    templatePath: 'wp_templates/A/A26-1 专业技术委员会业务报告审核提交资料清单.docx',
    relatedLinks: [{ label: 'A26 专委会审批程序表', wpCode: 'A26' }],
  },
  'A26-2': {
    title: '专业技术委员会委员审核记录',
    guidance: [
      '记录专委会委员对业务报告的审核意见及结论。',
    ],
    applicableNote: '专委会委员审核时适用',
    templatePath: 'wp_templates/A/A26-2 专业技术委员会委员审核记录.docx',
    relatedLinks: [{ label: 'A26 专委会审批程序表', wpCode: 'A26' }],
  },
  'A26-3': {
    title: '专业技术委员会会议记录',
    guidance: [
      '记录专委会会议的时间、参会人员、讨论事项及决议。',
    ],
    applicableNote: '召开专委会会议时适用',
    templatePath: 'wp_templates/A/A26-3 专业技术委员会会议记录.docx',
    relatedLinks: [{ label: 'A26 专委会审批程序表', wpCode: 'A26' }],
  },
  'A26-4': {
    title: '专业技术委员会重大业务咨询意见或分歧会议记录',
    guidance: [
      '记录专委会就重大业务咨询意见或专业分歧召开的专项会议。',
    ],
    applicableNote: '存在重大咨询意见或分歧需专委会讨论时适用',
    templatePath: 'wp_templates/A/A26-4 专业技术委员会重大业务咨询意见或分歧会议记录.docx',
    relatedLinks: [{ label: 'A26 专委会审批程序表', wpCode: 'A26' }],
  },
  'A27-1': {
    title: 'IT审计总结备忘录',
    guidance: [
      '汇总 IT 审计的发现、结论及对财务报表审计的影响。',
      '应与 A14-3 IT 缺陷汇总底稿保持一致。',
    ],
    applicableNote: '执行 IT 相关审计程序时适用',
    templatePath: 'wp_templates/A/A27-1 IT审计总结备忘录.docx',
    relatedLinks: [
      { label: 'A14 内控缺陷程序表', wpCode: 'A14' },
      { label: 'A14-3 IT缺陷汇总', wpCode: 'A14-3' },
    ],
  },
}

/** 所有 docx 弹窗 wp_code 集合（供 INLINE_POPUP 判定） */
export const DOCX_POPUP_WP_CODES = new Set(Object.keys(DOCX_POPUP_CONFIGS))

/** 非 docx 专用弹窗 + docx 弹窗的完整 INLINE_POPUP 集合 */
export const INLINE_POPUP_WP_CODES = new Set([
  'A1-11',
  'A1-12',
  'A1-17',
  'A1-18',
  ...DOCX_POPUP_WP_CODES,
])
