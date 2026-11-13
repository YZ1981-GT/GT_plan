/**
 * 浏览器检查 ③ — 全局发布 → 项目待确认 → 采用 / 保留 → 有效定义（含陈旧决策）
 *
 * 一条真实业务链（spec formula-management-repair-closure R7.2），用底稿公式域（种子项目有 D2-1 底稿）：
 * 1. 本项目先适配一处底稿公式；2. 管理员把同一公式位发布为全局（冲突交项目确认）；
 * 3. 项目待确认里出现这一条；带过期修订号 / 不带修订号提交分别 409 / 428；
 * 4. 采用 ⇒ 有效定义变成全局；同一事项再提交 409（陈旧决策）；5. 另一处选保留 ⇒ 有效定义仍是本项目的。
 * 原用例只读待确认列表、404 即通过。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import { api, apiToken, requireIsolatedDb, runTag, standaloneProjectId } from './helpers'

const MINE = "TB('1122','期末余额')*2"
const GLOBAL = "TB('1122','期末余额')"
const wpDef = (expression: string) => ({ expression, formula_type: 'auto_calc' })
const strip = (s: string) => String(s || '').replace(/^=/, '').trim()

async function adaptThenPublish(request: APIRequestContext, token: string, pid: string, slot: string) {
  const adapted = await api(request, token, 'PUT', `/api/projects/${pid}/formula-settings/wp/overrides`, {
    data: { items: [{ slot_key: slot, definition: wpDef(MINE) }] },
  })
  expect(adapted.status, JSON.stringify(adapted.error)).toBe(200)
  expect(adapted.data.saved.map((s: any) => s.slot_key)).toEqual([slot])

  const published = await api(request, token, 'POST', '/api/formula-settings/wp/global/publish', {
    data: {
      scope: '*', changes: [{ slot_key: slot, definition: wpDef(GLOBAL), expected_version: null }],
      decisions: { project_choices: {}, conflict_choices: {}, default_conflict: 'ask' }, request_id: `e2e-${runTag()}`,
    },
  })
  expect(published.status, JSON.stringify(published.error)).toBe(200)
  expect(published.data.summary.pending_total).toBeGreaterThanOrEqual(1)

  const pending = await api(request, token, 'GET', `/api/projects/${pid}/formula-settings/pending`)
  expect(pending.status).toBe(200)
  const item = (pending.data.items as any[]).find((i) => i.domain === 'wp' && i.slot_key === slot)
  expect(item, `待确认里没有 ${slot}`).toBeTruthy()
  expect(item.reason).toBe('conflict')
  expect(strip(item.local_definition.expression)).toBe(strip(MINE))
  expect(strip(item.upstream_definition.expression)).toBe(strip(GLOBAL))
  return item
}

async function effectiveExpression(request: APIRequestContext, token: string, pid: string, slot: string) {
  const eff = await api(request, token, 'GET', `/api/projects/${pid}/formula-settings/wp/effective`)
  expect(eff.status).toBe(200)
  const s = (eff.data.slots as any[]).find((x) => x.slot_key === slot)
  expect(s, `有效定义里没有 ${slot}`).toBeTruthy()
  return strip(s.definition?.expression)
}

test.describe('全局发布 → 待确认 → 采用 / 保留', () => {
  let token = ''
  const pid = standaloneProjectId()
  test.beforeAll(async ({ request }) => { token = await apiToken(request) })

  test('采用全局：修订号校验 → 有效定义变成全局 → 同一事项再提交为陈旧决策', async ({ request }) => {
    await requireIsolatedDb(request, token)
    const slot = `D2-1|E2E-${runTag()}|B5`
    const item = await adaptThenPublish(request, token, pid, slot)
    const url = `/api/projects/${pid}/formula-settings/pending/resolve`

    const stale = await api(request, token, 'POST', url, {
      data: { resolutions: [{ item_id: item.id, choice: 'adopt', revision: item.revision + 1 }] } })
    expect(stale.status).toBe(409)
    expect(stale.error.error_code).toBe('FORMULA_SYNC_ITEM_STALE')
    const missing = await api(request, token, 'POST', url, {
      data: { resolutions: [{ item_id: item.id, choice: 'adopt' }] } })
    expect(missing.status).toBe(428)
    expect(await effectiveExpression(request, token, pid, slot), '被拒的提交不改有效定义').toBe(strip(MINE))

    const adopted = await api(request, token, 'POST', url, {
      data: { resolutions: [{ item_id: item.id, choice: 'adopt', revision: item.revision }] } })
    expect(adopted.status, JSON.stringify(adopted.error)).toBe(200)
    expect(adopted.data.recalc_domains).toContain('wp')
    expect(await effectiveExpression(request, token, pid, slot)).toBe(strip(GLOBAL))

    const again = await api(request, token, 'POST', url, {
      data: { resolutions: [{ item_id: item.id, choice: 'adopt', revision: item.revision }] } })
    expect(again.status).toBe(409)
    expect(again.error.error_code).toBe('FORMULA_SYNC_ITEM_STALE')
    const left = await api(request, token, 'GET', `/api/projects/${pid}/formula-settings/pending`)
    expect((left.data.items as any[]).some((i) => i.id === item.id), '处理过的事项不再待确认').toBe(false)
  })

  test('保留本项目：有效定义仍是本项目的', async ({ request }) => {
    await requireIsolatedDb(request, token)
    const slot = `D2-1|E2E-${runTag()}|C6`
    const item = await adaptThenPublish(request, token, pid, slot)
    const kept = await api(request, token, 'POST', `/api/projects/${pid}/formula-settings/pending/resolve`, {
      data: { resolutions: [{ item_id: item.id, choice: 'keep', revision: item.revision }] } })
    expect(kept.status, JSON.stringify(kept.error)).toBe(200)
    expect(await effectiveExpression(request, token, pid, slot)).toBe(strip(MINE))
  })
})
