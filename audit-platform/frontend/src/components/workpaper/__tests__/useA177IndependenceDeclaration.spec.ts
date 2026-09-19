/**
 * Unit Tests — useA177IndependenceDeclaration composable
 *
 * Spec: .kiro/specs/a17-7-independence-declaration/
 * Task: 2.3
 *
 * Tests: debounce timing, team CRUD operations, threat CRUD,
 *        variant switching prefix, JSON serialization
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA177IndependenceDeclaration } from '../composables/useA177IndependenceDeclaration'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

describe('useA177IndependenceDeclaration', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-177') {
    const wpIdRef = ref(wpId)
    return useA177IndependenceDeclaration(wpIdRef)
  }

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads all sections from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            variant: 'team',
            meta_info: { client_name: '测试公司', audit_year: '2025', index_no: 'A17-7' },
            declaration_text: '声明正文',
            period_data: { business_start: '2025-01-01', business_end: '2025-12-31', report_start: '2025-01-01', report_end: '2025-12-31' },
            team_sign_table: [{ index: 1, name: '张三', signed: true, date: '2025-06-01' }],
            partner_section: { confirmed: true, explanation: null, partner_sign: { name: '王五', date: '2025-06-15' }, manager_sign: { name: '赵六', date: '2025-06-15' } },
            threat_records: { economic_interest: [{ member: 'A', type: '股票', amount: '10万', measure: '处置' }], loan_guarantee: [], business_relation: [] },
            guidance_notes: ['1', '2', '3', '4', '5'],
            project_context: { client_name: '测试公司', audit_year: '2025', team_members: [{ name: '张三' }] },
          },
        }],
      })

      const c = setup()
      await c.loadData()

      expect(c.variant.value).toBe('team')
      expect(c.metaInfo.value.client_name).toBe('测试公司')
      expect(c.declarationText.value).toBe('声明正文')
      expect(c.periodData.value.business_start).toBe('2025-01-01')
      expect(c.teamSignTable.value).toHaveLength(1)
      expect(c.teamSignTable.value[0].name).toBe('张三')
      expect(c.partnerSection.value.confirmed).toBe(true)
      expect(c.threatRecords.value.economic_interest).toHaveLength(1)
      expect(c.commitmentItems.value.length).toBeGreaterThan(0)
      expect(c.projectContext.value.team_members).toHaveLength(1)
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network'))
      const c = setup()
      await c.loadData()
      expect(c.loading.value).toBe(false)
      expect(c.variant.value).toBe('team') // default preserved
    })
  })

  // ─── Team Sign Table CRUD ───

  describe('team sign table CRUD', () => {
    it('addTeamMember adds a row with next index', () => {
      const c = setup()
      c.addTeamMember()
      expect(c.teamSignTable.value).toHaveLength(1)
      expect(c.teamSignTable.value[0].index).toBe(1)
      expect(c.teamSignTable.value[0].name).toBe('')
      expect(c.teamSignTable.value[0].signed).toBe(false)
    })

    it('addTeamMember increments index from existing max', () => {
      const c = setup()
      c.teamSignTable.value = [{ index: 3, name: 'A', signed: false, date: null }]
      c.addTeamMember()
      expect(c.teamSignTable.value).toHaveLength(2)
      expect(c.teamSignTable.value[1].index).toBe(4)
    })

    it('removeTeamMember removes and re-indexes', () => {
      const c = setup()
      c.teamSignTable.value = [
        { index: 1, name: 'A', signed: false, date: null },
        { index: 2, name: 'B', signed: false, date: null },
        { index: 3, name: 'C', signed: false, date: null },
      ]
      c.removeTeamMember(1)
      expect(c.teamSignTable.value).toHaveLength(2)
      expect(c.teamSignTable.value[0].name).toBe('A')
      expect(c.teamSignTable.value[1].name).toBe('C')
      // Re-indexed
      expect(c.teamSignTable.value[0].index).toBe(1)
      expect(c.teamSignTable.value[1].index).toBe(2)
    })

    it('removeTeamMember with invalid index does nothing', () => {
      const c = setup()
      c.teamSignTable.value = [{ index: 1, name: 'A', signed: false, date: null }]
      c.removeTeamMember(5)
      expect(c.teamSignTable.value).toHaveLength(1)
    })

    it('updateTeamMember updates specific field', () => {
      const c = setup()
      c.teamSignTable.value = [{ index: 1, name: 'A', signed: false, date: null }]
      c.updateTeamMember(0, 'name', '新名字')
      expect(c.teamSignTable.value[0].name).toBe('新名字')
    })

    it('updateTeamMember sets signed to true', () => {
      const c = setup()
      c.teamSignTable.value = [{ index: 1, name: 'A', signed: false, date: null }]
      c.updateTeamMember(0, 'signed', true)
      expect(c.teamSignTable.value[0].signed).toBe(true)
    })
  })

  // ─── Threat Record CRUD ───

  describe('threat record CRUD', () => {
    it('addThreatRow adds economic interest row', () => {
      const c = setup()
      c.addThreatRow('economic_interest')
      expect(c.threatRecords.value.economic_interest).toHaveLength(1)
      expect(c.threatRecords.value.economic_interest[0].member).toBe('')
    })

    it('addThreatRow adds loan guarantee row', () => {
      const c = setup()
      c.addThreatRow('loan_guarantee')
      expect(c.threatRecords.value.loan_guarantee).toHaveLength(1)
    })

    it('addThreatRow adds business relation row', () => {
      const c = setup()
      c.addThreatRow('business_relation')
      expect(c.threatRecords.value.business_relation).toHaveLength(1)
      expect(c.threatRecords.value.business_relation[0]).toHaveProperty('description')
    })

    it('removeThreatRow removes from correct type', () => {
      const c = setup()
      c.threatRecords.value.economic_interest = [
        { member: 'A', type: '股票', amount: '10', measure: '处置' },
        { member: 'B', type: '债券', amount: '20', measure: '转让' },
      ]
      c.removeThreatRow('economic_interest', 0)
      expect(c.threatRecords.value.economic_interest).toHaveLength(1)
      expect(c.threatRecords.value.economic_interest[0].member).toBe('B')
    })

    it('removeThreatRow with invalid index does nothing', () => {
      const c = setup()
      c.threatRecords.value.loan_guarantee = [{ member: 'A', type: 't', amount: '0', measure: 'x' }]
      c.removeThreatRow('loan_guarantee', 5)
      expect(c.threatRecords.value.loan_guarantee).toHaveLength(1)
    })

    it('updateThreatRow updates specific field', () => {
      const c = setup()
      c.threatRecords.value.business_relation = [{ member: '', description: '', measure: '' }]
      c.updateThreatRow('business_relation', 0, 'member', '张三')
      expect(c.threatRecords.value.business_relation[0].member).toBe('张三')
    })
  })

  // ─── Variant Switching Prefix ───

  describe('variant prefix', () => {
    it('team variant uses a177- prefix for period saves', async () => {
      const c = setup()
      c.variant.value = 'team'
      c.updatePeriod('business_start', '2025-01-01')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-177/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a177-period-business-start' }),
          ]),
        }),
      )
    })

    it('committee variant uses a177a- prefix for period saves', async () => {
      const c = setup()
      c.variant.value = 'committee'
      c.updatePeriod('report_end', '2025-12-31')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-177/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a177a-period-report-end' }),
          ]),
        }),
      )
    })

    it('partner section uses correct prefix', async () => {
      const c = setup()
      c.variant.value = 'team'
      c.updatePartner('confirmed', true)

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-177/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a177-partner-confirmed', conclusion: 'Y' }),
          ]),
        }),
      )
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const c = setup()
      c.updatePeriod('business_start', '2025-01-01')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('batches multiple updates into single save', async () => {
      const c = setup()
      c.updatePeriod('business_start', '2025-01-01')
      c.updatePeriod('business_end', '2025-12-31')
      c.updatePartner('confirmed', true)

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBeGreaterThanOrEqual(3)
    })

    it('resets debounce timer on subsequent update', async () => {
      const c = setup()
      c.updatePeriod('business_start', '2025-01-01')

      vi.advanceTimersByTime(1500)
      c.updatePeriod('business_end', '2025-12-31')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  // ─── JSON Serialization ───

  describe('JSON serialization', () => {
    it('sign table rows are serialized as JSON in remark', async () => {
      const c = setup()
      c.teamSignTable.value = [{ index: 1, name: '测试', signed: true, date: '2025-01-01' }]
      c.addTeamMember() // trigger save

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      const items = mockPut.mock.calls[0][1].items
      const signItem = items.find((i: any) => i.item_id.includes('sign-'))
      expect(signItem).toBeDefined()
      const parsed = JSON.parse(signItem.remark)
      expect(parsed).toHaveProperty('name')
      expect(parsed).toHaveProperty('signed')
    })

    it('partner sign is serialized as JSON', async () => {
      const c = setup()
      c.updatePartner('partner_sign', { name: '合伙人', date: '2025-06-15' })

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      const items = mockPut.mock.calls[0][1].items
      const partnerItem = items.find((i: any) => i.item_id.includes('partner-sign'))
      expect(partnerItem).toBeDefined()
      const parsed = JSON.parse(partnerItem.remark)
      expect(parsed.name).toBe('合伙人')
      expect(parsed.date).toBe('2025-06-15')
    })

    it('threat rows are serialized as JSON in remark', async () => {
      const c = setup()
      c.threatRecords.value.economic_interest = [{ member: '张三', type: '股票', amount: '10万', measure: '处置' }]
      c.addThreatRow('economic_interest') // triggers save

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      const items = mockPut.mock.calls[0][1].items
      const threatItem = items.find((i: any) => i.item_id.includes('threat-economic-'))
      expect(threatItem).toBeDefined()
      const parsed = JSON.parse(threatItem.remark)
      expect(parsed).toHaveProperty('member')
    })
  })

  // ─── Flush ───

  describe('flushPendingSaves', () => {
    it('immediately saves pending items', async () => {
      const c = setup()
      c.updatePeriod('business_start', '2025-03-01')

      await c.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('does nothing when no pending changes', async () => {
      const c = setup()
      await c.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  // ─── Save Status ───

  describe('save status', () => {
    it('transitions saved → unsaved → saving → saved', async () => {
      const c = setup()
      expect(c.saveStatus.value).toBe('saved')

      c.updatePeriod('business_start', '2025-01-01')
      expect(c.saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(c.saveStatus.value).toBe('saved')
    })
  })
})
