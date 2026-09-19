/**
 * Property Test P9: Registry 拆分前后 componentType 集合完全相等，且每个值唯一注册
 *
 * **Validates: Requirements 6.4, 6.5**
 *
 * 不变量：
 * - 拆分后的 barrel 导出的 componentType 集合 === 原始注册表的集合
 * - 每个 componentType 在注册表中恰好出现一次（唯一性）
 * - 每个条目保持 icon/label/emits/contextProps 等价
 * - 对任意从注册表中随机选取的 componentType，barrel 和原注册表返回相同 entry 属性
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
  type HtmlComponentType,
} from '../htmlRendererRegistry'

import {
  getAllComponentTypes,
  getAllEntries,
  validateRegistryUniqueness,
  getEntriesByDomain,
  classifyDomain,
  type RegistryDomain,
} from '../registry'

// ─── P9.1: componentType 集合完全相等 ────────────────────────────────────────

describe('P9: Registry 拆分前后 componentType 集合等价性', () => {
  it('barrel 导出的 componentType 集合与原注册表完全一致', () => {
    const barrelTypes = getAllComponentTypes()
    const originalTypes = HTML_COMPONENT_TYPE_SET

    // 大小相等
    expect(barrelTypes.size).toBe(originalTypes.size)

    // 原注册表每个类型都在 barrel 中
    for (const ct of originalTypes) {
      expect(barrelTypes.has(ct)).toBe(true)
    }

    // barrel 中每个类型都在原注册表中
    for (const ct of barrelTypes) {
      expect(originalTypes.has(ct as HtmlComponentType)).toBe(true)
    }
  })

  it('注册表条目总数等于 componentType 集合大小（无遗漏无冗余）', () => {
    const entries = getAllEntries()
    const types = getAllComponentTypes()
    expect(entries.length).toBe(types.size)
  })
})

// ─── P9.2: 唯一性属性测试（fast-check） ─────────────────────────────────────

describe('P9: componentType 唯一性', () => {
  it('validateRegistryUniqueness 对全量注册表返回 valid=true', () => {
    const entries = getAllEntries()
    const { valid, duplicates } = validateRegistryUniqueness(entries)
    expect(valid).toBe(true)
    expect(duplicates).toEqual([])
  })

  it('[PBT] 对任意重复注入的 componentType，唯一性校验能检测到', () => {
    const entries = getAllEntries()
    const componentTypes = [...getAllComponentTypes()]

    fc.assert(
      fc.property(
        fc.nat({ max: componentTypes.length - 1 }),
        (idx) => {
          // 注入一个重复条目
          const duplicate = entries[idx]
          const withDuplicate = [...entries, duplicate]
          const { valid, duplicates } = validateRegistryUniqueness(withDuplicate)
          // 必须检测到重复
          expect(valid).toBe(false)
          expect(duplicates).toContain(duplicate.componentType)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('[PBT] 原始注册表中每个 componentType 恰好注册一次', () => {
    const entries = getAllEntries()
    const componentTypes = [...getAllComponentTypes()]

    fc.assert(
      fc.property(
        fc.nat({ max: componentTypes.length - 1 }),
        (idx) => {
          const ct = componentTypes[idx]
          // 在全量 entries 中搜索该 componentType 的出现次数
          const count = entries.filter((e) => e.componentType === ct).length
          expect(count).toBe(1)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P9.3: 拆分前后 entry 属性等价（fast-check 采样） ──────────────────────────

describe('P9: entry 属性等价', () => {
  it('[PBT] barrel 导出的任意 entry 与原注册表 Map 中同 key 的 entry 属性一致', () => {
    const componentTypes = [...getAllComponentTypes()]

    fc.assert(
      fc.property(
        fc.nat({ max: componentTypes.length - 1 }),
        (idx) => {
          const ct = componentTypes[idx] as HtmlComponentType
          const originalEntry = HTML_RENDERER_REGISTRY.get(ct)
          const barrelEntries = getAllEntries()
          const barrelEntry = barrelEntries.find((e) => e.componentType === ct)

          expect(barrelEntry).toBeDefined()
          expect(originalEntry).toBeDefined()

          // icon 等价
          expect(barrelEntry!.icon).toBe(originalEntry!.icon)
          // label 等价
          expect(barrelEntry!.label).toBe(originalEntry!.label)
          // emits 等价
          expect([...barrelEntry!.emits]).toEqual([...originalEntry!.emits])
          // contextProps 等价
          expect(barrelEntry!.contextProps).toBe(originalEntry!.contextProps)
          // component 引用同源
          expect(barrelEntry!.component).toBe(originalEntry!.component)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P9.4: 领域分类覆盖完整性 ────────────────────────────────────────────────

describe('P9: 领域分类覆盖完整', () => {
  const ALL_DOMAINS: RegistryDomain[] = ['core', 'a-b', 'c', 'd-f', 'g-i', 'j-n', 's', 'confirmation']

  it('所有领域的 entry 合集 === 全量注册表', () => {
    const allFromDomains = new Set<string>()
    for (const domain of ALL_DOMAINS) {
      for (const entry of getEntriesByDomain(domain)) {
        allFromDomains.add(entry.componentType)
      }
    }

    const allOriginal = getAllComponentTypes()
    expect(allFromDomains.size).toBe(allOriginal.size)
    for (const ct of allOriginal) {
      expect(allFromDomains.has(ct)).toBe(true)
    }
  })

  it('[PBT] 任意 componentType 恰好属于一个领域', () => {
    const componentTypes = [...getAllComponentTypes()]

    fc.assert(
      fc.property(
        fc.nat({ max: componentTypes.length - 1 }),
        (idx) => {
          const ct = componentTypes[idx]
          const domain = classifyDomain(ct)
          // 验证该 componentType 确实出现在对应领域的 entries 中
          const domainEntries = getEntriesByDomain(domain)
          const found = domainEntries.some((e) => e.componentType === ct)
          expect(found).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})
