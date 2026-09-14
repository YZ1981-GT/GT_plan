/**
 * 「1年以内小计」行的产出条件契约。
 *
 * 源模板依据：
 * - 上市版 `附注披露信息(上市公司)` r8~r12：1年以内被细分为 `其中：0-X个月` /
 *   `X-Y个月`，故有 `1年以内小计：` 行；
 * - 国企版 `附注披露信息(国企)` r7~r15：6 档账龄无细分，**无**该小计行。
 *
 * 因此规则按「1年以内是否被细分为多段」判定，而非按 variant 硬分：
 * 段数 = 1 时小计恒等于该段本身 → 不产出（否则附注多一行凭空的结构行）。
 *
 * spec: d2-ar-disclosure-soe-alignment（附带修复）
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { AgingSegment } from '@/composables/useAgingConfig'

const segmentsRef = ref<AgingSegment[]>([])

vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return { ...actual, useAgingConfig: () => ({ segments: segmentsRef }) }
})

const { useD2DisclosureNote } = await import('../composables/useD2DisclosureNote')
const { PRESET_SEGMENTS } = await import('@/composables/useAgingConfig')

function api(segments: AgingSegment[]) {
  segmentsRef.value = segments
  return useD2DisclosureNote({
    allResponses: ref(new Map()),
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    variant: 'soe',
    save: vi.fn(),
    isReadonly: ref(false),
  })
}

describe('账龄「1年以内小计」产出条件', () => {
  it('1年以内只有一段（5年段预设）→ 不产出小计行', () => {
    const rows = api(PRESET_SEGMENTS.FIVE_YEAR as AgingSegment[]).agingRows.value
    expect(rows.some((r) => r.kind === 'within1Subtotal')).toBe(false)
    expect(rows.slice(-3).map((r) => r.label)).toEqual(['小计', '减：坏账准备', '合计'])
  })

  it('1年以内被细分为多段 → 产出小计行，且金额 = 各细分段之和', () => {
    const segs: AgingSegment[] = [
      { key: 'm0to6', label: '6个月以内', dayFrom: 0, dayTo: 180 },
      { key: 'm6to12', label: '6个月至1年', dayFrom: 181, dayTo: 365 },
      { key: 'y1to2', label: '1至2年', dayFrom: 366, dayTo: 730 },
    ] as AgingSegment[]
    const a = api(segs)
    a.setOverride('aging:end:m0to6', 600)
    a.setOverride('aging:end:m6to12', 400)
    a.setOverride('aging:end:y1to2', 200)

    const rows = a.agingRows.value
    const sub = rows.find((r) => r.kind === 'within1Subtotal')
    expect(sub, '1年以内被细分时必须产出小计行').toBeDefined()
    expect(sub!.label).toBe('1年以内小计')
    expect(sub!.endAmount).toBe(1000)
    // 「小计」仍为全部账龄段之和（不含 1年以内小计，避免重复计入）
    expect(rows.find((r) => r.kind === 'subtotal')!.endAmount).toBe(1200)
  })
})
