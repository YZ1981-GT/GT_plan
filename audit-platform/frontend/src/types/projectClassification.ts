/**
 * 项目质控业务分类 / 专项场景（spec trim-generation-plan-followup-optimizations R4）。
 *
 * 后端单一解释：`app.services.project_classification.ProjectClassification.as_dict()`，随项目详情、
 * 向导基本信息、D4 渲染的 project_context 下发。前端只读它的结果，不再按 business_category 首字母或子串自行判断。
 * 场景登记值与中文名与后端 SCENARIOS / SCENARIO_LABELS 逐值一致（backend tests/test_project_classification.py 对拍）。
 */

export type ProjectScenario =
  | 'normal'
  | 'ipo'
  | 'listed'
  | 'refinancing'
  | 'transfer'
  | 'restructure'
  | 'fraud_response'

export interface ProjectClassification {
  /** 参考标准登记码（A / A1~A8、B / B1~B6、C）；未填写为 null */
  category_code: string | null
  category_group: 'A' | 'B' | 'C'
  /** 未填写分类：判定按 C 类，界面应注明「按 C 类」 */
  defaulted: boolean
  scenario: ProjectScenario
  scenario_label: string
  is_ipo: boolean
  is_refinancing: boolean
  is_capital_market: boolean
  /** 适用性标签（ipo / listed / neeq / restructuring / refinancing / fraud_risk） */
  tags: string[]
}

export const SCENARIO_OPTIONS: ReadonlyArray<{ value: ProjectScenario; label: string }> = [
  { value: 'normal', label: '常规年审' },
  { value: 'ipo', label: 'IPO 申报' },
  { value: 'listed', label: '上市公司年审' },
  { value: 'refinancing', label: '再融资' },
  { value: 'transfer', label: '新三板挂牌' },
  { value: 'restructure', label: '重大资产重组' },
  { value: 'fraud_response', label: '舞弊应对' },
]

/** 向导只提供组级选择；已有细分类（A1~B6）读回时原样保留并显示，不擅自改子类。 */
export const CATEGORY_GROUP_OPTIONS: ReadonlyArray<{ value: 'A' | 'B' | 'C'; label: string }> = [
  { value: 'A', label: 'A 类 — 重大公众利益实体（上市、IPO、重组、再融资、央企 / 大型国企、金融机构等）' },
  { value: 'B', label: 'B 类 — 其他公众利益实体及特殊行业（新三板 / 北交所、债券发行、特定行业等）' },
  { value: 'C', label: 'C 类 — 一般审计业务' },
]

/** 报告模板类型（company_subtype）字母 → 质控分类组别建议；只用于提示，不自动写入。 */
export function categoryGroupFromSubtype(subtype: string | null | undefined): 'A' | 'B' | 'C' | null {
  const letter = (subtype || '').replace(/^type_/i, '').toUpperCase()
  return letter === 'A' || letter === 'B' || letter === 'C' ? letter : null
}

export type CategoryGroup = ProjectClassification['category_group']

/** 参考标准登记的分类码（与后端 `project_classification.category_codes()` 逐值一致，backend tests 对拍）。 */
export const CATEGORY_CODES: ReadonlyArray<string> = [
  'A', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8',
  'B', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6',
  'C',
]

/**
 * 分类码 → 组别，与后端 `resolve` 同口径：登记码取所属组；空值、未登记值（含 V219 迁移前残留的 IPO）按 C。
 * 只给不来自项目分类列的码用（如 A1-11 表里填的「鉴证业务分类」）；项目分类读 {@link classificationOf}。
 * 原先各处 `=== 'A'` 精确比较：A1~A8 项目被当成非 A 类（A1-11 少了质控复核 / EQCR 必签）。
 */
export function categoryGroupOfCode(code: string | null | undefined): CategoryGroup {
  const normalized = String(code ?? '').trim().toUpperCase()
  return CATEGORY_CODES.includes(normalized) ? (normalized.charAt(0) as CategoryGroup) : 'C'
}

/** 后端下发的分类解释：项目详情 / project_context / 复核上下文上的 `project_classification`，或它本身；没有返回 null。 */
export function classificationOf(source: unknown): ProjectClassification | null {
  if (!source || typeof source !== 'object') return null
  const holder = source as { project_classification?: unknown }
  const candidate = (holder.project_classification && typeof holder.project_classification === 'object'
    ? holder.project_classification
    : source) as Partial<ProjectClassification>
  const group = candidate.category_group
  return group === 'A' || group === 'B' || group === 'C' ? (candidate as ProjectClassification) : null
}

/** 组别展示：`A 类`、细分类 `A 类（A1）`、未填写 `C 类（分类未填写）`；没有分类信息返回空串。 */
export function describeCategoryGroup(classification: ProjectClassification | null | undefined): string {
  if (!classification) return ''
  const { category_group: group, category_code: code } = classification
  if (classification.defaulted || !code) return `${group} 类（分类未填写）`
  return code === group ? `${group} 类` : `${group} 类（${code}）`
}
