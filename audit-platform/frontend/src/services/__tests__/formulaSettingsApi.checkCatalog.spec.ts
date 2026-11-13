/** R3：运行真实目录 API 方法，仅隔离 apiProxy 传输层；未连接服务。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CheckCatalogQuery } from '@/composables/formula/useFormulaSettings'

const mocked = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: mocked }))
import { formulaSettingsApi } from '../formulaSettingsApi'

beforeEach(() => { mocked.get.mockReset() })

describe('formulaSettingsApi.checkRules', () => {
  it.each<CheckCatalogQuery>([
    {}, { project_id: 'p1' }, { year: 2025 }, { source: 'cross_check_preset' }, { q: '合成规则' },
    { source: 'report_builtin', project_id: 'p1', year: 2025 },
    { q: '合成规则', project_id: 'p2', year: 2024 },
  ])('透传完整参数 %j，静默请求且不再解包业务数据', async (params) => {
    const result = { sources: [], total: 0 }
    mocked.get.mockResolvedValueOnce(result)
    await expect(formulaSettingsApi.checkRules(params)).resolves.toBe(result)
    expect(mocked.get).toHaveBeenCalledTimes(1)
    expect(mocked.get).toHaveBeenCalledWith('/api/formula-catalog/check-rules', {
      params, _silent: true,
    })
    expect(params.year === undefined || typeof params.year === 'number').toBe(true)
  })

  it('不传参数时保留定义目录用法，不伪造项目或年度', async () => {
    mocked.get.mockResolvedValueOnce({ sources: [], total: 0 })
    await formulaSettingsApi.checkRules()
    expect(mocked.get).toHaveBeenCalledTimes(1)
    expect(mocked.get).toHaveBeenCalledWith('/api/formula-catalog/check-rules', {
      params: {}, _silent: true,
    })
  })

  it('真实 API 方法原样抛出读取错误，不改写为无历史或通过', async () => {
    const error = new Error('合成读取失败')
    mocked.get.mockRejectedValueOnce(error)
    await expect(formulaSettingsApi.checkRules({ project_id: 'p1', year: 2025 })).rejects.toBe(error)
  })
})
