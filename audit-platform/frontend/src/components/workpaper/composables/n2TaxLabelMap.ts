/**
 * N2 应交税费——税种名称归一映射（单一真源）
 *
 * 三层共用：
 * 1. 后端 `_classify_tax_type` 的 classifyKey → 审定预填键 `N2-1-{key}-*`
 * 2. 前端披露表行骨架默认 label
 * 3. 附注模板 rows[].label
 *
 * 源模板权威 = `backend/wp_templates/N/N2 应交税费.xlsx`
 *   `附注披露信息（上市公司）` R8~R20  /  `附注披露信息（国企）` R8~R20
 *   两版 A 列逐字一致（13 行）。
 *
 * spec: .kiro/specs/n2-disclosure-and-extraction-alignment/
 * Requirements: 6.1, 6.2, 6.3
 */

// ─── 源模板 13 固定税种映射 ──────────────────────────────────────────────────

export interface N2TaxLabelEntry {
  /** 源模板披露 A 列逐字（= 附注模板 rows[].label） */
  disclosureLabel: string
  /** 后端 `_classify_tax_type` 输出键（= 审定预填 `N2-1-{key}-*` 的 key 段） */
  classifyKey: string
  /** 源模板行序（R8=1 … R20=13），控制默认排序 */
  sortOrder: number
}

/**
 * 规范名 → 源模板映射。
 *
 * key = 规范名（`normalizeTaxLabel` 的**输出**）。
 * 🔴 key 必须逐字等于 `disclosureLabel`——规范名即源模板 label。
 */
export const N2_TAX_LABEL_MAP: Record<string, N2TaxLabelEntry> = {
  '企业所得税': { disclosureLabel: '企业所得税', classifyKey: 'cit', sortOrder: 1 },
  '增值税': { disclosureLabel: '增值税', classifyKey: 'vat', sortOrder: 2 },
  '消费税': { disclosureLabel: '消费税', classifyKey: 'consumption', sortOrder: 3 },
  '资源税': { disclosureLabel: '资源税', classifyKey: 'resource', sortOrder: 4 },
  '土地增值税': { disclosureLabel: '土地增值税', classifyKey: 'lvt', sortOrder: 5 },
  '城市维护建设税': { disclosureLabel: '城市维护建设税', classifyKey: 'urban', sortOrder: 6 },
  '车船牌照税': { disclosureLabel: '车船牌照税', classifyKey: 'vehicle', sortOrder: 7 },
  '房产税': { disclosureLabel: '房产税', classifyKey: 'property', sortOrder: 8 },
  '土地使用税': { disclosureLabel: '土地使用税', classifyKey: 'land-use', sortOrder: 9 },
  '教育费附加': { disclosureLabel: '教育费附加', classifyKey: 'education', sortOrder: 10 },
  '矿产资源补偿费': { disclosureLabel: '矿产资源补偿费', classifyKey: 'mineral', sortOrder: 11 },
  '代扣代缴外国企业所得税': { disclosureLabel: '代扣代缴外国企业所得税', classifyKey: 'wh-foreign-cit', sortOrder: 12 },
  '代扣代缴个人所得税': { disclosureLabel: '代扣代缴个人所得税', classifyKey: 'wh-iit', sortOrder: 13 },
}

/**
 * 源模板 R8~R20 逐字 label 数组（排序同源模板行序）。
 * 供 `N2_LISTED_TAX_ITEMS` / `N2_SOE_TAX_ITEMS` / 附注模板 rows 引用。
 */
export const N2_FIXED_TAX_LABELS: readonly string[] = Object.values(N2_TAX_LABEL_MAP)
  .sort((a, b) => a.sortOrder - b.sortOrder)
  .map((e) => e.disclosureLabel)

/** classifyKey → 源模板 label 反查（供后端 prefill 键映射到披露行） */
export const DISCLOSURE_LABEL_BY_CLASSIFY_KEY: Record<string, string> = Object.fromEntries(
  Object.values(N2_TAX_LABEL_MAP).map((e) => [e.classifyKey, e.disclosureLabel]),
)

/** classifyKey → 规范名反查（与 DISCLOSURE_LABEL_BY_CLASSIFY_KEY 同值，因 key = label） */
export const NORMALIZE_NAME_BY_CLASSIFY_KEY = DISCLOSURE_LABEL_BY_CLASSIFY_KEY

// ─── 归一函数 ────────────────────────────────────────────────────────────────

/**
 * 变体名 → 规范名（= 源模板 label）。
 *
 * 覆盖已知变体：
 * - 未交增值税 / 简易计税 / 转让金融商品应交增值税 → 增值税（合并到同一披露行）
 * - 城建税 / 城市维护建设 → 城市维护建设税
 * - 车船税 / 车船使用税 → 车船牌照税
 * - 城镇土地使用税 → 土地使用税
 * - 个人所得税（不含「代扣代缴」前缀）→ 代扣代缴个人所得税
 * - 地方教育附加 / 地方教育费附加 → 教育费附加（合并列示）
 *
 * 🔴 「印花税」源模板无固定行——不归一到任何固定行，保留原名（走动态增行或合并到其他）。
 *
 * @returns 规范名。无法归一的返回原始 trim 值（外层按 includes 匹配或走动态行）。
 */
export function normalizeTaxLabel(raw: string): string {
  const s = (raw ?? '').trim()
  if (!s) return ''

  // 精确命中规范名直接返回
  if (s in N2_TAX_LABEL_MAP) return s

  // ── 增值税族（源模板一行合并）──────────────────────────────────────
  // 🔴 「简易计税」**不含「增值税」子串**，必须单列且用 includes（真实科目名带前缀，
  //    如 `应交税费_简易计税`；精确匹配会漏）。源模板附注提示要求增值税含：
  //    未交增值税 / 简易计税 / 转让金融商品应交增值税 / 代扣代缴增值税。
  if (s.includes('简易计税')) return '增值税'
  // "增值税" 子串（排除已单独判断的「土地增值税」）
  if (s.includes('增值税') && !s.includes('土地增值税')) return '增值税'

  // ── 城建税 ─────────────────────────────────────────────────────────
  if (s === '城建税' || s.includes('城市维护建设')) return '城市维护建设税'

  // ── 车船税 ─────────────────────────────────────────────────────────
  if (s === '车船税' || s === '车船使用税') return '车船牌照税'

  // ── 土地使用税 ─────────────────────────────────────────────────────
  if (s === '城镇土地使用税' || (s.includes('土地使用') && !s.includes('增值'))) return '土地使用税'

  // ── 代扣代缴外国企业所得税（必须先于「企业所得税」判断）───────────────
  if (s.includes('代扣代缴') && s.includes('外国') && s.includes('所得税')) return '代扣代缴外国企业所得税'

  // ── 代扣代缴个人所得税 ─────────────────────────────────────────────
  if (s.includes('代扣代缴') && s.includes('个人所得税')) return '代扣代缴个人所得税'

  // ── 个人所得税（无「代扣代缴」前缀）→ 合并到代扣代缴行 ─────────────
  // 🔴 用 includes 而非 ===：真实科目名带前缀（`应交税费_应交个人所得税`）
  if (s.includes('个人所得税')) return '代扣代缴个人所得税'

  // ── 地方教育附加 → 合并到教育费附加（须先于「教育费附加」判定）──────
  // 🔴 用 includes：真实科目名 `应交税费_应交地方教育附加`
  if (s.includes('地方教育')) return '教育费附加'

  // ── 教育费附加（含前缀形态）────────────────────────────────────────
  if (s.includes('教育费附加')) return '教育费附加'

  // ── 矿产资源补偿费（含「矿产资源」关键字，须先于「资源税」）───────────
  if (s.includes('矿产资源')) return '矿产资源补偿费'

  // ── 其余固定行的「带科目前缀」兜底 ─────────────────────────────────
  // 真实 tb_balance 科目名形如 `应交税费_应交城市维护建设税`，精确匹配全部落空，
  // 故对剩余固定行统一做子串包含兜底。顺序已由上方各条消解子串冲突。
  if (s.includes('资源税')) return '资源税'
  if (s.includes('消费税')) return '消费税'
  if (s.includes('房产税')) return '房产税'
  if (s.includes('企业所得税')) return '企业所得税'
  // 🔴 印花税不在源模板 13 固定行 —— 不归一，保留原名走动态增行

  // 无法归一 → 返回原名（走动态增行）
  return s
}

/**
 * classifyKey（后端预填键）→ 源模板 label。
 * 无映射返回 undefined（该 key 对应的税种在源模板无固定行，走动态行或 other）。
 */
export function classifyKeyToLabel(key: string): string | undefined {
  return DISCLOSURE_LABEL_BY_CLASSIFY_KEY[key]
}
