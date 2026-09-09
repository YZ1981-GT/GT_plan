import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useSheetNavFacade } from '../useSheetNavFacade'

function allCycleFlagsFalse() {
  const no = computed(() => false)
  return {
    code: computed(() => ''),
    isBCycle: no,
    isCCycle: no,
    isDCycle: no,
    isFCycle: no,
    isGCycle: no,
    isHCycle: no,
    isICycle: no,
    isKCycle: no,
    isLCycle: no,
    isMCycle: no,
    isNCycle: no,
  } as any
}

describe('useSheetNavFacade — 真实 Univer API 绑定与三路导航共同状态', () => {
  it('bind 后 custom nav 可切换，native tab 后 refresh 可读取同一 active id', () => {
    let activeId = 'sheet-a'
    const makeSheet = (id: string, name: string) => ({
      getSheetId: () => id,
      getSheetName: () => name,
      isSheetHidden: () => false,
      activate: vi.fn(() => { activeId = id }),
    })
    const sheets = [
      makeSheet('sheet-a', '询证函控制表D0-4b'),
      makeSheet('sheet-b', '附注披露信息（上市公司）D0-8'),
    ]
    const workbook = {
      getSheets: () => sheets,
      getActiveSheet: () => sheets.find((sheet) => sheet.getSheetId() === activeId),
    }
    const api = { getActiveWorkbook: () => workbook }
    const apiRef = ref<any>(null)
    const facade = useSheetNavFacade(
      apiRef,
      ref(null),
      allCycleFlagsFalse(),
      computed(() => null),
      computed(() => 'cost'),
    )

    expect(facade.flatSheets.value).toEqual([])
    facade.bindUniverApi(api)
    facade.refresh()
    expect(facade.flatSheets.value).toEqual([
      { id: 'sheet-a', name: '询证函控制表D0-4b' },
      { id: 'sheet-b', name: '附注披露信息（上市公司）D0-8' },
    ])
    expect(facade.activeSheetId.value).toBe('sheet-a')

    facade.switchTo('sheet-b')
    expect(sheets[1].activate).toHaveBeenCalledTimes(1)
    expect(facade.activeSheetId.value).toBe('sheet-b')

    // 模拟用户点击 Univer 原生底部 tab：引擎先改变 active sheet，再由 command handler refresh。
    activeId = 'sheet-a'
    facade.refresh()
    expect(facade.activeSheetId.value).toBe('sheet-a')

    facade.bindUniverApi(null)
    facade.refresh()
    expect(facade.flatSheets.value).toEqual([])
  })
})
