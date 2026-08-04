/**
 * confirmationColumnSourceManifest.ts — X0-1 源模板列清单（契约守卫基准 / M0 硬前置）
 *
 * spec: confirmation-shared-model-extension（Requirement 8.1/8.2/9.2，决策 2；tasks 1.1）
 *
 * 本文件是「宁缺勿造」的 M0 硬前置成果：逐枢纽逐 sheet 对照致同 2025 源模板 X0-1
 * 实测录入真实列清单，作为 `resolveConfirmationColumns(cycle)` 的漂移守卫比对基准：
 *   Property 3：resolve 出的每列 key SHALL 在 CONFIRMATION_SOURCE_MANIFEST[cycle] 中有出处；漂移即失败。
 *   Property 9：Shared_Row_Model 每字段 SHALL 在此清单有出处或被登记为 CONFIRMATION_SOURCE_EXTRA。
 *
 * ─── 源模板实测结论（读 `BCD类底稿md/{循环}/{循环}底稿模板库.md` 逐列核对，2026-07-26） ───
 *
 * 【发现 A：D0/F0/G0/H0/K0/L0 六枢纽 X0-1 同构 28 列】
 *   六枢纽源模板 X0-1 的行级明细列**完全同构**（仅个别用词与索引号不同），列结构为：
 *     序号 / 询证函索引号 / 选取样本目的 / 被询证单位名称 / 账户或交易 / 金额 /
 *     函证方式 / 发函日期 / 发函单号 / 收件地址 / 地址核查是否一致 /
 *     是否收到回函 / 回函方式 / 是否相符 / 回函日期 / 回函快递单号 / 回函发出地址 /
 *     发函地址与回函地址是否一致 / 回函金额 / 差异 / 可确认金额 / 调节索引 / 其他说明备注 /
 *     是否采取替代程序 / 替代后可确认金额 / 替代后不可确认金额 / 替代程序索引号 / 审计结论
 *
 * 【发现 B：「发函询证纪要」是段（group）而非可填列】
 *   源模板顶部合并表头把「发函询证纪要」作为**段标题**，其下辖 选取样本目的 / 被询证单位名称 /
 *   账户或交易 / 金额 四子列。源模板中**没有名为「发函询证纪要」的标量可填列**。
 *   现实现 confirmationColumnSpec 的 `send_memo` 是承载「纪要」文本的**建模列**（源外建模，非源列），
 *   仅 K0/L0 variant 启用。守卫据本清单放行（见 CONFIRMATION_SOURCE_MANIFEST K0/L0 注释）。
 *
 * 【发现 C：「审计结论」是所有循环的真实末列（含 E0），非 K0/L0 专属】
 *   design 早期「实证基线」称「只有 K0/L0 有审计结论列」——经源模板逐列核对**不准确**：
 *   D0/E0/F0/G0/H0/K0/L0 七枢纽 X0-1 源模板**均以「审计结论」为末列**。
 *   故 `row_conclusion` 登记为七枢纽共性列（COMMON_KEYS）。confirmationColumnSpec 当前仅为
 *   K0/L0 渲染该列（打磨/取舍），属实现侧收窄；manifest 忠于源模板记全集（resolve⊆manifest 恒成立）。
 *   ⚠️ 待决策（tasks 2.x/3.x）：是否把 row_conclusion 扩展到 D0/F0/G0/H0 渲染。此处只登记源真相。
 *
 * 【发现 D：E0 结构异构（银行/票据/预付多子版本）】
 *   E0-1 源模板与其余六枢纽**不同构**：
 *     - 无「选取样本目的」列；无「替代程序」段（是否采取替代程序/替代后可/不可确认金额/替代程序索引号）；
 *     - 增「账号或理财产品名称」，金额拆「发函金额（原币）/币种/汇率/发函金额（本位币）」双列 + 汇率；
 *       可确认金额拆「可确认金额（原币）/可确认金额（本位币）」；
 *     - 银行版增银行专属回函列：抵押质押等事项回函说明 / 其他函证事项回函是否相符 /
 *       函证不符事项说明 / 不符事项检查索引号；
 *     - 存在多个子版本：银行版、应付票据版（增「二级科目」「账号/银行承兑汇票号码/理财产品名称」）、
 *       预付账款/应付款多科目版（该版又含「选取样本目的」与「替代程序」段）。
 *   宁缺勿造：E0 银行专属回函列（抵押质押等/其他函证事项/不符事项检查索引号）暂无 columnspec 承载，
 *   **不臆造对应 key**，标记为「E0 待补列（银行专属回函块）」（见文末 E0_PENDING_COLUMNS）。
 *
 * 【发现 E：各枢纽用词差异（Requirement 8.3 不强行统一，见 CONFIRMATION_SOURCE_COLUMN_LABELS）】
 *   - 账户/交易列：D0/F0/K0/L0 用「账户/交易」；G0/H0 亦「账户/交易」；本模型映射到既有 account_type（科目大类语义保留）
 *   - 金额列：D0/F0/K0/L0 用「金额」；G0 用「账面期末余额」；H0 用「金额或合同条款」；E0 用「发函金额（原币/本位币）」
 *   - 回函发出地址：D0/F0/H0/K0/L0/E0 用「回函发出地址」；G0 用「回函地址」
 *   - 发函单号：K0 用「发函单号/跟函记录索引号」；其余「发函单号」
 *   - 调节索引：D0/F0=（F0-4）；G0=（G0-3）；H0=差异核对索引（H0-4）；K0=（K1-12）；L0=（F0-4）
 *   - 回函金额/差异/可确认金额：H0 为「回函金额/条款」「差异（金额/条款）」「可确认金额/条款」（金额或条款双口径）
 */

import type { ConfirmCycle } from './confirmationColumnSpec'

/**
 * 每枢纽源模板 X0-1 的**真实源列名清单**（各枢纽自身用词，逐列录入 / 发现 E）。
 * 仅供人工核对与文档追溯；机器守卫用下方 key 化的 CONFIRMATION_SOURCE_MANIFEST。
 * 「发函询证纪要」是段标题不列入（发现 B）。
 */
export const CONFIRMATION_SOURCE_COLUMN_LABELS: Record<ConfirmCycle, string[]> = {
  // D0 应收账款/合同负债/销售 —— 28 列（发函询证纪要段 + 审计结论列）
  D0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '金额',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额', '调节索引（F0-4）', '其他说明/备注',
    '是否采取替代程序', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
  // E0 银行/货币资金 —— 异构（无选取样本目的/无替代程序段；原币本位币汇率；银行专属回函列）
  E0: [
    '序号', '询证函索引号', '被询证单位名称', '账户/交易', '账号/理财产品名称',
    '发函金额（原币）', '币种', '汇率', '发函金额（本位币）',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额（原币）', '可确认金额（本位币）',
    '抵押质押等事项回函说明', '其他函证事项回函是否相符', '函证不符事项说明', '不符事项检查索引号', '审计结论',
  ],
  // F0 预付账款/应付票据/应付账款/采购 —— 与 D0 同构 28 列
  F0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '金额',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额', '调节索引（F0-4）', '其他说明/备注',
    '是否采取替代程序', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
  // G0 投资循环 —— 28 列（金额=账面期末余额；回函发出地址=回函地址；调节索引=G0-3）
  G0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '账面期末余额',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函（√）', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额', '调节索引（G0-3）', '其他说明/备注',
    '是否采取替代程序（√）', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
  // H0 固定资产/工程物资/使用权资产/租赁负债 —— 28 列（金额或合同条款双口径；差异核对索引 H0-4）
  H0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '金额或合同条款',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额/条款', '差异（金额/条款）', '可确认金额/条款', '差异核对索引（H0-4）', '其他说明/备注',
    '是否采取替代程序', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
  // K0 其他应收款/其他应付款 —— 28 列（发函单号/跟函记录索引号；调节索引 K1-12）
  K0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '金额',
    '函证方式', '发函日期', '发函单号/跟函记录索引号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额', '调节索引（K1-12）', '其他说明/备注',
    '是否采取替代程序', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
  // L0 长期应付款/应付债券 —— 与 D0 同构 28 列（调节索引 F0-4）
  L0: [
    '序号', '询证函索引号', '选取样本目的', '被询证单位名称', '账户/交易', '金额',
    '函证方式', '发函日期', '发函单号', '收件地址', '地址核查是否一致',
    '是否收到回函', '回函方式', '是否相符', '回函日期', '回函快递单号', '回函发出地址',
    '发函地址与回函地址是否一致', '回函金额', '差异', '可确认金额', '调节索引（F0-4）', '其他说明/备注',
    '是否采取替代程序', '替代后可确认金额', '替代后不可确认金额', '替代程序索引号', '审计结论',
  ],
}

/**
 * 七枢纽共性列 key（BASE_CONFIRMATION_COLUMNS 的 key 集合 + 通用末列 row_conclusion）。
 * 与 CONFIRMATION_SOURCE_COLUMN_LABELS 中「除各枢纽特有列外」的部分一一对应。
 * row_conclusion（审计结论）为源模板七枢纽通用末列（发现 C），故登记为共性。
 */
const COMMON_KEYS: string[] = [
  // 发函信息
  'seq', 'sample_purpose', 'confirm_index', 'account_type', 'entity_name',
  'entity_address', 'contact_person', 'contact_phone', 'amount', 'currency',
  'confirmation_method', 'send_date', 'send_doc_no', 'send_addr_match',
  // 收到回函
  'is_replied', 'reply_method', 'reply_date', 'reply_courier_no',
  'reply_from_addr', 'send_reply_addr_match',
  // 回函金额确认
  'reply_amount', 'match_status', 'difference', 'confirmed_amount',
  // 未收到回函的替代程序
  'use_alternative', 'alt_confirmed', 'alt_unconfirmed', 'alt_ref_index',
  'diff_ref_index', 'remark',
  // 审计结论（源模板七枢纽通用末列，发现 C）
  'row_conclusion',
]

/**
 * 每枢纽源模板 X0-1 真实列清单（key 化）= 共性列 ∪ 该枢纽特有列。
 * 守卫 Property 3：resolveConfirmationColumns(cycle) 每列 key ∈ 本清单[cycle]（resolve ⊆ manifest）。
 *
 * 说明（宁缺勿造）：
 *   - row_conclusion 已并入 COMMON_KEYS（发现 C，七枢纽通用），故各枢纽均含。
 *   - K0/L0 的 send_memo 是「发函询证纪要」段的建模承载列（发现 B，源模板无标量同名列），
 *     在此登记为 K0/L0 出处以放行守卫；用词见 confirmationColumnSpec.ColumnDef.label。
 *   - E0 保留共性列（含 sample_purpose/替代程序键）因 E0 预付账款子版本确有这些列；
 *     E0 银行专属回函列（发现 D）暂不臆造 key，见 E0_PENDING_COLUMNS。
 */
export const CONFIRMATION_SOURCE_MANIFEST: Record<ConfirmCycle, string[]> = {
  D0: [...COMMON_KEYS],
  E0: [...COMMON_KEYS, 'account_no', 'amount_orig', 'fx_rate', 'confirmed_amount_orig', 'pledge_note', 'other_items_match', 'mismatch_note', 'e0_row_conclusion'],
  F0: [...COMMON_KEYS],
  // G0 的 `send_channel` = 源模板「函证方式」列（G0-2!C7:C19 的 DV 实证为渠道
  // `邮寄/跟函/电子函证/其他`，经 VLOOKUP 带入 G0-1!G），与承载积极式/消极式的
  // `confirmation_method` 是两个维度 → 源列「函证方式」由 send_channel 承载。
  // spec: g0-confirmation-source-alignment R2.3
  G0: [...COMMON_KEYS, 'send_channel'],
  // H0 的 `send_channel` = 源模板「函证方式」列（DV 实证为渠道 邮寄/跟函/电子函证/其他，
  // 见 X0-2!C7），与承载积极式/消极式的 `confirmation_method` 是两个维度 →
  // 源列「函证方式」由 send_channel 承载，故在此登记出处。
  // spec: h0-confirmation-source-fidelity-and-linkage R7.2
  H0: [...COMMON_KEYS, 'send_channel', 'term_book', 'term_reply', 'term_match', 'term_note'],
  K0: [...COMMON_KEYS, 'send_memo'],
  L0: [...COMMON_KEYS, 'send_memo'],
}

/**
 * E0 银行专属回函列（源模板 E0-1 银行版确有，但当前 columnspec 无承载列）。
 * 宁缺勿造：**不臆造 ConfirmationRow 字段 key**，登记为「待逐列核实/待补列」，
 * 供 Wave 2（tasks 3.2 E0 variant）决策是否补 columnspec 列。
 */
export const E0_PENDING_COLUMNS: string[] = [
  '抵押质押等事项回函说明',
  '其他函证事项回函是否相符',
  '函证不符事项说明',
  '不符事项检查索引号',
  '二级科目（应付票据子版本）',
  '账号/银行承兑汇票号码/理财产品名称（应付票据子版本）',
]

/**
 * ─── X0-2 ↔ X0-7 同义列归属判定（Requirement 3.5，design 决策 5；tasks 1.1） ───
 *
 * 源模板逐列核对结论（读 L0-2 核实被函证单位信息 + L0-6 回函可靠性验证记录）：
 *
 *   X0-2「核实被函证单位信息」的「回函信息情况（回函核对记录）」块含：
 *     回函方式 / 是否为原件 / 是否直接收到回函 / 回函发出地址 / 回函寄件人 / 回函电话 /
 *     发函地址与回函地址是否一致 / 发函收件人与回函寄件人是否一致 /
 *     发函收件人电话与回函寄件人电话是否一致 / 不一致的说明 / 核实支持性证据索引号 / 跟函函证控制过程
 *
 *   X0-7「邮件/传真回函可靠性验证记录」含：
 *     回函方式 / 是否由审计项目组直接接收 / 是否寄回原件 / 被函证者身份确认 /
 *     发函及回函传真信息及验证 / 发函邮箱 / 回函邮箱 / 邮箱可靠性验证 /
 *     是否致电被函证者确认 / 对函证信息可靠性的考虑 / 回函可靠性结论
 *
 *   ⇒ 三项同义列在 X0-2 与 X0-7 源模板中**同时存在**：
 *        回函方式        （X0-2「回函方式」        ↔ X0-7「回函方式」）
 *        是否原件        （X0-2「是否为原件」      ↔ X0-7「是否寄回原件」）
 *        是否直接接收    （X0-2「是否直接收到回函」↔ X0-7「是否由审计项目组直接接收」）
 *
 * 【归属决策（design 决策 5）】：这三项以 **X0-7（回函可靠性核对）为唯一录入位置**。
 *   X0-2 侧对应字段（EntityVerifyRow.is_original / direct_received）为**只读引用**（UI 层禁编辑，
 *   明示「详见 X0-7」），不形成两处可各自编辑的双真源（Property 8）。
 *   X0-2 补齐的是 X0-7 没有的差集：回函发出地址 / 寄件人 / 电话 / 三项一致性判定 /
 *   不一致说明 / 核实证据索引 / 跟函控制过程索引。
 */
export const X02_X07_OVERLAP_OWNERSHIP: Array<{
  semantic: string
  x02_label: string
  x07_label: string
  owner: 'X0-7'
  x02_role: 'readonly-reference'
}> = [
  { semantic: '回函方式', x02_label: '回函方式', x07_label: '回函方式', owner: 'X0-7', x02_role: 'readonly-reference' },
  { semantic: '是否原件', x02_label: '是否为原件', x07_label: '是否寄回原件', owner: 'X0-7', x02_role: 'readonly-reference' },
  { semantic: '是否直接接收', x02_label: '是否直接收到回函', x07_label: '是否由审计项目组直接接收', owner: 'X0-7', x02_role: 'readonly-reference' },
]

/**
 * 现有实现中超出源模板的字段（源外增强，Requirement 8.4 保留不删）。
 * Shared_Row_Model 现有但源模板 X0-1 无独立列的字段登记于此，Property 9 守卫据此放行。
 */
export const CONFIRMATION_SOURCE_EXTRA: Array<{ key: string; reason: string }> = [
  { key: '_row_id', reason: '前端内部行 ID（UUID），非源模板列' },
  { key: '_source', reason: '数据来源标识（auto/manual/import），平台内部质量标记' },
  { key: '_overridden', reason: '是否被用户覆盖，平台内部质量标记' },
  { key: '_hub_confirmation_id', reason: '函证中心台账投影 id（syncHubFromSummary 写回），平台内部' },
  { key: 'electronic_reply', reason: '是否电子回函，平台反舞弊/可靠性联动标记（源外增强）' },
  { key: 'reliability_verified', reason: '可靠性已验证，联动 X0-7 的行级标记（源外增强）' },
  { key: 'fraud_risk_flag', reason: '舞弊风险标志，联动 X0-8 舞弊风险迹象（源外增强）' },
]

/** 全部已登记 key（manifest 全并集 + 源外增强），供守卫「每字段可追溯」使用 */
export function allRegisteredConfirmationKeys(): Set<string> {
  const s = new Set<string>()
  for (const cycle of Object.keys(CONFIRMATION_SOURCE_MANIFEST) as ConfirmCycle[]) {
    for (const k of CONFIRMATION_SOURCE_MANIFEST[cycle]) s.add(k)
  }
  for (const e of CONFIRMATION_SOURCE_EXTRA) s.add(e.key)
  return s
}
