/**
 * fraudRiskPresets.ts — 函证程序舞弊风险迹象 19 条（**平台唯一真源**）
 *
 * 🔴 文字逐字取自源模板，不得改写、不得意译（2026-08-03 openpyxl 直读实证）：
 * `函证程序舞弊风险评价表{D0-8,E0-8,F0-8,H0-7,K0-8,L0-7}` 的 A6:A24，
 * 六张表的 19 条内容**完全一致**（去序号去尾标点后 md5 `9abe16b804` 全等）
 * → 跨循环共用一份常量在事实层面成立。
 *
 * 依据：《中国注册会计师审计准则问题解答第2号——函证》
 * （源模板 F0-8 A31 编制说明第 1 条明示）。
 *
 * ⚠️ 2026-08-03 更正记录（f0-confirmation-linkage-and-structural-enhancement Task 27）：
 * 本文件原 19 条描述**与任何源模板都不一致**（如原第 1 条写「被审计单位管理层凌驾于
 * 内部控制之上」，源模板实为「管理层不允许寄发询证函」），属自造内容；
 * 原 `item_18_19_examples` tooltip（分行业举例）在源模板中亦不存在。
 * 现按源模板逐字重写，并把两条真实举例（J18/J19）挂回它们真正解释的条目：
 * - J18 的内容讲的是「回函率」→ 对应第 **14** 条（源模板把注写在上一行，属排版偏移）
 * - J19 的内容讲的是「被询证者缺乏独立性」→ 对应第 **15** 条
 * 守卫 `backend/tests/test_fraud_risk_presets_source_fidelity.py` 以 xlsx 为裁决者交叉锁死。
 */
import type { FraudRiskItem } from './fraudRiskTypes'

// ─── 19 条预置舞弊风险迹象（源模板 A6:A24 逐字） ────────────────────────────

export const PRESET_FRAUD_ITEMS: FraudRiskItem[] = [
  {
    seq: 1,
    description: '管理层不允许寄发询证函',
    _preset: true,
  },
  {
    seq: 2,
    description: '管理层过度热情配合函证程序',
    _preset: true,
  },
  {
    seq: 3,
    description: '管理层试图干预、拦截、篡改询证函或回函，如坚持以特定的方式发送询证函',
    _preset: true,
  },
  {
    seq: 4,
    description: '管理层提供的函证相关信息含糊、矛盾、不完整或有缺失',
    _preset: true,
  },
  {
    seq: 5,
    description: '被询证者将回函寄至被审计单位，被审计单位将其转交注册会计师',
    _preset: true,
  },
  {
    seq: 6,
    description: '注册会计师跟进访问被询证者，发现回函信息与被询证者记录不一致',
    _preset: true,
  },
  {
    seq: 7,
    description: '从私人电子信箱发送的回函',
    _preset: true,
  },
  {
    seq: 8,
    description: '收到同一日期发回的、相同笔迹的多份回函',
    _preset: true,
  },
  {
    seq: 9,
    description: '收到的回函与发出的询证函不是同一份、不是原件',
    _preset: true,
  },
  {
    seq: 10,
    description: '不同被询证者回函信封上的联系方式（地址、电话等）相同或相近；位于不同地址的多家被询证者的回函邮戳显示的发函地址相同',
    _preset: true,
  },
  {
    seq: 11,
    description: '印章模糊不清难以核对，或印章存在明显瑕疵，或与被询证者不一致',
    _preset: true,
  },
  {
    seq: 12,
    description: '收到不同被询证者用快递寄回的回函，但快递的交寄人或发件人是同一个人或是被审计单位的员工（或关联方），或者虽然寄件人名字不同，但手机号或其他联系方式相同，或者不同被询证者回函单号相连或相近',
    _preset: true,
  },
  {
    seq: 13,
    description: '回函显示的发函地址与被审计单位记录的被询证者的地址不一致',
    _preset: true,
  },
  {
    seq: 14,
    description: '不正常的回函率',
    tooltip_key: 'item_14_reply_rate',
    _preset: true,
  },
  {
    seq: 15,
    description: '被询证者缺乏独立性；配合被审计单位，向注册会计师提供不真实或不准确的回函信息，隐瞒相关事实和情况',
    tooltip_key: 'item_15_independence',
    _preset: true,
  },
  {
    seq: 16,
    description: '管理层不愿意提高函证所涉及信息（如抵押、担保等信息）的披露质量，使财务报表更为完整透明，但又不能提供合理解释',
    _preset: true,
  },
  {
    seq: 17,
    description: '回函印章与以前期间收到的回函印章不一致',
    _preset: true,
  },
  {
    seq: 18,
    description: '回函中包含免责或其他限制性条款',
    _preset: true,
  },
  {
    seq: 19,
    description: '第三方对函证信息有误的询证函作出与函证信息相符的回函，或对前后两次函证信息有差异的询证函均作出信息相符的回函',
    _preset: true,
  },
]

// ─── tooltip 举例（源模板 J 列逐字，只有两条，不得增补） ─────────────────────

export const ITEM_TOOLTIPS_D08: Record<string, string> = {
  /** 第 14 条「不正常的回函率」举例 — 源模板 J18 */
  item_14_reply_rate:
    '例如：银行函证未回函；与以前年度相比，回函率异常偏高或回函率重大变动；向被审计单位债权人发送的询证函回函率很低；',

  /** 第 15 条「被询证者缺乏独立性」举例 — 源模板 J19 */
  item_15_independence:
    '例如：被审计单位及其管理层能够对被询证者施加重大影响以使其向注册会计师提供虚假或误导信息（如被审计单位是被询证者唯一或重要的客户或供应商）；被询证者既是被审计单位资产的保管人又是资产的管理者。',
}

// ─── 编制说明（源模板 A26 汇总行 + A31 编制说明） ────────────────────────────

export const GUIDANCE_NOTES_D08 = {
  /** ① 顶部说明 — 源模板 A26 汇总行 + A31 编制说明第 1 条 */
  top_note:
    '汇总上述所有已发现的舞弊迹象，在“汇总识别的风险因素”中记录并区分财务报表层次的风险和认定层次的风险，制订初步的应对措施。'
    + '本底稿系根据《中国注册会计师审计准则问题解答第2号——函证》的要求，对执行函证程序过程中需要关注的舞弊风险迹象厘定；'
    + '在进行了解时，应考虑上述表格中列示的项目，但考虑内容不限于这些内容。',
  /** ② 应对措施 placeholder */
  countermeasure_placeholder: '请描述针对该风险迹象的具体应对措施（如扩大样本范围/追加审计程序/与管理层沟通等）',
  /** ③ 索引列 tooltip — 源模板列头「索引号或信息来源」 */
  source_ref_tooltip: '填写支持性底稿的索引号或信息来源（如 D0-1/D0-4/D0-7 等），可跳转查看相关底稿。',
  /** ④ 是=是 条件提示 — 源模板 A26 汇总行去向 B50 */
  exist_yes_warning: '已识别舞弊风险迹象，请填写应对措施。汇总结果应记录到 B50 风险评估底稿，并区分财务报表层次与认定层次的风险。',
} as const
