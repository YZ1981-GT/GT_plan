/**
 * g0SourceDefects.ts — G0 源模板自身缺陷登记表（**7 条**）
 *
 * spec: g0-confirmation-source-alignment，Task 20（Requirement 10.1~10.4 / Property 24 / 27）
 *
 * ─── 为什么要有这张表 ────────────────────────────────────────────────────────
 * 源模板 `backend/wp_templates/G/G0 投资循环函证.xlsx` 自身含 7 处缺陷。平台的处置铁律是
 * **「按意图实现，不照抄错误，也不静默顺手修正」**：
 *   · 照抄 → 把错误固化进平台（如 M 列方向、越界求和范围）
 *   · 静默修正 → 下一个会话精读源模板时会发现平台与源不一致，无从判断是有意还是漂移，
 *     且以源 xlsx 为裁决者的三向守卫会打红
 * → 逐条登记 + 双向守卫（源侧「缺陷确实存在」× 平台侧「已按 handling 处置」，缺一即红）。
 *
 * ─── 双向守卫的两侧分工 ──────────────────────────────────────────────────────
 * (a) 源侧「缺陷确实存在」= `backend/tests/test_g0_source_template_facts.py::TestSourceDefectsExist`
 *     （openpyxl 直读源 xlsx 逐锚点验证，7 条一一对应）
 * (b) 平台侧「已按意图处置」= `__tests__/g0SourceDefects.spec.ts`
 *     （读平台实现源码断言 `platformEvidence` 指向的处置确实存在）
 * 两侧都以本表的 `id` 为连接键；本表少一条、后端多一条断言，或反之，都打红。
 *
 * ─── handling 三态语义 ───────────────────────────────────────────────────────
 * | handling                 | 含义                                     | 平台可见效果 |
 * |--------------------------|------------------------------------------|--------------|
 * | `implement-intent`       | 按正确意图实现，平台行为**不复现**缺陷    | 计算/分段正确 |
 * | `display-as-is`          | 源文字原样展示 + 加标注（R10.3）          | 原文 + tooltip |
 * | `index-label-correction` | 定位仍用源 tab 名、展示改用底稿目录索引号 | 展示值修正 + tooltip |
 *
 * 🔴 `display-as-is` 的条目必须给 `sourceText`，守卫据此断言「平台展示文字与源原文逐字相等」
 *    —— 防被后来的会话「顺手修正」成 G0-7 后三向比对打红。
 */

// ─── 类型 ────────────────────────────────────────────────────────────────────

export type G0DefectHandling = 'implement-intent' | 'display-as-is' | 'index-label-correction'

export interface G0SourceDefect {
  /** 稳定 id（与后端 `TestSourceDefectsExist` 的用例一一对应，改名会打断双向守卫） */
  id: string
  /** 源锚点（`{tab 名}!{格}` 或多格区间；多锚点用 ' / ' 连接） */
  anchor: string
  /** 源模板事实（客观描述"源里写的是什么"，不含主观判断） */
  defect: string
  /** 正确意图（**必须有源模板内部旁证**，见 `intentEvidence`） */
  intent: string
  /** 判定「这是缺陷而非有意」的旁证（同表同组公式 / 表头声明 / D0·F0 同构表） */
  intentEvidence: string
  handling: G0DefectHandling
  /**
   * 平台侧处置证据：`{文件相对 g0-confirmation 或 confirmation 的路径}#{符号或字面量}`。
   * 守卫读该文件断言符号存在 —— 使「已处置」不是一句自述而是可验证事实。
   */
  platformEvidence: readonly string[]
  /** `display-as-is` 必填：源原文逐字（守卫断言平台展示与之相等） */
  sourceText?: string
  /** UI 提示文案（tooltip / 琥珀条）；`implement-intent` 亦可有，用于说明"平台为何与源不同" */
  uiNote: string
  note?: string
}

// ─── 7 条登记 ────────────────────────────────────────────────────────────────

export const G0_SOURCE_DEFECTS: readonly G0SourceDefect[] = Object.freeze([
  {
    id: 'directory-serial',
    anchor: '底稿目录!D7 / 底稿目录!D10',
    defect:
      '序号列除 D4 为常量 1 外应逐格 `=D(n-1)+1`，但 D7 硬写 2、D10 硬写 3 → 渲染出的序号为 1,2,3,2,3,4,3,4,5（两处回退）。',
    intent: '序号应连续递增 1~9（底稿目录恰 9 条索引：G0A / G0-1 … G0-8）。',
    intentEvidence: 'D5/D6/D8/D9/D11/D12 六格均为 `=D(n-1)+1` → D7/D10 的常量是笔误而非有意分段。',
    handling: 'implement-intent',
    platformEvidence: ['g0SheetRegistry.ts#G0_SHEET_REGISTRY'],
    uiNote:
      '源模板底稿目录序号列有两处硬写值（D7=2 / D10=3），渲染为 1,2,3,2,3,4,3,4,5。平台按声明顺序自行编号，不复现该回退。',
  },
  {
    id: 'matrix-sumif-range',
    anchor: '函证结果汇总表G0-1!E24',
    defect:
      "「回函确认金额」首列公式为 `=SUMIF($E$8:$E$17,E$20,U8:U179)`，求和区 `U8:U179` 越界（明细区只到第 17 行），且未加 `$` 绝对引用。",
    intent: '按品种对「可确认金额（U 列）」在实际明细行范围内求和。',
    intentEvidence:
      "同一行相邻列 F24 为 `=SUMIF($E$8:$E$17,F$20,U8:U17)` —— 范围正确 → E24 的 179 是笔误。",
    handling: 'implement-intent',
    platformEvidence: ['g0SummaryMatrix.ts#sumByCategory'],
    uiNote:
      '平台按上区**实际明细行数**聚合（不固定 8~17 行也不复现 179 的越界范围），故行数超过源模板 10 行时结果依然正确。',
  },
  {
    id: 'xref-reliability',
    anchor: '函证结果汇总表G0-1!S24',
    defect:
      '审计说明第 3 项标题的交叉引用写「（G0-6）」，而 G0-6 是「替代程序检查表」；回函可靠性验证表实为 G0-7。',
    intent: '交叉引用应指向 `邮件传真回函可靠性验证G0-7`。',
    intentEvidence:
      '底稿目录 F10=`G0-6`→替代程序检查表、F11=`G0-7`→邮件传真回函可靠性验证 → S24 的 G0-6 与本项主题（回函可靠性）不符。',
    handling: 'display-as-is',
    sourceText: '3、对以传真或电子邮件形式收到的回函的可靠性的考虑（G0-6）',
    platformEvidence: ['g0SummaryLowerZone.ts#G0_AUDIT_NOTE_DEFS'],
    uiNote: '源模板此处写「（G0-6）」，实为笔误；回函可靠性验证表是 G0-7（G0-6 是替代程序检查表）。',
    note: '标题逐字保留原文（守卫按原文断言）；正确指向由 AI prompt 与本提示承担。',
  },
  {
    id: 'xref-followup-self',
    anchor: '核实被函证单位信息G0-2!AA6',
    defect: '列标题写「跟函函证控制过程（G0-2）」—— 索引号指向本表自己（G0-2），构成自引用。',
    intent: '应指向 `跟函函证过程控制G0-3`。',
    intentEvidence:
      '底稿目录 F6=`G0-2`→核实被函证单位信息（即本表）、F7=`G0-3`→跟函函证过程控制 → 列名主题与索引号矛盾。',
    handling: 'display-as-is',
    sourceText: '跟函函证控制过程（G0-2）',
    platformEvidence: ['g0SourceDefects.ts#G0_SOURCE_DEFECTS'],
    uiNote: '源模板此列标题写「（G0-2）」构成自引用，实为笔误；跟函函证过程控制表是 G0-3。',
    note:
      '平台 G0-2 列集不渲染该源字面（列标签走 `confirmationColumnSpec` 的平台用词），故本条只做登记与集中展示，不改任何共享列定义。',
  },
  {
    id: 'securities-mv-diff-direction',
    anchor: '函证差异核对表G0-3（证券投资）!M7:M17',
    defect:
      '「差异公允价值」列公式为 `=J−G`（回函 − 账面），与本表表头声明 `差异③=①-②`（①账面 / ②回函）及同组 `K=E−H`、`L=F−I` 方向相反。',
    intent: '三个差异列方向统一为 **账面 − 回函**。',
    intentEvidence:
      "K5 表头逐字 `差异③=①-②`；B5=`账面结存证券投资①`、H5=`证券投资回函②`；同组 K7=`=E7-H7`、L7=`=F7-I7` 均为账面−回函；姊妹表 `函证差异核对表G0-4(非证券投资)` 的 I7=`=C7-F7`、J7=`=D7-G7` 亦为账面−回函 → M 列是唯一反向者。",
    handling: 'implement-intent',
    platformEvidence: [
      'composables/useG0FormulaEngine.ts#calcMarketValueDiff',
      'composables/useG0FormulaEngine.ts#calcQuantityDiff',
      'composables/useG0FormulaEngine.ts#calcFairValueDiff',
    ],
    uiNote: '差异 = 账面 − 回函（源模板表头 ③=①−②）。源模板「差异公允价值」列公式方向写反，平台按表头意图统一。',
    note:
      '平台曾照抄该缺陷方向：归档 spec `g0-confirmation` 把三列全实现为「回函 − 账面」（其需求 2.5/2.6/2.7 逐条如此写），而后续归档 spec `g0-investment-diff-model` 已定「数值维度差异 = 账面 − 回函（符号与口径固定）」并只在非证券表落地 → 证券表是未修的遗留，两张差异表因此互相矛盾。本 spec 按 R10.2 统一。',
  },
  {
    id: 'reply-amount-group-header-shift',
    anchor: '函证结果汇总表G0-1!U5:W5',
    defect:
      '第 3 段段头「3、回函金额确认」落在 `U5:W5`，S5/T5 无段头 → `S 回函金额` 与 `T 差异` 两列无段归属。',
    intent: '段头应覆盖 `S5:W5`，把 S/T/U 三列一并归入「回函金额确认」段。',
    intentEvidence:
      'D0-1 与 F0-1 同构汇总表的同位段头均为 `S5:W5`（`S5` 逐字即「3、回函金额确认」）→ G0-1 的 U5 起点是右移笔误。',
    handling: 'implement-intent',
    platformEvidence: ['../confirmation/confirmationColumnSpec.ts#reply_amount'],
    uiNote:
      '源模板此段段头右移两列，导致「回函金额」「差异」两列无段归属。平台按 D0-1/F0-1 同构表的正确意图把三列归入「回函金额确认」段。',
  },
  {
    id: 'alt-total-sums-index-column',
    anchor: '替代程序检查表G0-6!M23',
    defect:
      '「（1）本期借方发生额」合计行除对金额列求和（`E23=SUM(E19:E22)`）外，还对**索引号**列求和（`M23=SUM(M19:M22)`）—— 索引号是文本列，求和无意义。',
    intent: '合计行只对金额列求和。',
    intentEvidence:
      '同表「（2）本期贷方发生额」的合计行 `R31` 只有 `E31=SUM(E27:E30)`、**没有 M31** → 借贷两块结构本应相同，M23 是复制残留。',
    handling: 'implement-intent',
    platformEvidence: ['alternativeG06/blockColumnConfigsG06.ts#sumField'],
    uiNote:
      '合计行只汇总金额列（源模板借方块多了一处对「索引号」列求和，属复制残留，平台不复现）。',
  },
  {
    id: 'alt-abnormal-dv-offset',
    anchor: '替代程序检查表G0-6!O35:O38',
    defect:
      '「是否异常」列在 `N`（`N33:N34` 合并），但取值为 `√,×` 的数据验证挂在 **`O35:O38`**（右移一列），且仅覆盖区块③ 的 4 行、区块①② 无任何验证。',
    intent: '「是否异常」列应有统一的取值约束，三个区块一致。',
    intentEvidence:
      '`N33` 逐字为「是否异常」而 `O` 列在两级表头里无任何标题 → 验证挂在无标题列上不可能是有意；且区块②（`N17`/`N25`）同名列完全没有验证，说明源模板本身未统一。',
    handling: 'implement-intent',
    platformEvidence: ['../confirmation/alternativeD05/blockColumnConfigs.ts#is_abnormal'],
    uiNote:
      '「是否异常」为点选列，三个区块统一取值。平台沿用七枢纽共享的「是/否」（源模板此处为 √/×，且验证挂错了列、只覆盖一个区块）。',
    note:
      '取值域「是/否」是 D0/E0/F0/G0/H0/K0/L0 共享 `CheckBlock` 的既有约定（`is_abnormal === "是"` 驱动异常行高亮与 AI 说明统计）→ 改成 √/× 会波及七枢纽，属平台级决策，本 spec 只登记。',
  },
  {
    id: 'tab-index-typos',
    anchor:
      '函证差异核对表G0-3（证券投资） / 函证差异核对表G0-4(非证券投资) / 函证程序舞弊风险评价表F0-8',
    defect:
      'sheet tab 名内嵌的索引号与底稿目录不一致：证券差异表 tab 写 G0-3（目录 G0-4）、非证券差异表 tab 写 G0-4（目录 G0-5）、舞弊风险评价表 tab 写 F0-8（F 不是 G，目录 G0-8）。',
    intent: '索引号以底稿目录为唯一裁决者：G0-4 / G0-5 / G0-8。',
    intentEvidence:
      '底稿目录 `F4:F12` 是索引号真源，其 9 条为 G0A/G0-1/G0-2/G0-3/G0-4/G0-5/G0-6/G0-7/G0-8 连续无重；而 tab 名里 `G0-3` 出现两次（跟函表与证券差异表）→ tab 名侧存在重复即证明其非真源。',
    handling: 'index-label-correction',
    platformEvidence: [
      'g0SheetRegistry.ts#indexTypoNote',
      'g0SheetRegistry.ts#G0_SHEET_REGISTRY',
    ],
    uiNote:
      '定位一律用源模板真实 tab 名（不改源 xlsx、不改分类表）；展示用底稿目录索引号并标注笔误。',
    note: '裁决门 B（2026-08-04 用户裁决）= 定位/展示分离 + tooltip 标注。',
  },
])

// ─── 便捷访问 ────────────────────────────────────────────────────────────────

/**
 * 缺陷条数（守卫的数量锚点；后端 `TestSourceDefectsExist` 须同为 9 条）。
 *
 * 7 → 9 的两条是 2026-08-04 逐格直读 `替代程序检查表G0-6` 时新发现的
 * （`alt-total-sums-index-column` / `alt-abnormal-dv-offset`）—— 此前的守卫只覆盖
 * 区块**列定义**，段结构与段内验证从未被校验过。
 */
export const G0_SOURCE_DEFECT_COUNT = 9

export function g0SourceDefect(id: string): G0SourceDefect {
  const d = G0_SOURCE_DEFECTS.find((x) => x.id === id)
  if (!d) throw new Error(`[g0SourceDefects] 未登记的缺陷 id: ${id}`)
  return d
}

/** 取 UI 提示文案（找不到时返回空串，不抛异常 —— UI 不因登记缺失而崩） */
export function g0DefectUiNote(id: string): string {
  return G0_SOURCE_DEFECTS.find((x) => x.id === id)?.uiNote ?? ''
}

/**
 * 差异列方向的统一口径文案（证券/非证券两表共用）。
 * 🔴 tooltip 一律引用它，禁在组件里各写一份"回函 − 账面"/"账面 − 回函"字面。
 */
export const G0_DIFF_DIRECTION_LABEL = '账面 − 回函'
export const G0_DIFF_DIRECTION_HINT = `差异 = ${G0_DIFF_DIRECTION_LABEL}（源模板表头 ③=①−②）`
