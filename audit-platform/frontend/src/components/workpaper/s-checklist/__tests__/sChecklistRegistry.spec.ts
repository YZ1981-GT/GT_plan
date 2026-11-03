/**
 * sChecklistRegistry.spec.ts — S-checklist 12-type 前端注册 parity 测试
 *
 * Feature: s-cycle-linkage-trimming-and-component-wiring, D3.2
 *
 * 验证前端 registry 的 s-checklist 条目与 sChecklistItemIds 权威清单完全对齐：
 * - 12 个 componentType 一个不多一个不少
 * - 每个条目有 component / label / icon
 * - emits 统一为 ['save', 'completed']
 * - contextProps 统一为 'standard'
 * - 可写 9 个（item_id 非 null）/ 只读 3 个（item_id 为 null）
 */
import { describe, expect, it } from 'vitest'

import { HTML_RENDERER_REGISTRY } from '../../htmlRendererRegistry'
import {
  sChecklistItemIds,
  type SChecklistComponentType,
} from '../sChecklistItemIds'

/** 后端 _s_checklist_sheets.py S_CHECKLIST_ITEM_IDS 的前端镜像（12-type canonical set） */
const S_CHECKLIST_CANONICAL_SET: ReadonlySet<string> = new Set(
  Object.keys(sChecklistItemIds),
)

/** 9 个可写类型（item_id 非 null） */
const WRITABLE_TYPES: readonly string[] = (
  Object.entries(sChecklistItemIds) as [string, string | null][]
)
  .filter(([, v]) => v !== null)
  .map(([k]) => k)

/** 3 个只读类型（item_id 为 null） */
const READONLY_TYPES: readonly string[] = (
  Object.entries(sChecklistItemIds) as [string, string | null][]
)
  .filter(([, v]) => v === null)
  .map(([k]) => k)

describe('D3.2 S-checklist registry parity', () => {
  it('canonical set has exactly 12 types', () => {
    expect(S_CHECKLIST_CANONICAL_SET.size).toBe(12)
  })

  it('every canonical type is registered in HTML_RENDERER_REGISTRY', () => {
    for (const ct of S_CHECKLIST_CANONICAL_SET) {
      expect(
        HTML_RENDERER_REGISTRY.has(ct),
        `${ct} missing from HTML_RENDERER_REGISTRY`,
      ).toBe(true)
    }
  })

  it('registry entries for s-checklist types have component / label / icon', () => {
    for (const ct of S_CHECKLIST_CANONICAL_SET) {
      const entry = HTML_RENDERER_REGISTRY.get(ct)!
      expect(entry.component, `${ct} missing component`).toBeDefined()
      expect(entry.label, `${ct} missing label`).toBeTruthy()
      expect(entry.icon, `${ct} missing icon`).toBeTruthy()
    }
  })

  it('all s-checklist entries use emits=[save,completed] and contextProps=standard', () => {
    for (const ct of S_CHECKLIST_CANONICAL_SET) {
      const entry = HTML_RENDERER_REGISTRY.get(ct)!
      expect(entry.emits, `${ct} emits mismatch`).toEqual(['save', 'completed'])
      expect(entry.contextProps, `${ct} contextProps mismatch`).toBe('standard')
    }
  })

  it('writable types (9) all have non-null item_id', () => {
    expect(WRITABLE_TYPES).toHaveLength(9)
    for (const ct of WRITABLE_TYPES) {
      expect(
        sChecklistItemIds[ct as SChecklistComponentType],
        `${ct} should have non-null item_id`,
      ).not.toBeNull()
    }
  })

  it('readonly types (3) all have null item_id', () => {
    expect(READONLY_TYPES).toHaveLength(3)
    const expected = new Set([
      's9-legal-regulations',
      's9-program-description',
      's10-environmental-regulations',
    ])
    expect(new Set(READONLY_TYPES)).toEqual(expected)
  })

  it('no extra s-checklist types exist in registry beyond the canonical 12', () => {
    const registryTypes = [...HTML_RENDERER_REGISTRY.keys()].filter((ct) =>
      ct.startsWith('s1-')
      || ct.startsWith('s8-')
      || ct.startsWith('s9-')
      || ct.startsWith('s10-')
      || ct.startsWith('s17-'),
    )
    for (const ct of registryTypes) {
      expect(
        S_CHECKLIST_CANONICAL_SET.has(ct),
        `unexpected s-checklist type in registry: ${ct}`,
      ).toBe(true)
    }
  })
})
