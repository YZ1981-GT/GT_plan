/**
 * useD2EntryDualMode — D2 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D2RenderMode = WorkpaperRenderMode

const D2_SHEET_MAP: Record<string, string> = {
  D2: 'D2',
  目录: 'D2',
  D2A: 'D2A',
  'D2-1': 'D2-1',
  'D2-2': 'D2-2',
  'D2-3': 'D2-3',
  'D2-4': 'D2-4',
  'D2-5': 'D2-5',
  'D2-6': 'D2-6',
  'D2-7': 'D2-7',
  'D2-8': 'D2-8',
  'D2-9': 'D2-9',
  'D2-10': 'D2-10',
  'D2-11': 'D2-11',
  'D2-12': 'D2-12',
  'D2-13': 'D2-13',
  附注上市: '附注披露信息(上市公司)',
  附注国企: '附注披露信息(国企)',
  截止测试: '截止测试',
}

export function getSheetNameFromD2Code(code: string): string {
  if (D2_SHEET_MAP[code]) return D2_SHEET_MAP[code]
  if (code.includes('截止')) return code
  return code
}

export function useD2EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  const dual = useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => getSheetNameFromD2Code(currentSheet.value),
  })

  return {
    ...dual,
    getSheetNameFromCode: getSheetNameFromD2Code,
    getDisabledTooltip: () =>
      !dual.ooAvailable.value ? 'OnlyOffice 服务不可用，仅支持 HTML 模式' : '',
  }
}

export default useD2EntryDualMode
