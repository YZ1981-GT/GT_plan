/**
 * useSheetNavFacade — 统一 Sheet 导航 facade
 *
 * 锚定 spec workpaper-editor-refactor Phase 2-3
 *
 * 把 WorkpaperEditor 中 11 个循环 nav 实例化 + 4 个 if-else facade 函数集中到此 composable。
 * 主组件只需 `const sheetNav = useSheetNavFacade(...)` 即可访问统一接口。
 *
 * 暴露接口与原 sheetNav 对象完全一致：
 * - groups: ComputedRef<SheetGroup[]>
 * - activeSheetId: ComputedRef<string>
 * - totalCount: ComputedRef<number>
 * - switchTo(id: string): void
 * - refresh(): void
 * - applyForeignCurrencyVisibility(): void
 * - flatSheets: ComputedRef<{id, name}[]>
 *
 * 额外暴露各循环 nav 实例（供 branch selector 等外部使用）：
 * - hCycleNav / iCycleNav（branch selector 需要 .sheets.value）
 */
import { computed, ref, type Ref, type ComputedRef } from 'vue'
import { useUniverSheetNav, type SheetGroup } from './useUniverSheetNav'
import { useDSalesCycleSheetGroups } from './useDSalesCycleSheetGroups'
import { useFPurchaseInventorySheetGroups } from './useFPurchaseInventorySheetGroups'
import { useHFixedAssetSheetGroups } from './useHFixedAssetSheetGroups'
import { useIIntangibleAssetSheetGroups } from './useIIntangibleAssetSheetGroups'
import { useGInvestmentCycleSheetGroups, type GParsedData } from './useGInvestmentCycleSheetGroups'
import { useKAdminCycleSheetGroups } from './useKAdminCycleSheetGroups'
import { useLDebtCycleSheetGroups } from './useLDebtCycleSheetGroups'
import { useMEquityCycleSheetGroups } from './useMEquityCycleSheetGroups'
import { useNTaxCycleSheetGroups } from './useNTaxCycleSheetGroups'
import { useBAuditPlanSheetGroups } from './useBAuditPlanSheetGroups'
import { useCControlTestSheetGroups } from './useCControlTestSheetGroups'
import type { CycleTypeFlags } from './useCycleType'

export interface SheetNavFacadeAPI {
  groups: ComputedRef<SheetGroup[]>
  activeSheetId: ComputedRef<string>
  totalCount: ComputedRef<number>
  switchTo: (id: string) => void
  refresh: () => void
  applyForeignCurrencyVisibility: () => void
  flatSheets: ComputedRef<Array<{ id: string; name: string }>>
  // 暴露各循环 nav 实例供外部使用（branch selector 等）
  hCycleNav: ReturnType<typeof useHFixedAssetSheetGroups>
  iCycleNav: ReturnType<typeof useIIntangibleAssetSheetGroups>
  gCycleNav: ReturnType<typeof useGInvestmentCycleSheetGroups>
}

export function useSheetNavFacade(
  univerAPIRef: Ref<any>,
  wpDetail: Ref<{ wp_code?: string | null; parsed_data?: any } | null>,
  cycleType: CycleTypeFlags,
  scenarioFilter: ComputedRef<{ scenario: string; hasForeignCurrency: boolean } | null>,
  measurementModel: ComputedRef<string>,
): SheetNavFacadeAPI {
  const { isBCycle, isCCycle, isDCycle, isFCycle, isGCycle, isHCycle, isICycle, isKCycle, isLCycle, isMCycle, isNCycle } = cycleType

  // ─── 实例化所有循环 nav ─────────────────────────────────────────────────────
  const eUniverNav = useUniverSheetNav(univerAPIRef, scenarioFilter)
  const dCycleNav = useDSalesCycleSheetGroups(univerAPIRef, scenarioFilter)
  const fCycleNav = useFPurchaseInventorySheetGroups(univerAPIRef, scenarioFilter)
  const hCycleNav = useHFixedAssetSheetGroups(univerAPIRef, measurementModel)
  const iCycleNav = useIIntangibleAssetSheetGroups(univerAPIRef)

  const gParsedDataRef = computed<GParsedData | null>(() => {
    const pd = (wpDetail.value as any)?.parsed_data
    return (pd ?? null) as GParsedData | null
  })
  const gCurrentInvesteeNameRef = ref<string | null>(null)
  const gCycleNav = useGInvestmentCycleSheetGroups(univerAPIRef, gParsedDataRef, gCurrentInvesteeNameRef)

  const kCycleNav = useKAdminCycleSheetGroups(univerAPIRef)
  const lCycleNav = useLDebtCycleSheetGroups(univerAPIRef)
  const mCycleNav = useMEquityCycleSheetGroups(univerAPIRef)
  const nCycleNav = useNTaxCycleSheetGroups(univerAPIRef)
  const bCycleNav = useBAuditPlanSheetGroups(univerAPIRef)
  const cCycleNav = useCControlTestSheetGroups(univerAPIRef)

  // ─── 统一 facade ───────────────────────────────────────────────────────────
  function _activeNav() {
    if (isHCycle.value) return hCycleNav
    if (isICycle.value) return iCycleNav
    if (isGCycle.value) return gCycleNav
    if (isKCycle.value) return kCycleNav
    if (isLCycle.value) return lCycleNav
    if (isMCycle.value) return mCycleNav
    if (isNCycle.value) return nCycleNav
    if (isBCycle.value) return bCycleNav
    if (isCCycle.value) return cCycleNav
    if (isFCycle.value) return fCycleNav
    if (isDCycle.value) return dCycleNav
    return eUniverNav
  }

  const groups = computed<SheetGroup[]>(() => _activeNav().groups.value as unknown as SheetGroup[])
  const activeSheetId = computed<string>(() => _activeNav().activeSheetId.value)
  const totalCount = computed<number>(() => _activeNav().totalCount.value)

  function switchTo(id: string) { _activeNav().switchTo(id) }
  function refresh() { _activeNav().refresh() }
  function applyForeignCurrencyVisibility() { eUniverNav.applyForeignCurrencyVisibility() }

  const flatSheets = computed(() => {
    const gs = groups.value || []
    const result: Array<{ id: string; name: string }> = []
    for (const g of gs) {
      for (const s of (g.sheets || [])) {
        if ((s as any).hidden) continue
        result.push({ id: s.id, name: s.name })
      }
    }
    return result
  })

  return {
    groups,
    activeSheetId,
    totalCount,
    switchTo,
    refresh,
    applyForeignCurrencyVisibility,
    flatSheets,
    hCycleNav,
    iCycleNav,
    gCycleNav,
  }
}
