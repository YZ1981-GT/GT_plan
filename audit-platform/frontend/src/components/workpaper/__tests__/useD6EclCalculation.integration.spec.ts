/**
 * Integration Test — D6-8 ECL 减值测算 账龄配置联动端到端（window-event → refresh → sync 串联）
 *
 * Spec: .kiro/specs/aging-config-enhancement/  Task: 14.2
 *
 * 与 13.2 的属性测试不同：13.2 直接测纯函数（createAgingRowsFromSegments/syncAgingGroupRows），
 * 本文件测「串联接线」——mount useD6EclCalculation（内部真实使用 useAgingConfig），
 * 通过 mock 的 api 层驱动配置，dispatch window `aging-config:changed` 事件，
 * 断言：
 *   1. ECL 分组创建时按项目账龄配置初始化行（Req 9.1 接线：useAgingConfig → segments → 建组）
 *   2. 配置变更事件经 useAgingConfig.refresh 更新 segments 后，D6 分组行同步到新段
 *      （已有段保留 lossRate/bookBalance，新增段零初始化）（Req 9.2/9.3 接线）
 *
 * 说明：生产链路为「后端 broadcast_raw('aging-config:changed') → SSE → 前端 window 事件」，
 * useAgingConfig 监听该事件 refresh 拉取最新配置（更新共享 segments ref），
 * D6 监听同名事件对已打开分组执行 syncAgingGroupRows。因两监听器共享同一 segments ref，
 * 本测试显式驱动「先 refresh 后 sync」的时序以验证串联结果。
 *
 * Validates: Requirements 9.2 (+ 9.1, 9.3 接线)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

// ── Mock api 层：useAgingConfig 通过 api.get 拉取项目账龄配置 ──────────────────
let mockConfigResponse: any = null
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async () => mockConfigResponse),
  },
}))

import { useD6EclCalculation } from '../composables/useD6EclCalculation'
import {
  PRESET_SEGMENTS,
  clearAgingConfigCache,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../composables/useD6FormData'

const FIVE: AgingSegment[] = PRESET_SEGMENTS.FIVE_YEAR   // 6 段
const THREE: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR // 4 段

function makeConfig(preset: 'THREE_YEAR' | 'FIVE_YEAR', segments: AgingSegment[]) {
  return { preset, effective_segments: segments, subject_overrides: {} }
}

/** 挂载 useD6EclCalculation，返回其 composable 结果与卸载函数。 */
async function mountEcl(projectId: string) {
  let captured: ReturnType<typeof useD6EclCalculation> | null = null
  const debouncedSave = vi.fn()
  const saveImmediate = vi.fn(async () => {})
  const allResponses = ref(new Map<string, ChecklistResponse>())

  const Comp = defineComponent({
    setup() {
      captured = useD6EclCalculation({
        allResponses,
        saveImmediate,
        debouncedSave,
        wpId: ref('wp-int-1'),
        projectId: ref(projectId),
      })
      return () => null
    },
  })
  const wrapper = mount(Comp)
  await flushPromises()
  return { ecl: captured!, unmount: () => wrapper.unmount(), debouncedSave }
}

function dispatchConfigChanged(): void {
  window.dispatchEvent(new Event('aging-config:changed'))
}

beforeEach(() => {
  clearAgingConfigCache()
  mockConfigResponse = null
})

describe('Feature: aging-config-enhancement — D6 ECL 联动集成 (Task 14.2)', () => {
  it('ECL 分组创建时按项目账龄配置初始化行 (Req 9.1 接线)', async () => {
    // **Validates: Requirements 9.1**
    mockConfigResponse = makeConfig('FIVE_YEAR', FIVE)
    const { ecl, unmount } = await mountEcl('proj-9-1')
    try {
      ecl.addAgingGroup()
      await flushPromises()

      expect(ecl.agingGroups.value).toHaveLength(1)
      const rows = ecl.agingGroups.value[0].rows
      // 按 5 年段(6 段)初始化，label/key 与配置逐一对应
      expect(rows).toHaveLength(FIVE.length)
      rows.forEach((row, i) => {
        expect(row.segmentKey).toBe(FIVE[i].key)
        expect(row.agingBand).toBe(FIVE[i].label)
      })
    } finally {
      unmount()
    }
  })

  it('配置变更事件端到端：refresh 更新 segments 后 D6 分组同步到新段并保留已填数据 (Req 9.2/9.3 接线)', async () => {
    // **Validates: Requirements 9.2, 9.3**
    mockConfigResponse = makeConfig('FIVE_YEAR', FIVE)
    const { ecl, unmount } = await mountEcl('proj-9-2')
    try {
      // 建组（6 段）并填入共有段(within1)的 lossRate/bookBalance
      ecl.addAgingGroup()
      await flushPromises()
      const groupId = ecl.agingGroups.value[0].groupId
      const within1Row = ecl.agingGroups.value[0].rows.find((r) => r.segmentKey === 'within1')!
      ecl.updateAgingCell(groupId, within1Row.rowId, 'lossRate', 0.05)
      ecl.updateAgingCell(groupId, within1Row.rowId, 'bookBalance', 1234)
      await flushPromises()
      expect(ecl.agingGroups.value[0].rows).toHaveLength(FIVE.length)

      // 配置切到 3 年段(4 段)
      mockConfigResponse = makeConfig('THREE_YEAR', THREE)

      // 事件 #1：驱动 useAgingConfig.refresh → 共享 segments ref 更新为 4 段
      dispatchConfigChanged()
      await flushPromises()

      // 事件 #2：D6 依据已更新的 segments 执行 syncAgingGroupRows
      dispatchConfigChanged()
      await flushPromises()

      const rows = ecl.agingGroups.value[0].rows
      const active = rows.filter((r) => !r.archived)
      // 同步到新配置的 4 段
      expect(active).toHaveLength(THREE.length)
      active.forEach((row, i) => {
        expect(row.segmentKey).toBe(THREE[i].key)
        expect(row.agingBand).toBe(THREE[i].label)
      })
      // 共有段 within1 的已填数据被保留（Req 9.3）
      const newWithin1 = active.find((r) => r.segmentKey === 'within1')!
      expect(newWithin1.lossRate).toBe(0.05)
      expect(newWithin1.bookBalance).toBe(1234)
    } finally {
      unmount()
    }
  })

  it('空分组时配置变更事件为 no-op（无分组不产生行）', async () => {
    mockConfigResponse = makeConfig('FIVE_YEAR', FIVE)
    const { ecl, unmount } = await mountEcl('proj-noop')
    try {
      expect(ecl.agingGroups.value).toHaveLength(0)
      mockConfigResponse = makeConfig('THREE_YEAR', THREE)
      dispatchConfigChanged()
      await flushPromises()
      dispatchConfigChanged()
      await flushPromises()
      expect(ecl.agingGroups.value).toHaveLength(0)
    } finally {
      unmount()
    }
  })
})
