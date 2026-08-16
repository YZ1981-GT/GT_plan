/**
 * entityVerifyGuidance.ts — X0-2「核实被函证单位信息」编制说明（只读方法论上下文）
 *
 * spec: k0-confirmation-source-alignment · Task 13（Requirement 8.4）
 *
 * 真源 = 源模板 `核实被函证单位信息K0-2` 的 `A28:A41`（openpyxl 直读固化在
 * `backend/tests/test_k0_source_template_facts.py::ENTITY_VERIFY_GUIDANCE`，
 * 前端守卫读该常量做跨前后端逐字交叉锁死）。
 *
 * 🔴 为什么只声明一份、不按枢纽分叉：
 *    七个函证枢纽的 X0-2 是同一张源模板结构（`test_{g0,h0,k0,l0}_source_template_facts.py`
 *    各自以 openpyxl 断言过 38 列 5 段），编制说明文字亦同源 ⇒ 平台侧一份常量。
 *    要改字面必须先改源模板（六份守卫会同时打红）。
 *
 * 🔴 说明 3 的「核实联系人的身份并记录工号（若有）」与 K0-3 跟函话术的工号占位
 *    交叉呼应（R8.4）—— 两处不得只改一处。
 */

export interface EntityVerifyGuidanceItem {
  /** 说明标题（逐字，含尾部全角冒号） */
  title: string
  /** 标题锚点（源模板 A 列坐标，供 tooltip 溯源） */
  anchor: string
  /** 正文要点（逐字，每项一条；说明 1 有四条子要点） */
  items: string[]
}

/**
 * 五条编制说明（逐字取自源模板 `A28:A41`）。
 *
 * ⚠️ `C26`「2.采用电子函证方式的应记录并检查回函能够证明电子地址或身份的信息…」
 *    是**回函核对块的列内提示**，不属于编制说明段 —— 后端守卫
 *    `test_entity_verify_guidance_anchors_are_in_column_a` 有反向自检钉死，
 *    不得混入本清单。
 */
export const ENTITY_VERIFY_GUIDANCE: readonly EntityVerifyGuidanceItem[] = Object.freeze([
  Object.freeze({
    title: '说明1：',
    anchor: 'A28',
    items: Object.freeze([
      '进行核实的信息应该包括单位名称，地址，以及联系人和电话。',
      '1.项目组可利用函证中心对接的企查查获取被函证单位地址，如果不一致的应使用多种方法来核实被函证单位的信息，如查找相关发票/合同，网站搜索，电话确认，邮件确认等，请详细记录核实的方式',
      '2.若检查了相关支持性文件或其他公开信息，请记录所检查的详细内容。',
      '3.请记录确认联系人身份的过程。注意：在银行函证中，也应注意核实联系人的身份并记录工号（若有）',
      '4.在核实结果中，应注明所检查的信息（包括单位名称、地址、联系人及电话等）是否与被函证单位信息相符。',
    ]) as unknown as string[],
  }),
  Object.freeze({
    title: '说明2：',
    anchor: 'A34',
    items: Object.freeze([
      '请详细记录核实函证被退回原因所进行的程序， 例如：询问，检查等程序的具体内容',
    ]) as unknown as string[],
  }),
  Object.freeze({
    title: '说明3：',
    anchor: 'A36',
    items: Object.freeze([
      '若退回的原因不合理或存在舞弊可能，审计项目组人员应及时告知项目负责人，并咨询有关针对舞弊的审计应对措施',
    ]) as unknown as string[],
  }),
  Object.freeze({
    title: '说明4：',
    anchor: 'A38',
    items: Object.freeze([
      '请跟进第二次发函的结果，记录是否送抵被函证方，对于仍被退回的函证，应进行进一步调查并考虑舞弊的可能，同时在相应底稿中记录与之相关的审计风险与对审计的影响。',
    ]) as unknown as string[],
  }),
  Object.freeze({
    title: '说明5：',
    anchor: 'A40',
    items: Object.freeze([
      '如果被询证者以传真、电子邮件方式回函，审计项目组应当直接接收，并验证传真、电子邮件回函的可靠性，要求被询证者在审计报告日之前寄回询证函原件',
    ]) as unknown as string[],
  }),
]) as readonly EntityVerifyGuidanceItem[]

/** 折叠区标题（源模板 `A27`） */
export const ENTITY_VERIFY_GUIDANCE_TITLE = '编制说明：'

/** 折叠区标题锚点 */
export const ENTITY_VERIFY_GUIDANCE_TITLE_ANCHOR = 'A27'
