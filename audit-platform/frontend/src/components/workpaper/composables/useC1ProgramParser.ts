/**
 * useC1ProgramParser — C1 企业层面控制测试 程序步骤解析引擎
 *
 * 将 procedure_table_templates.json 中 C1 的 131 个扁平条目
 * 解析为九段结构化步骤树（section → top-level steps → sub-items）。
 *
 * 纯函数，无 Vue 响应式依赖，便于单元测试和 PBT。
 *
 * Spec: .kiro/specs/c1-entity-level-control/
 */

import type { C1SectionSlug } from './useC1SectionEngine'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface C1ProgramStep {
  /** 所属段 slug: ce/ra/mo/bu/ic/fr/el/ye/rp */
  section: C1SectionSlug
  /** 段内 0-based 索引 */
  stepIndex: number
  /** 顶级步骤全文（如 "1. 询问高级管理层关于企业的价值体系，关于："） */
  name: string
  /** 子项文本列表（如 "（1） 组织机构的行为规范..."） */
  subItems: string[]
}

export interface C1RawItem {
  seq: number
  content: string
  is_header?: boolean
  ref_index?: string | null
  auto_data_source?: string | null
  applicable_default?: string
}

// ─── 段标题 → slug 映射 ───────────────────────────────────────────────────────

const SECTION_HEADER_MAP: [RegExp, C1SectionSlug][] = [
  [/^一\s/, 'ce'],
  [/^二\s/, 'ra'],
  [/^三\s/, 'mo'],
  [/^四\s/, 'bu'],
  [/^五\s/, 'ic'],
  [/^六\s/, 'fr'],
  [/^七\s/, 'el'],
  [/^八\s/, 'ye'],
  [/^九\s/, 'rp'],
]


/**
 * 判断一个条目是否为段标题。
 * 标题判定规则：
 * 1. is_header === true
 * 2. 内容以中文数字序号开头（"一 "/"二 "/.../"九 "）且非"N. "开头的步骤
 */
function isSectionHeader(item: C1RawItem): boolean {
  if (item.is_header === true) return true
  // 部分段标题 is_header=false（如"六 财务报告"/"七..."/"八..."/"九..."）
  for (const [re] of SECTION_HEADER_MAP) {
    if (re.test(item.content)) return true
  }
  return false
}

/**
 * 判断内容是否为顶级步骤（"N. " — 阿拉伯数字 + 句号/点 + 空格）
 */
function isTopLevelStep(content: string): boolean {
  return /^\d+\.\s/.test(content) || /^\d+．\s/.test(content)
}

/**
 * 判断内容是否为子项（"（N）" — 中文圆括号包裹数字）
 */
function isSubItem(content: string): boolean {
  return /^（\d+）/.test(content)
}

/**
 * 从段标题内容解析对应的 slug
 */
function parseSectionSlug(content: string): C1SectionSlug | null {
  for (const [re, slug] of SECTION_HEADER_MAP) {
    if (re.test(content)) return slug
  }
  return null
}


/**
 * 将扁平的 C1 程序步骤列表（131 项）解析为结构化的九段步骤树。
 *
 * 解析规则：
 * 1. 遇到段标题 → 切换当前段 slug，不生成步骤
 * 2. 遇到顶级步骤（"N. "）→ 在当前段新建一个 C1ProgramStep
 * 3. 遇到子项（"（N）"）→ 追加到当前顶级步骤的 subItems
 * 4. 其他内容（既非段标题、非"N."、非"（N）"）→ 视为独立顶级步骤（无子项）
 */
export function parseC1Programs(items: C1RawItem[]): C1ProgramStep[] {
  const result: C1ProgramStep[] = []
  let currentSection: C1SectionSlug = 'ce' // 默认首段
  let sectionStepCount: Record<string, number> = { ce: 0, ra: 0, mo: 0, bu: 0, ic: 0, fr: 0, el: 0, ye: 0, rp: 0 }
  let lastStep: C1ProgramStep | null = null

  for (const item of items) {
    const content = (item.content || '').trim()
    if (!content) continue

    // 1. 段标题检测
    if (isSectionHeader(item)) {
      const slug = parseSectionSlug(content)
      if (slug) {
        currentSection = slug
        lastStep = null
      }
      continue
    }

    // 2. 子项检测（必须先于顶级步骤判断，因为顶级步骤可能没有子项）
    if (isSubItem(content)) {
      if (lastStep) {
        lastStep.subItems.push(content)
      }
      // 如果没有前置顶级步骤，丢弃（不应出现）
      continue
    }

    // 3. 顶级步骤或独立条目
    const stepIndex = sectionStepCount[currentSection]
    sectionStepCount[currentSection]++
    const step: C1ProgramStep = {
      section: currentSection,
      stepIndex,
      name: content,
      subItems: [],
    }
    result.push(step)
    lastStep = step
  }

  return result
}


// ─── C1 程序步骤原始数据（来自 procedure_table_templates.json "C1".items） ────

export const C1_PROGRAM_ITEMS: C1RawItem[] = [
  { seq: 1, content: '一 控制环境', is_header: true },
  { seq: 2, content: '1. 询问高级管理层关于企业的价值体系，关于：', is_header: false },
  { seq: 3, content: '（1） 组织机构的行为规范，是否被编制成书面形式，并广泛适用于所有员工。', is_header: false },
  { seq: 4, content: '（2） 违反行为规范（如有）的后果。', is_header: false },
  { seq: 5, content: '（3） 考虑询问被审计单位其他员工对于行为规范及违法该行为规范后果的理解。', is_header: false },
  { seq: 6, content: '2. 观察并了解高级管理人员的经营风格以便确定下列事项：', is_header: false },
  { seq: 7, content: '（1） 与公司内其他职员进行公开的沟通。', is_header: false },
  { seq: 8, content: '（2） 他们了解在整个组织范围内正在发生的事件。', is_header: false },
  { seq: 9, content: '（3） 为公司职业制定了可实现的目的与目标。', is_header: false },
  { seq: 10, content: '（4） 他们准确描述运行结果。', is_header: false },
  { seq: 11, content: '3. 观察组织架构是否：', is_header: false },
  { seq: 12, content: '（1） 担任职务的人员能否有效地完成工作。', is_header: false },
  { seq: 13, content: '（2） 提供足够的财务报告来源。', is_header: false },
  { seq: 14, content: '（3） 为高层管理人士提供有关精确的财务报告的反馈信息。', is_header: false },
  { seq: 15, content: '4. 调查人力资源管理 。', is_header: false },
  { seq: 16, content: '（1） 他们如何确定人员已具备必需的技能来履行他们的职责。', is_header: false },
  { seq: 17, content: '（2） 在关键职位任职的员工了解自己所需胜任的工作。', is_header: false },
  { seq: 18, content: '（3） 他们如何对培训需求进行监控，并衡量表现。', is_header: false },
  { seq: 19, content: '（4） 职员普遍对于自己的角色和职责是否了解。', is_header: false },
  { seq: 20, content: '（5） 通常，人们是否了解他们的角色和职责。', is_header: false },
  { seq: 21, content: '（6） 薪酬政策是否恰当。', is_header: false },
  { seq: 22, content: '（7） 为了完成收益目标，薪酬政策是否容易导致动机或压力。', is_header: false },
  { seq: 23, content: '（8） 他们如何确定财务报告所需职位均由合格的有道德的人员担任。', is_header: false },
  { seq: 24, content: '（9） 他们如何为待招聘的职位刊登广告。', is_header: false },
  { seq: 25, content: '（10） 他们如何确定HR人员拥有足够的技能进行招聘。', is_header: false },
  { seq: 26, content: '5. 获得并阅读审计委员会章程，评定其是否适当。', is_header: false },
  { seq: 27, content: '6. 获取所有审计委员会成员的简历，简历中描述了其背景、经验、资格和目前的职业：', is_header: false },
  { seq: 28, content: '（1） 他们与被审计单位及其管理层保持独立。', is_header: false },
  { seq: 29, content: '（2） 至少有一个成员具有财务报告的技能。', is_header: false },
  { seq: 30, content: '7. 获取本年度审计委员会的所有会议记录，并确定下列情况：', is_header: false },
  { seq: 31, content: '（1） 有效监督的会议数目及频率的适当性 。', is_header: false },
  { seq: 32, content: '（2） 由管理者、内部审计员和外部审计员向审计委员会所报告项目的性质是适当的。', is_header: false },
  { seq: 33, content: '（3） 是否采取补救措施并有后续跟进。', is_header: false },
  { seq: 34, content: '（4） 审计委员会出席所有的会议。', is_header: false },
  { seq: 35, content: '（5） 财务报表在发布之前得到批准。', is_header: false },
  { seq: 36, content: '（6） 外部审计员以及审计费用已经过审核。', is_header: false },
  { seq: 37, content: '（7） 由外部审计员执行的非审计服务已通过批准。', is_header: false },
  { seq: 38, content: '（8） 外部审计师独立性的确认已获得书面材料。', is_header: false },
  { seq: 39, content: '（9） 内部审计计划和预算得到批准。', is_header: false },
  { seq: 40, content: '8. 就以下事项询问审计委员会主席（治理层）：', is_header: false },
  { seq: 41, content: '（1） 成员的组成和经验是否适合。', is_header: false },
  { seq: 42, content: '（2） 员工是否了解其职责。', is_header: false },
  { seq: 43, content: '（3） 成员对讨论和问题解决的参与。', is_header: false },
  { seq: 44, content: '（4） 具有财务专长的成员。', is_header: false },
  { seq: 45, content: '（5） 向管理人员、内部和外部审计员提出的问题实例。', is_header: false },
  { seq: 46, content: '（6） 是否对成员进行定期评价，以及对相关评价结果采取的措施。', is_header: false },
  { seq: 47, content: '（7） 是否已设置控制点以防止或发现舞弊。', is_header: false },
  { seq: 48, content: '（8） 他或她对审计委员会有效性的观点。', is_header: false },
  { seq: 49, content: '9. 询问经营过程中用以发现或防止舞弊行为的具体控制点。', is_header: false },
  { seq: 50, content: '10. 观察这些控制，以便确定他们是否已被实施。', is_header: false },
  { seq: 51, content: '11. 基于这些测试结果，我确信控制环境的控制有效运行。', is_header: false },
  { seq: 52, content: '二 风险评估', is_header: true },
  { seq: 53, content: '1. 针对企业风险评估流程，按照如下列示询问高级管理人员：', is_header: false },
  { seq: 54, content: '（1） 阐明了希望达到的目标和成就的宗旨声明是否存在。', is_header: false },
  { seq: 55, content: '（2） 在流程中是否在恰当的时间使用了适合的人。', is_header: false },
  { seq: 56, content: '（3） 预算是否实用，并且是基于可实现、可达成的假设的。', is_header: false },
  { seq: 57, content: '（4） 预算是否可以反映企业目标和目的。', is_header: false },
  { seq: 58, content: '（5） 如何确认可能影响目标达成的内部及外部风险。', is_header: false },
  { seq: 59, content: '（6） 经确认的商业风险是否与负责管理的董事会成员进行沟通过。', is_header: false },
  { seq: 60, content: '（7） 计划是否被制定和实施以应对已确认的风险。', is_header: false },
  { seq: 61, content: '2. 根据这些检测结果，我对风险评价控制的有效运行很满意。', is_header: false },
  { seq: 62, content: '三 监督', is_header: true },
  { seq: 63, content: '1. 询问管理层是否做了如下的监控活动：', is_header: false },
  { seq: 64, content: '（1） 监督控制活动信息是否有效。', is_header: false },
  { seq: 65, content: '（2） 监控活动如何被执行。', is_header: false },
  { seq: 66, content: '（3） 监控活动多久被执行一次。', is_header: false },
  { seq: 67, content: '（4） 外包业务如何获得监控。', is_header: false },
  { seq: 68, content: '（5） 如何分析和评估偏差。', is_header: false },
  { seq: 69, content: '（6） 内部审计如何与监督活动相互作用？', is_header: false },
  { seq: 70, content: '（7） 财务报告流程如何得到监督。', is_header: false },
  { seq: 71, content: '2. 基于这些测试结果，我确信企业层面监督控制有效运行。', is_header: false },
  { seq: 72, content: '四 监控业务单元（适用于集团审计）', is_header: true },
  { seq: 73, content: '1. 就管理层如何在其业务单元中评估风险获得理解并做记录。', is_header: false },
  { seq: 74, content: '2. 就风险评估对被审计单位执行业务单元监督的适当性进行评定。', is_header: false },
  { seq: 75, content: '3. 观察选定的业务单元中已建立的标准化业务单元流程和控制，以进行记录与测试。', is_header: false },
  { seq: 76, content: '4. 复核本年度内由内部审计完成的测试结果。', is_header: false },
  { seq: 77, content: '5. 获取由业务单元提交的财务分析报告，并执行下列程序：', is_header: false },
  { seq: 78, content: '（1） 确定此类分析是否由监督人员一贯执行。', is_header: false },
  { seq: 79, content: '（2） 确定工作是否被程序或其他标准的方法论支持。', is_header: false },
  { seq: 80, content: '（3） 确定预期和分析是否适合以识别潜在的误差。', is_header: false },
  { seq: 81, content: '（4） 确定关于对所识别出的异常情况进行跟踪与解决的证据得到了记录。', is_header: false },
  { seq: 82, content: '6. 基于该测试结果，针对业务单元实行监管控制的效果令人满意。', is_header: false },
  { seq: 83, content: '五 信息与沟通', is_header: true },
  { seq: 84, content: '1. 询问主要会计人员如下事项：', is_header: false },
  { seq: 85, content: '（1） 财务报告流程是否在恰当的时间向合适的人员传递正确的信息。', is_header: false },
  { seq: 86, content: '（2） 监控和企业管理所需的信息是否可得 。', is_header: false },
  { seq: 87, content: '（3） 是否存在实现收入目标的强大压力。', is_header: false },
  { seq: 88, content: '2. 根据这些测试结果，我确信信息与沟通控制的有效运行。', is_header: false },
  { seq: 89, content: '六 财务报告', is_header: false },
  { seq: 90, content: '1. 询问主要会计人员关于更改账户结构图的流程。', is_header: false },
  { seq: 91, content: '（1） 记录讨论内容，包括变更是如何生成，变更是如何批准，谁被授权做出变更以及记录的格式。', is_header: false },
  { seq: 92, content: '（2） 如果在此期间发生变动，请检查批准变动的文件。', is_header: false },
  { seq: 93, content: '2. 对每一个重要的会计职位：', is_header: false },
  { seq: 94, content: '（1） 确定在职人员的教育背景和工作经历。', is_header: false },
  { seq: 95, content: '（2） 检查他们参与了继续教育程序的相关支持性证据。', is_header: false },
  { seq: 96, content: '（3） 根据我们的经验，考虑相关人员个人经验以及过去所做的财务报告的质量。', is_header: false },
  { seq: 97, content: '3. 询问会计主管是否复核被审计单位在以下方面符合适用的会计准则和相关会计制度规定、法规或政策的规定的情况：', is_header: false },
  { seq: 98, content: '（1） 复核中用到的信息（交易与文献来源）', is_header: false },
  { seq: 99, content: '（2） 执行分析程序的频率以及下一次计划执行的时间。', is_header: false },
  { seq: 100, content: '（3） 在确定适当处理中使用的原则(高质量财务报告，实质重于形式)。', is_header: false },
  { seq: 101, content: '（4） 所执行的测试的程度及由谁来完成的。', is_header: false },
  { seq: 102, content: '（5） 记录的完成及其保存形式。', is_header: false },
  { seq: 103, content: '（6） 涉及的人员，若聘用专家，他们的资质如何。', is_header: false },
  { seq: 104, content: '（7） 检查复核的记录或观察一次复核。', is_header: false },
  { seq: 105, content: '4. 选定在规范性档案中规定的财务信息和其他信息的样本，并追溯到原始分录或其他支持性会计记录：', is_header: false },
  { seq: 106, content: '（1） 单个项目及/或合并总额被确认。', is_header: false },
  { seq: 107, content: '（2） 控制工具或其它查证信息完整性和准确性的方式均被使用并经过核实。', is_header: false },
  { seq: 108, content: '5. 调查流程以确认相对外部信息来源的披露，包括：', is_header: false },
  { seq: 109, content: '（1） 经执行的对比细节(经证实的披露以及所使用的外部资源)以及流程的频率。', is_header: false },
  { seq: 110, content: '（2） 经执行上述流程确认的项目例子。', is_header: false },
  { seq: 111, content: '（3） 项目如何得到解决，以及由谁来解决。', is_header: false },
  { seq: 112, content: '（4） 如何报告结果。', is_header: false },
  { seq: 113, content: '（5） 创建和保留的文件。', is_header: false },
  { seq: 114, content: '（6） 检查文件或审查复核流程。', is_header: false },
  { seq: 115, content: '6. 鉴于这些测试结果，我对财务报告控制的有效运行很满意。', is_header: false },
  { seq: 116, content: '七 对业务层面控制的影响', is_header: false },
  { seq: 117, content: '1. 企业层面控制是否可以以足够的精准程度运行以达到业务层面控制的模板，如有：', is_header: false },
  { seq: 118, content: '（1） 记录适用的循环和流程。', is_header: false },
  { seq: 119, content: '（2） 在企业层面控制完成控制目标的每一个流程中，记录企业层面控制。', is_header: false },
  { seq: 120, content: '（3） 在设计有效性中，将可应用的控制目标与控制相联系。', is_header: false },
  { seq: 121, content: '八 年终程序', is_header: false },
  { seq: 122, content: '1. 在年底，对企业层面控制持续有效操作执行询问。', is_header: false },
  { seq: 123, content: '九 对控制环境中与降低关联方关系及其交易导致的重大错报风险相关的内容进行测试：', is_header: false },
  { seq: 124, content: '1. 用于规范在何种情形下被审计单位可以从事特定类型关联方交易的内部职业道德手册，该手册已适当地向员工传达并得以贯彻执行。', is_header: false },
  { seq: 125, content: '2. 公开、及时披露管理层和治理层在关联方交易中的利益的政策和程序。', is_header: false },
  { seq: 126, content: '3. 被审计单位内部对识别、记录、汇总和披露关联方交易的职责分工。', is_header: false },
  { seq: 127, content: '4. 管理层和治理层就超出正常经营过程的重大关联方交易及时进行的讨论和披露，包括治理层是否通过向外部专业人员咨询等方式恰当质疑交易商业理由的合理性。', is_header: false },
  { seq: 128, content: '5. 对涉及现实或潜在利益冲突的关联方交易的批准，提供清晰的指引。例如，由独立于管理层的人员组成的治理层的下设委员会进行审批。', is_header: false },
  { seq: 129, content: '6. 内部审计人员的定期检查。', is_header: false },
  { seq: 130, content: '7. 管理层为解决关联方披露问题而采取的积极行动，如向注册会计师或外部法律顾问咨询。', is_header: false },
  { seq: 131, content: '8. 举报政策和程序。', is_header: false },
]

/**
 * 预解析的 C1 程序步骤（fallback 常量，无需运行时重新解析）
 */
let _cachedParsed: C1ProgramStep[] | null = null

export function getC1ProgramsFallback(): C1ProgramStep[] {
  if (!_cachedParsed) {
    _cachedParsed = parseC1Programs(C1_PROGRAM_ITEMS)
  }
  return _cachedParsed
}

/**
 * 按段 slug 过滤步骤
 */
export function filterBySection(steps: C1ProgramStep[], section: string): C1ProgramStep[] {
  return steps.filter((s) => s.section === section)
}
