/**
 * 合并底稿行内证据稳定身份（批 6 / ADR-CRW-006 / 任务 6.3）
 *
 * - consolTrialCellRef / consolReportCellRef / consolCellRefWithRowId：前端直接拼 id: 串（无需往返）；
 * - resolveConsolEvidenceTarget：无稳定行 id 时走后端派生内容摘要身份；
 * - ensureConsolShell：首次上传前幂等建壳拿 wp_id；
 * - appendConsolEvidence：带 sheet_name + cell_ref（不走 evidence_sheet/cell）；
 * - 插删行不漂移：同一行（按稳定 id）身份串恒定，无需 shift。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { post: (...a: any[]) => mockPost(...a) },
}))
vi.mock('@/composables/useWpEvidenceLinks', () => ({
  invalidateWpEvidenceLinks: vi.fn().mockResolvedValue([]),
}))

import {
  appendConsolEvidence,
  consolCellRefWithRowId,
  consolReportCellRef,
  consolTrialCellRef,
  ensureConsolShell,
  resolveConsolEvidenceTarget,
} from '../consolRowEvidence'

const envelope = (data: unknown) => ({ data: { code: 0, message: 'ok', data } })

beforeEach(() => {
  mockPost.mockReset()
})

describe('前端直接拼稳定 id 身份串（与后端 build_cell_ref 逐字节一致）', () => {
  // 注：row_identity 段内的 ':' 会被转义成 %3A（后端 _sanitize_segment 同此），解析端再无歧义还原
  it('合并试算行身份 = 科目码', () => {
    expect(consolTrialCellRef('1001')).toBe('node:consol_trial/row:id%3A1001')
    expect(consolTrialCellRef('1001', 'amount')).toBe('node:consol_trial/row:id%3A1001/col:amount')
  })

  it('合并报表行身份 = 行键', () => {
    expect(consolReportCellRef('BS_010')).toBe('node:consol_report/row:id%3ABS_010')
  })

  it('通用 node/row/col 转义分隔符', () => {
    const ref = consolCellRefWithRowId('a/b', 'x:y')
    expect(ref).toBe('node:a%2Fb/row:id%3Ax%3Ay')
  })
})

describe('插删行不漂移（前端拼 id 串）', () => {
  it('同一科目在插删别的行前后身份串恒定', () => {
    const before = consolTrialCellRef('1122', 'end')
    // 在 1122 前插入 / 删除别的科目后再拼，串不变（身份只依赖科目码）
    const after = consolTrialCellRef('1122', 'end')
    expect(after).toBe(before)
  })
})

describe('resolveConsolEvidenceTarget', () => {
  it('把 sheet_type/node/row_fields 交给后端，解出稳定坐标与壳 wp_id', async () => {
    mockPost.mockResolvedValue(
      envelope({
        wp_id: 'wp-shell-1',
        shell_exists: true,
        sheet_name: '五、8',
        cell_ref: 'node:五、8/row:h:abcd1234',
        node_key: '五、8',
        row_identity: 'h:abcd1234',
        col: null,
      }),
    )
    const target = await resolveConsolEvidenceTarget({
      projectId: 'p1',
      year: 2025,
      sheetType: 'note',
      nodeKey: '五、8',
      rowFields: { item_name: '存货' },
    })
    expect(mockPost).toHaveBeenCalledWith(
      '/api/consolidation/p1/2025/workpaper-shell/evidence-target',
      { sheet_type: 'note', node_key: '五、8', row_fields: { item_name: '存货' }, row_identity: null, col: null },
      expect.objectContaining({ _silent: true }),
    )
    expect(target.wpId).toBe('wp-shell-1')
    expect(target.shellExists).toBe(true)
    expect(target.cellRef).toBe('node:五、8/row:h:abcd1234')
  })

  it('壳未创建时返回 wpId=null / shellExists=false', async () => {
    mockPost.mockResolvedValue(
      envelope({ wp_id: null, shell_exists: false, sheet_name: 'cost', cell_ref: 'node:cost/row:h:zz', node_key: 'cost', row_identity: 'h:zz', col: null }),
    )
    const target = await resolveConsolEvidenceTarget({
      projectId: 'p1', year: 2025, sheetType: 'worksheet', nodeKey: 'cost', rowFields: { company_code: 'C1' },
    })
    expect(target.wpId).toBeNull()
    expect(target.shellExists).toBe(false)
  })

  it('缺项目或年度直接抛错，不发请求', async () => {
    await expect(
      resolveConsolEvidenceTarget({ projectId: '', year: 2025, sheetType: 'trial', nodeKey: 'consol_trial' }),
    ).rejects.toThrow()
    expect(mockPost).not.toHaveBeenCalled()
  })
})

describe('ensureConsolShell', () => {
  it('幂等建壳并返回 working_paper_id', async () => {
    mockPost.mockResolvedValue(envelope({ working_paper_id: 'wp-ensured', version: 1, created: true }))
    const wpId = await ensureConsolShell('p1', 2025)
    expect(wpId).toBe('wp-ensured')
    expect(mockPost).toHaveBeenCalledWith(
      '/api/consolidation/p1/2025/workpaper-shell/ensure',
      {},
      expect.objectContaining({ _silent: true }),
    )
  })

  it('未返回 working_paper_id 抛错', async () => {
    mockPost.mockResolvedValue(envelope({}))
    await expect(ensureConsolShell('p1', 2025)).rejects.toThrow()
  })
})

describe('appendConsolEvidence', () => {
  it('带 sheet_name + cell_ref（不走 evidence_sheet/cell）', () => {
    const form = new FormData()
    appendConsolEvidence(form, 'consol_trial', 'node:consol_trial/row:id%3A1001')
    expect(form.get('sheet_name')).toBe('consol_trial')
    expect(form.get('cell_ref')).toBe('node:consol_trial/row:id%3A1001')
    // 合并身份已无漂移，不用底稿 OCR 端点的 evidence_sheet/evidence_cell 字段
    expect(form.has('evidence_sheet')).toBe(false)
    expect(form.has('evidence_cell')).toBe(false)
  })
})
