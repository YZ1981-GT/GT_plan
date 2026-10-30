/** 受限资产同步载荷纯构建器，供页面编排与离屏 provider 共用。 */
import {
  buildRestrictedAssetsPayloads,
  RESTRICTED_ASSETS_OWNERS,
  summarizeRestrictedRows,
  type RestrictedAssetsOwner,
  type RestrictedAssetsSheetNames,
  type RestrictedAssetsVariant,
} from './restrictedAssetsNoteSectionMap'
import { findRestrictedAssetsSource, type ResponseMap } from './restrictedAssetsSources'

export interface RestrictedAssetsPayloadInput {
  owner: RestrictedAssetsOwner
  variant: RestrictedAssetsVariant
  wpId: string
  responses: ResponseMap
  applicableStandards?: readonly string[] | null
  sheetNames: RestrictedAssetsSheetNames
}

export function buildRestrictedAssetsSyncPayloads(input: RestrictedAssetsPayloadInput): {
  payloads: ReturnType<typeof buildRestrictedAssetsPayloads>
  wpCode: string | null
} {
  const source = findRestrictedAssetsSource(input.owner)
  if (!source) return { payloads: [], wpCode: null }
  const details = source.collect(input.responses)
  return {
    payloads: buildRestrictedAssetsPayloads(
      input.variant,
      input.wpId,
      input.applicableStandards ?? null,
      {
        ownerRowCode: input.owner,
        rows: summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS[input.owner], details),
      },
      input.sheetNames,
    ),
    wpCode: source.wpCode,
  }
}
