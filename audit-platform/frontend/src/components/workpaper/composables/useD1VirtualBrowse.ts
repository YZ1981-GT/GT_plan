/**

 * useD1VirtualBrowse — 兼容层，委托 useWorkpaperWideTable

 */

import { type Ref } from 'vue'

import { D1_VIRTUAL_SCROLL_THRESHOLD } from './d1SheetLabels'

import { useWorkpaperWideTable } from './useWorkpaperWideTable'



export function useD1VirtualBrowse(rowCount: Ref<number>, threshold = D1_VIRTUAL_SCROLL_THRESHOLD) {

  return useWorkpaperWideTable({

    rowCount,

    rowThreshold: threshold,

  })

}



export default useD1VirtualBrowse

