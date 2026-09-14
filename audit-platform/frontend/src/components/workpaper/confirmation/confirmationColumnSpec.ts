/**
 * confirmationColumnSpec.ts — X0-1 函证结果汇总表 列配置驱动层
 *
 * spec: confirmation-shared-model-extension（决策 1/2/3/4）
 *
 * 现状 `ConfirmationMaster.vue` 列硬编码。补 ~8 共性列 + 三类 Cycle_Variant 列若继续
 * 硬编码 + if-else 不可维护且违反 Requirement 2.1「配置驱动而非 if-else」。
 * 本文件抽 `ColumnDef`，`resolveConfirmationColumns(cycle)` 返回该枢纽应渲染的列
 * （BASE ∪ 该枢纽 variant），Master 用 v-for 渲染，分段表头按 `ColumnDef.group` 分组。
 *
 * 铁律：
 * - 各枢纽源模板用词不同不强行统一（Requirement 8.3）→ `label` 按各自源模板
 * - 源模板没有的列不进集合（Requirement 2.5 空列噪声避免）
 * - 每列 `source` 标注源模板出处（Requirement 8.2）
 */

export type ConfirmCycle = 'D0' | 'E0' | 'F0' | 'G0' | 'H0' | 'K0' | 'L0'

export type ColumnGroup =
  | 'send_info' // 发函信息
  | 'reply_info' // 收到回函
  | 'reply_amount' // 回函金额确认
  | 'alternative' // 未收到回函的替代程序
  | 'send_memo' // 发函询证纪要（K0/L0）
  | 'row_summary' // 行级汇总与审计结论（E0）

export const COLUMN_GROUP_LABELS: Record<ColumnGroup, string> = {
  send_info: '发函信息',
  reply_info: '收到回函',
  reply_amount: '回函金额确认',
  alternative: '未收到回函的替代程序',
  send_memo: '发函询证纪要',
  row_summary: '行级审计结论',
}

export interface ColumnDef {
  /** 对应 ConfirmationRow 字段名 */
  key: string
  /** 源模板列名（各枢纽用词，不强行统一） */
  label: string
  group: ColumnGroup
  width?: number
  minWidth?: number
  align?: 'left' | 'right' | 'center'
  editable?: boolean
  kind?: 'text' | 'number' | 'amount' | 'date' | 'bool' | 'select'
  /** 源模板出处「枢纽·sheet·列名」（Requirement 8.2） */
  source: string
  /** 固定列（关键列横向滚动仍可辨识，Requirement 6.4） */
  fixed?: 'left' | 'right'
  /** 派生列（自动计算，只读，Requirement 1.5） */
  derived?: boolean
}

// ─── BASE：七枢纽共性列（含本 spec 补的 8 个共性新列 + 既有列） ──────────────

export const BASE_CONFIRMATION_COLUMNS: ColumnDef[] = [
  // 发函信息
  { key: 'seq', label: '序号', group: 'send_info', width: 50, align: 'center', editable: false, kind: 'number', fixed: 'left', source: 'X0-1·序号' },
  { key: 'sample_purpose', label: '选取样本目的', group: 'send_info', minWidth: 120, kind: 'text', source: 'X0-1·选取样本目的' },
  { key: 'confirm_index', label: '函证索引号', group: 'send_info', width: 90, kind: 'text', fixed: 'left', source: 'X0-1·函证索引号' },
  { key: 'account_type', label: '科目', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·科目大类' },
  { key: 'entity_name', label: '被询证单位名称', group: 'send_info', minWidth: 140, kind: 'text', fixed: 'left', source: 'X0-1·被询证单位名称' },
  { key: 'entity_address', label: '地址', group: 'send_info', minWidth: 130, kind: 'text', source: 'X0-1·地址' },
  { key: 'contact_person', label: '联系人', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·联系人' },
  { key: 'contact_phone', label: '联系电话', group: 'send_info', width: 110, kind: 'text', source: 'X0-1·联系电话' },
  { key: 'amount', label: '函证金额', group: 'send_info', minWidth: 110, align: 'right', kind: 'amount', source: 'X0-1·函证金额' },
  { key: 'currency', label: '币种', group: 'send_info', width: 70, kind: 'text', source: 'X0-1·币种' },
  { key: 'confirmation_method', label: '函证方式', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·函证方式' },
  { key: 'send_date', label: '发函日期', group: 'send_info', width: 110, kind: 'date', source: 'X0-1·发函日期' },
  { key: 'send_doc_no', label: '发函单号', group: 'send_info', width: 100, kind: 'text', source: 'X0-1·发函单号' },
  { key: 'send_addr_match', label: '收件地址核查是否一致', group: 'send_info', width: 120, align: 'center', kind: 'select', source: 'X0-1·收件地址核查是否一致' },

  // 收到回函
  { key: 'is_replied', label: '是否已回函', group: 'reply_info', width: 80, align: 'center', kind: 'bool', source: 'X0-1·是否已回函' },
  { key: 'reply_method', label: '回函方式', group: 'reply_info', width: 90, kind: 'text', source: 'X0-1·回函方式' },
  { key: 'reply_date', label: '收函日期', group: 'reply_info', width: 110, kind: 'date', source: 'X0-1·收函日期' },
  { key: 'reply_courier_no', label: '回函快递单号', group: 'reply_info', width: 110, kind: 'text', source: 'X0-1·回函快递单号' },
  { key: 'reply_from_addr', label: '回函发出地址', group: 'reply_info', minWidth: 130, kind: 'text', source: 'X0-1·回函发出地址' },
  { key: 'send_reply_addr_match', label: '发函地址与回函地址是否一致', group: 'reply_info', width: 130, align: 'center', kind: 'select', source: 'X0-1·发函地址与回函地址是否一致' },

  // 回函金额确认
  { key: 'reply_amount', label: '回函金额', group: 'reply_amount', minWidth: 110, align: 'right', kind: 'amount', source: 'X0-1·回函金额' },
  { key: 'match_status', label: '相符情况', group: 'reply_amount', width: 80, align: 'center', kind: 'select', source: 'X0-1·相符情况' },
  { key: 'difference', label: '差异金额', group: 'reply_amount', minWidth: 100, align: 'right', kind: 'amount', editable: false, derived: true, source: 'X0-1·差异金额(自动)' },
  { key: 'confirmed_amount', label: '可确认金额', group: 'reply_amount', minWidth: 110, align: 'right', kind: 'amount', editable: false, derived: true, source: 'X0-1·可确认金额(自动)' },

  // 未收到回函的替代程序
  { key: 'use_alternative', label: '是否采取替代程序', group: 'alternative', width: 110, align: 'center', kind: 'bool', source: 'X0-1·是否采取替代程序' },
  { key: 'alt_confirmed', label: '替代程序确认金额', group: 'alternative', minWidth: 120, align: 'right', kind: 'amount', source: 'X0-1·替代程序确认金额' },
  { key: 'alt_unconfirmed', label: '替代后不可确认金额', group: 'alternative', minWidth: 130, align: 'right', kind: 'amount', source: 'X0-1·替代后不可确认金额' },
  { key: 'alt_ref_index', label: '替代程序索引', group: 'alternative', width: 100, kind: 'text', source: 'X0-1·替代程序索引' },
  { key: 'diff_ref_index', label: '差异调节表索引', group: 'alternative', width: 100, kind: 'text', source: 'X0-1·差异调节表索引' },
  { key: 'remark', label: '备注', group: 'alternative', minWidth: 120, kind: 'text', source: 'X0-1·备注' },
]

// ─── Cycle_Variant 列定义（仅部分枢纽源模板存在） ───────────────────────────

const VARIANT_COLUMN_DEFS: Record<string, ColumnDef> = {
  /**
   * 🔴🔴 **伪列 `send_memo` 与其配套的 `row_conclusion` def 已于 2026-08-07 全部删除**
   * （`k0-confirmation-source-alignment` R2.1/R2.4，L0 侧已于其自身 spec 先行撤下）。
   *
   * 判据（openpyxl `merged_cells.ranges` 实证，K0/L0 两侧同款）：
   * 源模板 `X0-1!C5:F5` 是「发函询证纪要」**跨 4 列的合并段头**，下辖
   * `C 选取样本目的` / `D 被询证单位名称` / `E 账户/交易` / `F 金额` 四列
   * → 把段头实现成一个自由文本列 = 给宽表凭空多出源模板不存在的输入位（**伪列**）。
   * 段本身（`ColumnGroup.send_memo`）**保留**：那四列现由 `CYCLE_COLUMN_GROUP_OVERRIDES`
   * 归入该段，与源模板逐段对应。
   *
   * `row_conclusion` 的旧 def（group 曾是 `send_memo`）同样删除 —— 源 `AB5` 是与前五段
   * **并列的独立末列**，不在纪要段内；四个循环现各有自己的注册项（`{e0,g0,h0,k0,l0}_row_conclusion`）。
   *
   * 🔴 **`ConfirmationRow.send_memo` / `row_conclusion` 两个字段一律不删**
   * （既有项目可能已填值，数据零丢失红线）；`send_memo` 的历史值由
   * `ConfirmationDetail.vue` 的 `v-if="row.send_memo"` 只读分支呈现并提示改填对应分段列。
   *
   * 🔴 `l0_row_conclusion` / `k0_row_conclusion` 的定义在下方 `g0_row_conclusion` 之后
   *    （与 h0/g0 聚在一处）。此处**不得再写一条** —— 对象字面量重复键会被静默取后者，
   *    `get_diagnostics` / vitest / Vite transform 三层都查不出（本文件曾真的重复过一次）。
   */

  // E0 原币/本位币/汇率（本位币复用既有 amount/confirmed_amount，见决策 3）
  account_no: { key: 'account_no', label: '账号或理财产品名称', group: 'send_info', minWidth: 140, kind: 'text', source: 'E0-1·账号或理财产品名称' },
  amount_orig: { key: 'amount_orig', label: '发函金额（原币）', group: 'send_info', minWidth: 120, align: 'right', kind: 'amount', source: 'E0-1·发函金额（原币）' },
  fx_rate: { key: 'fx_rate', label: '汇率', group: 'reply_amount', width: 90, align: 'right', kind: 'number', source: 'E0-1·汇率' },
  confirmed_amount_orig: { key: 'confirmed_amount_orig', label: '可确认金额（原币）', group: 'reply_amount', minWidth: 130, align: 'right', kind: 'amount', source: 'E0-1·可确认金额（原币）' },

  // E0 尾部四列（源模板 Z~AD，不属于前四组）
  /**
   * H0 行级审计结论 —— 源模板 H0-1 AB 列（AB5:AB7 rowspan，五段之外的独立末列）。
   *
   * 注册 key 用 `h0_row_conclusion` 以免与 K0/L0 的 `row_conclusion` def 冲突，
   * 但列 `key` 仍是 `row_conclusion` —— 与 COMMON_KEYS 同字段，故 `resolve ⊆ manifest` 恒成立，
   * 且与 K0/L0 共享同一持久化字段（同一语义不该两个字段）。
   * group 用 `row_summary`（「行级审计结论」）而非 K0/L0 的 `send_memo`（「发函询证纪要」）——
   * H0 源模板的 AB 列不在发函询证纪要段内。
   * spec: h0-confirmation-source-fidelity-and-linkage R6.1
   */
  h0_row_conclusion: { key: 'row_conclusion', label: '审计结论', group: 'row_summary', minWidth: 140, kind: 'text', source: 'H0-1·AB列·审计结论' },

  /**
   * G0 行级审计结论 —— 源模板 G0-1 AB 列（`AB5:AB7` rowspan，五段之外的独立末列）。
   *
   * 与 `h0_row_conclusion` 同形（列 `key` 同为 `row_conclusion`，group 同为 `row_summary`），
   * 另立注册 key 只为让 `source` 如实指向 G0-1；不可复用 H0 那条，否则溯源标注会串枢纽。
   * spec: g0-confirmation-source-alignment R2.1
   */
  g0_row_conclusion: { key: 'row_conclusion', label: '审计结论', group: 'row_summary', minWidth: 140, kind: 'text', source: 'G0-1·AB列·审计结论' },

  /**
   * L0 行级审计结论 —— 源模板 L0-1 AB 列（`AB5:AB7` rowspan，四段之外的独立末列）。
   *
   * 与 `h0_row_conclusion` / `g0_row_conclusion` 同形（列 `key` 同为 `row_conclusion`，
   * group 同为 `row_summary`），另立注册 key 只为让 `source` 如实指向 L0-1。
   *
   * 🔴 改造前 L0 用的是 `row_conclusion` def（group=`send_memo`「发函询证纪要」），
   *    而源模板 `AB5:AB7` 是**独立末列**、不在纪要段内 → 分段表头把它错归一段。
   * spec: l0-confirmation-source-alignment R4.3
   */
  l0_row_conclusion: { key: 'row_conclusion', label: '审计结论', group: 'row_summary', minWidth: 140, kind: 'text', source: 'L0-1·AB列·审计结论' },

  /**
   * K0 行级审计结论 —— 源模板 K0-1 `AB5:AB6` rowspan（六段之外的独立末列）。
   *
   * 与 `h0_row_conclusion` / `g0_row_conclusion` / `l0_row_conclusion` 同形
   * （列 `key` 同为 `row_conclusion`，group 同为 `row_summary`），另立注册 key
   * 只为让 `source` 如实指向 K0-1。
   *
   * 🔴 改造前 K0 用的是已删除的 `row_conclusion` def（group=`send_memo`「发函询证纪要」），
   *    而源 `AB5` 是**独立末列**、不在纪要段内 → 分段表头把它错归一段。
   * spec: k0-confirmation-source-alignment R2.4
   */
  k0_row_conclusion: { key: 'row_conclusion', label: '审计结论', group: 'row_summary', minWidth: 140, kind: 'text', source: 'K0-1·AB列·审计结论' },

  pledge_note: { key: 'pledge_note', label: '抵押质押等事项回函说明', group: 'row_summary', minWidth: 160, kind: 'text', source: 'E0-1·Z列·抵押质押等事项回函说明' },
  other_items_match: { key: 'other_items_match', label: '其他函证事项回函是否相符', group: 'row_summary', width: 130, align: 'center', kind: 'select', source: 'E0-1·AA列·其他函证事项回函是否相符' },
  mismatch_note: { key: 'mismatch_note', label: '函证不符事项说明', group: 'row_summary', minWidth: 160, kind: 'text', source: 'E0-1·AB列·函证不符事项说明' },
  e0_row_conclusion: { key: 'e0_row_conclusion', label: '审计结论', group: 'row_summary', minWidth: 140, kind: 'text', source: 'E0-1·AD列·审计结论' },

  /**
   * 发函渠道 —— 源模板 X0-1「函证方式」列（X0-2!C 列 VLOOKUP 而来）。
   *
   * 🔴 为什么另立字段而不复用 `confirmation_method`：
   * 源模板的「函证方式」DV 是 `邮寄/跟函/电子函证/其他`（渠道），而平台既有
   * `confirmation_method` 是 `积极式/消极式`（准则 1312 的程序层面概念）**且驱动**
   * `ConfirmationDetail` 的可确认金额派生（「消极式 + 未回函 → 视同相符」）。
   * 把 `confirmation_method` 改绑渠道枚举会让该派生分支永久失效。
   * spec: h0-confirmation-source-fidelity-and-linkage R7.2（含设计更正记录）
   */
  send_channel: { key: 'send_channel', label: '函证方式', group: 'send_info', width: 100, kind: 'select', source: 'X0-1·函证方式（渠道，X0-2!C 列带入）' },

  // H0 条款口径（决策 4：文本载体，不改 amount 类型）
  term_book: { key: 'term_book', label: '账面合同条款', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·金额或合同条款(账面侧)' },
  term_reply: { key: 'term_reply', label: '回函合同条款', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·金额或合同条款(回函侧)' },
  term_match: { key: 'term_match', label: '条款是否一致', group: 'reply_amount', width: 100, align: 'center', kind: 'select', source: 'H0-1·条款一致性' },
  term_note: { key: 'term_note', label: '条款差异说明', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·条款差异说明' },
}

/** 枢纽 → 启用的 variant 列 key（源模板没有的不进集合） */
export const CYCLE_VARIANT_COLUMNS: Record<ConfirmCycle, string[]> = {
  D0: [],
  E0: ['account_no', 'amount_orig', 'fx_rate', 'confirmed_amount_orig', 'pledge_note', 'other_items_match', 'mismatch_note', 'e0_row_conclusion'],
  F0: [],
  // G0：源模板「函证方式」（渠道，G0-2!C 的 DV 实测为 `邮寄/跟函/电子函证/其他`）+ AB 列审计结论
  G0: ['send_channel', 'g0_row_conclusion'],
  // H0：条款口径 4 列 + 源模板「函证方式」（渠道）+ AB 列审计结论
  H0: ['send_channel', 'term_book', 'term_reply', 'term_match', 'term_note', 'h0_row_conclusion'],
  // K0：源模板「函证方式」（渠道，K0-2!C7:C24 的 DV 实测 `邮寄/跟函/电子函证/其他`，
  // 经 VLOOKUP 带入 K0-1!G）+ AB 列审计结论。
  // 🔴 撤 `send_memo`（源 C5:F5 是合并段头 = 伪列，R2.1/R2.2）；
  //    `row_conclusion` 换成 `k0_row_conclusion`（源 AB5 在六段之外，group 应为 row_summary，R2.4）。
  K0: ['send_channel', 'k0_row_conclusion'],
  // L0：源模板「函证方式」（渠道，L0-2!C 的 DV 实测 `邮寄/跟函/电子函证/其他`）+ AB 列审计结论。
  // 🔴 撤 `send_memo`（源 C5:F5 是合并段头 = 伪列，R4.1/R4.2）；
  //    `row_conclusion` 换成 `l0_row_conclusion`（源 AB5:AB7 在四段之外，group 应为 row_summary，R4.3）。
  L0: ['send_channel', 'l0_row_conclusion'],
}

/**
 * 枢纽 → 需从 BASE 剔除的列 key
 * （源模板没有该列 → 空列噪声，Requirement 2.5）
 * 除 E0 外全为空数组 → 其余六个循环列集逐字节不变（零回归支点）
 */
export const CYCLE_EXCLUDED_COLUMNS: Record<ConfirmCycle, string[]> = {
  D0: [],
  E0: [
    'sample_purpose',    // E0-1 源模板无「选取样本目的」
    'contact_person',    // E0-1 源模板无「联系人」
    'contact_phone',     // E0-1 源模板无「联系电话」
    'use_alternative',   // E0-1 无替代程序区（替代程序在「回函情况汇编」）
    'alt_confirmed',
    'alt_unconfirmed',
    'alt_ref_index',
    'remark',            // E0-1 源模板无「备注」
  ],
  F0: [],
  // G0-1 源模板 28 列中**没有**联系人 / 联系电话（它们在 G0-2 的 F/G 列）与币种 →
  // 保留会形成三列空列噪声（g0 spec R2.2）。仅影响渲染，不删除既有持久化字段值。
  G0: ['contact_person', 'contact_phone', 'currency'],
  // H0-1 源模板 28 列中**没有**联系人 / 联系电话（它们在 H0-2）与币种 →
  // 保留会形成三列空列噪声（Requirement 2.5 / h0 spec R6.2）。
  // 🔴 仅影响渲染，不删除既有持久化字段值（h0 spec R6.3 / Property 18）。
  H0: ['contact_person', 'contact_phone', 'currency'],
  // K0-1 源模板 28 列（A..AB）中**没有**联系人 / 联系电话（它们在 K0-2 的 F/G 列）与币种 →
  // 保留会形成三列空列噪声（R2.6），与 G0/H0/L0 同款处置。
  // 🔴 仅影响渲染，不删除既有持久化字段值。
  K0: ['contact_person', 'contact_phone', 'currency'],
  // L0-1 源模板 28 列（A..AB）中**没有**联系人 / 联系电话（它们在 L0-2 的 F/G 列）与币种 →
  // 保留会形成三列空列噪声（R4.4）。
  // 🔴 仅影响渲染，不删除既有持久化字段值（R10.6 数据零丢失红线）。
  L0: ['contact_person', 'contact_phone', 'currency'],
}

/**
 * 枢纽 → 列 label 覆盖（各枢纽源模板用词不同不强行统一，Requirement 8.3）
 *
 * 🔴 **SHALL NOT 改 `BASE_CONFIRMATION_COLUMNS` 的 label** —— 那会波及其余六枢纽。
 * 本表只有 `G0` / `H0` 两个 key ⇒ 其余五个循环 `resolveConfirmationColumns` 输出逐字节不变
 * （零回归支点，守卫 Property 17 / g0 spec Property 3）。
 *
 * H0 的 13 处偏差逐条取自源模板 `函证结果汇总表H0-1` 第 6 行表头
 * （openpyxl 直读实证，守卫用后端导出的 fixture 交叉锁死）。
 * spec: h0-confirmation-source-fidelity-and-linkage R6.4 / R6.5 / R7.3
 *
 * G0 的 11 处偏差逐条取自源模板 `函证结果汇总表G0-1` 第 6 行表头
 * （守卫 `backend/tests/test_g0_source_template_facts.py::TestSummaryUpperZone` 已固化源侧事实）。
 * spec: g0-confirmation-source-alignment R2.3
 */
export const CYCLE_COLUMN_LABEL_OVERRIDES: Partial<Record<ConfirmCycle, Readonly<Record<string, string>>>> = {
  G0: Object.freeze({
    confirm_index: '询证函索引号',        // 源 B5（BASE 写「函证索引号」）
    account_type: '账户/交易',            // 源 E6（BASE 写「科目」）—— 亦是下区矩阵的品种维度
    amount: '账面期末余额',               // 源 F6（BASE 写「函证金额」）
    entity_address: '收件地址',           // 源 J6（BASE 写「地址」）
    send_addr_match: '地址核查是否一致',   // 源 K6（BASE 写「收件地址核查是否一致」）
    is_replied: '是否收到回函',           // 源 L6（BASE 写「是否已回函」；源含「（√）」，DV 实为 是/否 故不带勾号）
    match_status: '是否相符',             // 源 N6（BASE 写「相符情况」）
    reply_date: '回函日期',               // 源 O6（BASE 写「收函日期」）
    reply_from_addr: '回函地址',          // 源 Q6（BASE 写「回函发出地址」）
    difference: '差异',                   // 源 T6（BASE 写「差异金额」）
    remark: '其他说明/备注',              // 源 W6（BASE 写「备注」）
    use_alternative: '是否采取替代程序',   // 源 X6（源含「（√）」，同 is_replied 处理）
    alt_confirmed: '替代后可确认金额',     // 源 Y6（BASE 写「替代程序确认金额」）
    alt_ref_index: '替代程序索引号',       // 源 AA6（BASE 写「替代程序索引」）
    // 🔴 源模板「函证方式」是**渠道**（G0-2!C 的 DV 实测 `邮寄/跟函/电子函证/其他`，
    //    经 VLOOKUP 带入 G0-1!G），故与 H0 同法：渠道走 variant 列 `send_channel`，
    //    本列承载准则 1312 的积极式/消极式，显式区分避免两列同名。
    confirmation_method: '函证类型（积极式/消极式）',
    // 🔴 `diff_ref_index` 的源字面是「调节索引（G0-3）」，其中 G0-3 是**源模板 tab 名索引号笔误**
    //    （底稿目录裁决为 G0-4）→ 该列 label 的处置归 g0 spec Task 10/11（裁决门 B），此处不先落。
  }),
  H0: Object.freeze({
    confirm_index: '询证函索引号',      // 源 B6
    account_type: '账户/交易',          // 源 E6（BASE 写「科目」）
    amount: '金额或合同条款',            // 源 F6（BASE 写「函证金额」）
    entity_address: '收件地址',          // 源 J6（BASE 写「地址」）
    send_addr_match: '地址核查是否一致',  // 源 K6（BASE 写「收件地址核查是否一致」）
    is_replied: '是否收到回函',          // 源 L6（BASE 写「是否已回函」）
    match_status: '是否相符',            // 源 N6（BASE 写「相符情况」）
    reply_date: '回函日期',              // 源 O6（BASE 写「收函日期」）
    reply_amount: '回函金额/条款',        // 源 S6（BASE 写「回函金额」）
    difference: '差异（金额/条款）',      // 源 T6（BASE 写「差异金额」）
    confirmed_amount: '可确认金额/条款',  // 源 U6（BASE 写「可确认金额」）
    diff_ref_index: '差异核对索引（H0-4）', // 源 V6（BASE 写「差异调节表索引」）
    remark: '其他说明/备注',             // 源 W6（BASE 写「备注」）
    alt_confirmed: '替代后可确认金额',    // 源 Y6（BASE 写「替代程序确认金额」）
    alt_ref_index: '替代程序索引号',      // 源 AA6（BASE 写「替代程序索引」，少一个「号」）
    // 🔴 源模板「函证方式」是渠道（见 VARIANT_COLUMN_DEFS.send_channel），
    //    本列承载的是准则 1312 的积极式/消极式，故显式区分避免两列同名。
    confirmation_method: '函证类型（积极式/消极式）',
  }),
  /**
   * K0 的 label 偏差逐条取自源模板 `函证结果汇总表K0-1` 第 6 行表头
   * （后端 `test_k0_source_template_facts.py::SUMMARY_LEAF_COLUMNS` 已以 openpyxl 直读固化，
   *  前端守卫读该常量做跨前后端交叉锁死）。
   * spec: k0-confirmation-source-alignment R2.5
   */
  K0: Object.freeze({
    confirm_index: '询证函索引号',        // 源 B5（BASE 写「函证索引号」）
    account_type: '账户/交易',            // 源 E6（BASE 写「科目」）—— 亦是下区矩阵的品种维度
    amount: '金额',                       // 源 F6（BASE 写「函证金额」）
    send_doc_no: '发函单号/跟函记录索引号', // 源 I6（BASE 写「发函单号」，少了跟函记录索引号）
    entity_address: '收件地址',           // 源 J6（BASE 写「地址」）
    send_addr_match: '地址核查是否一致',   // 源 K6（BASE 写「收件地址核查是否一致」）
    is_replied: '是否收到回函',           // 源 L6（BASE 写「是否已回函」）
    match_status: '是否相符',             // 源 N6（BASE 写「相符情况」）
    reply_date: '回函日期',               // 源 O6（BASE 写「收函日期」）
    difference: '差异',                   // 源 T6（BASE 写「差异金额」）
    remark: '其他说明/备注',              // 源 W6（BASE 写「备注」）
    alt_confirmed: '替代后可确认金额',     // 源 Y6（BASE 写「替代程序确认金额」）
    alt_ref_index: '替代程序索引号',       // 源 AA6（BASE 写「替代程序索引」，少一个「号」）
    // 🔴 源字面「调节索引（K1-12）」中的 K1-12 是**源模板索引号笔误**
    //    （函证差异调节表实为 K0-4；K1-12 是 K1 循环底稿）→ 按意图展示 K0-4，
    //    笔误不静默改写而是登记在 `k0LowerZoneSpec.K0_INDEX_TYPO_MAP`（R6.1/R6.2）。
    diff_ref_index: '调节索引（K0-4）',
    // 🔴 源模板「函证方式」（源 G）是**渠道**（K0-2!C7:C24 的 DV 实测 `邮寄/跟函/电子函证/其他`），
    //    故与 G0/H0/L0 同法：渠道走 variant 列 `send_channel`，
    //    本列承载准则 1312 的积极式/消极式（**源模板无此列，显式登记的源外保留列**，R2.7），
    //    显式区分避免两列同名。
    confirmation_method: '函证类型（积极式/消极式）',
  }),
  /**
   * L0 的 label 偏差逐条取自源模板 `函证结果汇总表L0-1` 第 5/6 行表头
   * （守卫 `backend/tests/test_l0_source_template_facts.py::SUMMARY_COLUMN_MAP` 已固化源侧事实，
   *  前端守卫读该常量做跨前后端交叉锁死）。
   * spec: l0-confirmation-source-alignment R4.5 / R4.6 / R4.7
   */
  L0: Object.freeze({
    confirm_index: '询证函索引号',        // 源 B（BASE 写「函证索引号」）
    account_type: '账户/交易',            // 源 E（BASE 写「科目」）—— 亦是下区矩阵的品种维度
    amount: '金额',                       // 源 F（BASE 写「函证金额」）
    entity_address: '收件地址',           // 源 J（BASE 写「地址」）
    send_addr_match: '地址核查是否一致',   // 源 K（BASE 写「收件地址核查是否一致」）
    is_replied: '是否收到回函',           // 源 L（BASE 写「是否已回函」；源 DV 为 √/× 故不带勾号字面）
    match_status: '是否相符',             // 源 N（BASE 写「相符情况」）
    reply_date: '回函日期',               // 源 O（BASE 写「收函日期」）
    reply_from_addr: '回函发出地址',       // 源 Q（与 BASE 同，登记以证明已逐列核对）
    difference: '差异',                   // 源 T（BASE 写「差异金额」）
    // 🔴 源字面「调节索引（F0-4）」中的 F0-4 是**源模板索引号笔误**（底稿目录 F8=L0-4 裁决）→
    //    按意图展示 L0-4，笔误不静默改写而是登记在 `l0SheetRegistry` 与 spec 的笔误表（R6.2）。
    diff_ref_index: '调节索引（L0-4）',
    remark: '其他说明/备注',              // 源 W（BASE 写「备注」）
    use_alternative: '是否采取替代程序',   // 源 X（源 DV 为 √/×，同 is_replied 处理）
    alt_confirmed: '替代后可确认金额',     // 源 Y（BASE 写「替代程序确认金额」）
    alt_unconfirmed: '替代后不可确认金额', // 源 Z（与 BASE 同，登记以证明已逐列核对）
    alt_ref_index: '替代程序索引号',       // 源 AA（BASE 写「替代程序索引」，少一个「号」）
    // 🔴 源模板「函证方式」（源 G）是**渠道**（L0-2!C 的 DV 实测 `邮寄/跟函/电子函证/其他`，
    //    经 VLOOKUP 带入 L0-1!G），故与 G0/H0 同法：渠道走 variant 列 `send_channel`，
    //    本列承载准则 1312 的积极式/消极式，显式区分避免两列同名。
    confirmation_method: '函证类型（积极式/消极式）',
  }),
}

/**
 * 枢纽 → 列**分段**覆盖（源模板段划分与 BASE 默认分段不一致时用）。
 *
 * 🔴 **缺省即不变** —— 未声明的循环 `resolveConfirmationColumns` 输出逐字节不变
 * （零回归支点，守卫 Property 4）。本表只有 `K0` 一个键。
 *
 * K0-1 源模板 6 段（`C5:F5` 发函询证纪要 / `G5:K5` 1、发函信息 / `L5:R5` 2、收到回函 /
 * `S5:W5` 3、回函金额确认 / `X5:AA5` 4、未收到回函的替代程序 / `AB5` 审计结论）
 * 与 BASE 默认分段的偏差恰好 7 处：
 *
 * | 列 | BASE 段 | 源模板段（列） | 判据 |
 * |---|---|---|---|
 * | `sample_purpose` | send_info | 发函询证纪要（C） | R2.3 |
 * | `entity_name`    | send_info | 发函询证纪要（D） | R2.3 |
 * | `account_type`   | send_info | 发函询证纪要（E） | R2.3 |
 * | `amount`         | send_info | 发函询证纪要（F） | R2.3 |
 * | `match_status`   | reply_amount | **2、收到回函（N）** | 见下方说明 |
 * | `diff_ref_index` | alternative  | 3、回函金额确认（V） | R2.3 |
 * | `remark`         | alternative  | 3、回函金额确认（W） | R2.3 |
 *
 * 🔴 **`match_status` 是 R2.3 的枚举里漏掉的第 7 处**：源 `N6 是否相符` 落在
 * `L5:R5「2、收到回函」`段内（L=是否收到回函 M=回函方式 **N=是否相符** O=回函日期
 * P=回函快递单号 Q=回函发出地址 R=发函地址与回函地址是否一致，恰 7 列），而 BASE 把它
 * 放进 `reply_amount`。R2.3 只列了 6 列但其明文目的是「**使分段与源模板 6 段逐段对应**」，
 * 且 Property 2 要求「每列的 group 与源模板段对应」⇒ 补上第 7 处才自洽。
 * 该偏差是 **BASE 的平台级默认**（X0-1 七枢纽源模板同构），G0/H0/L0 侧未处置 ⇒
 * 只对 K0 声明，不动 BASE（改 BASE 会波及六枢纽）。
 *
 * 🔴 `seq`/`confirm_index` 在源模板是 `A5:A6`/`B5:B6` rowspan（**六段之外**），
 * 而 `ColumnGroup` 没有「无段」取值、新增会波及全部循环 ⇒ 沿用 G0/H0/L0 的既定处置
 * 保留在 `send_info` 段，不为此扩枚举。
 */
export const CYCLE_COLUMN_GROUP_OVERRIDES: Partial<
  Record<ConfirmCycle, Readonly<Record<string, ColumnGroup>>>
> = {
  K0: Object.freeze({
    sample_purpose: 'send_memo',
    entity_name: 'send_memo',
    account_type: 'send_memo',
    amount: 'send_memo',
    match_status: 'reply_info',
    diff_ref_index: 'reply_amount',
    remark: 'reply_amount',
  }),
}

/**
 * 段的默认渲染顺序。
 *
 * 🔴 这是**列序的唯一真源** —— `ConfirmationFullGrid` 是原生 `<table>`，
 * 列头行按 `resolveConfirmationColumns` 的返回序渲染、分段表头行用 `colspan` 覆盖，
 * 两者顺序不一致就会**错位**。故分段表头必须由列序推导（见 `buildGroups`），
 * 不得在组件里另抄一份 order（组件那份曾漏掉 `row_summary` ⇒ E0 的 4 列与
 * G0/H0/L0 的审计结论列上方没有段标题，colspan 之和小于列数）。
 */
export const DEFAULT_COLUMN_GROUP_ORDER: readonly ColumnGroup[] = Object.freeze([
  'send_info',
  'reply_info',
  'reply_amount',
  'alternative',
  'send_memo',
  'row_summary',
])

/**
 * 枢纽 → 段渲染顺序覆盖（缺省用 `DEFAULT_COLUMN_GROUP_ORDER`）。
 *
 * K0 源模板段序为 `C:F 发函询证纪要` → `G:K 1、发函信息` → `L:R 2、收到回函`
 * → `S:W 3、回函金额确认` → `X:AA 4、未收到回函的替代程序` → `AB 审计结论`。
 *
 * 🔴 **`send_memo` 无法排到 `send_info` 之前**（唯一的结构性偏离，已在 spec Notes 登记）：
 * 源模板 `A5:A6 序号` 与 `B5:B6 询证函索引号` 是 **rowspan、在六段之外**，而
 * `ColumnGroup` 没有「无段」取值（新增会波及全部七枢纽的 `COLUMN_GROUP_LABELS`）⇒
 * 这两列只能留在 `send_info`；而它们 `fixed: 'left'`、CSS 冻结列必须**连续在最左**
 * ⇒ `send_info` 必须是第一段。
 * 折中后 K0 段序 = `发函信息(A,B,G..K)` → `发函询证纪要(C..F)` → 其余按源序，
 * 与源模板的唯一差异是「`C:F` 段被后移到 `G:K` 之后」，其余五段逐段对应。
 */
export const CYCLE_COLUMN_GROUP_ORDER_OVERRIDES: Partial<
  Record<ConfirmCycle, readonly ColumnGroup[]>
> = {
  K0: Object.freeze([
    'send_info',
    'send_memo',
    'reply_info',
    'reply_amount',
    'alternative',
    'row_summary',
  ]),
}

/** 该枢纽的段渲染顺序（纯函数，供 `resolveConfirmationColumns` 与守卫共用） */
export function resolveConfirmationGroupOrder(cycle: ConfirmCycle): readonly ColumnGroup[] {
  return CYCLE_COLUMN_GROUP_ORDER_OVERRIDES[cycle] ?? DEFAULT_COLUMN_GROUP_ORDER
}

const BASE_BY_KEY: Record<string, ColumnDef> = Object.fromEntries(
  BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c]),
)

/**
 * 纯函数：返回该枢纽应渲染的列 = (BASE − EXCLUDED) ∪ CYCLE_VARIANT_COLUMNS[cycle]
 * variant 列插到其 group 内既有 BASE 列之后，保持分段表头顺序。
 * 最后按 CYCLE_COLUMN_LABEL_OVERRIDES 覆盖 label（浅拷贝，不 mutate 常量对象）。
 */
export function resolveConfirmationColumns(cycle: ConfirmCycle): ColumnDef[] {
  const variantKeys = CYCLE_VARIANT_COLUMNS[cycle] ?? []
  const excludedKeys = new Set(CYCLE_EXCLUDED_COLUMNS[cycle] ?? [])
  const groupOverrides = CYCLE_COLUMN_GROUP_OVERRIDES[cycle]

  // BASE 过滤掉该枢纽不要的列
  let filteredBase = excludedKeys.size
    ? BASE_CONFIRMATION_COLUMNS.filter((c) => !excludedKeys.has(c.key))
    : BASE_CONFIRMATION_COLUMNS

  // 分段覆盖 —— 🔴 必须在分组装配**之前**套用，且必须浅拷贝新对象；
  // 直接写 `c.group` 会污染 BASE 常量并让后续对其它枢纽的调用也拿到 K0 的分段。
  if (groupOverrides) {
    filteredBase = filteredBase.map((c) =>
      groupOverrides[c.key] ? { ...c, group: groupOverrides[c.key] } : c,
    )
  }

  let result: ColumnDef[]
  if (!variantKeys.length && !groupOverrides) {
    result = [...filteredBase]
  } else {
    let variantDefs = variantKeys
      .map((k) => VARIANT_COLUMN_DEFS[k])
      .filter((d): d is ColumnDef => !!d)
    if (groupOverrides) {
      variantDefs = variantDefs.map((c) =>
        groupOverrides[c.key] ? { ...c, group: groupOverrides[c.key] } : c,
      )
    }

    // 分 group 合并：先 BASE 该 group 列，再该 group 的 variant 列，保持 group 顺序
    result = []
    for (const g of resolveConfirmationGroupOrder(cycle)) {
      result.push(...filteredBase.filter((c) => c.group === g))
      result.push(...variantDefs.filter((c) => c.group === g))
    }
  }

  // label 覆盖 —— 🔴 必须浅拷贝新对象，直接写 col.label 会污染 BASE/VARIANT 常量，
  // 使后续对其它枢纽的调用也拿到 H0 的用词（Property 17）。
  const overrides = CYCLE_COLUMN_LABEL_OVERRIDES[cycle]
  if (overrides) {
    result = result.map((c) => (overrides[c.key] ? { ...c, label: overrides[c.key] } : c))
  }
  return result
}

/** 该枢纽默认「核心」列 key（列显隐预设，Requirement 6.1 覆盖最常用列） */
export const CORE_COLUMN_KEYS: string[] = [
  'seq', 'confirm_index', 'entity_name', 'account_type', 'amount',
  'confirmation_method', 'send_date', 'is_replied', 'reply_amount',
  'match_status', 'difference', 'confirmed_amount',
]

export { VARIANT_COLUMN_DEFS, BASE_BY_KEY }
