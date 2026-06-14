/**
 * DisclosureEditor — per-table guidance 显示逻辑单测
 *
 * 对应 spec `note-per-table-guidance` Phase 2（任务 2.1 / 2.3 / 2.5）。
 * DisclosureEditor.vue 体量过大（>2100 行、含大量子组件依赖）无法整体 mount，
 * 此处以相同的 Vue 响应式原语复刻组件内 `activeTableGuidance` / `showGuidance` /
 * `dismissGuidance` 三者的实现，验证：
 *   1. per-table guidance 优先、章节级 guidance_text 降级（任务 2.1）
 *   2. dismiss 粒度为 `note_section:tabIdx`，关闭一个 Tab 不影响另一个（任务 2.3）
 *   3. 单表章节走章节级降级、行为不变（任务 2.4）
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref, reactive, computed } from 'vue'

// 复刻组件内的最小响应式状态机（与 DisclosureEditor.vue 实现一一对应）
function createGuidanceModel() {
  const currentNote = ref<any>(null)
  const activeTableTab = ref('0')
  const dismissedGuidance = reactive(new Set<string>())

  const currentNoteTables = computed(() => {
    const td = currentNote.value?.table_data
    if (!td) return [] as any[]
    if (Array.isArray(td._tables) && td._tables.length > 0) return td._tables
    if (td.headers && td.rows) {
      return [{ name: currentNote.value.section_title, headers: td.headers, rows: td.rows }]
    }
    return [] as any[]
  })

  const activeTableData = computed(() => {
    const idx = parseInt(activeTableTab.value) || 0
    return currentNoteTables.value[idx] || currentNoteTables.value[0] || null
  })

  const activeTableGuidance = computed(() => {
    const t = activeTableData.value as any
    if (t?.guidance?.trim()) return t.guidance
    return currentNote.value?.guidance_text || ''
  })

  const showGuidance = computed(() => {
    if (!activeTableGuidance.value?.trim()) return false
    const key = `${currentNote.value?.note_section}:${activeTableTab.value}`
    return !dismissedGuidance.has(key)
  })

  function dismissGuidance() {
    const sec = currentNote.value?.note_section
    if (sec) dismissedGuidance.add(`${sec}:${activeTableTab.value}`)
  }

  return {
    currentNote, activeTableTab, dismissedGuidance,
    activeTableGuidance, showGuidance, dismissGuidance,
  }
}

describe('DisclosureEditor activeTableGuidance — 降级逻辑（任务 2.1）', () => {
  let m: ReturnType<typeof createGuidanceModel>
  beforeEach(() => { m = createGuidanceModel() })

  it('多表章节：优先显示当前 Tab 表格的 guidance', () => {
    m.currentNote.value = {
      note_section: '八、1',
      guidance_text: '章节级通用提示',
      table_data: {
        _tables: [
          { name: '货币资金', headers: [], rows: [], guidance: '（注：如有因抵押…）\n（提示：企业持有…）' },
          { name: '受限制的货币资金明细', headers: [], rows: [] },
        ],
      },
    }
    m.activeTableTab.value = '0'
    expect(m.activeTableGuidance.value).toBe('（注：如有因抵押…）\n（提示：企业持有…）')
  })

  it('多表章节：当前 Tab 表格无 guidance 时降级到章节级 guidance_text', () => {
    m.currentNote.value = {
      note_section: '八、1',
      guidance_text: '章节级通用提示',
      table_data: {
        _tables: [
          { name: '货币资金', headers: [], rows: [], guidance: '表0提示' },
          { name: '受限制的货币资金明细', headers: [], rows: [] }, // 无 guidance
        ],
      },
    }
    m.activeTableTab.value = '1'
    expect(m.activeTableGuidance.value).toBe('章节级通用提示')
  })

  it('表级 guidance 仅含空白时视为无，降级到章节级', () => {
    m.currentNote.value = {
      note_section: '八、1',
      guidance_text: '章节级通用提示',
      table_data: { _tables: [{ name: 't0', headers: [], rows: [], guidance: '   ' }] },
    }
    expect(m.activeTableGuidance.value).toBe('章节级通用提示')
  })

  it('表级与章节级均无 guidance 时返回空串', () => {
    m.currentNote.value = {
      note_section: '八、9',
      guidance_text: '',
      table_data: { _tables: [{ name: 't0', headers: [], rows: [] }] },
    }
    expect(m.activeTableGuidance.value).toBe('')
  })

  it('切换 Tab 时 activeTableGuidance 随之切换', () => {
    m.currentNote.value = {
      note_section: '八、1',
      guidance_text: '章节级',
      table_data: {
        _tables: [
          { name: 't0', headers: [], rows: [], guidance: '表0提示' },
          { name: 't1', headers: [], rows: [], guidance: '表1提示' },
        ],
      },
    }
    m.activeTableTab.value = '0'
    expect(m.activeTableGuidance.value).toBe('表0提示')
    m.activeTableTab.value = '1'
    expect(m.activeTableGuidance.value).toBe('表1提示')
  })
})

describe('DisclosureEditor 单表章节零回归（任务 2.4）', () => {
  let m: ReturnType<typeof createGuidanceModel>
  beforeEach(() => { m = createGuidanceModel() })

  it('单表（旧格式 headers/rows）章节仍走章节级 guidance_text', () => {
    m.currentNote.value = {
      note_section: '七',
      section_title: '应付账款',
      guidance_text: '单表章节提示',
      table_data: { headers: ['项目', '期末'], rows: [{ label: 'a', values: [1] }] },
    }
    expect(m.activeTableGuidance.value).toBe('单表章节提示')
    expect(m.showGuidance.value).toBe(true)
  })

  it('单表（_tables 长度为 1）无表级 guidance 时显示章节级', () => {
    m.currentNote.value = {
      note_section: '七',
      guidance_text: '单表章节提示',
      table_data: { _tables: [{ name: 't0', headers: [], rows: [] }] },
    }
    expect(m.activeTableGuidance.value).toBe('单表章节提示')
  })
})

describe('DisclosureEditor dismiss 粒度 — section:tabIdx（任务 2.3）', () => {
  let m: ReturnType<typeof createGuidanceModel>
  beforeEach(() => {
    m = createGuidanceModel()
    m.currentNote.value = {
      note_section: '八、1',
      guidance_text: '章节级',
      table_data: {
        _tables: [
          { name: 't0', headers: [], rows: [], guidance: '表0提示' },
          { name: 't1', headers: [], rows: [], guidance: '表1提示' },
        ],
      },
    }
  })

  it('关闭某 Tab 提示后该 Tab 不再显示', () => {
    m.activeTableTab.value = '0'
    expect(m.showGuidance.value).toBe(true)
    m.dismissGuidance()
    expect(m.showGuidance.value).toBe(false)
    expect(m.dismissedGuidance.has('八、1:0')).toBe(true)
  })

  it('关闭一个 Tab 不影响另一个 Tab 的提示显示', () => {
    m.activeTableTab.value = '0'
    m.dismissGuidance()        // 关闭 Tab0
    expect(m.showGuidance.value).toBe(false)

    m.activeTableTab.value = '1' // 切到 Tab1
    expect(m.showGuidance.value).toBe(true)
    expect(m.dismissedGuidance.has('八、1:1')).toBe(false)
  })

  it('两个 Tab 分别关闭后各自独立记忆', () => {
    m.activeTableTab.value = '0'
    m.dismissGuidance()
    m.activeTableTab.value = '1'
    m.dismissGuidance()
    expect(m.dismissedGuidance.has('八、1:0')).toBe(true)
    expect(m.dismissedGuidance.has('八、1:1')).toBe(true)
    // 两个 Tab 都已关闭
    m.activeTableTab.value = '0'
    expect(m.showGuidance.value).toBe(false)
    m.activeTableTab.value = '1'
    expect(m.showGuidance.value).toBe(false)
  })

  it('无 guidance 内容时 showGuidance 恒为 false', () => {
    m.currentNote.value = {
      note_section: '八、9',
      guidance_text: '',
      table_data: { _tables: [{ name: 't0', headers: [], rows: [] }] },
    }
    expect(m.showGuidance.value).toBe(false)
  })
})
