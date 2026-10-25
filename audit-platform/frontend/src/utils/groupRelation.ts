/**
 * 与上级企业关系（子公司 / 分公司）的取值与默认判定。
 *
 * spec consol-tree-three-code-autobuild 需求 2 / 属性 P11。
 * 🔴 与后端 `backend/app/services/group_relation.py` 是同一规则的两份实现，
 *    两端测试逐条跑共享夹具 `backend/data/relation_to_parent_cases.json`，
 *    改规则必须两端同改并补用例。
 */

export type GroupRelation = 'subsidiary' | 'branch'

export const RELATION_LABELS: Record<GroupRelation, string> = {
  subsidiary: '子公司',
  branch: '分公司',
}

/** 下拉选项（label 含含义说明，value 为落库值） */
export const RELATION_OPTIONS: ReadonlyArray<{ value: GroupRelation; label: string; hint: string }> = [
  { value: 'subsidiary', label: '子公司', hint: '独立法人，合并时抵销' },
  { value: 'branch', label: '分公司', hint: '非独立法人，并入母公司汇总' },
]

/** 分支机构常见名称结尾（「店」覆盖「门店/分店/药店」等） */
const BRANCH_SUFFIXES: ReadonlyArray<string> = [
  '分公司', '分店', '分厂', '营业部', '经营部', '办事处',
  '分行', '支行', '分所', '门店', '店',
]

/** 名称末尾的括号注记，如「（筹）」「（特殊普通合伙）」「(有限合伙)」 */
const TRAILING_PAREN = /[（(][^（()）]*[）)]\s*$/

function stripTrailingParens(name: string): string {
  let out = name
  for (let i = 0; i < 3; i += 1) {
    const stripped = out.replace(TRAILING_PAREN, '').trimEnd()
    if (stripped === out) break
    out = stripped
  }
  return out
}

/**
 * 按企业名称推断默认关系（只作默认值，用户手选优先）。
 * 去掉末尾括号注记后：以分支机构结尾词结尾，或「公司」二字之后仍有字符 ⇒ 分公司；其余 ⇒ 子公司。
 */
export function inferRelationFromName(name: string | null | undefined): GroupRelation {
  const core = stripTrailingParens((name ?? '').trim())
  if (!core) return 'subsidiary'
  if (BRANCH_SUFFIXES.some((s) => core.endsWith(s))) return 'branch'
  const idx = core.lastIndexOf('公司')
  if (idx !== -1 && idx + 2 < core.length) return 'branch'
  return 'subsidiary'
}

/** 关系标签；未知/空值返回空串 */
export function relationLabel(value: string | null | undefined): string {
  return value === 'subsidiary' || value === 'branch' ? RELATION_LABELS[value] : ''
}

function cleanCode(code: string | null | undefined): string {
  return (code ?? '').trim()
}

/**
 * 有效上级代码（需求 1.5）：空 ⇒ null；等于本企业代码 ⇒ null。
 * 上级代码填成本企业代码 = 用户确认「本企业就是上级企业」：本企业是集团顶层，没有另外的上级。
 */
export function effectiveParentCode(
  companyCode: string | null | undefined,
  parentCode: string | null | undefined,
): string | null {
  const parent = cleanCode(parentCode)
  if (!parent || parent === cleanCode(companyCode)) return null
  return parent
}

/** 上级=本企业时的含义：三码相同 ⇒ 'ultimate'（最终控制方）；否则 ⇒ 'top'（顶层企业）；不等 ⇒ null */
export type SelfReferenceKind = 'top' | 'ultimate'

export function selfReferenceKind(
  companyCode: string | null | undefined,
  parentCode: string | null | undefined,
  ultimateCode: string | null | undefined,
): SelfReferenceKind | null {
  const own = cleanCode(companyCode)
  if (!own || cleanCode(parentCode) !== own) return null
  return cleanCode(ultimateCode) === own ? 'ultimate' : 'top'
}

/** 保存前的确认文案（需求 1.5：不拒绝，请用户确认） */
export const SELF_REFERENCE_CONFIRM: Record<SelfReferenceKind, string> = {
  top:
    '上级企业代码与本企业代码相同。确认本企业就是上级企业吗？'
    + '确认后本企业作为集团顶层企业，企业树里只保留这一个节点，不会重复生成上级节点。',
  ultimate:
    '上级企业代码、最终控制方代码都与本企业代码相同。确认本企业即为最终控制方（集团总部或母公司）吗？'
    + '确认后本企业作为企业树的根节点。',
}
