/**
 * PAC Task 20 — registry domain split guards
 *
 * - Projection equality vs pre-split golden (componentType/icon/label/emits/contextProps/importPath)
 * - Collision RED (assertUniqueRegistryComponentTypes)
 * - Unconsumed domain array RED
 * - No startsWith classifier
 * - Literal dynamic imports retained
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'fs'
import { resolve } from 'path'

import {
  REGISTRY_LIST,
  HTML_RENDERER_REGISTRY,
  getRendererEntry,
  assertUniqueRegistryComponentTypes,
  assertAllDomainArraysConsumed,
  DOMAIN_ENTRY_ARRAYS,
  getAllEntries,
  getEntriesByDomain,
  type RegistryDomain,
} from '../registry'

import { coreEntries } from '../registry/entries/core'
import { formsEntries } from '../registry/entries/forms'
import { programsEntries } from '../registry/entries/programs'
import { confirmationsEntries } from '../registry/entries/confirmations'
import { reportsEntries } from '../registry/entries/reports'
import { specializedEntries } from '../registry/entries/specialized'

const GOLDEN_PATH = resolve(__dirname, 'fixtures/registry-entries.golden.json')

interface GoldenEntry {
  componentType: string
  importPath: string
  icon: string
  label: string
  emits: string[]
  contextProps: string | null
  domain: string
}

describe('PAC T20: registry domain assembly', () => {
  const golden = JSON.parse(readFileSync(GOLDEN_PATH, 'utf8')) as GoldenEntry[]

  it('entry count matches golden (pre-split REGISTRY_LIST)', () => {
    expect(REGISTRY_LIST.length).toBe(golden.length)
    expect(HTML_RENDERER_REGISTRY.size).toBe(golden.length)
  })

  it('projection equality: componentType/icon/label/emits/contextProps', () => {
    const byType = new Map(REGISTRY_LIST.map((e) => [e.componentType, e]))
    expect(byType.size).toBe(golden.length)
    for (const g of golden) {
      const e = byType.get(g.componentType)
      expect(e, `missing ${g.componentType}`).toBeDefined()
      expect(e!.icon).toBe(g.icon)
      expect(e!.label).toBe(g.label)
      expect([...e!.emits]).toEqual(g.emits)
      expect(e!.contextProps ?? null).toBe(g.contextProps)
    }
  })

  it('getRendererEntry is synchronous and matches Map', () => {
    for (const g of golden) {
      const entry = getRendererEntry(g.componentType)
      expect(entry).toBe(HTML_RENDERER_REGISTRY.get(g.componentType as never))
      expect(entry?.componentType).toBe(g.componentType)
    }
  })

  it('every domain array is consumed by REGISTRY_LIST concat', () => {
    expect(() =>
      assertAllDomainArraysConsumed(
        [
          coreEntries,
          formsEntries,
          programsEntries,
          confirmationsEntries,
          reportsEntries,
          specializedEntries,
        ],
        DOMAIN_ENTRY_ARRAYS,
      ),
    ).not.toThrow()
  })

  it('RED: unconsumed domain array fails assertAllDomainArraysConsumed', () => {
    expect(() =>
      assertAllDomainArraysConsumed(
        [coreEntries, formsEntries, programsEntries, confirmationsEntries, reportsEntries],
        DOMAIN_ENTRY_ARRAYS,
      ),
    ).toThrow(/not consumed/)
  })

  it('RED: duplicate componentType fails assertUniqueRegistryComponentTypes', () => {
    const dup = [...REGISTRY_LIST, REGISTRY_LIST[0]]
    expect(() => assertUniqueRegistryComponentTypes(dup)).toThrow(/重复声明/)
  })

  it('no startsWith classifier remains in registry barrel', () => {
    const barrelSrc = readFileSync(resolve(__dirname, '../registry/index.ts'), 'utf8')
    expect(barrelSrc).not.toMatch(/classifyDomain/)
    expect(barrelSrc).not.toMatch(/\.startsWith\(/)
  })

  it('domain entry files use literal dynamic import() paths', () => {
    const entriesDir = resolve(__dirname, '../registry/entries')
    for (const name of readdirSync(entriesDir).filter((f) => f.endsWith('.ts'))) {
      const src = readFileSync(resolve(entriesDir, name), 'utf8')
      const imports = [...src.matchAll(/import\(([^)]+)\)/g)].map((m) => m[1].trim())
      expect(imports.length, name).toBeGreaterThan(0)
      for (const spec of imports) {
        expect(spec.startsWith("'") || spec.startsWith('"'), `${name}: ${spec}`).toBe(true)
        expect(spec.includes('+') || spec.startsWith('import('), `${name}: non-literal ${spec}`).toBe(
          false,
        )
      }
    }
  })

  it('getEntriesByDomain returns explicit domain arrays (not startsWith)', () => {
    const domains = Object.keys(DOMAIN_ENTRY_ARRAYS) as RegistryDomain[]
    const all = new Set<string>()
    for (const d of domains) {
      for (const e of getEntriesByDomain(d)) {
        expect(all.has(e.componentType)).toBe(false)
        all.add(e.componentType)
      }
    }
    expect(all.size).toBe(getAllEntries().length)
  })

  it('golden domain membership matches explicit arrays', () => {
    for (const g of golden) {
      const domainEntries = DOMAIN_ENTRY_ARRAYS[g.domain as RegistryDomain]
      expect(
        domainEntries.some((e) => e.componentType === g.componentType),
        `${g.componentType} not in domain ${g.domain}`,
      ).toBe(true)
    }
  })
})
