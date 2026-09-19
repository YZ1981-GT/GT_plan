/**
 * Property-Based Tests for FourColumnCatalog debounce/state logic
 * Feature: four-panel-note-linkage
 * numRuns: 20
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// Mock API and eventBus before importing component
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@/services/apiPaths', () => ({
  trialBalance: { get: () => '/mock-tb' },
  workpapers: { list: () => '/mock-wp' },
  projects: { list: '/mock-projects' },
}))

const mockEmit = vi.fn()
const mockOn = vi.fn()
const mockOff = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: (...args: any[]) => mockOn(...args), off: (...args: any[]) => mockOff(...args), emit: (...args: any[]) => mockEmit(...args) },
}))

import FourColumnCatalog from '../FourColumnCatalog.vue'

function mountCatalog(projectId = 'proj-1') {
  return mount(FourColumnCatalog, {
    props: { project: { id: projectId, audit_year: 2025 } },
    global: {
      stubs: { ElIcon: true, ElTag: true, ElEmpty: true },
    },
  })
}

describe('FourColumnCatalog Property-Based Tests', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  // Feature: four-panel-note-linkage, Property 8: 防抖仅执行最后一次
  it('Property 8: debounce only executes the last click in rapid sequence', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.string({ minLength: 1, maxLength: 10 }),
          { minLength: 2, maxLength: 20 },
        ),
        (noteCodes) => {
          const wrapper = mountCatalog('current-proj')
          const vm = wrapper.vm as any

          // Reset state
          vm.selectedKey = ''
          vm.isNavigating = false

          // Rapid-fire note section clicks (all different keys to bypass same-key guard)
          const uniqueCodes = [...new Set(noteCodes.map((c, i) => `${c}-${i}`))]
          for (const code of uniqueCodes) {
            vm.selectItem('note', { code })
          }

          // Before timer: no 'select' emitted yet (all debounced)
          const beforeEvents = (wrapper.emitted('select') || [])
          expect(beforeEvents.length).toBe(0)

          // Advance past debounce window
          vi.advanceTimersByTime(350)

          // Exactly 1 emit with the LAST code
          const afterEvents = (wrapper.emitted('select') || []) as any[][]
          expect(afterEvents.length).toBe(1)
          expect(afterEvents[0][0].code).toBe(uniqueCodes[uniqueCodes.length - 1])

          wrapper.unmount()
        },
      ),
      { numRuns: 20 },
    )
  })

  // Feature: four-panel-note-linkage, Property 9: 导航期间禁用交互
  it('Property 9: no navigation dispatched while isNavigating=true', () => {
    fc.assert(
      fc.property(
        fc.record({ id: fc.uuid(), name: fc.string({ minLength: 1, maxLength: 20 }) }),
        (project) => {
          const wrapper = mountCatalog('current-proj')
          const vm = wrapper.vm as any

          // Set isNavigating = true
          vm.isNavigating = true

          // Try to switch project
          vm.onSwitchProject({ id: project.id, audit_year: 2025 })

          // Advance timer
          vi.advanceTimersByTime(500)

          // No select event should be emitted
          const events = wrapper.emitted('select') || []
          expect(events.length).toBe(0)

          wrapper.unmount()
        },
      ),
      { numRuns: 20 },
    )
  })

  // Feature: four-panel-note-linkage, Property 2: 已选中项点击为空操作
  it('Property 2: clicking already-selected item is no-op', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        (noteCode) => {
          const wrapper = mountCatalog('proj-1')
          const vm = wrapper.vm as any

          // Pre-set selectedKey to simulate already selected
          const key = `note:${noteCode}`
          vm.selectedKey = key

          // Call selectItem with same note
          vm.selectItem('note', { code: noteCode })

          vi.advanceTimersByTime(500)

          // No select event emitted (same key guard)
          const events = wrapper.emitted('select') || []
          expect(events.length).toBe(0)

          wrapper.unmount()
        },
      ),
      { numRuns: 20 },
    )
  })


  // Feature: four-panel-note-linkage, Property 6: 项目切换清除选中状态
  it('Property 6: project switch clears selectedKey', async () => {
    // Use real timers for this async test (watch triggers are sync in Vue)
    vi.useRealTimers()

    await fc.assert(
      fc.asyncProperty(
        fc.record({
          oldKey: fc.string({ minLength: 1, maxLength: 20 }),
          newProjectId: fc.uuid(),
        }),
        async ({ oldKey, newProjectId }) => {
          vi.useFakeTimers()
          const wrapper = mountCatalog('proj-old')
          const vm = wrapper.vm as any

          // Wait for initial watchers to settle
          await vi.advanceTimersByTimeAsync(50)

          // Set some selectedKey (simulating user had selected a note)
          vm.selectedKey = `note:${oldKey}`

          // Simulate project prop change (triggers watch with oldId='proj-old')
          const targetId = newProjectId === 'proj-old' ? 'proj-new' : newProjectId
          await wrapper.setProps({ project: { id: targetId, audit_year: 2025 } })
          await vi.advanceTimersByTimeAsync(50)

          // selectedKey should be cleared
          const result = vm.selectedKey === ''
          wrapper.unmount()
          vi.useRealTimers()
          return result
        },
      ),
      { numRuns: 20 },
    )

    // Restore fake timers for other tests
    vi.useFakeTimers()
  })

  // Feature: four-panel-note-linkage, Property 7: 乐观更新立即生效
  it('Property 7: optimistic update is synchronous (before debounce resolves)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        (noteCode) => {
          const wrapper = mountCatalog('proj-1')
          const vm = wrapper.vm as any

          // Ensure different from current
          vm.selectedKey = ''
          vm.isNavigating = false

          // Call selectItem — selectedKey should update IMMEDIATELY (sync)
          vm.selectItem('note', { code: noteCode })

          // Check BEFORE timer advances (no await, no advanceTimers)
          expect(vm.selectedKey).toBe(`note:${noteCode}`)

          wrapper.unmount()
        },
      ),
      { numRuns: 20 },
    )
  })
})
