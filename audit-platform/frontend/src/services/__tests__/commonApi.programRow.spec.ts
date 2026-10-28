/**
 * 程序表按行裁剪 / 行归属的 API 层（spec procedure-trim-generation-delegation-chain 需求 6 / 7）：
 * 地址与后端路由逐字一致（trim / restore 两个端点、行归属带 sheet_name 查询参数），一律静默（调用方自己提示），
 * 解包统一信封。路由字面量与后端 `procedure_trim.py` / `wp_program_row_access.py` 对照（改一侧另一侧必须同步）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const http = vi.hoisted(() => ({ put: vi.fn(), post: vi.fn(), get: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { getProgramRowAccess, setProgramRowApplicability } from '../commonApi'

beforeEach(() => {
  vi.clearAllMocks()
  http.post.mockResolvedValue({ data: { data: { changed: true } } })
  http.get.mockResolvedValue({ data: { data: { full_power: false, own_program_nos: ['2'] } } })
})

const BODY = { sheet_name: '应收账款实质性程序表D2A', program_no: '3', reason: '不适用', request_id: 'rq' }

describe('按行裁剪 / 恢复的地址', () => {
  it('trim / restore 各走自己的端点，静默，解包信封', async () => {
    expect(await setProgramRowApplicability('p1', 'wp1', 'trim', BODY)).toEqual({ changed: true })
    expect(http.post).toHaveBeenLastCalledWith(
      '/api/projects/p1/procedure-trim/workpapers/wp1/program-rows/not-applicable', BODY, { _silent: true })
    await setProgramRowApplicability('p1', 'wp1', 'restore', { sheet_name: BODY.sheet_name, program_no: 3 })
    expect(http.post).toHaveBeenLastCalledWith(
      '/api/projects/p1/procedure-trim/workpapers/wp1/program-rows/restore',
      { sheet_name: BODY.sheet_name, program_no: 3 }, { _silent: true })
  })

  it('行归属：sheet_name 作查询参数，静默，解包信封', async () => {
    expect(await getProgramRowAccess('wp1', 'D2A')).toEqual({ full_power: false, own_program_nos: ['2'] })
    expect(http.get).toHaveBeenCalledWith('/api/workpapers/wp1/program-row-access',
      { params: { sheet_name: 'D2A' }, _silent: true })
  })

  it('与后端路由字面量一致', () => {
    const root = resolve(__dirname, '../../../../../backend/app/routers')
    const trim = readFileSync(resolve(root, 'procedure_trim.py'), 'utf-8')
    expect(trim).toContain('@router.post("/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/not-applicable")')
    expect(trim).toContain('@router.post("/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/restore")')
    expect(trim).toContain('router = APIRouter(prefix="/api/projects"')
    const access = readFileSync(resolve(root, 'wp_program_row_access.py'), 'utf-8')
    expect(access).toContain('APIRouter(prefix="/api/workpapers"')
    expect(access).toContain('@router.get("/{wp_id}/program-row-access")')
  })
})
