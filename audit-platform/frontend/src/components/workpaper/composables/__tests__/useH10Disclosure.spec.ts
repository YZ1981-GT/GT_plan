/**
 * useH10Disclosure — 审定带入 / 试运行净额 / 旧键迁移
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useH10Disclosure } from '../useH10Disclosure'
import { buildH10SyncPayloads } from '../h10DisclosureSyncPayload'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn().mockResolvedValue({ data: { content: 'AI说明' } }) },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

describe('useH10Disclosure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('旧版 listed_sub_dr/nm 迁移合并到主行', () => {
    const allResponses = ref(new Map<string, any>([
      ['H10-disclosure-listed', {
        item_id: 'H10-disclosure-listed',
        remark: JSON.stringify([
          { rowKey: 'fixed_asset_disposal', currentAmount: 10, priorAmount: 1 },
          { rowKey: 'listed_sub_dr', currentAmount: 20, priorAmount: 2 },
          { rowKey: 'debt_restructuring_disposal', currentAmount: 5, priorAmount: 0 },
          { rowKey: 'listed_sub_nm', currentAmount: 7, priorAmount: 3 },
        ]),
      }],
    ]))

    const disc = useH10Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp-1'),
      isReadonly: ref(false),
    })

    const debt = disc.rows.value.find((r) => r.rowKey === 'debt_restructuring_disposal')
    const nm = disc.rows.value.find((r) => r.rowKey === 'non_monetary_exchange')
    expect(debt?.currentAmount).toBe(25) // 20+5
    expect(debt?.priorAmount).toBe(2)
    expect(nm?.currentAmount).toBe(7)
    expect(nm?.priorAmount).toBe(3)
    expect(disc.rows.value.some((r) => r.rowKey === 'listed_sub_dr')).toBe(false)
  })

  it('试运行明细净额回写主表 trial_operation_sales', () => {
    const saves: Array<{ id: string; data: any }> = []
    const allResponses = ref(new Map<string, any>())

    const disc = useH10Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: (id, data) => saves.push({ id, data }),
      wpId: ref('wp-1'),
      isReadonly: ref(false),
    })

    disc.updateTrialField('fixed_asset_trial', 'currentIncome', 200)
    disc.updateTrialField('fixed_asset_trial', 'currentCost', 80)
    disc.updateTrialField('rd_sample_sales', 'priorIncome', 50)
    disc.updateTrialField('rd_sample_sales', 'priorCost', 10)

    const trial = disc.rows.value.find((r) => r.rowKey === 'trial_operation_sales')
    expect(trial?.currentAmount).toBe(120)
    expect(trial?.priorAmount).toBe(40)
    expect(saves.some((s) => s.id === 'H10-disclosure-listed-trial')).toBe(true)
    expect(saves.some((s) => s.id === 'H10-disclosure-listed')).toBe(true)
  })

  it('pullFromAdjudication 从 H10-adj-rows 带入分项', () => {
    const allResponses = ref(new Map<string, any>([
      ['H10-adj-rows', {
        item_id: 'H10-adj-rows',
        remark: JSON.stringify({
          fixed_asset_disposal: {
            currentUnadjusted: 100,
            currentAje: 10,
            currentRje: 0,
            priorUnadjusted: 40,
            priorAje: 0,
            priorRje: 0,
          },
          construction_disposal: {
            currentUnadjusted: 50,
            currentAje: 0,
            currentRje: 0,
            priorUnadjusted: 0,
            priorAje: 0,
            priorRje: 0,
          },
        }),
      }],
      ['H10-1-adjudicated-amount', {
        item_id: 'H10-1-adjudicated-amount',
        conclusion: '160',
      }],
    ]))

    const disc = useH10Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp-1'),
      isReadonly: ref(false),
    })

    disc.pullFromAdjudication()

    expect(disc.adjudicatedAmount.value).toBe(160)
    expect(disc.rows.value.find((r) => r.rowKey === 'fixed_asset_disposal')?.currentAmount).toBe(110)
    expect(disc.rows.value.find((r) => r.rowKey === 'fixed_asset_disposal')?.priorAmount).toBe(40)
    expect(disc.rows.value.find((r) => r.rowKey === 'construction_disposal')?.currentAmount).toBe(50)
    expect(disc.disclosureTotal.value.currentAmount).toBe(160)
    expect(disc.reconcileDiff.value).toBe(0)
  })

  it('国企 pull 默认非经常性=本期审定', () => {
    const allResponses = ref(new Map<string, any>([
      ['H10-adj-rows', {
        remark: JSON.stringify({
          fixed_asset_disposal: {
            currentUnadjusted: 88,
            currentAje: 0,
            currentRje: 0,
            priorUnadjusted: 0,
            priorAje: 0,
            priorRje: 0,
          },
        }),
      }],
    ]))

    const disc = useH10Disclosure({
      variant: 'soe',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp-1'),
      isReadonly: ref(false),
    })

    disc.pullFromAdjudication()
    const fa = disc.rows.value.find((r) => r.rowKey === 'fixed_asset_disposal')
    expect(fa?.currentAmount).toBe(88)
    expect(fa?.nonRecurringAmount).toBe(88)
  })

  it('getSyncSnapshot + buildH10SyncPayloads 推送试运行子表', () => {
    const allResponses = ref(new Map<string, any>())
    const disc = useH10Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      isReadonly: ref(false),
    })

    disc.updateField('fixed_asset_disposal', 'currentAmount', 100)
    disc.updateTrialField('fixed_asset_trial', 'currentIncome', 30)
    disc.updateTrialField('fixed_asset_trial', 'currentCost', 10)
    disc.updateNoteText('测试附注')

    const payloads = buildH10SyncPayloads('wp-1', 'listed', [], disc.getSyncSnapshot())
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('三、资产处置收益')
    const main = payloads[0].sub_table_data['项  目']
    expect(main.some((r) => r.row_key === 'fixed_asset_disposal')).toBe(true)
    expect(main.some((r) => r.row_key === 'trial_operation_sales' && r.current_amount === 20)).toBe(true)
    expect(payloads[0].sub_table_data._trial_detail?.[0]?.current_amount).toBe(20)
    expect(payloads[0].sub_table_data._note_texts?.[0]?.text).toBe('测试附注')
  })
})
