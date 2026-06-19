/**
 * wpPopupDocxConfigsB — B 循环 docx 子底稿弹窗配置
 *
 * B 类（承接与计划阶段）docx 底稿弹窗注册。
 * 新增 B 类 docx 弹窗只需在此文件加条目。
 */

import type { DocxPopupConfig } from './wpPopupDocxConfigs'

export const B_DOCX_POPUP_CONFIGS: Record<string, DocxPopupConfig> = {
  // ─── G1: 业务承接与保持 ───────────────────────────────────────────────
  'B1-3': {
    title: '业务评价表',
    guidance: [
      '本表用于对审计业务进行综合评价，记录评价结论。',
      '红色字体为需根据项目实际情况填写的内容。',
    ],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B1-3 业务评价表.docx',
    relatedLinks: [
      { label: 'B1A 业务承接程序表', wpCode: 'B1A' },
      { label: 'B1B 业务保持程序表', wpCode: 'B1B' },
    ],
  },
  'B1-4': {
    title: '业务承接阶段尽职调查报告',
    guidance: [
      '本报告用于记录业务承接阶段的尽职调查过程和结论。',
      '提供标准版和简化版，根据项目复杂程度选用。',
      '红色字体为需根据项目实际情况填写或删除的内容。',
    ],
    applicableNote: '首次承接审计业务时适用',
    templatePath: 'wp_templates/B/B1-4 业务承接阶段尽职调查（预备调查）报告（标准版）.docx',
    relatedLinks: [
      { label: 'B1A 业务承接程序表', wpCode: 'B1A' },
      { label: 'B1-1 风险评估表（承接）', wpCode: 'B1-1' },
    ],
  },
  'B1-7': {
    title: '质量控制委员会会议记录',
    guidance: [
      '记录质量控制委员会就项目承接/保持决议的会议过程。',
      '应包括参会人员、讨论事项及最终决议。',
    ],
    applicableNote: '需质量控制委员会审批的项目适用',
    templatePath: 'wp_templates/B/B1-7 质量控制委员会会议记录.docx',
    relatedLinks: [
      { label: 'B1A 业务承接程序表', wpCode: 'B1A' },
    ],
  },

  // ─── G2: 与前任注册会计师沟通 ─────────────────────────────────────────
  'B2-1': {
    title: '向被审计单位发出的沟通函副本（就业务承接事项）',
    guidance: [
      '本函为向被审计单位发出的关于允许注册会计师与前任沟通的函件副本。',
    ],
    applicableNote: '首次承接且存在前任注册会计师时适用',
    templatePath: 'wp_templates/B/B2-1 向被审计单位发出的沟通函副本（就业务承接事项）.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
    ],
  },
  'B2-3': {
    title: '与前任注册会计师的沟通函副本（就业务承接事项）',
    guidance: [
      '本函为与前任注册会计师就业务承接相关事项进行沟通的函件。',
      '包含第一封和第二封沟通函模板。',
    ],
    applicableNote: '首次承接且需与前任沟通时适用',
    templatePath: 'wp_templates/B/B2-3 与前任注册会计师的沟通函副本（就业务承接事项，第一封沟通函）.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
    ],
  },
  'B2-6': {
    title: '向被审计单位发出的沟通函副本（就底稿使用事项）',
    guidance: [
      '本函为向被审计单位发出的关于允许注册会计师查阅前任底稿的函件。',
    ],
    applicableNote: '需查阅前任底稿时适用',
    templatePath: 'wp_templates/B/B2-6 向被审计单位发出的沟通函副本（就底稿使用事项）.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
    ],
  },
  'B2-8': {
    title: '与前任注册会计师的沟通函副本（就底稿查阅事项）',
    guidance: [
      '本函为就查阅前任注册会计师工作底稿事项的沟通函副本。',
    ],
    applicableNote: '需查阅前任底稿时适用',
    templatePath: 'wp_templates/B/B2-8 与前任注册会计师的沟通函副本（就底稿查阅事项）.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
    ],
  },
  'B2-11': {
    title: '与前任注册会计师的沟通函（就沪深交易所涉及复核时的重要事项）',
    guidance: [
      '本函针对沪深交易所监管相关的复核事项与前任注册会计师沟通。',
    ],
    applicableNote: '上市公司首次承接且涉及沪深交易所复核时适用',
    templatePath: 'wp_templates/B/B2-11 与前任注册会计师的沟通函（就沪深交易所涉及复核时的重要事项）.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
    ],
  },
  'B2-12': {
    title: '对前任注册会计师的评价底稿',
    guidance: [
      '本底稿用于记录对前任注册会计师专业能力和独立性等方面的评价。',
    ],
    applicableNote: '首次承接且已完成前任沟通时适用',
    templatePath: 'wp_templates/B/B2-12 对前任注册会计师的评价底稿.docx',
    relatedLinks: [
      { label: 'B2 与前任沟通程序表', wpCode: 'B2' },
      { label: 'B2-5 沟通后评价', wpCode: 'B2-5' },
    ],
  },

  // ─── G3: 独立性确认 + 业务约定书 ─────────────────────────────────────
  'B3-1': {
    title: '审计项目团队成员独立性声明书',
    guidance: [
      '本声明书由项目组全体成员签署，确认其在审计业务中保持独立性。',
      '适用于中国审计准则及国际审计准则。',
      '{{团队成员名单}} 将自动替换为项目组成员列表。',
    ],
    applicableNote: '所有审计项目均适用，项目组全体成员须签署',
    templatePath: 'wp_templates/B/B3-1 审计项目团队成员独立性声明书（适用于中国及国际审计准则）.docx',
    relatedLinks: [
      { label: 'B3 独立性确认程序表', wpCode: 'B3' },
    ],
  },
  'B5': {
    title: '业务约定书控制表',
    guidance: [
      '本控制表用于管理业务约定书的签署流程和状态。',
    ],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B5 业务约定书控制表.docx',
    relatedLinks: [
      { label: 'B1A 业务承接程序表', wpCode: 'B1A' },
    ],
  },
  'B5-1': {
    title: '财务报表审计业务约定书（通用）',
    guidance: [
      '通用财务报表审计业务约定书，适用于一般企业审计。',
      '含总分所共同签署版本。',
    ],
    applicableNote: '一般企业财务报表审计适用',
    templatePath: 'wp_templates/B/B5-1 财务报表审计业务约定书（通用）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-2': {
    title: '财务报表审计业务约定书（上市公司审计）',
    guidance: [
      '适用于上市公司财务报表审计项目的业务约定书。',
    ],
    applicableNote: '上市公司审计适用',
    templatePath: 'wp_templates/B/B5-2 财务报表审计业务约定书（适用于上市公司审计）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-3': {
    title: '财务报表审计业务约定书（国有企业审计）',
    guidance: [
      '适用于国有企业财务报表审计项目的业务约定书。',
    ],
    applicableNote: '国有企业审计适用',
    templatePath: 'wp_templates/B/B5-3 财务报表审计业务约定书（适用于国有企业审计）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-4': {
    title: '财务报表审计业务约定书（IPO审计）',
    guidance: [
      '适用于 IPO 申报财务报表审计项目的业务约定书。',
    ],
    applicableNote: 'IPO 审计适用',
    templatePath: 'wp_templates/B/B5-4 财务报表审计业务约定书（适用于IPO审计）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-5': {
    title: '内部控制审计业务约定书',
    guidance: [
      '适用于内部控制审计业务的约定书。',
    ],
    applicableNote: '内部控制审计项目适用',
    templatePath: 'wp_templates/B/B5-5 内部控制审计业务约定书.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-6': {
    title: 'IPO季度财务报表审阅业务约定书',
    guidance: ['适用于 IPO 季度财务报表审阅业务。'],
    applicableNote: 'IPO 季度审阅适用',
    templatePath: 'wp_templates/B/B5-6 IPO季度财务报表审阅业务约定书.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-7': {
    title: '审计及专项报告等其他鉴证业务约定书（新三板）',
    guidance: ['适用于新三板挂牌相关审计及专项报告鉴证业务。'],
    applicableNote: '新三板项目适用',
    templatePath: 'wp_templates/B/B5-7 审计及专项报告等其他鉴证业务约定书（新三板）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-8': {
    title: '审计及专项报告等其他鉴证业务约定书（企业债）',
    guidance: ['适用于企业债发行相关审计及专项报告鉴证业务。'],
    applicableNote: '企业债项目适用',
    templatePath: 'wp_templates/B/B5-8-1 审计及专项报告等其他鉴证业务约定书（企业债：会计准则）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-8-1': {
    title: '审计及专项报告等其他鉴证业务约定书（企业债：会计准则）',
    guidance: ['适用于企业债发行相关审计及专项报告鉴证业务（会计准则版）。'],
    applicableNote: '企业债项目适用',
    templatePath: 'wp_templates/B/B5-8-1 审计及专项报告等其他鉴证业务约定书（企业债：会计准则）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-8-2': {
    title: '审计及专项报告等其他鉴证业务约定书（企业债：会计制度）',
    guidance: ['适用于企业债发行相关审计及专项报告鉴证业务（会计制度版）。'],
    applicableNote: '企业债项目适用',
    templatePath: 'wp_templates/B/B5-8-2 审计及专项报告等其他鉴证业务约定书（企业债：会计制度）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-9': {
    title: '医院审计业务约定书',
    guidance: ['适用于医院审计业务的约定书。'],
    applicableNote: '医院审计项目适用',
    templatePath: 'wp_templates/B/B5-9-1 医院审计业务约定书（被审计医院直接委托）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-9-1': {
    title: '医院审计业务约定书（被审计医院直接委托）',
    guidance: ['适用于医院审计业务（被审计医院直接委托模式）。'],
    applicableNote: '医院审计项目适用',
    templatePath: 'wp_templates/B/B5-9-1 医院审计业务约定书（被审计医院直接委托）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5-9-2': {
    title: '医院审计业务约定书（第三方委托）',
    guidance: ['适用于医院审计业务（第三方委托模式）。'],
    applicableNote: '医院审计项目适用',
    templatePath: 'wp_templates/B/B5-9-2 医院审计业务约定书（第三方委托）.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },
  'B5附件': {
    title: '数据分级确认函',
    guidance: ['用于向被审计单位确认数据分级要求的函件。'],
    applicableNote: '涉及数据分级要求的项目适用',
    templatePath: 'wp_templates/B/B5附件：数据分级确认函.docx',
    relatedLinks: [{ label: 'B5 约定书控制表', wpCode: 'B5' }],
  },

  // ─── G4: 了解内部审计 ─────────────────────────────────────────────────
  'B18-3-1': {
    title: '利用内部审计人员书面协议（企业设立内审部门）',
    guidance: [
      '适用于被审计单位设立内部审计部门或职能岗位的情形。',
      '与内部审计人员签署的协助审计书面协议。',
    ],
    applicableNote: '利用内部审计人员为审计提供直接协助时适用',
    templatePath: 'wp_templates/B/B18-3-1 利用内部审计人员为审计提供直接协助的书面协议（适用于企业设立内部审计部门或职能岗位）.docx',
    relatedLinks: [{ label: 'B18 了解内部审计程序表', wpCode: 'B18' }],
  },
  'B18-3-2': {
    title: '利用内部审计人员书面协议（内审外包）',
    guidance: [
      '适用于被审计单位内部审计职能外包的情形。',
    ],
    applicableNote: '内部审计职能外包且需利用内审人员时适用',
    templatePath: 'wp_templates/B/B18-3-2 利用内部审计人员为审计提供直接协助的书面协议（适用于内部审计职能外包）.docx',
    relatedLinks: [{ label: 'B18 了解内部审计程序表', wpCode: 'B18' }],
  },

  // ─── G5: B23 流程图 docx（14 份）─────────────────────────────────────
  'B23-1-2': {
    title: '销售循环业务层面控制 - 流程图及描述',
    guidance: ['记录销售循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-1-2 销售循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-1 销售循环业务层面控制', wpCode: 'B23-1' }],
  },
  'B23-2-2': {
    title: '货币资金循环业务层面控制 - 流程图及描述',
    guidance: ['记录货币资金循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-2-2 货币资金循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-2 货币资金循环控制', wpCode: 'B23-2' }],
  },
  'B23-3-2': {
    title: '存货循环业务层面控制 - 流程图及描述',
    guidance: ['记录存货循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-3-2 存货循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-3 存货循环控制', wpCode: 'B23-3' }],
  },
  'B23-4-2': {
    title: '投资循环业务层面控制 - 流程图及描述',
    guidance: ['记录投资循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-4-2 投资循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-4 投资循环控制', wpCode: 'B23-4' }],
  },
  'B23-5-2': {
    title: '固定资产循环业务层面控制 - 流程图及描述',
    guidance: ['记录固定资产循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-5-2 固定资产循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-5 固定资产循环控制', wpCode: 'B23-5' }],
  },
  'B23-6-2': {
    title: '在建工程循环业务层面控制 - 流程图及描述',
    guidance: ['记录在建工程循环业务层面控制的流程图和文字描述。'],
    applicableNote: '存在在建工程的项目适用',
    templatePath: 'wp_templates/B/B23-6-2 在建工程循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-6 在建工程循环控制', wpCode: 'B23-6' }],
  },
  'B23-7-2': {
    title: '无形资产及其他长期资产循环业务层面控制 - 流程图及描述',
    guidance: ['记录无形资产及其他长期资产循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-7-2 无形资产及其他长期资产循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-7 无形资产循环控制', wpCode: 'B23-7' }],
  },
  'B23-8-2': {
    title: '研发循环业务层面控制 - 流程图及描述',
    guidance: ['记录研发循环业务层面控制的流程图和文字描述。'],
    applicableNote: '存在研发活动的项目适用',
    templatePath: 'wp_templates/B/B23-8-2 研发循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-8 研发循环控制', wpCode: 'B23-8' }],
  },
  'B23-9-2': {
    title: '职工薪酬循环业务层面控制 - 流程图及描述',
    guidance: ['记录职工薪酬循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-9-2 职工薪酬循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-9 职工薪酬循环控制', wpCode: 'B23-9' }],
  },
  'B23-10-2': {
    title: '管理循环业务层面控制 - 流程图及描述',
    guidance: ['记录管理循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-10-2 管理循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-10 管理循环控制', wpCode: 'B23-10' }],
  },
  'B23-11-2': {
    title: '税金循环业务层面控制 - 流程图及描述',
    guidance: ['记录税金循环业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-11-2 税金循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-11 税金循环控制', wpCode: 'B23-11' }],
  },
  'B23-12-2': {
    title: '债务循环业务层面控制 - 流程图及描述',
    guidance: ['记录债务循环业务层面控制的流程图和文字描述。'],
    applicableNote: '存在债务融资的项目适用',
    templatePath: 'wp_templates/B/B23-12-2 债务循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-12 债务循环控制', wpCode: 'B23-12' }],
  },
  'B23-13-2': {
    title: '租赁循环业务层面控制 - 流程图及描述',
    guidance: ['记录租赁循环业务层面控制的流程图和文字描述。'],
    applicableNote: '存在租赁业务的项目适用',
    templatePath: 'wp_templates/B/B23-13-2 租赁循环业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-13 租赁循环控制', wpCode: 'B23-13' }],
  },
  'B23-14-2': {
    title: '关联方及交易业务层面控制 - 流程图及描述',
    guidance: ['记录关联方及交易业务层面控制的流程图和文字描述。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B23-14-2 关联方及交易业务层面控制 - 流程图及描述.docx',
    relatedLinks: [{ label: 'B23-14 关联方循环控制', wpCode: 'B23-14' }],
  },

  // ─── G6: 集团审计系列 docx ────────────────────────────────────────────
  'B30-3': {
    title: '集团审计指令',
    guidance: ['集团项目组向组成部分注册会计师下达的审计指令。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-3 集团审计指令（2023年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-3-1': {
    title: '集团主要会计政策和会计估计',
    guidance: ['记录集团统一的会计政策和会计估计。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-3-1 集团主要会计政策和会计估计.docx',
    relatedLinks: [{ label: 'B30-3 集团审计指令', wpCode: 'B30-3' }],
  },
  'B30-3-2': {
    title: '集团项目组就关联方事项致组成部分注册会计师询证函',
    guidance: ['集团项目组就关联方识别事项向组成部分注册会计师发送的询证函。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-3-2 集团项目组就关联方事项致组成部分注册会计师询证函.docx',
    relatedLinks: [{ label: 'B30-3 集团审计指令', wpCode: 'B30-3' }],
  },
  'B30-4': {
    title: '组成部分注册会计师执行的工作',
    guidance: ['记录组成部分注册会计师被要求执行的具体工作内容。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-4 组成部分注册会计师执行的工作（2021年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-4-1': {
    title: '组成部分注册会计师 - 特定审计程序模板',
    guidance: ['为组成部分注册会计师提供的特定审计程序执行模板。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-4-1 组成部分注册会计师 - 特定审计程序模板.docx',
    relatedLinks: [{ label: 'B30-4 组成部分工作', wpCode: 'B30-4' }],
  },
  'B30-5': {
    title: '集团审计 - 服务协议',
    guidance: ['集团审计中各参与方之间签署的服务协议。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-5 集团审计 - 服务协议（2023年3月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-6': {
    title: '集团审计会议议程',
    guidance: ['集团审计项目组会议的议程模板。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-6 集团审计会议议程（2021年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-7': {
    title: '集团审计指令确认函',
    guidance: ['组成部分注册会计师对集团审计指令的确认回复。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-7 集团审计指令确认函（2023年6月）.docx',
    relatedLinks: [{ label: 'B30-3 集团审计指令', wpCode: 'B30-3' }],
  },
  'B30-9': {
    title: '集团审计备忘录',
    guidance: ['记录集团审计过程中的重要事项和决策。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-9 集团审计备忘录（2023年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-10': {
    title: '复核组成部分注册会计师工作底稿',
    guidance: ['集团项目组复核组成部分注册会计师工作底稿的记录。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-10 复核组成部分注册会计师工作底稿（2021年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-11': {
    title: '审计完成备忘录',
    guidance: ['集团审计完成阶段的综合备忘录。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-11 审计完成备忘录（2023年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-11-1': {
    title: '重大问题发现及解决汇总',
    guidance: ['汇总集团审计中发现的重大问题及其解决情况。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-11-1 重大问题发现及解决汇总.docx',
    relatedLinks: [{ label: 'B30-11 审计完成备忘录', wpCode: 'B30-11' }],
  },
  'B30-11-2': {
    title: '内部控制缺陷汇总与评估',
    guidance: ['汇总各组成部分发现的内部控制缺陷并进行集团层面评估。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-11-2 内部控制缺陷汇总与评估.docx',
    relatedLinks: [{ label: 'B30-11 审计完成备忘录', wpCode: 'B30-11' }],
  },
  'B30-11-3': {
    title: '新增关联方信息',
    guidance: ['记录集团审计中新发现的关联方信息。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-11-3 新增关联方信息.docx',
    relatedLinks: [{ label: 'B30-11 审计完成备忘录', wpCode: 'B30-11' }],
  },
  'B30-13': {
    title: '致集团项目组的报告示例',
    guidance: ['组成部分注册会计师致集团项目组的报告模板。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-13 致集团项目组的报告示例（2018年11月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },
  'B30-14': {
    title: '期后事项备忘录',
    guidance: ['记录集团审计中各组成部分期后事项的汇总备忘录。'],
    applicableNote: '合并审计项目适用',
    templatePath: 'wp_templates/B/B30-14 期后事项备忘录（2021年6月）.docx',
    relatedLinks: [{ label: 'B30 集团审计程序表', wpCode: 'B30' }],
  },

  // ─── G7: 项目组讨论 + 审计策略 ───────────────────────────────────────
  'B40-1': {
    title: '项目组讨论备忘录',
    guidance: [
      '记录项目组就舞弊风险等事项进行讨论的过程和结论。',
      '准则要求项目组在计划阶段就重大错报风险（含舞弊）进行讨论。',
    ],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B40-1 项目组讨论备忘录.docx',
    relatedLinks: [{ label: 'B40 项目组讨论程序表', wpCode: 'B40' }],
  },
  'B40-2': {
    title: '对SCOT+的完整性进行再评估',
    guidance: [
      '对 SCOT+（重大类别交易/账户余额/披露）的完整性进行再评估。',
      '确认是否遗漏需要进一步审计程序的重大领域。',
    ],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B40-2 对SCOT+的完整性进行再评估.docx',
    relatedLinks: [{ label: 'B40 项目组讨论程序表', wpCode: 'B40' }],
  },
  'B60': {
    title: '总体审计策略及具体审计计划',
    guidance: [
      '本文档为审计项目的顶层战略文档，涵盖总体审计策略和具体审计计划。',
      '应根据对被审计单位的了解和风险评估结果制定。',
    ],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B60 总体审计策略及具体审计计划.docx',
    relatedLinks: [
      { label: 'B50 汇总风险评估', wpCode: 'B50' },
      { label: 'B10 了解被审计单位', wpCode: 'B10' },
    ],
  },
  'B60-2-1': {
    title: 'IT复杂性判断表',
    guidance: ['用于评估被审计单位 IT 环境复杂性的判断表。'],
    applicableNote: '所有审计项目均适用',
    templatePath: 'wp_templates/B/B60-2-1 IT复杂性判断表.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60-2-2': {
    title: 'IT审计进场前通知表',
    guidance: ['IT 审计进场前向被审计单位发送的通知。'],
    applicableNote: '需执行 IT 审计程序时适用',
    templatePath: 'wp_templates/B/B60-2-2 IT审计进场前通知表.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60-2-3': {
    title: 'IT审计计划备忘录',
    guidance: ['记录 IT 审计的具体计划和范围。'],
    applicableNote: '需执行 IT 审计程序时适用',
    templatePath: 'wp_templates/B/B60-2-3 IT审计计划备忘录.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60-3': {
    title: '评估专家工作计划',
    guidance: ['利用专家工作时的计划和协调安排。'],
    applicableNote: '需利用专家工作时适用',
    templatePath: 'wp_templates/B/B60-3 评估专家工作计划.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60A': {
    title: '对内控审计的特殊考虑',
    guidance: ['内部控制审计项目的特殊考虑事项。'],
    applicableNote: '整合审计（含内控审计）项目适用',
    templatePath: 'wp_templates/B/B60A 对内控审计的特殊考虑.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60B': {
    title: '对IPO申报财务报表审计的特殊考虑',
    guidance: ['IPO 项目审计策略的特殊考虑事项。'],
    applicableNote: 'IPO 项目适用',
    templatePath: 'wp_templates/B/B60B 对IPO申报财务报表审计的特殊考虑.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60C': {
    title: '对国有企业年度财务报表审计的特殊考虑',
    guidance: ['国有企业审计策略的特殊考虑事项。'],
    applicableNote: '国有企业审计项目适用',
    templatePath: 'wp_templates/B/B60C 对国有企业年度财务报表审计的特殊考虑.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
  'B60D': {
    title: '向监管机构报送总体审计策略和具体审计计划的函副本',
    guidance: ['向证券监管机构报送审计策略和计划的函件副本。'],
    applicableNote: '上市公司等需向监管报送时适用',
    templatePath: 'wp_templates/B/B60D 向监管机构报送总体审计策略和具体审计计划的函副本.docx',
    relatedLinks: [{ label: 'B60 总体审计策略', wpCode: 'B60' }],
  },
}
