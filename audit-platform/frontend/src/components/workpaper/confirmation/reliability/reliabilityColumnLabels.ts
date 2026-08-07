/**
 * reliabilityColumnLabels.ts — X0-7 回函可靠性表的列标签真源与源外列登记
 *
 * spec: k0-confirmation-source-alignment · Task 14（Requirement 9.3 / 9.4）
 *
 * ══════════════════════════════════════════════════════════════════════════════
 * 🔴🔴 落地时推翻了 R9.3 的立项描述（openpyxl 直读七枢纽源模板实证，勿按旧描述改）
 * ══════════════════════════════════════════════════════════════════════════════
 *
 * R9.3 原文：「源模板 K0-7 **无「回函日期」列**而平台渲染了该列 ⇒ SHALL 按循环控制该列
 * 可见性，SHALL 保持 D0/F0/G0/H0/L0 侧行为不变（其源模板是否有该列须各自核实）」。
 *
 * 逐个核实的结果是：**六个可见的可靠性 sheet 表头逐字完全相同，一个都没有「回函日期」列**
 * （`邮件传真回函可靠性验证D0-7` / `F0-7` / `G0-7` / `H0-6` / `K0-7` / `L0-6`，
 * 都是 14 列、`G5:M5` 合并父表头、r5/r6 叶子列逐字一致；E0 无可靠性 sheet）。
 *
 * ⇒ 「按循环控制可见性」这个形态**不成立**：没有任何一个循环的源模板有该列，
 *   按循环分叉只会产出「K0 藏起来、另五个继续显示源模板没有的列」这种自相矛盾的结果。
 *
 * ⇒ 正确形态 = **平台级源外保留列 + 显式登记依据**（同 `confirmation_method` 在
 *   X0-1 的处置：源模板无该列，但承载准则要求的信息，故保留并登记）。
 *   「回函日期」是判断「回函是否在审计报告日前收到」「传真/电邮回函是否已按 A41
 *   说明 5 要求寄回原件」的时间基准，属平台有意增强，不撤列。
 *
 * 若将来确有某个枢纽的源模板出现该列，再把 `SOURCE_EXTRA_RELIABILITY_COLUMNS`
 * 的登记改成按循环声明 —— 守卫 `reliabilityColumnLabels.spec.ts` 会以
 * 后端六份事实守卫的表头常量为裁决者，届时自动打红提醒。
 *
 * ══════════════════════════════════════════════════════════════════════════════
 * R9.4 列标签：源模板用词 vs 平台既有简称
 * ══════════════════════════════════════════════════════════════════════════════
 *
 * 平台既有列头用的是简称（「身份已确认」/「邮箱已验证」/「信息可靠性」），
 * 而源模板 r5/r6 用的是全称（「被函证者身份确认（注1）」/「邮箱可靠性验证（注2）」/
 * 「对函证信息可靠性的考虑（注3）」）。R9.4 要求 K0 侧显示源模板用词。
 *
 * 🔴 但同上：**六个枢纽的源模板用词逐字相同** ⇒ 同样不该按循环分叉。
 *    故这里给出的是**平台唯一一份**源模板用词映射，六个枢纽一致套用：
 *    - 表头显示源模板全称（审计师看到的就是源模板的字）
 *    - `（注N）` 后缀不进 label（平台把注 1/2/3 做成了列头问号 tooltip，
 *      `FIELD_TOOLTIPS_D07` 已承载全文），否则列头出现「（注1）」又挂一个问号图标 = 重复
 *
 * 真源 = 源模板 r5/r6，后端 `test_k0_source_template_facts.py::TestReliability`
 * 以 openpyxl 直读断言；本文件的守卫读该后端常量做跨前后端逐字交叉锁死。
 */

/** 源模板列出处（r5 = 一级表头行 / r6 = `G:M` 父表头下的叶子行） */
export type ReliabilitySourceRow = 'r5' | 'r6'

export interface ReliabilityColumnLabelDef {
  /** `ReliabilityRow` 字段名 */
  field: string
  /** 源模板逐字用词（已去掉 `（注N）` 后缀，见文件头说明） */
  sourceLabel: string
  /** 改造前平台显示的简称（守卫用它断言「确实改了」，防这份映射变成空操作） */
  legacyLabel: string
  /** 源模板坐标 */
  anchor: string
  /** 该列位于源模板哪一行表头 */
  row: ReliabilitySourceRow
}

/**
 * 源模板 14 列中「平台用词与源模板不同」的那些列。
 *
 * 用词已一致的列（序号 / 回函方式 / 发函邮箱 / 回函邮箱 / 电话来源 等）不进本表 ——
 * 登记恒等映射只会让守卫的「必须真的改了」断言失去意义。
 */
export const RELIABILITY_COLUMN_SOURCE_LABELS: readonly ReliabilityColumnLabelDef[] =
  Object.freeze([
    Object.freeze({
      field: 'entity_name',
      sourceLabel: '被询证单位名称',
      legacyLabel: '被询证单位',
      anchor: 'C5',
      row: 'r5' as const,
    }),
    Object.freeze({
      field: 'direct_received',
      sourceLabel: '是否由审计项目组直接接收',
      legacyLabel: '直接接收',
      anchor: 'E5',
      row: 'r5' as const,
    }),
    Object.freeze({
      field: 'original_returned',
      sourceLabel: '是否寄回原件',
      legacyLabel: '寄回原件',
      anchor: 'F5',
      row: 'r5' as const,
    }),
    Object.freeze({
      field: 'identity_verified',
      sourceLabel: '被函证者身份确认',
      legacyLabel: '身份已确认',
      anchor: 'G6',
      row: 'r6' as const,
    }),
    Object.freeze({
      field: 'fax_info_verify',
      sourceLabel: '发函及回函传真信息及验证',
      legacyLabel: '传真信息及验证',
      anchor: 'H6',
      row: 'r6' as const,
    }),
    Object.freeze({
      field: 'email_verified',
      sourceLabel: '邮箱可靠性验证',
      legacyLabel: '邮箱已验证',
      anchor: 'K6',
      row: 'r6' as const,
    }),
    Object.freeze({
      field: 'phone_called',
      sourceLabel: '是否致电被函证者确认',
      legacyLabel: '已致电',
      anchor: 'L6',
      row: 'r6' as const,
    }),
    Object.freeze({
      field: 'reliability_consideration',
      sourceLabel: '对函证信息可靠性的考虑',
      legacyLabel: '可靠性考虑',
      anchor: 'M6',
      row: 'r6' as const,
    }),
    Object.freeze({
      field: 'conclusion_status',
      sourceLabel: '回函可靠性结论',
      legacyLabel: '信息可靠性',
      anchor: 'N5',
      row: 'r5' as const,
    }),
  ]) as readonly ReliabilityColumnLabelDef[]

/** 按字段名取源模板用词；未登记的字段返回 `undefined`（调用方保留既有 label） */
export function reliabilitySourceLabel(field: string): string | undefined {
  return RELIABILITY_COLUMN_SOURCE_LABELS.find((d) => d.field === field)?.sourceLabel
}

/**
 * `field → sourceLabel` 的派生映射，供 Vue 模板直接写 `RELIABILITY_COLUMN_LABELS.entity_name`。
 *
 * 🔴 **由上面的数组派生，不是第二份真源** —— 改字面只许改 `RELIABILITY_COLUMN_SOURCE_LABELS`。
 *
 * 🔴🔴 为什么需要这个对象（2026-08-07 浏览器实测踩出的 P0，勿删）：
 *    模板里写 `:label="reliabilitySourceLabel('entity_name')"` 每次渲染都要遍历数组；
 *    而写 `RELIABILITY_COLUMN_LABELS.entity_name` 直接取值。更重要的是 —— 一旦模板引用了
 *    一个**未定义**的标识符（本轮就是把它写成了 `RELIABILITY_COLUMN_LABELS` 而真源只导出数组），
 *    `get_diagnostics`(Volar) **零诊断** / Vite transform **200** / vitest **全绿**，
 *    只有浏览器打开该 sheet 才会炸「页面渲染出错：Cannot read properties of undefined
 *    (reading 'entity_name')」整页白屏。故这里显式导出该对象，并由守卫
 *    `k0SharedComponentBoundary.spec.ts` 断言「模板引用的每个 `.field` 都在本对象里真实存在」。
 */
export const RELIABILITY_COLUMN_LABELS: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(RELIABILITY_COLUMN_SOURCE_LABELS.map((d) => [d.field, d.sourceLabel])),
)

export interface SourceExtraReliabilityColumn {
  field: string
  label: string
  /** 为什么保留（审计依据，禁写「历史遗留」这类无信息量的理由） */
  reason: string
}

/**
 * 源模板没有、平台有意保留的列（源外增强）。
 *
 * 🔴 六个枢纽的源模板都没有这些列 ⇒ 平台级一份登记，不按循环分叉（见文件头）。
 */
export const SOURCE_EXTRA_RELIABILITY_COLUMNS: readonly SourceExtraReliabilityColumn[] =
  Object.freeze([
    Object.freeze({
      field: 'reply_date',
      label: '回函日期',
      reason:
        '源模板 X0-7 十四列均无该列（D0-7/F0-7/G0-7/H0-6/K0-7/L0-6 表头逐字相同，openpyxl 实证）。' +
        '保留理由：源模板 X0-2 编制说明 5 要求「要求被询证者在审计报告日之前寄回询证函原件」，' +
        '判断该要求是否满足必须有回函时间基准；同时准则 1312 对回函及时性的评价亦以此为依据。' +
        '属平台有意增强，不撤列。',
    }),
    Object.freeze({
      field: 'identity_method',
      label: '确认方式',
      reason:
        '源模板 `G6` 只有「被函证者身份确认（注1）」一列（是/否），而注1 列举四种确认方式' +
        '（电话/邮件/见面/系统）。把「用了哪种方式」结构化成独立列，使身份确认过程可复核，' +
        '否则注1 的四选一只能写进自由文本备注。属源模板注释要求的结构化落地。',
    }),
    Object.freeze({
      field: 'phone_source',
      label: '电话来源',
      reason:
        '源模板 `L6`「是否致电被函证者确认」只记是否致电。而「号码取自独立公开来源」是该程序' +
        '有效性的前提（致电被审计单位提供的号码等于没验证），故独立成列。' +
        '与 X0-3 跟函话术「号码取自独立公开来源」交叉呼应。',
    }),
    Object.freeze({
      field: 'reliability_note',
      label: '验证备注',
      reason: '自由文本补充位，承载注1/注2/注3 未覆盖的个案说明；不参与任何派生与勾稽。',
    }),
  ]) as readonly SourceExtraReliabilityColumn[]

/** 该字段是否为源模板没有的平台增强列 */
export function isSourceExtraReliabilityColumn(field: string): boolean {
  return SOURCE_EXTRA_RELIABILITY_COLUMNS.some((c) => c.field === field)
}
