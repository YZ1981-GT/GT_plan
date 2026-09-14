/**
 * useC22BundleState — C22 IT 一般控制测试聚合组件的跨 Tab 业务状态管理
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Tasks 3.1 / 3.2
 * Requirements: 4.1, 5.1, 5.2, 7.1, 7.2, 7.4
 *
 * 职责（对齐 useA17BundleState / useA1SubWorkpapers 模式）：
 * 1. sheetTabs 分组：matrix + 4 大类（SA/PE/PM/NS）子页 + C21 + C21-1
 *    —— 严格按 Phase0 §3 TabDef 分组表（35 tabs，matrix 排序按控制编号）
 * 2. wpIdMap：C21 / C21-1 → wp_id（通过 wp_index 解析）
 * 3. completionMap：按控制点读取 设计/执行有效性结论 推导 CompletionStatus
 * 4. defects：收集所有子页「是否异常=是」的缺陷（联动 C21-1）
 * 5. progressSummary：完成/进行中/未开始 + 缺陷总数
 * 6. refreshCompletion：拉取 C22 父底稿 checklist-responses 刷新状态
 *
 * 🔴 Phase0 关键修正（§7 差异清单）：
 * - PE 组实为 8 sheet（含 2 个 aux 续页 PE-5.1 / PE-8.1），但续页**无缺陷评估、
 *   不计入控制点/缺陷统计** → kind='itgc-aux'。
 * - 33 子页中仅 **31 个为真正控制点**（kind='itgc-sheet'）；completionMap 与 defects
 *   只遍历这 31 个 itgc-sheet，排除 matrix / C21 / C21-1 / aux 续页。
 * - PM-4c 源模板公式损坏（B1/B2 = `!#REF!`，对应矩阵 C32/D32）→ refBroken 兜底。
 * - C21-1「财务报表认定」为 9 子列（附加于缺陷条目，用户补充）。
 *
 * 仅做数据读取与状态推导，不做数据写入（写入由主入口组件负责）。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { getWpIndex } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'

// ─── Types (exported for testability) ───

export type CompletionStatus = 'completed' | 'in_progress' | 'not_started'

/** C22 四大 IT 控制类别（+ matrix / 独立底稿分组） */
export type ItgcGroup =
  | 'matrix'
  | '信息安全'
  | '运行维护'
  | '程序变更'
  | '新系统'
  | 'IT团队'
  | '发现汇总'

/**
 * TabDef.kind：
 * - 'matrix'     ITGC 控制矩阵总览
 * - 'itgc-sheet' 真正的 IT 控制测试子页（有缺陷评估，计入 31 控制点）
 * - 'itgc-aux'   续页/样本页（PE-5.1 / PE-8.1，无缺陷评估，不计入统计）
 * - 'c21'        C21 IT 专业成员（独立底稿）
 * - 'c21-1'      C21-1 IT 审计发现汇总表（独立底稿）
 */
export type TabKind = 'matrix' | 'itgc-sheet' | 'itgc-aux' | 'c21' | 'c21-1'

export interface TabDef {
  id: string
  label: string
  group: ItgcGroup
  kind: TabKind
  /** C22 工作簿内 sheet 名（matrix / itgc-sheet / itgc-aux） */
  sheet?: string
  /** 独立底稿编码（C21 / C21-1） */
  wpCode?: string
  /** 主矩阵行引用（C 列控制编号所在行；多控制子页取首行） */
  matrixRow?: number
  /** 多控制子页额外引用的控制描述行（D 列） */
  extraDescRows?: number[]
  /** 🔴 源模板公式损坏（PM-4c B1/B2=#REF!）→ 渲染兜底 */
  refBroken?: boolean
}

/**
 * ItgcDefect — 子页缺陷评估「是否异常=是」汇总到 C21-1 的缺陷条目。
 * 字段对齐 Phase0 §5 缺陷字段映射（子页 → C21-1 实列）。
 */
export interface ItgcDefect {
  /** 子页控制编号（如 SA-7） */
  controlId: string
  /** 所属大类（信息安全/运行维护/程序变更/新系统）→ C21-1「类别」 */
  group: ItgcGroup
  /** 来源 sheet（双向追溯，Req 12.3） */
  sheet: string
  /** 缺陷描述 → C21-1「问题描述」 */
  description: string
  /** 缺陷编号 ITGC#N（索引至 C21-1） */
  defectNo: string
  /** 相关应用系统（矩阵 E 列回填，可选） */
  appSystem?: string
}

export interface ProgressSummary {
  completed: number
  inProgress: number
  notStarted: number
  defectCount: number
}

/** checklist_responses 精简形态 */
export interface ChecklistResponse {
  item_id: string
  conclusion?: string | null
  remark?: string | null
  wp_ref?: string | null
}

/** 单个控制点从 responses 抽取的字段集合 */
export interface ControlPointFields {
  designConclusion: string | null
  execConclusion: string | null
  abnormal: string | null
  defectDesc: string | null
  defectNo: string | null
  appSystem: string | null
  itCategory: string | null
}

export interface UseC22BundleStateOptions {
  projectId: Ref<string>
  /** C22 父底稿 wp_id（33 子页同属该工作簿，responses 挂在此底稿下） */
  wpId: Ref<string>
}

export interface UseC22BundleStateReturn {
  wpIdMap: ComputedRef<Record<string, string>>
  sheetTabs: ComputedRef<TabDef[]>
  controlPointTabs: ComputedRef<TabDef[]>
  completionMap: ComputedRef<Record<string, CompletionStatus>>
  /** 每个控制点从 responses 抽取的字段集合（matrix 总览面板消费：设计/执行结论/是否异常/缺陷编号/应用系统） */
  controlFields: ComputedRef<Record<string, ControlPointFields>>
  defects: ComputedRef<ItgcDefect[]>
  progressSummary: ComputedRef<ProgressSummary>
  loading: Ref<boolean>
  loadWpIndex: () => Promise<void>
  refreshCompletion: (sheet?: string) => Promise<void>
}

// ─── TabDef 分组表（Phase0 §3，单一来源） ───
// 顺序：matrix → 信息安全 SA(10) → 运行维护 PE(6 控制点 + 2 aux 续页) →
//        程序变更 PM(6) → 新系统 NS(9) → C21 → C21-1
// matrix 排序按控制编号（矩阵 C 列顺序），非工作簿 sheet 物理顺序（Phase0 §7 D6）。

export const C22_BUNDLE_TABS: readonly TabDef[] = Object.freeze([
  { id: 'matrix', label: 'ITGC 控制矩阵总览', group: 'matrix', kind: 'matrix', sheet: 'C22 IT一般控制测试' },

  // ── 信息安全 SA（10 控制点） ──
  { id: 'SA-3', label: 'SA-3', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-3', matrixRow: 10 },
  { id: 'SA-4c', label: 'SA-4c', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-4c', matrixRow: 11 },
  { id: 'SA-5', label: 'SA-5', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-5', matrixRow: 12 },
  { id: 'SA-7', label: 'SA-7', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-7', matrixRow: 13 },
  { id: 'SA-9', label: 'SA-9', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-9', matrixRow: 14 },
  { id: 'SA-10', label: 'SA-10', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-10', matrixRow: 15 },
  { id: 'SA-11', label: 'SA-11', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-11', matrixRow: 16 },
  { id: 'SA-12', label: 'SA-12', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-12', matrixRow: 17 },
  { id: 'SA-13', label: 'SA-13', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-13', matrixRow: 18 },
  { id: 'SA-14', label: 'SA-14', group: '信息安全', kind: 'itgc-sheet', sheet: 'SA-14', matrixRow: 19 },

  // ── 运行维护 PE（6 控制点 + 2 aux 续页） ──
  { id: 'PE-3a', label: 'PE-3a', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-3a', matrixRow: 20 },
  { id: 'PE-3d', label: 'PE-3d', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-3d', matrixRow: 21, extraDescRows: [22] },
  { id: 'PE-5', label: 'PE-5', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-5', matrixRow: 23 },
  { id: 'PE-5.1', label: 'PE-5.1（续页）', group: '运行维护', kind: 'itgc-aux', sheet: 'PE-5.1' },
  { id: 'PE-6', label: 'PE-6', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-6', matrixRow: 24, extraDescRows: [25, 26, 27] },
  { id: 'PE-7', label: 'PE-7', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-7', matrixRow: 28 },
  { id: 'PE-8', label: 'PE-8', group: '运行维护', kind: 'itgc-sheet', sheet: 'PE-8', matrixRow: 29, extraDescRows: [30] },
  { id: 'PE-8.1', label: 'PE-8.1（续页）', group: '运行维护', kind: 'itgc-aux', sheet: 'PE-8.1' },

  // ── 程序变更 PM（6 控制点） ──
  { id: 'PM-3', label: 'PM-3', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-3', matrixRow: 31 },
  { id: 'PM-4c', label: 'PM-4c', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-4c', matrixRow: 32, refBroken: true },
  { id: 'PM-4b', label: 'PM-4b', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-4b', matrixRow: 33 },
  { id: 'PM-4e', label: 'PM-4e', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-4e', matrixRow: 34 },
  { id: 'PM-5', label: 'PM-5', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-5', matrixRow: 35 },
  { id: 'PM-6', label: 'PM-6', group: '程序变更', kind: 'itgc-sheet', sheet: 'PM-6', matrixRow: 36 },

  // ── 新系统 NS（9 控制点；NS-5.x/6.x 仅引用 D 列） ──
  { id: 'NS-1', label: 'NS-1', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-1', matrixRow: 37 },
  { id: 'NS-3', label: 'NS-3', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-3', matrixRow: 38 },
  { id: 'NS-4', label: 'NS-4', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-4', matrixRow: 39 },
  { id: 'NS-5.1', label: 'NS-5.1', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-5.1', matrixRow: 40 },
  { id: 'NS-5.2', label: 'NS-5.2', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-5.2', matrixRow: 41 },
  { id: 'NS-5.3', label: 'NS-5.3', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-5.3', matrixRow: 42 },
  { id: 'NS-5.4', label: 'NS-5.4', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-5.4', matrixRow: 43 },
  { id: 'NS-6.1', label: 'NS-6.1', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-6.1', matrixRow: 44 },
  { id: 'NS-6.2', label: 'NS-6.2', group: '新系统', kind: 'itgc-sheet', sheet: 'NS-6.2', matrixRow: 45 },

  // ── 独立底稿 ──
  { id: 'C21', label: 'C21 IT专业成员', group: 'IT团队', kind: 'c21', wpCode: 'C21' },
  { id: 'C21-1', label: 'C21-1 IT发现汇总', group: '发现汇总', kind: 'c21-1', wpCode: 'C21-1' },
])

/** 4 大 IT 控制类别（分组页签用；不含 matrix / 独立底稿） */
export const ITGC_GROUPS: readonly ItgcGroup[] = Object.freeze([
  '信息安全', '运行维护', '程序变更', '新系统',
])

/** 31 个真正控制点的 sheet 名（PBT 生成器用） */
export const ITGC_CONTROL_SHEETS: readonly string[] = Object.freeze(
  C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-sheet').map(t => t.sheet as string),
)

/** 33 个 C22 工作簿子页 sheet 名（含 2 aux 续页） */
export const ITGC_ALL_SHEETS: readonly string[] = Object.freeze(
  C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-sheet' || t.kind === 'itgc-aux').map(t => t.sheet as string),
)

// ─── 点选枚举选项（Task 8.1，Req 10.1/10.2 单一来源） ───

/** 设计/执行有效性结论选项（el-select 点选，Req 10.1） */
export const CONCLUSION_OPTIONS = ['有效', '部分有效', '无效'] as const

/** IT 控制类别选项（矩阵多选，Req 10.2；Phase0 §2 分类一致） */
export const IT_CATEGORY_OPTIONS = [
  '访问安全', '程序变更', '程序开发', '计算机运行',
  '逻辑安全', '物理安全', '数据备份', '系统接口',
] as const

/** 常见应用系统选项（矩阵多选 + 可自定义，Req 10.2） */
export const APP_SYSTEM_OPTIONS = [
  'ERP', 'OA', '财务系统', '供应链系统', '人力资源系统',
  'CRM', 'MES', 'WMS', '邮件系统', '数据库', '操作系统', '其他',
] as const

// ─── item_id 编码（单一来源，与主入口组件共享） ───

export type ItgcField =
  // ── 结论/枚举字段（存 conclusion） ──
  | 'design-conclusion'   // 设计有效性测试结论（有效/无效/部分有效）
  | 'exec-conclusion'     // 执行有效性测试结论（有效/无效/部分有效）
  | 'abnormal'            // 是否发现异常（是/否）
  // ── 自由文本/结构化字段（存 remark） ──
  | 'defect-desc'         // 缺陷描述
  | 'defect-no'           // 缺陷编号（ITGC#N，索引至 C21-1）
  | 'app-system'          // 相关应用系统（多选 JSON 数组，Req 10.2）
  | 'it-category'         // IT 控制类别（多选 JSON 数组，Req 10.2）
  // ── 子页测试内容（Task 4.2，存 remark） ──
  | 'design-procedure'    // 设计有效性执行的审计程序（长文本）
  | 'design-evidence'     // 设计有效性审计证据（含证据索引号）
  | 'test-period'         // 执行有效性：测试期间 & 样本总量
  | 'sample-size'         // 执行有效性：抽样数量
  | 'exec-procedure'      // 执行有效性执行的审计程序 / 测试步骤
  | 'sample-records'      // 样本记录表（JSON 序列化，抽样>1 时其余样本）
  // ── 附件证据字段（Task 8.2，Req 11.1~11.5，存 remark） ──
  | 'evidence-attachments' // 审计证据区附件列表（JSON 序列化：[{id,name,index,ocrMerged}]）

/**
 * 结论/枚举类字段集合 —— 存入 checklist_responses.conclusion；
 * 其余字段存入 remark。与 extractControlPointFields 的读取口径保持一致（单一来源）。
 */
export const ITGC_CONCLUSION_FIELDS: readonly ItgcField[] = Object.freeze([
  'design-conclusion', 'exec-conclusion', 'abnormal',
])

/** 判定某字段存储于 conclusion（true）还是 remark（false） */
export function itgcFieldStorage(field: ItgcField): 'conclusion' | 'remark' {
  return ITGC_CONCLUSION_FIELDS.includes(field) ? 'conclusion' : 'remark'
}

/** 生成子页字段 item_id：`C22.{controlId}.{field}`（controlId 即 tab.id / sheet 名） */
export function itgcItemId(controlId: string, field: ItgcField): string {
  return `C22.${controlId}.${field}`
}

/**
 * 证据索引号建议规则（Phase0 §D8）：`C22.{控制点}-{序号}`（如 `C22.SA-3-1`）。
 * 序号自 1 起（用于附件/审计证据编号，Task 8.2 复用）。
 */
export function suggestEvidenceIndex(controlId: string, seq: number): string {
  return `C22.${controlId}-${seq}`
}

/** 缺陷编号建议规则：`ITGC#{N}`（N 自 1 起） */
export function suggestDefectNo(n: number): string {
  return `ITGC#${n}`
}

// ─── C21-1 IT 发现汇总 补充字段（Task 5.1） ───
//
// C21-1 汇总视图在自动汇总的缺陷条目上，允许用户补充影响分析 / 整改建议 /
// 财务报表认定（9 认定）等（Req 5.3）。这些补充持久化于 C22 父底稿的
// checklist_responses，item_id 前缀 `C22.C21-1.`（区别于子页 `C22.{控制点}.`），
// 故不与控制点字段抽取冲突（extractControlPointFields 仅查 31 个真实控制点前缀）。
//
// 🔴 持久化锚 = 缺陷来源控制点 controlId（稳定且唯一、恒非空）；不用 defectNo 作 key，
//   因 defectNo 可能为空或被用户改动，会导致补充数据错位/丢失。

/** C21-1 汇总补充字段 */
export type C21SummaryField =
  | 'impact'        // 风险及影响 / 影响分析（Phase0 §5「风险及影响」）
  | 'remediation'   // 整改建议
  | 'assertions'    // 财务报表认定（9 认定，JSON 数组序列化于 remark）
  | 'compensating'  // 补偿性控制及有效性
  | 'report-item'   // 相关报表项目
  | 'audit-effect'  // 对相关财务报表审计工作的影响
  | 'note'          // 备注

/**
 * 财务报表认定 9 项（Phase0 §5：C21-1「财务报表认定」跨 9 子列）。
 * C21-1 汇总视图以多选点选（checkbox）勾选适用认定。
 */
export const FS_ASSERTIONS: readonly string[] = Object.freeze([
  '发生', '完整性', '准确性', '截止', '分类', '存在', '权利和义务', '计价和分摊', '列报',
])

/**
 * C21-1 汇总补充 item_id：`C22.C21-1.{controlId}.{field}`。
 * controlId 为缺陷来源控制点（稳定锚，见上）。
 */
export function c21SummaryItemId(controlId: string, field: C21SummaryField): string {
  return `C22.C21-1.${controlId}.${field}`
}

/** C21-1「上年度/上次审计发现整改情况」表（Phase0 §5 第二张表）item_id（整表 JSON 序列化） */
export const C21_CARRYOVER_ITEM_ID = 'C22.C21-1.__carryover__'

// ─── 纯函数（导出供单元/PBT 测试） ───

/** 判定字符串为非空（trim 后有内容） */
function isFilled(v: string | null | undefined): boolean {
  return !!(v && v.trim())
}

/**
 * 从 responses Map 抽取某控制点的字段集合。
 * conclusion 存结论/枚举值，remark 存自由文本（描述/编号/系统）。
 */
export function extractControlPointFields(
  responsesById: Map<string, ChecklistResponse>,
  controlId: string,
): ControlPointFields {
  const get = (field: ItgcField) => responsesById.get(itgcItemId(controlId, field))
  const design = get('design-conclusion')
  const exec = get('exec-conclusion')
  const abn = get('abnormal')
  const desc = get('defect-desc')
  const no = get('defect-no')
  const app = get('app-system')
  const cat = get('it-category')
  return {
    designConclusion: design?.conclusion ?? null,
    execConclusion: exec?.conclusion ?? null,
    abnormal: abn?.conclusion ?? null,
    defectDesc: desc?.remark ?? null,
    defectNo: no?.remark ?? null,
    appSystem: app?.remark ?? null,
    itCategory: cat?.remark ?? null,
  }
}

/**
 * 完成状态推导（Req 7.1 / design「完成状态推导」）：
 * - 设计 + 执行有效性结论均非空 → completed
 * - 仅其一非空 → in_progress
 * - 均空 → not_started
 */
export function deriveItgcStatus(fields: ControlPointFields): CompletionStatus {
  const d = isFilled(fields.designConclusion)
  const e = isFilled(fields.execConclusion)
  if (d && e) return 'completed'
  if (d || e) return 'in_progress'
  return 'not_started'
}

/**
 * 收集单个控制点的缺陷（若「是否异常=是」）。
 * 返回 null 表示无缺陷（异常≠是）。
 */
export function collectControlPointDefect(
  tab: TabDef,
  fields: ControlPointFields,
): ItgcDefect | null {
  if (fields.abnormal !== '是') return null
  return {
    controlId: tab.id,
    group: tab.group,
    sheet: tab.sheet ?? tab.id,
    description: fields.defectDesc ?? '',
    defectNo: fields.defectNo ?? '',
    appSystem: fields.appSystem ?? undefined,
  }
}

/**
 * 计算进度汇总（Property 4：completed+inProgress+notStarted == 控制点总数；
 * defectCount == defects 长度）。
 */
export function computeProgressSummary(
  completionMap: Record<string, CompletionStatus>,
  defects: readonly ItgcDefect[],
): ProgressSummary {
  let completed = 0, inProgress = 0, notStarted = 0
  for (const status of Object.values(completionMap)) {
    if (status === 'completed') completed++
    else if (status === 'in_progress') inProgress++
    else notStarted++
  }
  return { completed, inProgress, notStarted, defectCount: defects.length }
}

/**
 * 解析 sheetName 路由目标（Property 5，纯函数）：
 * - 合法 Tab id（在 validIds 中）→ 返回该 id
 * - 非法 / 空 / undefined → 返回 null（调用方保持当前 active 不变，默认 matrix）
 *
 * 对应组件 `activateSheet` 的核心判定逻辑（Req 6.1~6.4）。
 */
export function resolveSheetRoute(
  sheetName: string | null | undefined,
  validIds: readonly string[],
): string | null {
  const id = (sheetName ?? '').trim()
  if (!id) return null
  return validIds.includes(id) ? id : null
}

/**
 * 规范化 readonly prop（Property 6，纯函数）：
 * - `true` → true（编辑禁止）
 * - 其他任何值 → false（允许编辑）
 *
 * 对应组件 `isReadonly = computed(() => props.readonly === true)` 的逻辑。
 * 保证 parent readonly → 所有子页/matrix/汇总接收相同值（Req 9.1/9.2）。
 */
export function normalizeReadonly(value: unknown): boolean {
  return value === true
}

/** 状态 → 显示映射（仪表盘三色，Req 7.2） */
export function statusToDisplay(status: CompletionStatus): { icon: string; color: string } {
  switch (status) {
    case 'completed': return { icon: '✓', color: '#52c41a' }
    case 'in_progress': return { icon: '◐', color: '#faad14' }
    case 'not_started': return { icon: '○', color: '#bfbfbf' }
  }
}

// ─── Composable ───

export function useC22BundleState(options: UseC22BundleStateOptions): UseC22BundleStateReturn {
  const { projectId, wpId } = options

  const loading = ref(false)
  /** C21 / C21-1 → wp_id */
  const wpIdMapState = ref<Record<string, string>>({})
  /** C22 父底稿 checklist-responses（item_id → 响应） */
  const responsesById = ref<Map<string, ChecklistResponse>>(new Map())

  // ─── sheetTabs：全部 Tab 定义（单一来源） ───
  const sheetTabs = computed<TabDef[]>(() => C22_BUNDLE_TABS.slice())

  /** 31 个真正控制点 Tab（completionMap / defects 只遍历这些） */
  const controlPointTabs = computed<TabDef[]>(() =>
    C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-sheet'),
  )

  // ─── wpIdMap：C21 / C21-1 ───
  const wpIdMap = computed<Record<string, string>>(() => wpIdMapState.value)

  // ─── completionMap：按 31 控制点推导 ───
  const completionMap = computed<Record<string, CompletionStatus>>(() => {
    const map: Record<string, CompletionStatus> = {}
    for (const tab of controlPointTabs.value) {
      const fields = extractControlPointFields(responsesById.value, tab.id)
      map[tab.id] = deriveItgcStatus(fields)
    }
    return map
  })

  // ─── controlFields：按 31 控制点抽取字段（matrix 总览面板消费） ───
  const controlFields = computed<Record<string, ControlPointFields>>(() => {
    const map: Record<string, ControlPointFields> = {}
    for (const tab of controlPointTabs.value) {
      map[tab.id] = extractControlPointFields(responsesById.value, tab.id)
    }
    return map
  })

  // ─── defects：收集 31 控制点中「是否异常=是」的缺陷 ───
  const defects = computed<ItgcDefect[]>(() => {
    const out: ItgcDefect[] = []
    for (const tab of controlPointTabs.value) {
      const fields = extractControlPointFields(responsesById.value, tab.id)
      const defect = collectControlPointDefect(tab, fields)
      if (defect) out.push(defect)
    }
    return out
  })

  // ─── progressSummary ───
  const progressSummary = computed<ProgressSummary>(() =>
    computeProgressSummary(completionMap.value, defects.value),
  )

  // ─── 数据加载 ───

  /** 解析 C21 / C21-1 的 wp_id（wp_index） */
  async function loadWpIndex(): Promise<void> {
    if (!projectId.value) {
      wpIdMapState.value = {}
      return
    }
    try {
      const items = await getWpIndex(projectId.value)
      const map: Record<string, string> = {}
      for (const item of items) {
        if (item.wp_code === 'C21' || item.wp_code === 'C21-1') {
          map[item.wp_code] = item.wp_id || item.id
        }
      }
      wpIdMapState.value = map
    } catch {
      wpIdMapState.value = {}
    }
  }

  /**
   * 拉取 C22 父底稿 checklist-responses 刷新完成状态与缺陷。
   * sheet 参数保留（Req 7.4：从某子页切走时刷新）；当前实现整表重载后
   * 各 computed 自动重算，故忽略 sheet 精细化。
   */
  async function refreshCompletion(_sheet?: string): Promise<void> {
    if (!wpId.value) {
      responsesById.value = new Map()
      return
    }
    loading.value = true
    try {
      const data = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`, {
        params: { project_id: projectId.value },
        _silent: true,
      } as any)
      const list = (data as ChecklistResponse[]) || []
      const map = new Map<string, ChecklistResponse>()
      for (const r of list) {
        if (r && r.item_id) map.set(r.item_id, r)
      }
      responsesById.value = map
    } catch {
      responsesById.value = new Map()
    } finally {
      loading.value = false
    }
  }

  return {
    wpIdMap,
    sheetTabs,
    controlPointTabs,
    completionMap,
    controlFields,
    defects,
    progressSummary,
    loading,
    loadWpIndex,
    refreshCompletion,
  }
}

export default useC22BundleState
