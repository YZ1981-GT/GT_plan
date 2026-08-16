/**
 * reliabilityTypes.ts — D0-7 邮件/传真回函可靠性验证 类型定义
 *
 * 核心设计：
 * - 中等宽度~14列单层网格（与 D0-4 类似，无需 master-detail）
 * - 条件列：寄回原件=是 → 灰掉验证6列；=否 → 展开身份确认+邮箱验证+致电
 * - 从 D0-1 带入"回函方式=传真/电子邮件"行（confirm_index 去重）
 * - 质量红线：未验证=橙, 不可靠=红
 * - 结论枚举：可靠/部分可靠需补充/不可靠
 */

// ─── 可靠性验证明细行（~18 字段） ───────────────────────────────────────────

export interface ReliabilityRow {
  /** 内部行 ID（UUID，前端生成） */
  _row_id?: string
  /** 序号 */
  seq?: number
  /** 函证索引号（全局唯一主键，跨 D0 系列引用） */
  confirm_index?: string
  /** 被询证单位名称 */
  entity_name?: string
  /** 回函方式（传真/电子邮件） */
  reply_method?: string
  /** 回函日期 */
  reply_date?: string

  // ─── 条件控制列 ─────────────────────────────────────────────────────────

  /** 是否寄回原件（是/否）—— 控制验证6列的展开/灰掉 */
  original_returned?: '是' | '否'

  // ─── 验证列（寄回原件=否时需填） ───────────────────────────────────────

  /** 身份已确认（注1） */
  identity_verified?: boolean
  /** 身份确认方式（电话确认/邮件确认/见面确认/系统确认） */
  identity_method?: string
  /** 邮箱已验证（注2） */
  email_verified?: boolean
  /** 邮箱域名/类型 */
  email_domain?: string
  /** 是否致电确认 */
  phone_called?: boolean
  /** 电话来源（工商/官网/独立来源） */
  phone_source?: string

  // ─── 结论列 ─────────────────────────────────────────────────────────────

  /** 信息可靠性结论（可靠/部分可靠需补充/不可靠） */
  conclusion_status?: '可靠' | '部分可靠需补充' | '不可靠'
  /** 可靠性说明/备注 */
  reliability_note?: string

  // ─── additive 补列（confirmation-shared-model-extension，Requirement 4.1） ─
  // 全部可选，旧 reliability-v1 payload 读回时为 undefined。
  // 已有等价字段复用不新增（confirm_index=函证索引号 / entity_name=被询证单位名称 /
  //   reply_method=回函方式 / original_returned=是否寄回原件 / email_domain=邮箱域名）。

  /** 是否项目组直接接收 — X0-7 回函可靠性核对（单一真源，Requirement 3.5） */
  direct_received?: '是' | '否' | '不适用'
  /** 传真信息及验证 — X0-7「传真信息及验证」 */
  fax_info_verify?: string
  /** 发函邮箱 — X0-7「发函邮箱」（与 email_domain 并存，双列口径） */
  send_email?: string
  /** 回函邮箱 — X0-7「回函邮箱」 */
  reply_email?: string
  /** 可靠性考虑文本 — X0-7「可靠性考虑」 */
  reliability_consideration?: string

  // ─── 已撤回：按渠道可靠性核对项 12 字段（k0-confirmation-source-alignment R9.1）──
  //
  // 🔴 **它们曾以死字段形态存在（类型声明了、UI 从未渲染），现按「明确撤回」处置。**
  //
  // 撤回依据（2026-08-07 openpyxl 直读七份源模板 + 库侧计数，三条并列）：
  //
  // 1. **六份 visible 源模板的可靠性表列集完全相同，且都没有这 12 列** ——
  //    `邮件传真回函可靠性验证` 在 D0-7 / F0-7 / G0-7 / H0-6 / K0-7 / L0-6 六处
  //    逐字同构：基本段 6 列（序号/函证索引号/被询证单位名称/回函方式/是否由审计项目组
  //    直接接收/是否寄回原件）+ `G5:M5` 父表头「期末未收回原件函证可靠性验证」下 7 列
  //    + 尾列「回函可靠性结论」= **14 列**，已由 `RELIABILITY_COLUMN_CONFIG` 与
  //    `g0SharedComponentCoverage.spec.ts` 的 `COLUMN_TO_FIELD` 双向覆盖。
  //
  // 2. **这 12 个字段的原始出处是 E0 的 `邮件传真回函核对记录F1-12`，而该 sheet 是
  //    `hidden`** —— 用户已于 2026-08-02 明确裁决「三张隐藏底稿不需要再实现了，已隐藏」
  //    （裁决门 A = A-否），`e0-confirmation-completion` 的 R7.1/R7.5 因此作废、其
  //    Wave 6 已整波删除。故它们**没有可实现的源模板落点**：接线出来的录入位在任何
  //    circle 的源模板上都不存在 = 自造底稿列（违反「增强打磨禁止自造披露内容」铁律）。
  //
  // 3. **零存量数据** —— 全库 `working_paper` 498 行，`parsed_data::text` 命中这 12 个
  //    字段名的行数为 **0**（逐字段查，全部 0）⇒ 删除不触碰「数据零丢失」红线。
  //
  // ⚠️ 请勿「顺手补回来」：若将来源模板真的新增按渠道核对列，正确做法是先在
  //    `test_k0_source_template_facts.py::TestReliability` 把源侧 14 列基线改掉
  //    （六份模板同构 ⇒ 六个 spec 的守卫会同时打红），再按新列集 additive 扩字段。
  //    守卫 `k0ReliabilityChannelFields.spec.ts` 已把「不得复活」钉死。

  // ─── 元数据 ─────────────────────────────────────────────────────────────

  /** 数据来源标识（auto/manual/import） */
  _source?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface ReliabilityMetrics {
  /** 总行数 */
  total_count: number
  /** 已验证数（conclusion_status 非空） */
  verified_count: number
  /** 已验证率（%） */
  verified_rate: number
  /** 可靠数 */
  reliable_count: number
  /** 部分可靠数 */
  partial_count: number
  /** 不可靠数 */
  unreliable_count: number
  /** 寄回原件数（免验证） */
  original_returned_count: number
}

// ─── 审计说明 ────────────────────────────────────────────────────────────────

export interface ReliabilityAuditNote {
  /** 验证总体情况说明 */
  note_general?: string
  /** 不可靠情况说明 */
  note_unreliable?: string
  /** 其他事项 */
  note_other?: string
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

export interface ReliabilityConclusion {
  /** 结论类型（可靠/部分可靠需补充/不可靠） */
  conclusion_type?: '可靠' | '部分可靠需补充' | '不可靠'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface ReliabilityPayload {
  /** 格式版本标识 */
  _format: 'reliability-v1'
  /** 明细行数组 */
  rows: ReliabilityRow[]
  /** 审计说明 */
  audit_note?: ReliabilityAuditNote
  /** 审计结论 */
  conclusion?: ReliabilityConclusion
}
