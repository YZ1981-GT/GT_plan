/**
 * useC1SectionEngine — C1 企业层面控制测试 九段分组 / 适用性 / 进度 纯函数引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 单一来源（single source）：九段定义、行区间切分、分组、适用性校验、进度分母
 * 统一由本模块提供，GtC1EntityControl.vue 与 useC1ControlData 复用，避免逻辑重复。
 *
 * 🔴 Phase0 实测修正：源模板主程序表**不是 5 段 COSO 五要素，而是九段（一~九）**。
 * COSO 五要素保留为方法论叙述，程序表分组按源模板九段落地。
 * 详见 .kiro/specs/c1-entity-level-control/phase0-notes.md 第 2、3 节。
 *
 * Spec: .kiro/specs/c1-entity-level-control/
 * Requirements: 2.1, 3.2, 3.3
 */

// ─── 九段 slug ─────────────────────────────────────────────────────────────────

/** 九段 slug（供 item_id 与前端 key 使用；Phase0 §3） */
export type C1SectionSlug = 'ce' | 'ra' | 'mo' | 'bu' | 'ic' | 'fr' | 'el' | 'ye' | 'rp'

/** 九段定义（含源模板行区间，Phase0 §2 实测逐行确认） */
export interface C1SectionDef {
  slug: C1SectionSlug
  order: number
  title: string
  /** 是否默认适用（bu/rp 需整段裁剪） */
  defaultApplicable: boolean
  /** 源模板主程序表内该段起始行（含） */
  startRow: number
  /** 源模板主程序表内该段结束行（含） */
  endRow: number
  /** 按需适用说明 */
  note?: string
}

/**
 * 九段权威定义（单一来源）。
 * 与后端 `_c1_entity_control.C1_SECTION_GROUPS` / `C1.yaml section_groups` 对齐；
 * startRow/endRow 取自 Phase0 §2 主程序表九段切分行。
 *
 * 铁律：九段行区间**连续无缝无重叠**（6..136），是 Property 2「分组完整性」的前提。
 */
export const C1_SECTION_DEFS: readonly C1SectionDef[] = Object.freeze([
  { slug: 'ce', order: 1, title: '控制环境', defaultApplicable: true, startRow: 6, endRow: 56 },
  { slug: 'ra', order: 2, title: '风险评估', defaultApplicable: true, startRow: 57, endRow: 66 },
  { slug: 'mo', order: 3, title: '监督', defaultApplicable: true, startRow: 67, endRow: 76 },
  { slug: 'bu', order: 4, title: '监控业务单元', defaultApplicable: false, startRow: 77, endRow: 87, note: '集团审计适用' },
  { slug: 'ic', order: 5, title: '信息与沟通', defaultApplicable: true, startRow: 88, endRow: 93 },
  { slug: 'fr', order: 6, title: '财务报告', defaultApplicable: true, startRow: 94, endRow: 120 },
  { slug: 'el', order: 7, title: '对业务层面控制的影响', defaultApplicable: true, startRow: 121, endRow: 125 },
  { slug: 'ye', order: 8, title: '年终程序', defaultApplicable: true, startRow: 126, endRow: 127 },
  { slug: 'rp', order: 9, title: '关联方相关内容', defaultApplicable: false, startRow: 128, endRow: 136, note: '有关联方交易适用' },
])

/** 九段 slug 有序列表 */
export const C1_SECTION_SLUGS: readonly C1SectionSlug[] = C1_SECTION_DEFS.map((d) => d.slug)

/** 主程序表段落总行区间（含端点），用于判定某行是否属于程序步骤范围 */
export const C1_PROGRAM_ROW_MIN = C1_SECTION_DEFS[0].startRow
export const C1_PROGRAM_ROW_MAX = C1_SECTION_DEFS[C1_SECTION_DEFS.length - 1].endRow

/** slug → def 快查表 */
const SLUG_TO_DEF = new Map<C1SectionSlug, C1SectionDef>(
  C1_SECTION_DEFS.map((d) => [d.slug, d]),
)

/** 判断字符串是否为合法九段 slug */
export function isC1SectionSlug(slug: unknown): slug is C1SectionSlug {
  return typeof slug === 'string' && SLUG_TO_DEF.has(slug as C1SectionSlug)
}

// ─── 行 → 段 唯一归属（Property 2） ─────────────────────────────────────────────

/**
 * 按源模板行号将程序步骤唯一归入九段之一。
 *
 * 九段行区间连续无缝无重叠，故任一行至多命中一个段：
 * - 行在 [startRow, endRow] 内 → 返回对应 slug
 * - 行在九段范围外（如表头 1-5 或 >136）→ 返回 null（非程序步骤）
 */
export function assignSectionByRow(row: number): C1SectionSlug | null {
  if (!Number.isFinite(row)) return null
  for (const d of C1_SECTION_DEFS) {
    if (row >= d.startRow && row <= d.endRow) return d.slug
  }
  return null
}

// ─── 分组（Property 2：无遗漏无重复） ──────────────────────────────────────────

/** 分组结果：九段各自的步骤 + 落在九段范围外的步骤 */
export interface GroupedSteps<T> {
  /** slug → 该段步骤（顺序保持输入顺序） */
  groups: Record<C1SectionSlug, T[]>
  /** 未归入任一段的步骤（行号越界） */
  ungrouped: T[]
}

function emptyGroups<T>(): Record<C1SectionSlug, T[]> {
  const g = {} as Record<C1SectionSlug, T[]>
  for (const slug of C1_SECTION_SLUGS) g[slug] = []
  return g
}

/**
 * 按行号将程序步骤分组到九段（Property 2）。
 *
 * 不变式：
 * - 每个步骤唯一归入某段或 ungrouped（无重复）
 * - Σ|groups[slug]| + |ungrouped| == steps.length（无遗漏）
 */
export function groupStepsByRow<T extends { row: number }>(steps: readonly T[]): GroupedSteps<T> {
  const groups = emptyGroups<T>()
  const ungrouped: T[] = []
  for (const step of steps) {
    const slug = assignSectionByRow(step.row)
    if (slug) groups[slug].push(step)
    else ungrouped.push(step)
  }
  return { groups, ungrouped }
}

/**
 * 按已标注的 section slug 将程序步骤分组到九段（后端 render-config 已附 section 时使用）。
 *
 * 不变式同 groupStepsByRow：合法 slug 唯一归入对应段，非法 slug 归入 ungrouped，
 * Σ 分组数 + ungrouped == 输入总数。
 */
export function groupStepsBySlug<T extends { section?: string; phase?: string }>(
  steps: readonly T[],
): GroupedSteps<T> {
  const groups = emptyGroups<T>()
  const ungrouped: T[] = []
  for (const step of steps) {
    const raw = step.section ?? step.phase
    if (isC1SectionSlug(raw)) groups[raw].push(step)
    else ungrouped.push(step)
  }
  return { groups, ungrouped }
}

/** 分组后所有段步骤数之和（不含 ungrouped） */
export function totalGrouped<T>(grouped: GroupedSteps<T>): number {
  let n = 0
  for (const slug of C1_SECTION_SLUGS) n += grouped.groups[slug].length
  return n
}

// ─── 适用性校验（Property 3：不适用必有理由方可保存） ──────────────────────────

/**
 * 判定「是否适用」标记能否持久化保存（Requirement 3.2）。
 *
 * - 适用（applicable=true）→ 始终可保存
 * - 不适用（applicable=false）→ 必须填写非空理由才可保存
 */
export function canPersistApplicability(applicable: boolean, reason?: string | null): boolean {
  if (applicable) return true
  return !!(reason && reason.trim())
}

// ─── 进度分母（Property 3：完成进度分母排除不适用项） ───────────────────────────

/** checklist_responses 精简形态（供纯函数进度计算） */
export interface C1ResponseLike {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 段进度明细 */
export interface SectionProgressDetail {
  /** 分母：本段「适用」且出现过的步骤数（排除不适用步骤，Req 3.3） */
  denominator: number
  /** 分子：已完成（有测试结果/执行人/索引值）的适用步骤数 */
  completed: number
  /** 完成百分比（0-100，四舍五入） */
  percent: number
}

/**
 * 计算某段完成进度明细（Requirement 2.3 / 3.3）。
 *
 * 口径（与 GtC1EntityControl 历史逻辑一致，单一来源）：
 * - 整段不适用（sectionApplicable=false）→ 视为已裁剪，percent=100（不拖累进度）
 * - 步骤适用性以 `C1-{slug}-{step}-applicable` 的 conclusion 判定（'N' 为不适用）
 * - 分母 = 「适用」且至少出现一个字段（applicable/result/executor/index）的步骤数
 *   （不适用步骤排除出分母，Req 3.3）
 * - 分子 = 适用步骤中，含非空「结果/执行人/索引」值的步骤数（仅标记适用不算完成）
 *
 * @param responses 本底稿全部 C1- 响应（数组；将被遍历两次）
 * @param slug 段 slug
 * @param sectionApplicable 整段是否适用（默认 true）
 */
export function sectionProgressDetail(
  responses: readonly C1ResponseLike[],
  slug: string,
  sectionApplicable = true,
): SectionProgressDetail {
  if (!sectionApplicable) return { denominator: 0, completed: 0, percent: 100 }

  const prefix = `C1-${slug}-`

  // 第一遍：收集各步骤适用性标记
  const stepApplicable = new Map<string, boolean>()
  for (const r of responses) {
    const itemId = r.item_id
    if (!itemId.startsWith(prefix)) continue
    const m = itemId.slice(prefix.length).match(/^(\d+)-applicable$/)
    if (m) stepApplicable.set(m[1], r.conclusion !== 'N')
  }

  // 第二遍：统计（排除不适用步骤，Req 3.3）
  const stepsSeen = new Set<string>()
  const stepsDone = new Set<string>()
  for (const r of responses) {
    const itemId = r.item_id
    if (!itemId.startsWith(prefix)) continue
    const m = itemId.slice(prefix.length).match(/^(\d+)-(applicable|result|executor|index)$/)
    if (!m) continue
    const step = m[1]
    const field = m[2]
    // 不适用步骤排除出分母（Req 3.3）
    if (stepApplicable.get(step) === false) continue
    stepsSeen.add(step)
    // 「已完成」以实际测试工作（结果/执行人/索引）为准；仅标记适用不算完成
    const hasVal = (r.conclusion && r.conclusion.trim()) || (r.remark && r.remark.trim())
    if (field !== 'applicable' && hasVal) stepsDone.add(step)
  }

  const denominator = stepsSeen.size
  const completed = stepsDone.size
  const percent = denominator === 0 ? 0 : Math.round((completed / denominator) * 100)
  return { denominator, completed, percent }
}

/** 计算某段完成百分比（sectionProgressDetail 的便捷包装） */
export function sectionProgressPercent(
  responses: readonly C1ResponseLike[],
  slug: string,
  sectionApplicable = true,
): number {
  return sectionProgressDetail(responses, slug, sectionApplicable).percent
}
