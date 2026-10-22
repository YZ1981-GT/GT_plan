/**
 * 合并附注差额 / 按公式填入（任务 12.2 / 需求 6）：纯逻辑 + 生产接线源码守卫。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  clearManual,
  fillDetailRows,
  fillSummaryText,
  findBreakdownCell,
  fromEditRows,
  isManual,
  markManual,
  noteBreakdownCheck,
  noteBreakdownCheckText,
  noteBreakdownRows,
  notePayload,
  parseManualCells,
  cellAggregateSummary,
  reaggregateSummary,
  sectionIdsWithFormulas,
  toEditRows,
} from '../composables/consolNoteView'
import type {
  ConsolNoteBreakdown,
  ConsolNoteFillResult,
  ConsolNoteReaggregateAction,
  ConsolNoteReaggregateNode,
} from '@/services/consolidationApi'

const HEADERS = ['项目', '期末余额', '期初余额']

function fillResult(extra: Partial<ConsolNoteFillResult> = {}): ConsolNoteFillResult {
  return {
    project_id: 'p', year: 2025, section_id: '五-1-1', template_type: 'soe',
    filled: [{ row_index: 1, col_index: 1, target_row: 1, value: '20.00' }],
    kept_manual: [{ row_index: 0, col_index: 1, target_row: 0, current: '手填', formula_value: '10.00' }],
    blank: [{ row_index: 2, col_index: 1, target_row: 2, reason: '取不到数' }],
    is_stale: false,
    data: { headers: HEADERS, rows: [['库存现金', '手填', ''], ['银行存款', '20.00', ''], ['其他', '', '']] },
    ...extra,
  }
}
function breakdown(): ConsolNoteBreakdown {
  return {
    project_id: 'p', year: 2025, template_type: 'soe', section_id: '五-1-1',
    title: '货币资金', parent_section: '五、1', node_key: 'G:consol', node_label: 'G（合并）',
    columns: [
      { key: 'individual', label: '个别数汇总' }, { key: 'adjustment', label: '调整' },
      { key: 'elimination', label: '抵销' }, { key: 'consolidated', label: '合并数' },
    ],
    children: [
      { node_key: 'G:parent', label: '母公司', kind: 'data' },
      { node_key: 'G:consol_elim', label: '合并差额', kind: 'elim' },
    ],
    cells: [
      {
        row_index: 0, col_index: 1, formula: "TB('1001','期末余额')", source: 'seed',
        individual: '100.00', adjustment: '0.00', elim_equity: '0.00', elim_trade: '-10.00',
        elimination: '-10.00', consolidated: '90.00', linear: true, note: null,
        children: { 'G:parent': '100.00', 'G:consol_elim': '-10.00' }, row_label: '库存现金', col_name: '期末余额',
      },
      {
        row_index: 1, col_index: 1, formula: "MAX(TB('1001','期末余额'),0)", source: 'manual',
        individual: '8.00', adjustment: '0.00', elim_equity: '0.00', elim_trade: '0.00',
        elimination: '0.00', consolidated: '8.00', linear: false, note: '公式非线性',
        children: { 'G:parent': null, 'G:consol_elim': null }, row_label: '银行存款', col_name: '期末余额',
      },
      {
        row_index: 2, col_index: 1, formula: "TB('9999','期末余额')", source: 'manual',
        individual: null, adjustment: null, elim_equity: null, elim_trade: null,
        elimination: null, consolidated: null, linear: true, note: '科目不存在',
        children: { 'G:parent': null, 'G:consol_elim': null }, row_label: '其他', col_name: '期末余额',
      },
    ],
  }
}

describe('合并附注手工单元格', () => {
  it('兼容三种 manual_cells 形态并忽略无效项', () => {
    const got = parseManualCells([{ row: 0, col: 1 }, [1, 2], '2:1', '坏', { row: -1, col: 2 }])
    expect([...got.get(0)!]).toEqual([1])
    expect([...got.get(1)!]).toEqual([2])
    expect([...got.get(2)!]).toEqual([1])
  })

  it('手工标记挂在行对象上：插删行后按当前行号序列化，且可恢复公式', () => {
    const rows = toEditRows(HEADERS, [['A', '1', ''], ['B', '2', '']], [{ row: 1, col: 1 }])
    expect(rows).toHaveLength(5)
    expect(isManual(rows[1], 1)).toBe(true)
    rows.splice(0, 1)
    markManual(rows[0], 2)
    expect(fromEditRows(HEADERS, rows).manual_cells).toEqual([{ row: 0, col: 1 }, { row: 0, col: 2 }])
    clearManual(rows[0], 1)
    expect(fromEditRows(HEADERS, rows).manual_cells).toEqual([{ row: 0, col: 2 }])
  })

  it('保存体保留未知元数据，只替换 headers/rows/manual_cells，不再整包丢手工保护', () => {
    const rows = toEditRows(HEADERS, [['A', '手填', '']], [{ row: 0, col: 1 }])
    const payload = notePayload({ source: 'legacy', nested: { x: 1 } }, HEADERS, rows)
    expect(payload).toMatchObject({
      source: 'legacy', nested: { x: 1 }, headers: HEADERS,
      manual_cells: [{ row: 0, col: 1 }],
    })
    expect((payload.rows as string[][])[0]).toEqual(['A', '手填', ''])
  })
})

describe('按公式填入结果', () => {
  it('显式汇总填入、手工保留与取不到数，并列出当前值/公式值/原因', () => {
    const result = fillResult()
    expect(fillSummaryText(result)).toBe('已按公式填入 1 格；1 格手工填写已保留；1 格取不到数未填')
    expect(fillDetailRows(result)).toEqual([
      expect.objectContaining({ kind: 'kept', position: '库存现金 · 期末余额', current: '手填', formula_value: '10.00' }),
      expect.objectContaining({ kind: 'blank', position: '其他 · 期末余额', reason: '取不到数' }),
    ])
  })

  it('全部填入时只显示填入数；批量操作只取真正有公式的章节', () => {
    expect(fillSummaryText(fillResult({ kept_manual: [], blank: [] }))).toBe('已按公式填入 1 格')
    expect(sectionIdsWithFormulas({ sections: [
      { section_id: 'A', title: null, parent_section: null, formulas: [{} as any] },
      { section_id: 'B', title: null, parent_section: null, formulas: [] },
    ] })).toEqual(['A'])
  })
})

describe('附注差额', () => {
  it('给出四度量与子节点贡献；线性格精确核对，非线性与留空分开计数', () => {
    const bd = breakdown()
    expect(noteBreakdownRows(bd)[0]).toMatchObject({
      position: '库存现金 · 期末余额', individual: '100.00', adjustment: '0.00',
      elimination: '-10.00', consolidated: '90.00',
    })
    const check = noteBreakdownCheck(bd)
    expect(check).toEqual({ checked: 1, mismatched: [], nonlinear: 1, blank: 1 })
    expect(noteBreakdownCheckText(check)).toContain('1 格各下级贡献之和 = 合并数')
    bd.cells[0].children['G:consol_elim'] = '-9.99'
    expect(noteBreakdownCheck(bd).mismatched).toEqual(['库存现金 · 期末余额'])
  })

  it('编辑格按模板同号同名优先，插行后按唯一项目名定位；重名时不猜', () => {
    const cells = breakdown().cells
    expect(findBreakdownCell(cells, '库存现金', 0, 1)?.row_index).toBe(0)
    expect(findBreakdownCell(cells, '库存现金', 4, 1)?.row_index).toBe(0)
    expect(findBreakdownCell(cells, '库存现金', 4, 0)).toBeNull()
    const dup = [...cells, { ...cells[0], row_index: 5 }]
    expect(findBreakdownCell(dup, '库存现金', 4, 1)).toBeNull()
  })
})

describe('重新汇总完成提示（节点子树）', () => {
  const node = (node_key: string, action: ConsolNoteReaggregateAction, written: number): ConsolNoteReaggregateNode => ({
    node_key, kind: action === 'pull' ? 'data' : action, action, label: node_key, written, skipped: 0, failed: 0, reasons: [],
  })
  const persisted = { section_id: '五-1-1', node_key: 'G:consol', action: 'aggregate' as const, status: 'persisted' as const, reason: null }

  it('按节点汇报拉数 / 差额 / 汇总分布；全部写上且无待确认、无出错 ⇒ ok', () => {
    const summary = reaggregateSummary({
      nodes: [node('G:consol', 'aggregate', 1), node('G:consol_elim', 'elim', 1), node('A:subsidiary', 'pull', 1),
        node('B:subsidiary', 'pull', 1), node('G:parent', 'pull', 0)],
      results: [persisted], pending_entities: [], failures: [],
    })
    expect(summary).toEqual({ ok: true, text: '重新汇总完成：写入 4 个节点（拉数 2 / 差额 1 / 汇总 1）' })
  })

  it('所选节点没写上、待确认映射、出错都写进提示且不算 ok', () => {
    const summary = reaggregateSummary({
      nodes: [node('A:subsidiary', 'pull', 1)],
      results: [{ ...persisted, status: 'skipped', reason: '下级企业都没有可汇总的单体附注数据' }],
      pending_entities: ['乙', '丙', '丁', '戊'].map((label) => ({
        node_key: `${label}:subsidiary`, label, section_count: 1, sections: ['五-1-1'], reasons: ['未确认映射'] })),
      failures: [{ section_id: '五-1-1', node_key: 'G:consol_elim', status: 'failed', error: '无法计算差额：当前合并范围尚未由用户确认' }],
    })
    expect(summary.ok).toBe(false)
    expect(summary.text).toBe('重新汇总完成：写入 1 个节点（拉数 1 / 差额 0 / 汇总 0）；本节点未更新：下级企业都没有可汇总的单体附注数据；'
      + '4 家企业待在「📋 明细映射」确认映射（乙、丙、丁 等）；1 处出错：无法计算差额：当前合并范围尚未由用户确认')
  })

  it('旧响应没有逐节点摘要时按章节计数', () => {
    expect(reaggregateSummary({ sections_updated: 3 })).toEqual({ ok: true, text: '重新汇总完成：更新 3 个章节' })
    expect(reaggregateSummary(null)).toEqual({ ok: true, text: '重新汇总完成：更新 0 个章节' })
  })
})

describe('单元格「Σ 汇总」提示（只取下级合并附注，R6.5）', () => {
  /** 打标记的格式化：断言合计确实经调用方传入的金额格式化（组件里是 fmtAmt） */
  const fmt = (v: number) => `<${v}>`

  it('全部下级都有数 ⇒ 成功', () => {
    expect(cellAggregateSummary({ value: 150, count: 2, empty_count: 0, missing_children: [] }, fmt))
      .toEqual({ level: 'success', text: '已汇总 2 家下级，合计：<150>' })
  })

  it('有下级没有附注数据 ⇒ 告警并点名，提示先做明细映射 / 重新汇总', () => {
    const s = cellAggregateSummary({
      value: 100, count: 1, empty_count: 1,
      missing_children: [{ node_key: 'C:subsidiary', name: '子公司C', reason: '没有附注数据' }],
    }, fmt)
    expect(s.level).toBe('warning')
    expect(s.text).toBe('已汇总 1 家下级，合计：<100>；1 家下级这一格没有数；'
      + '1 家下级没有附注数据，未计入（子公司C；请先对其执行「📋 明细映射」或「🔄 重新汇总」）')
  })

  it('一个数都没有：没有附注 ⇒ 告警；只是这一格为空 ⇒ 普通提示；错误信封 ⇒ 汇总失败', () => {
    const missing = cellAggregateSummary({ value: null, count: 0, missing_children: [{ node_key: 'A:parent' }] }, fmt)
    expect(missing).toEqual({ level: 'warning', text: '没有可汇总的数：1 家下级没有附注数据，未计入（A:parent；请先对其执行「📋 明细映射」或「🔄 重新汇总」）' })
    expect(cellAggregateSummary({ value: null, count: 0, empty_count: 2, missing_children: [] }, fmt).level).toBe('info')
    expect(cellAggregateSummary({ detail: '合并附注模板（soe）中没有表格 x' }, fmt))
      .toEqual({ level: 'warning', text: '汇总失败：合并附注模板（soe）中没有表格 x' })
  })
})

describe('ConsolNoteTab 生产接线守卫', () => {
  const component = fs.readFileSync(path.resolve(__dirname, '../ConsolNoteTab.vue'), 'utf-8')
  const index = fs.readFileSync(path.resolve(__dirname, '../../../views/ConsolidationIndex.vue'), 'utf-8')
  const api = fs.readFileSync(path.resolve(__dirname, '../../../services/consolidationApi.ts'), 'utf-8')

  it('16 处错误的未插值地址归零，所有章节请求走 P_cn 路径函数', () => {
    expect(component.match(/`P_[A-Za-z_]+\./g) || []).toEqual([])
    for (const call of ['P_cn.list(', 'P_cn.detail(', 'P_cn.data(', 'P_cn.aggregate(', 'P_cn.auditAll(', 'P_cn.audit(']) {
      expect(component, `缺路径函数 ${call}`).toContain(call)
    }
  })

  it('重新汇总走真实 consolidation 路由，回载事件传模板准则而非企业代码', () => {
    expect(component).toContain('P_consol.notes.reaggregate(')
    expect(component).not.toContain('/api/disclosure-notes/${props.projectId}/${props.year}/reaggregate')
    const body = component.slice(component.indexOf('async function handleReaggregate'), component.indexOf('function addNoteRow'))
    expect(body).toContain('standard: props.standard')
    expect(body).not.toContain('standard: props.currentEntity')
    // 完成提示按节点汇报（不再只报「更新 N 个章节」），按钮说明是子树拉数 + 汇总而不是「按公式重算」
    expect(body).toContain('reaggregateSummary(result)')
    expect(component).toContain('本节点下各企业按已确认映射从单体附注重新拉数，差额节点按抵销分录重算，再自下而上汇总到本节点')
    expect(component).not.toContain('按公式重算本节点合并附注')
    expect(component).toContain("lastWrite === 'subtree_aggregate'")
  })

  it('单元格汇总两种模式都走同一提示（没有附注的下级点名）', () => {
    const body = component.slice(component.indexOf('async function executeAggregate'), component.indexOf('// ─── 附注数据操作'))
    expect(body.match(/applyCellAggregate\(sec, c, data\)/g) || []).toHaveLength(2)
    expect(component).toContain('cellAggregateSummary(result, fmtAmt)')
    expect(body).not.toContain('暂无下级数据可汇总')
  })

  it('页面按钮接入新 fill/breakdown API；编辑即标手工；保存保留原 data', () => {
    expect(component).toContain('data-testid="consol-note-fill"')
    expect(component).toContain('data-testid="consol-note-breakdown"')
    expect(component).toContain('fillConsolNoteByFormula(')
    expect(component).toContain('getConsolNoteBreakdown(')
    expect(component).toContain('@input="onNoteCellInput(row, hi)"')
    expect(component).toContain('notePayload(sec.savedData, sec.headers, sec.editRows)')
    expect(component).toContain('toEditRows(headers, rows, savedContent.manual_cells)')
    expect(component).not.toContain('P_cn.applyFormulas(')
    expect(component).not.toContain('P_cn.refresh(')
  })

  it('合并页按企业树年度传给附注，并让顶部“查看”调用新附注差额而非旧汇总估算', () => {
    expect(index).toContain(':year="effectiveConsolYear()"')
    expect(index).toContain("if (activeTab.value === 'consol_note')")
    expect(index).toContain('noteTab.openNoteBreakdownForSelection()')
    expect(index).toContain('<ConsolReportBreakdownView')
  })

  it('400/423 由附注页显示后端具体原因，服务层抑制全局重复提示', () => {
    expect(component).toContain('status === 400 || status === 423')
    expect(component).toContain('ElMessage.warning(`${action}：${detail}`)')
    const fill = api.slice(api.indexOf('export async function fillConsolNoteByFormula'))
    expect(fill).toContain('{ _silent: true } as any')
  })
})
