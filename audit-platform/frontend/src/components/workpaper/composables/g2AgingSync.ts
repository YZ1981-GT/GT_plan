/**
 * G2 账龄口径跨表同步 — 将 3/5/自定义 写到 G2-2/3/6/7 各自存储键并广播事件
 */
import type { AgingPreset } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from './useF1FormData'

export const G2_AGING_PRESET_KEYS = [
  'G2-2-aging-preset',
  'G2-3-aging-preset',
  'G2-6-aging-preset',
  'G2-7-aging-preset',
] as const

export const G2_AGING_CUSTOM_KEYS = [
  'G2-2-aging-custom-segments',
  'G2-3-aging-custom-segments',
  'G2-6-aging-custom-segments',
  'G2-7-aging-custom-segments',
] as const

export interface G2AgingSyncDetail {
  preset: AgingPreset
  customLabels: string[]
  source?: string
}

/** 写入各表账龄键，并派发 g2:aging-preset-sync（各表 composable 监听后 remap） */
export function syncG2AgingPresetToAllSheets(
  allResponses: Map<string, ChecklistResponse>,
  preset: AgingPreset,
  customLabels: string[] = [],
  source = 'manual',
): void {
  const labels =
    preset === 'CUSTOM'
      ? customLabels.map((x) => String(x || '').trim()).filter(Boolean)
      : []

  for (const key of G2_AGING_PRESET_KEYS) {
    allResponses.set(key, { item_id: key, conclusion: null, remark: preset })
  }
  for (const key of G2_AGING_CUSTOM_KEYS) {
    allResponses.set(key, {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(preset === 'CUSTOM' ? labels : []),
    })
  }

  try {
    window.dispatchEvent(
      new CustomEvent('g2:aging-preset-sync', {
        detail: { preset, customLabels: labels, source } satisfies G2AgingSyncDetail,
      }),
    )
    window.dispatchEvent(new CustomEvent('g2:save-items', {
      detail: {
        items: [
          ...G2_AGING_PRESET_KEYS.map((k) => allResponses.get(k)),
          ...G2_AGING_CUSTOM_KEYS.map((k) => allResponses.get(k)),
        ].filter(Boolean),
      },
    }))
  } catch {
    /* silent */
  }
}
