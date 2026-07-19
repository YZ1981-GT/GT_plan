/**
 * G5 国企附注披露行模型 — 对齐致同 Excel「附注披露信息（国企）」
 *
 * 与上市共享：性质分类 / 坏账概况 / 单项明细 / 组合账龄块
 * 国企专有：（2）终止确认  （3）继续涉入  （4）坏账方法说明红区
 * 列标签口径：期末数 / 期初数（展示层处理）
 */
import {
  buildDefaultMethodRows,
  buildDefaultNatureRows,
  createEmptyIndividualDetail,
  createEmptyPortfolio,
  parseListedDisclosure,
  recomputeMethodTotals,
  recomputeNatureDerived,
  serializeListedDisclosure,
  type G5IndividualDetailRow,
  type G5ListedDisclosureState,
  type G5MethodRow,
  type G5NatureRow,
  type G5PortfolioBlock,
} from './g5ListedDisclosureRows'

export interface G5DerecogRow {
  id: string
  item: string
  transferMethod: string
  amount: number
  gainLoss: number
}

export interface G5ContinuingInvolvement {
  assetEnd: number
  liabilityEnd: number
}

export interface G5SoeDisclosureState {
  version: 1
  natureRows: G5NatureRow[]
  methodRows: G5MethodRow[]
  individualDetails: G5IndividualDetailRow[]
  portfolios: G5PortfolioBlock[]
  /** （2）终止确认的长期应收款 */
  derecogRows: G5DerecogRow[]
  /** （3）继续涉入形成的资产、负债 */
  continuing: G5ContinuingInvolvement
  /** （4）坏账准备计提方法说明（模板红区） */
  provisionMethodNote: string
}

const uid = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

export const G5_SOE_PROVISION_METHOD_PLACEHOLDER =
  '说明坏账准备计提方法、期初余额调整及本期增减变动原因（按单项/按组合）。若采用三阶段模型，请参考其他应收款坏账准备披露格式。'

export function createEmptyDerecogRow(): G5DerecogRow {
  return {
    id: uid('dr'),
    item: '',
    transferMethod: '',
    amount: 0,
    gainLoss: 0,
  }
}

export function buildDefaultSoeState(): G5SoeDisclosureState {
  return {
    version: 1,
    natureRows: buildDefaultNatureRows(),
    methodRows: buildDefaultMethodRows(),
    individualDetails: [],
    portfolios: [createEmptyPortfolio('组合1')],
    derecogRows: [],
    continuing: { assetEnd: 0, liabilityEnd: 0 },
    provisionMethodNote: '',
  }
}

export function serializeSoeDisclosure(state: G5SoeDisclosureState): string {
  return JSON.stringify({ ...state, version: 1 })
}

export function parseSoeDisclosure(raw: string | null | undefined): G5SoeDisclosureState | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    // 兼容误存的上市结构
    if (parsed.movementRows && !parsed.derecogRows && !('provisionMethodNote' in parsed)) {
      const listed = parseListedDisclosure(raw)
      if (!listed) return null
      return listedToSoe(listed)
    }
    const base = buildDefaultSoeState()
    const asListed = parseListedDisclosure(
      JSON.stringify({
        version: 1,
        natureRows: parsed.natureRows,
        methodRows: parsed.methodRows,
        individualDetails: parsed.individualDetails,
        portfolios: parsed.portfolios,
        movementRows: [],
        unrealizedNote: '',
        writeoffRows: [],
        leaseMlpRows: [],
        useThreeStageHintAck: false,
      }),
    )
    return {
      version: 1,
      natureRows: asListed?.natureRows?.length
        ? recomputeNatureDerived(asListed.natureRows)
        : base.natureRows,
      methodRows: asListed?.methodRows?.length
        ? recomputeMethodTotals(asListed.methodRows)
        : base.methodRows,
      individualDetails: Array.isArray(parsed.individualDetails)
        ? parsed.individualDetails.map((r: G5IndividualDetailRow) => ({
            ...createEmptyIndividualDetail(),
            ...r,
            id: r.id || uid('ind'),
          }))
        : [],
      portfolios: asListed?.portfolios?.length ? asListed.portfolios : base.portfolios,
      derecogRows: Array.isArray(parsed.derecogRows)
        ? parsed.derecogRows.map((r: G5DerecogRow) => ({
            ...createEmptyDerecogRow(),
            ...r,
            id: r.id || uid('dr'),
          }))
        : [],
      continuing: {
        assetEnd: Number(parsed.continuing?.assetEnd) || 0,
        liabilityEnd: Number(parsed.continuing?.liabilityEnd) || 0,
      },
      provisionMethodNote: String(parsed.provisionMethodNote ?? ''),
    }
  } catch {
    return null
  }
}

function listedToSoe(listed: G5ListedDisclosureState): G5SoeDisclosureState {
  return {
    version: 1,
    natureRows: listed.natureRows,
    methodRows: listed.methodRows,
    individualDetails: listed.individualDetails,
    portfolios: listed.portfolios,
    derecogRows: [],
    continuing: { assetEnd: 0, liabilityEnd: 0 },
    provisionMethodNote: listed.unrealizedNote || '',
  }
}

/** 供 serializeListed 工具链复用（取数后合并） */
export function soeSharedSlice(state: G5SoeDisclosureState): Pick<
  G5ListedDisclosureState,
  'natureRows' | 'methodRows' | 'individualDetails' | 'portfolios'
> {
  return {
    natureRows: state.natureRows,
    methodRows: state.methodRows,
    individualDetails: state.individualDetails,
    portfolios: state.portfolios,
  }
}

export function cloneSharedFromListed(
  state: G5SoeDisclosureState,
  listed: G5ListedDisclosureState,
): G5SoeDisclosureState {
  return {
    ...state,
    natureRows: listed.natureRows,
    methodRows: listed.methodRows,
    individualDetails: listed.individualDetails,
    portfolios: listed.portfolios,
  }
}

export { serializeListedDisclosure }
