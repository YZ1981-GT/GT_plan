/**
 * PAC split-face type coverage (Task 21 typecheck follow-up).
 *
 * Full-repo `vue-tsc` OOMs; the isolated `tsconfig.pac-t21.json` OOMs too once
 * the 11 route domains + 6 registry entry arrays are added (their
 * `() => import('*.vue')` targets pull 200+ SFC graphs). Vitest resolves .vue
 * through the Vue plugin without that blowup, so the pure-type shape of both
 * physical-split faces is asserted here instead: every domain array must be
 * assignable to `RouteRecordRaw[]` and every entry array to
 * `HtmlRendererEntry[]`. This is compile-time coverage — the `expectTypeOf`
 * calls fail the build if any array drifts off its declared element type.
 */
import { describe, it, expectTypeOf, expect } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'

import { authRoutes } from '@/router/domains/auth'
import { confirmationsRoutes } from '@/router/domains/confirmations'
import { dashboardRoutes } from '@/router/domains/dashboard'
import { extensionRoutes } from '@/router/domains/extension'
import { notesRoutes } from '@/router/domains/notes'
import { projectsRoutes } from '@/router/domains/projects'
import { qcRoutes } from '@/router/domains/qc'
import { reportsRoutes as reportsRouteDomain } from '@/router/domains/reports'
import { standaloneRoutes } from '@/router/domains/standalone'
import { systemRoutes } from '@/router/domains/system'
import { workpapersRoutes } from '@/router/domains/workpapers'

import type { HtmlRendererEntry } from '@/components/workpaper/registry/types'
import { coreEntries } from '@/components/workpaper/registry/entries/core'
import { formsEntries } from '@/components/workpaper/registry/entries/forms'
import { programsEntries } from '@/components/workpaper/registry/entries/programs'
import { confirmationsEntries } from '@/components/workpaper/registry/entries/confirmations'
import { reportsEntries } from '@/components/workpaper/registry/entries/reports'
import { specializedEntries } from '@/components/workpaper/registry/entries/specialized'

const ROUTE_DOMAINS = {
  auth: authRoutes,
  confirmations: confirmationsRoutes,
  dashboard: dashboardRoutes,
  extension: extensionRoutes,
  notes: notesRoutes,
  projects: projectsRoutes,
  qc: qcRoutes,
  reports: reportsRouteDomain,
  standalone: standaloneRoutes,
  system: systemRoutes,
  workpapers: workpapersRoutes,
} as const

const ENTRY_DOMAINS = {
  core: coreEntries,
  forms: formsEntries,
  programs: programsEntries,
  confirmations: confirmationsEntries,
  reports: reportsEntries,
  specialized: specializedEntries,
} as const

describe('PAC split-face type coverage (11 route domains + 6 registry entry arrays)', () => {
  it('all 11 route domain exports are RouteRecordRaw[]', () => {
    expectTypeOf(authRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(confirmationsRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(dashboardRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(extensionRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(notesRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(projectsRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(qcRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(reportsRouteDomain).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(standaloneRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(systemRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expectTypeOf(workpapersRoutes).toEqualTypeOf<RouteRecordRaw[]>()
    expect(Object.keys(ROUTE_DOMAINS)).toHaveLength(11)
  })

  it('all 6 registry entry domain arrays are HtmlRendererEntry[]', () => {
    expectTypeOf(coreEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expectTypeOf(formsEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expectTypeOf(programsEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expectTypeOf(confirmationsEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expectTypeOf(reportsEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expectTypeOf(specializedEntries).toEqualTypeOf<HtmlRendererEntry[]>()
    expect(Object.keys(ENTRY_DOMAINS)).toHaveLength(6)
  })

  it('every route domain is a non-empty array (runtime shape)', () => {
    for (const [name, routes] of Object.entries(ROUTE_DOMAINS)) {
      expect(Array.isArray(routes), `${name} not an array`).toBe(true)
    }
  })

  it('every registry entry domain is a non-empty array (runtime shape)', () => {
    for (const [name, entries] of Object.entries(ENTRY_DOMAINS)) {
      expect(Array.isArray(entries), `${name} not an array`).toBe(true)
      expect(entries.length, `${name} empty`).toBeGreaterThan(0)
    }
  })
})
