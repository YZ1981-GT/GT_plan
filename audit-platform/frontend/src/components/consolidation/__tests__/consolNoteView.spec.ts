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
  sectionIdsWithFormulas,
  toEditRows,
} from '../composables/consolNoteView'
import type { ConsolNoteBreakdown, ConsolNoteFillResult } from '@/services/consolidationApi'

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
