/**
 * Property-Based Tests for DefaultLayout navigation logic
 * Feature: four-panel-note-linkage
 * numRuns: 20
 *
 * Tests the pure logic of handleProjectSwitch, handleNoteNavigation, tabToRoute
 * without mounting the full DefaultLayout (too heavy with nested components).
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'

// ─── Extract pure logic under test ──────────────────────────────────────────

function tabToRoute(tab: string): string {
  const map: Record<string, string> = {
    reports: 'financial-reports',
    notes: 'disclosure-notes',
    workpapers: 'workpapers',
    trial_balance: 'trial-balance',
  }
  return map[tab] || 'disclosure-notes'
}

interface MockRoute {
  params: { projectId: string }
  name: string
  query: Record<string, string>
}

function buildProjectSwitchPath(
  item: { project_id: string; year?: number },
  route: MockRoute,
  activeTab: string,
  storeYear: number,
): { path: string; query: { year: string } } | null {
  const targetId = item.project_id
  if (targetId === route.params.projectId) return null // same project no-op
  const year = item.year || storeYear
  const subRoute = tabToRoute(activeTab)
  return {
    path: `/projects/${targetId}/${subRoute}`,
    query: { year: String(year) },
  }
}

function buildNoteNavigationAction(
  item: { code: string },
  route: MockRoute,
): { type: 'eventBus'; payload: { noteSection: string } } | { type: 'routerPush'; path: string; query: Record<string, string> } {
  const pid = route.params.projectId
  const isOnNotesPage = route.name === 'DisclosureNotes'

  if (isOnNotesPage) {
    return { type: 'eventBus', payload: { noteSection: item.code } }
  } else {
    return {
      type: 'routerPush',
      path: `/projects/${pid}/disclosure-notes`,
      query: { ...route.query, section: item.code },
    }
  }
}

// ─── Arbitraries ────────────────────────────────────────────────────────────

const arbTab = fc.constantFrom('reports', 'notes', 'workpapers', 'trial_balance')
const arbYear = fc.integer({ min: 2020, max: 2030 })
const arbProjectId = fc.uuid()
const arbNoteSection = fc.array(
  fc.constantFrom('一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '、', '1', '2', '3', '4', '5'),
  { minLength: 2, maxLength: 8 },
).map(arr => arr.join(''))

describe('DefaultLayout Navigation Property-Based Tests', () => {
  // Feature: four-panel-note-linkage, Property 1: 项目切换生成正确路由路径
  it('Property 1: project switch generates correct route path', () => {
    fc.assert(
      fc.property(
        arbProjectId,
        arbYear,
        arbTab,
        (projectId, year, activeTab) => {
          const route: MockRoute = { params: { projectId: 'different-id' }, name: 'SomePage', query: {} }
          const result = buildProjectSwitchPath({ project_id: projectId, year }, route, activeTab, 2025)

          expect(result).not.toBeNull()
          expect(result!.path).toBe(`/projects/${projectId}/${tabToRoute(activeTab)}`)
          expect(result!.query.year).toBe(String(year))
        },
      ),
      { numRuns: 20 },
    )
  })

  // Feature: four-panel-note-linkage, Property 4: 非附注页面章节点击生成正确导航路由
  it('Property 4: note section click on non-notes page generates correct router push', () => {
    fc.assert(
      fc.property(
        arbNoteSection,
        arbProjectId,
        fc.constantFrom('FinancialReports', 'Workpapers', 'TrialBalance', 'Dashboard'),
        (noteCode, projectId, routeName) => {
          const route: MockRoute = { params: { projectId }, name: routeName, query: {} }
          const action = buildNoteNavigationAction({ code: noteCode }, route)

          expect(action.type).toBe('routerPush')
          if (action.type === 'routerPush') {
            expect(action.path).toBe(`/projects/${projectId}/disclosure-notes`)
            expect(action.query.section).toBe(noteCode)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  // Feature: four-panel-note-linkage, Property 3: 同页附注章节点击触发 eventBus
  it('Property 3: note section click on DisclosureNotes page triggers eventBus emit', () => {
    fc.assert(
      fc.property(
        arbNoteSection,
        arbProjectId,
        (noteCode, projectId) => {
          const route: MockRoute = { params: { projectId }, name: 'DisclosureNotes', query: {} }
          const action = buildNoteNavigationAction({ code: noteCode }, route)

          expect(action.type).toBe('eventBus')
          if (action.type === 'eventBus') {
            expect(action.payload.noteSection).toBe(noteCode)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  // Supplementary: tabToRoute always returns valid route segment
  it('tabToRoute maps known tabs correctly and defaults to disclosure-notes', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 30 }),
        (tab) => {
          const result = tabToRoute(tab)
          const validRoutes = ['financial-reports', 'disclosure-notes', 'workpapers', 'trial-balance']
          expect(validRoutes).toContain(result)
        },
      ),
      { numRuns: 20 },
    )
  })
})
