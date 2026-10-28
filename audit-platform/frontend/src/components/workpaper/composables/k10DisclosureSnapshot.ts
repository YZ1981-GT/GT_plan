/**
 * K10 其他收益披露表：表单状态（固定来源分类行 + 已保存覆盖 + 动态追加行 + 说明）与同步快照
 * （底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K10TabDisclosureListed` / `K10TabDisclosureSoe` 原先在组件里内联「默认分类行 → 已保存行覆盖 → 动态追加行 → 拼载荷行
 * （国企另汇总「其中：政府补助」）」；抽成本模块的纯函数后 Tab（setup / onMounted / 同步按钮）与离屏 provider 调同一份计算
 * ⇒ 两条路径发出逐字节相同的载荷。「从审定表取数」（读 K10-1-rows、提示、逐行保存）是按钮 / 事件动作，Tab 挂载时不跑，
 * 离屏也不跑。
 */
import type { K10DisclosureRow, K10DisclosureVariant } from './k10NoteSectionMap'

/** 上市行（补助类型 / 确认方式 / 说明不进附注列） */
export interface K10ListedFormRow {
  category: string
  grantType: string
  recognitionMethod: string
  currentAmount: number
  priorAmount: number
  remark: string
}

/** 国企行（「是否为政府补助」点选只决定合计后「其中：政府补助」行的金额，不是附注列） */
export interface K10SoeFormRow {
  category: string
  currentAmount: number
  priorAmount: number
  isGovGrant: string
  remark: string
}

export interface K10DisclosureFormState<R> {
  rows: R[]
  narrativeText: string
}

/** 底稿回复：`remark` 可能是 JSON 串或已解析对象（与 Tab 读法一致），说明另认 `conclusion` */
export type K10DisclosureResponses = ReadonlyMap<string, any>

/** 固定来源分类（与 K10-1 审定表行对应；上市 9 类 / 国企简洁版 7 类） */
export const K10_DISCLOSURE_CATEGORIES: Record<K10DisclosureVariant, readonly string[]> = {
  listed: [
    '政府补助-即征即退',
    '政府补助-财政贴息',
    '政府补助-研发补助',
    '政府补助-稳岗补贴',
    '政府补助-资源税返还',
    '政府补助-产业扶持',
    '政府补助-其他',
    '其他收益-个税手续费返还',
    '其他收益-其他',
  ],
  soe: ['政府补助', '即征即退', '财政贴息', '研发补助', '稳岗补贴', '其他补贴收入', '个税手续费返还'],
}

/** 动态追加行的条目前缀（K10-1 中不在固定分类的来源，按名持久化；Tab 写、本模块读） */
export const K10_DISCLOSURE_DYN_PREFIX: Record<K10DisclosureVariant, string> = {
  listed: 'K10-disc-listed-dyn-',
  soe: 'K10-disc-soe-dyn-',
}

/** 说明条目 */
const NARRATIVE_ITEM: Record<K10DisclosureVariant, string> = {
  listed: 'K10-disclosure-listed-narrative',
  soe: 'K10-disclosure-soe-narrative',
}

/** 第 i 个固定分类行的条目（键形态与 Tab 保存处 `K10-disc-{variant}-row-${idx}` 一致；K 循环键全集守卫按字面量计数，勿改写法） */
function fixedRowItem(variant: K10DisclosureVariant, i: number): string {
  return variant === 'listed' ? `K10-disc-listed-row-${i}` : `K10-disc-soe-row-${i}`
}

/** 国企固定分类中语义上即政府补助的项目（「是否为政府补助」默认「是」，可人工改选） */
const SOE_GOV_GRANT_DEFAULT = new Set(['政府补助', '即征即退', '财政贴息', '研发补助', '稳岗补贴'])

function parseRemark(saved: any): any {
  return typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
}

function listedDefaultRow(category: string): K10ListedFormRow {
  return {
    category,
    grantType: category.startsWith('政府补助') ? '与收益相关' : '',
    recognitionMethod: '',
    currentAmount: 0,
    priorAmount: 0,
    remark: '',
  }
}

function soeDefaultRow(category: string): K10SoeFormRow {
  return {
    category,
    currentAmount: 0,
    priorAmount: 0,
    isGovGrant: SOE_GOV_GRANT_DEFAULT.has(category) ? '是' : '否',
    remark: '',
  }
}

/** 默认行：固定来源分类、金额 0（上市：政府补助类默认「与收益相关」；国企：语义上即政府补助的默认「是」） */
export function k10DefaultDisclosureRows(variant: 'listed'): K10ListedFormRow[]
export function k10DefaultDisclosureRows(variant: 'soe'): K10SoeFormRow[]
export function k10DefaultDisclosureRows(variant: K10DisclosureVariant): Array<K10ListedFormRow | K10SoeFormRow>
export function k10DefaultDisclosureRows(variant: K10DisclosureVariant): Array<K10ListedFormRow | K10SoeFormRow> {
  return variant === 'listed'
    ? K10_DISCLOSURE_CATEGORIES.listed.map((c) => listedDefaultRow(c))
    : K10_DISCLOSURE_CATEGORIES.soe.map((c) => soeDefaultRow(c))
}

/** 动态追加行（`K10-disc-{variant}-dyn-*`），按回复的遍历顺序；解析失败 / 没有来源名的跳过 */
export function k10DynamicDisclosureRows(responses: K10DisclosureResponses, variant: 'listed'): K10ListedFormRow[]
export function k10DynamicDisclosureRows(responses: K10DisclosureResponses, variant: 'soe'): K10SoeFormRow[]
export function k10DynamicDisclosureRows(
  responses: K10DisclosureResponses,
  variant: K10DisclosureVariant,
): Array<K10ListedFormRow | K10SoeFormRow>
export function k10DynamicDisclosureRows(
  responses: K10DisclosureResponses,
  variant: K10DisclosureVariant,
): Array<K10ListedFormRow | K10SoeFormRow> {
  const prefix = K10_DISCLOSURE_DYN_PREFIX[variant]
  const out: Array<K10ListedFormRow | K10SoeFormRow> = []
  for (const [key, saved] of responses) {
    if (!key.startsWith(prefix)) continue
    try {
      const parsed = parseRemark(saved)
      if (parsed && parsed.category) {
        out.push(variant === 'listed'
          ? {
              category: parsed.category,
              grantType: parsed.grantType || '',
              recognitionMethod: parsed.recognitionMethod || '',
              currentAmount: Number(parsed.currentAmount || 0),
              priorAmount: Number(parsed.priorAmount || 0),
              remark: parsed.remark || '',
            }
          : {
              category: parsed.category,
              currentAmount: Number(parsed.currentAmount || 0),
              priorAmount: Number(parsed.priorAmount || 0),
              isGovGrant: parsed.isGovGrant || '否',
              remark: parsed.remark || '',
            })
      }
    } catch { /* ignore */ }
  }
  return out
}

/**
 * 读已保存的披露表（Tab onMounted 的 loadSavedData）：默认分类行 → 已保存的固定分类行逐位覆盖（`K10-disc-{variant}-row-{i}`）
 * → 追加动态行；说明取 `remark`，没有时取 `conclusion`。
 */
export function loadK10DisclosureState(
  responses: K10DisclosureResponses,
  variant: 'listed',
): K10DisclosureFormState<K10ListedFormRow>
export function loadK10DisclosureState(
  responses: K10DisclosureResponses,
  variant: 'soe',
): K10DisclosureFormState<K10SoeFormRow>
export function loadK10DisclosureState(
  responses: K10DisclosureResponses,
  variant: K10DisclosureVariant,
): K10DisclosureFormState<K10ListedFormRow | K10SoeFormRow>
export function loadK10DisclosureState(
  responses: K10DisclosureResponses,
  variant: K10DisclosureVariant,
): K10DisclosureFormState<K10ListedFormRow | K10SoeFormRow> {
  const categories = K10_DISCLOSURE_CATEGORIES[variant]
  const rows = k10DefaultDisclosureRows(variant)
  for (let i = 0; i < categories.length; i++) {
    const saved = responses.get(fixedRowItem(variant, i))
    if (!saved) continue
    try {
      const parsed = parseRemark(saved)
      if (parsed) {
        rows[i] = variant === 'listed'
          ? {
              category: categories[i],
              grantType: parsed.grantType || (rows[i] as K10ListedFormRow).grantType,
              recognitionMethod: parsed.recognitionMethod || '',
              currentAmount: Number(parsed.currentAmount || 0),
              priorAmount: Number(parsed.priorAmount || 0),
              remark: parsed.remark || '',
            }
          : {
              category: categories[i],
              currentAmount: Number(parsed.currentAmount || 0),
              priorAmount: Number(parsed.priorAmount || 0),
              isGovGrant: parsed.isGovGrant || (SOE_GOV_GRANT_DEFAULT.has(categories[i]) ? '是' : '否'),
              remark: parsed.remark || '',
            }
      }
    } catch { /* ignore */ }
  }
  rows.push(...k10DynamicDisclosureRows(responses, variant))
  const narrativeSaved = responses.get(NARRATIVE_ITEM[variant])
  return {
    rows,
    narrativeText: narrativeSaved ? (narrativeSaved.remark || narrativeSaved.conclusion || '') : '',
  }
}

/**
 * 披露表 → `buildK10SyncPayload` 的入参：行模型字段是 `category`（旧载荷读 `project` 曾把标签推成空串）；
 * 国企另把「是否为政府补助」=「是」的行汇总成合计后的「其中：政府补助」结构行（R8.4 批 9b-2，不推成附注列）。
 */
export function buildK10DisclosureSnapshot(
  variant: K10DisclosureVariant,
  rows: ReadonlyArray<{ category: string; currentAmount: number; priorAmount: number; isGovGrant?: string }>,
): { rows: K10DisclosureRow[]; govGrantRow?: { currentAmount: number; priorAmount: number } } {
  const detail = rows.map((r) => ({
    project: r.category,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
  }))
  if (variant === 'listed') return { rows: detail }
  const govGrantRow = rows
    .filter((r) => r.isGovGrant === '是')
    .reduce(
      (acc, r) => ({
        currentAmount: acc.currentAmount + (Number(r.currentAmount) || 0),
        priorAmount: acc.priorAmount + (Number(r.priorAmount) || 0),
      }),
      { currentAmount: 0, priorAmount: 0 },
    )
  return { rows: detail, govGrantRow }
}
