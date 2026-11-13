/**
 * 公式选址（地址库）契约 — 截断必须如实回报，不能让前端把截断后的结果当成完整的
 *
 * `GET /api/address-registry`：`total` 是真实匹配数，`returned` 是本次条数，`truncated` 说明被 `limit` 截断，
 * `truncated_domains` 列出有地址没返回的域（前端据此不把这些域当完整的）。不按域取时按
 * report → tb → note → wp → aux 的顺序拼接，所以按域取的总数之和等于不按域取的总数，`limit=1` 时返回的是
 * 第一个有地址的域的第一条、被截的域可以逐个算出来。超出上限直接 422（不静默截成上限）。
 * 原用例打不存在的 `/projects/{pid}/formula-management/address-registry`，只断言「不是 500」⇒ 恒绿。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import { api, apiToken, seedYear, standaloneProjectId } from './helpers'

const MAX_LIMIT = 50_000
const DOMAINS = ['report', 'tb', 'note', 'wp', 'aux']

interface Registry {
  total: number
  returned: number
  truncated: boolean
  truncated_domains: string[]
  items: Array<{ uri: string; domain: string; formula_ref: string; label: string }>
}

function search(request: APIRequestContext, token: string, params: Record<string, string | number>) {
  return api<Registry>(request, token, 'GET', '/api/address-registry', {
    params: { project_id: standaloneProjectId(), year: seedYear(), ...params },
  })
}

/** 各域地址总数（逐域取，每条都核对确实属于该域） */
async function domainTotals(request: APIRequestContext, token: string) {
  const totals: Record<string, number> = {}
  for (const domain of DOMAINS) {
    const one = await search(request, token, { domain, limit: MAX_LIMIT })
    expect(one.status, `域 ${domain}：${JSON.stringify(one.error)}`).toBe(200)
    expect(one.data.returned).toBe(one.data.items.length)
    expect(one.data.truncated).toBe(false)
    expect(one.data.items.filter((i) => i.domain !== domain).map((i) => i.uri),
      `域 ${domain} 返回了别的域的地址`).toEqual([])
    totals[domain] = one.data.total
  }
  return totals
}

test.describe('公式选址地址库', () => {
  let token = ''
  test.beforeAll(async ({ request }) => { token = await apiToken(request) })

  test('整库：条数自洽，按域取的总数之和等于不按域的总数', async ({ request }) => {
    const all = await search(request, token, { limit: MAX_LIMIT })
    expect(all.status, JSON.stringify(all.error)).toBe(200)
    expect(all.data.total, '底稿域由 wp_account_mapping.json 构建，整库不应为空').toBeGreaterThan(0)
    expect(all.data.returned).toBe(all.data.items.length)
    expect(all.data.truncated).toBe(all.data.total > MAX_LIMIT)
    expect(all.data.truncated_domains).toEqual([])
    for (const item of all.data.items.slice(0, 200)) {
      expect(item.uri, '地址缺 uri').toBeTruthy()
      expect(item.formula_ref, `地址 ${item.uri} 缺可插入的公式引用`).toBeTruthy()
    }
    const totals = await domainTotals(request, token)
    expect(Object.values(totals).reduce((a, b) => a + b, 0), '按域取的总数之和应等于整库总数').toBe(all.data.total)
  })

  test('截断：total 是真实总数，返回第一个有地址的域的第一条，被截的域逐个点名', async ({ request }) => {
    const totals = await domainTotals(request, token)
    const total = Object.values(totals).reduce((a, b) => a + b, 0)
    expect(total, '至少要有两条地址才能验证截断').toBeGreaterThan(1)
    const first = DOMAINS.find((d) => totals[d] > 0)!
    const expectedCut = DOMAINS.filter((d) => totals[d] > (d === first ? 1 : 0))

    const r = await search(request, token, { limit: 1 })
    expect(r.status, JSON.stringify(r.error)).toBe(200)
    expect(r.data.returned).toBe(1)
    expect(r.data.items.map((i) => i.domain)).toEqual([first])
    expect(r.data.total, 'total 必须是真实总数，不是截断后的条数').toBe(total)
    expect(r.data.truncated).toBe(true)
    expect(r.data.truncated_domains).toEqual(expectedCut)
  })

  test('越界参数：超过上限 422、非 UUID 项目 422', async ({ request }) => {
    const over = await search(request, token, { limit: MAX_LIMIT + 1 })
    expect(over.status, '超过上限应 422，不能静默截成上限').toBe(422)
    const bad = await api(request, token, 'GET', '/api/address-registry',
      { params: { project_id: 'not-a-uuid', year: seedYear(), limit: 10 } })
    expect(bad.status).toBe(422)
  })
})
