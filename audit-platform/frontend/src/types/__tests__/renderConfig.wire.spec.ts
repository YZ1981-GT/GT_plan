/**
 * RenderConfigWire 字段生命周期守卫。
 * active = 已有消费方；reserved = 显式裁决暂不消费；禁止未分类漂浮字段。
 */
import { describe, expect, it } from 'vitest'
import {
  RENDER_CONFIG_FIELD_STATUS,
  type RenderConfigWire,
} from '@/types/renderConfig'

const EXPECTED_RESERVED = [
  'scope',
  'guidance',
  'sign_status',
  'permissions',
] as const

const EXPECTED_ACTIVE = [
  'wp_id',
  'wp_code',
  'project_id',
  'is_real_workpaper',
  'template_version',
  'sheets',
  'audit_year',
  'applicable_standards',
  'fill_results',
  'redirect',
  'delegated_module',
  'target_path',
  'decision_trace',
] as const

describe('RenderConfigWire field lifecycle', () => {
  it('enumerates every root wire field as active or reserved', () => {
    const statusKeys = Object.keys(RENDER_CONFIG_FIELD_STATUS).sort()
    const wireKeys = [
      ...EXPECTED_ACTIVE,
      ...EXPECTED_RESERVED,
    ].sort()
    expect(statusKeys).toEqual(wireKeys)
  })

  it('keeps reserved adjudication exact and non-empty', () => {
    const reserved = Object.entries(RENDER_CONFIG_FIELD_STATUS)
      .filter(([, status]) => status === 'reserved')
      .map(([key]) => key)
      .sort()
    expect(reserved).toEqual([...EXPECTED_RESERVED].sort())
  })

  it('marks known consumers as active', () => {
    for (const key of EXPECTED_ACTIVE) {
      expect(RENDER_CONFIG_FIELD_STATUS[key]).toBe('active')
    }
  })

  it('type-locks status map to RenderConfigWire keys', () => {
    // Compile-time: satisfies Record<keyof RenderConfigWire, ...>
    // Runtime: no extra / missing keys beyond the wire surface.
    const sample: RenderConfigWire = {
      wp_id: 'w',
      wp_code: 'D2',
      project_id: 'p',
      scope: 'standalone',
      is_real_workpaper: true,
      template_version: null,
      sheets: [],
    }
    for (const key of Object.keys(sample) as (keyof RenderConfigWire)[]) {
      expect(RENDER_CONFIG_FIELD_STATUS[key] === 'active' || RENDER_CONFIG_FIELD_STATUS[key] === 'reserved').toBe(true)
    }
  })
})
