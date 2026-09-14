/**
 * I2 P0/P1 复盘修复回归单测
 *
 * 覆盖：
 * 1. fetchI2TbData / persistI2TbData — TB带入(I2-1)取数与持久化形状
 * 2. computeI2SheetCompletion — 附注(上市/国企)完成度前缀须与 useI2Disclosure 实际持久化 key 一致
 *    （回归 I2TabIndex.vue 曾用错误前缀 'I2-disc-L-'/'I2-disc-S-' 的问题）
 * 3. useI2Impairment.publishImpairmentToParent — 保存后始终推送 K11 事件（即使补提为0）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { fetchI2TbData, persistI2TbData, type I2TbData } from '../useI2FormData'
import { computeI2SheetCompletion } from '../i2ConsistencyModel'
import { I2_DISC_KEYS } from '../i2DisclosureModel'
import { useI2Impairment } from '../useI2Impairment'

// ─── 1. fetchI2TbData / persistI2TbData ────────────────────────────────────

describe('fetchI2TbData', () => {
  it('聚合科目1717未审/审定/AJE/RJE（axios风格 res.data）', async () => {
    const httpClient = {
      get: vi.fn().mockResolvedValue({
        data: [
          { standard_account_code: '171701', unadjusted_amount: 100, audited_amount: 120, aje_adjustment: 10, rje_adjustment: 10 },
          { standard_account_code: '171702', unadjusted_amount: 50, audited_amount: 50, aje_adjustment: 0, rje_adjustment: 0 },
          { standard_account_code: '2221', unadjusted_amount: 999, audited_amount: 999, aje_adjustment: 0, rje_adjustment: 0 },
        ],
      }),
    }
    const tb = await fetchI2TbData(httpClient, 'proj-1')
    expect(tb).toEqual({ unadjusted1717: 150, audited1717: 170, aje1717: 10, rje1717: 10 })
    expect(httpClient.get).toHaveBeenCalledWith(
      '/projects/proj-1/trial-balance',
      expect.objectContaining({ params: { account_prefix: '1717' } }),
    )
  })

  it('聚合科目1717未审/审定/AJE/RJE（api风格：已解包为数组）', async () => {
    const httpClient = {
      get: vi.fn().mockResolvedValue([
        { account_code: '1717', unadjusted_amount: 200, audited_amount: 200, aje_adjustment: 0, rje_adjustment: 0 },
      ]),
    }
    const tb = await fetchI2TbData(httpClient, 'proj-2')
    expect(tb.unadjusted1717).toBe(200)
  })

  it('projectId 为空时返回全零，不发起请求', async () => {
    const httpClient = { get: vi.fn() }
    const tb = await fetchI2TbData(httpClient, '')
    expect(tb).toEqual({ unadjusted1717: 0, audited1717: 0, aje1717: 0, rje1717: 0 })
    expect(httpClient.get).not.toHaveBeenCalled()
  })

  it('请求失败时静默返回全零', async () => {
    const httpClient = { get: vi.fn().mockRejectedValue(new Error('network')) }
    const tb = await fetchI2TbData(httpClient, 'proj-3')
    expect(tb).toEqual({ unadjusted1717: 0, audited1717: 0, aje1717: 0, rje1717: 0 })
  })
})

describe('persistI2TbData', () => {
  it('写入 I2-1 sheet 下的 I2-tb-data（JSON字符串），供 I2TabAdjudication tbData computed 消费', async () => {
    const saveResponse = vi.fn().mockResolvedValue(undefined)
    const tb: I2TbData = { unadjusted1717: 100, audited1717: 110, aje1717: 5, rje1717: 5 }
    await persistI2TbData(saveResponse, tb)
    expect(saveResponse).toHaveBeenCalledWith('I2-1', { 'I2-tb-data': JSON.stringify(tb) })
  })
})

// ─── 2. 附注完成度前缀回归（I2TabIndex.vue 修复） ──────────────────────────

describe('computeI2SheetCompletion — 附注前缀须匹配 useI2Disclosure 实际持久化 key', () => {
  function makeItem(value: string) {
    return { item_id: 'x', conclusion: null, remark: value }
  }

  it('I2_DISC_KEYS 常量以 I2-disc-listed- / I2-disc-soe- 为前缀（回归错误前缀 I2-disc-L-/I2-disc-S-）', () => {
    expect(I2_DISC_KEYS.listedNature).toMatch(/^I2-disc-listed-/)
    expect(I2_DISC_KEYS.listedMovement).toMatch(/^I2-disc-listed-/)
    expect(I2_DISC_KEYS.soeMovement).toMatch(/^I2-disc-soe-/)
  })

  it('使用正确前缀 I2-disc-listed- 能识别已填写的附注(上市)数据', () => {
    const map = new Map<string, any>([
      [I2_DISC_KEYS.listedNature, makeItem(JSON.stringify([{ name: '课题1' }]))],
      [I2_DISC_KEYS.listedMovement, makeItem(JSON.stringify([{ name: '课题1' }]))],
    ])
    const result = computeI2SheetCompletion(map, ['I2-disc-listed-'])
    expect(result.filled).toBeGreaterThan(0)
    expect(result.status).not.toBe('未开始')
  })

  it('旧的错误前缀 I2-disc-L- 无法匹配任何实际持久化 key（说明修复前的 bug 场景）', () => {
    const map = new Map<string, any>([
      [I2_DISC_KEYS.listedNature, makeItem(JSON.stringify([{ name: '课题1' }]))],
      [I2_DISC_KEYS.listedMovement, makeItem(JSON.stringify([{ name: '课题1' }]))],
    ])
    const result = computeI2SheetCompletion(map, ['I2-disc-L-'])
    expect(result.filled).toBe(0)
    expect(result.total).toBe(0)
    expect(result.status).toBe('未开始')
  })

  it('使用正确前缀 I2-disc-soe- 能识别已填写的附注(国企)数据', () => {
    const map = new Map<string, any>([
      [I2_DISC_KEYS.soeMovement, makeItem(JSON.stringify([{ name: '课题1' }]))],
      [I2_DISC_KEYS.soeNote, makeItem('说明文本')],
    ])
    const result = computeI2SheetCompletion(map, ['I2-disc-soe-'])
    expect(result.filled).toBe(2)
    expect(result.total).toBe(2)
    expect(result.status).toBe('已完成')
  })
})

// ─── 3. I2-15 保存时始终推送 K11（即使补提为0） ────────────────────────────

describe('useI2Impairment.publishImpairmentToParent', () => {
  let dispatchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    dispatchSpy = vi.spyOn(window, 'dispatchEvent')
  })

  it('补提金额为0时仍派发 impairment:calculated 事件并调用 onSave 刷新（保存后始终执行）', () => {
    const onSave = vi.fn()
    const { impairmentRows, addImpairmentRow, publishImpairmentToParent } = useI2Impairment(
      ref('wp-1'),
      ref(new Map()),
      { onSave },
    )
    addImpairmentRow({ name: '项目A', bookValue: 100, hasIndication: 'N' })
    expect(impairmentRows.value[0].shouldProvision).toBe(0)

    const r = publishImpairmentToParent()

    expect(r.ok).toBe(true)
    expect(r.supplement).toBe(0)
    expect(onSave).toHaveBeenCalledWith('I2-15-supplement-total', 0)
    const calancedCalls = dispatchSpy.mock.calls.filter(
      ([evt]) => (evt as CustomEvent).type === 'impairment:calculated',
    )
    expect(calancedCalls.length).toBeGreaterThan(0)
  })

  it('补提金额>0时消息提示应包含金额', () => {
    const onSave = vi.fn()
    const { addImpairmentRow, updateImpairmentField, publishImpairmentToParent } = useI2Impairment(
      ref('wp-1'),
      ref(new Map()),
      { onSave },
    )
    addImpairmentRow({ name: '项目B', bookValue: 100, hasIndication: 'Y' })
    updateImpairmentField(0, 'fairValueLessDisposal', 40)
    updateImpairmentField(0, 'dcfValue', 30)

    const r = publishImpairmentToParent()
    expect(r.supplement).toBeGreaterThan(0)
    expect(r.message).toContain('已推送本期补提')
  })
})
