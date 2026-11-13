/**
 * fetchNoteSectionsWithData（从 ReportView 抽出，spec post-push-residual-defect-closure R2）：
 * - 项目没填审计年度（null）⇒ 不请求、返回 null（原先拼出 /null/ 路径）；
 * - 有年度 ⇒ 收集有内容的章节（含子节点）；
 * - 取数失败 ⇒ 返回 null（调用方保留原值，不影响报表渲染）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', () => ({ default: { get } }))

import { fetchNoteSectionsWithData } from '../useReportData'

describe('fetchNoteSectionsWithData', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('年度为空：不请求，返回 null', async () => {
    expect(await fetchNoteSectionsWithData('p1', null)).toBeNull()
    expect(get).not.toHaveBeenCalled()
  })

  it('有年度：按年度取章节树，收集有内容的章节与子章节', async () => {
    get.mockResolvedValue({
      data: {
        data: [
          { note_section: '五、1', has_data: true },
          { note_section: '五、2', has_data: false, children: [{ note_section: '五、2-1', has_data: true }] },
        ],
      },
    })
    const set = await fetchNoteSectionsWithData('p1', 2025)
    // 附注目录端点（原先钉的是后端没有的 …/notes-tree，恒 404，这条用例把缺陷固定成了「正确」）
    expect(get.mock.calls[0][0]).toBe('/api/disclosure-notes/p1/2025')
    expect(set && [...set].sort()).toEqual(['五、1', '五、2-1'])
  })

  it('契约：请求的地址在后端附注路由里真实存在（目录端点 GET /{project_id}/{year}）', () => {
    const src = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../backend/app/routers/disclosure_notes.py'),
      'utf-8',
    )
    expect(src).toMatch(/APIRouter\(\s*prefix="\/api\/disclosure-notes"/)
    expect(src).toContain('@router.get("/{project_id}/{year}")')
    expect(src).not.toContain('notes-tree')
  })

  it('取数失败：返回 null', async () => {
    get.mockRejectedValue(new Error('boom'))
    expect(await fetchNoteSectionsWithData('p1', 2025)).toBeNull()
  })
})
