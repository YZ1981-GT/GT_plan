/**
 * confirmationLinkageMatrix.ts — 七枢纽联动覆盖矩阵
 *
 * 数据源：postgres workpaper_sheet_classification + wp_code_overrides.json + 代码实证
 * 用于覆盖守卫（findLinkageGaps）与 spec 实施跟踪。
 *
 * 核实依据（Task 1.1 / 1.4 实测结论）：
 * - D0A：无 wp_code_overrides 条目，class_code 为 "A-程序表" → 派生 a-program-console（正确）
 * - E0A：无 wp_code_overrides 条目，class_code 为 "A-程序表" → 派生 a-program-console（正确）
 * - E0-6（理财产品发函记录表E0-6）：无 override，class_code 派生为 d-form-table
 * - E0-7（跟函函证过程控制E0-7）：无 override，尾码 E0-7 未在 overrides → class_code 派生
 *   但因 E0 重建映射表需给 E0-7 加 sheet_name 精确 override → confirmation-followup
 * - 回函情况汇编：无 override，class_code 派生（保留不 skip）
 * - G0 差异核对表G0-3（证券投资）：尾码正则不命中（以括号收尾）→ 落 class_code 派生
 *   → G0 内 class_code startsWith("G-") → 强制 onlyoffice-sheet（非 confirmation-hub）
 *   需 sheet_name 精确 override → confirmation-diff-securities
 * - G0 差异核对表G0-4(非证券投资)：同上，落 onlyoffice-sheet
 *   需 sheet_name 精确 override → confirmation-diff-reconcile
 * - L0 程序表 "函证程序表F0A"：尾码提取为 F0A → get_template("F0A") 若无模板则用 xlsx 兜底
 *   → 需父码优先 resolve_program_template_code("函证程序表F0A","L0") → "L0A" 使 L0A 模板生效
 * - G0-3S 编码 key：sheet 名中不存在该编码，属死配置（不影响任何解析结果）
 */

// ─────────────────────────── Types ───────────────────────────

export type ConfirmationHubCycle = 'D0' | 'E0' | 'F0' | 'G0' | 'H0' | 'K0' | 'L0'

export type LinkageCapability =
  | 'sync_to_center'
  | 'reply_backflow'
  | 'unreplied_pull'
  | 'center_entry'

export type CapabilityState =
  | 'implemented'
  | 'stub'
  | 'missing'
  | 'not_applicable'

export interface HubCycleSpec {
  cycle: ConfirmationHubCycle
  /** X0-1 summary sheet_name（null = 该枢纽无 summary sheet，如 E0 重建前） */
  summarySheet: string | null
  /** Alternative sheet 的 sheet_name 列表（0~2 张） */
  alternativeSheets: string[]
  /** 四条联动链覆盖状态 */
  capabilities: Record<LinkageCapability, CapabilityState>
  /** not_applicable 项的依据说明 */
  notApplicableReason?: string
}

// ─────────────────────────── Data ───────────────────────────

/**
 * Linkage_Matrix 定义（实证基线 + spec 目标态）
 *
 * 所有 state 值反映 **spec 完成后** 的目标态（implemented）。
 * 当前 STUB / missing 项在 spec 执行过程中逐一替换。
 */
export const CONFIRMATION_LINKAGE_MATRIX: HubCycleSpec[] = [
  {
    cycle: 'D0',
    summarySheet: '函证结果汇总表D0-1',
    alternativeSheets: ['合同负债及销售替代程序D0-5', '应收及销售替代程序D0-6'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // D0-5 已实现；D0-6 本 spec 从 stub → implemented
      center_entry: 'implemented',
    },
  },
  {
    cycle: 'E0',
    summarySheet: '函证结果汇总表E0-1',
    alternativeSheets: [], // 源模板确无替代程序 sheet
    capabilities: {
      sync_to_center: 'implemented', // 决策 4 重建后
      reply_backflow: 'implemented',
      unreplied_pull: 'not_applicable',
      center_entry: 'implemented',
    },
    notApplicableReason: 'E0 源模板无替代程序 sheet（E0-3~E0-6 是发函前清单非替代确认）',
  },
  {
    cycle: 'F0',
    summarySheet: '函证结果汇总表F0-1',
    alternativeSheets: ['预付及采购替代程序F0-5', '应付及采购替代程序F0-6'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // F0-5 / F0-6 本 spec 从 stub → implemented
      center_entry: 'implemented',
    },
  },
  {
    cycle: 'G0',
    summarySheet: '函证结果汇总表G0-1',
    alternativeSheets: ['替代程序检查表G0-6'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // G0-6 已实现（pullFromG01）
      center_entry: 'implemented',
    },
  },
  {
    cycle: 'H0',
    summarySheet: '函证结果汇总表H0-1',
    alternativeSheets: ['替代程序H0-5'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // H0-5 已实现
      center_entry: 'implemented',
    },
  },
  {
    cycle: 'K0',
    summarySheet: '函证结果汇总表K0-1',
    alternativeSheets: ['其他应收款替代程序K0-5', '其他应付款替代程序K0-6'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // K0-6 已实现；K0-5 本 spec 补带入入口
      center_entry: 'implemented',
    },
  },
  {
    cycle: 'L0',
    summarySheet: '函证结果汇总表L0-1',
    alternativeSheets: ['长期应付款替代程序L0-5'],
    capabilities: {
      sync_to_center: 'implemented',
      reply_backflow: 'implemented',
      unreplied_pull: 'implemented', // L0-5 已实现
      center_entry: 'implemented',
    },
  },
]

// ─────────────────────────── Guard ───────────────────────────

export interface LinkageGap {
  cycle: string
  capability: LinkageCapability
  state: CapabilityState
}

/**
 * 覆盖守卫：列出应实现但未实现的 (cycle, capability)。
 * - state 为 'stub' 或 'missing' → 视为 gap
 * - state 为 'not_applicable' 但缺 notApplicableReason → 也视为 gap
 * - 全部 implemented 或 not_applicable(带 reason) → 返回空数组
 */
export function findLinkageGaps(matrix: HubCycleSpec[]): LinkageGap[] {
  const gaps: LinkageGap[] = []
  for (const spec of matrix) {
    for (const [cap, state] of Object.entries(spec.capabilities) as Array<[LinkageCapability, CapabilityState]>) {
      if (state === 'stub' || state === 'missing') {
        gaps.push({ cycle: spec.cycle, capability: cap, state })
      } else if (state === 'not_applicable' && !spec.notApplicableReason) {
        gaps.push({ cycle: spec.cycle, capability: cap, state })
      }
    }
  }
  return gaps
}

// ─────────────────────────── Index_Code_Map ───────────────────────────

/**
 * Index_Code_Map：每张未 skip 的 Hub_Sheet 的 sheet_name / Sheet_Code_Tail / 源模板真实索引号 / 偏差原因
 *
 * 偏差来源：
 * - 跨枢纽编码污染（G0 内 F0-8、L0 内 F0A）
 * - 源模板内部索引错位（K0-1 调节写 K1-12、L0-1 调节写 F0-4）
 * - 尾码正则不命中（G0 差异表以括号收尾）
 * - 借用编码（E0 的 F1-12 邮件传真回函核对 → 功能是 E0 可靠性）
 */
export interface IndexCodeEntry {
  /** 所属枢纽 */
  cycle: ConfirmationHubCycle
  /** 精确 sheet_name（classification 中的值） */
  sheetName: string
  /** _SHEET_CODE_RE 尾码提取结果（null = 提取失败） */
  sheetCodeTail: string | null
  /** 源模板内该 sheet 真实索引号 */
  sourceIndexNo: string
  /** 偏差原因（无偏差则空字符串） */
  deviationReason: string
}

/**
 * 已知偏差清单（不改源 xlsx，仅登记）
 * 完整的 Index_Code_Map 待 Task 1.4 实测后补全；此处先列已确认偏差项。
 */
export const KNOWN_INDEX_DEVIATIONS: IndexCodeEntry[] = [
  {
    cycle: 'G0',
    sheetName: '函证程序舞弊风险评价表F0-8',
    sheetCodeTail: 'F0-8',
    sourceIndexNo: 'G0-8',
    deviationReason: '跨枢纽编码污染：G0 源模板复制自 F0，保留了 F0-8 编码未改为 G0-8',
  },
  {
    cycle: 'G0',
    sheetName: '函证差异核对表G0-3（证券投资）',
    sheetCodeTail: null, // 尾码正则不命中（以全角括号收尾）
    sourceIndexNo: 'G0-4', // 源模板真实索引号（G0-3 是跟函控制）
    deviationReason: '尾码正则不命中 + 源模板索引号实为 G0-4（G0-3 = 跟函控制）',
  },
  {
    cycle: 'G0',
    sheetName: '函证差异核对表G0-4(非证券投资)',
    sheetCodeTail: null, // 尾码正则不命中（以半角括号收尾）
    sourceIndexNo: 'G0-5', // 源模板真实索引号
    deviationReason: '尾码正则不命中 + 源模板索引号实为 G0-5（G0-4 = 差异核对证券版）',
  },
  {
    cycle: 'L0',
    sheetName: '函证程序表F0A',
    sheetCodeTail: 'F0A',
    sourceIndexNo: 'L0A',
    deviationReason: '跨枢纽编码污染：L0 源模板复制自 F0，保留了 F0A 编码未改为 L0A',
  },
  {
    cycle: 'E0',
    sheetName: '邮件传真回函核对记录F1-12',
    sheetCodeTail: 'F1-12',
    sourceIndexNo: 'E0-可靠性',
    deviationReason: '借用编码：E0 无 X0-7 可靠性 sheet，该表是 E0 回函可靠性核对（借 F1-12 编码）',
  },
]
