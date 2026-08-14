/**
 * useB23ImportExport — B23 控制矩阵/穿行/控制测试/缺陷 导入导出（ExcelJS）
 *
 * Spec: .kiro/specs/b23-business-control-rework/ | Task: 2.2
 *
 * - 按 Business_Cycle 分 sheet 导出
 * - 导入校验列结构，匹配回写，不匹配列跳过并提示
 * - rows↔model 纯函数拆出供往返 PBT（Property P2）
 */
import { ElMessage } from 'element-plus'
import { createExcelJsWorkbook, loadExcelJsWorkbook } from '@/composables/useExcelIO'
import { B23_CYCLES } from './b23CycleConfig'
import type { B23ControlPoint } from './useB23ProcessControl'

// ─── 控制矩阵列定义（导出表头 ≡ 导入解析顺序） ──────────────────────────────

export const CONTROL_MATRIX_HEADERS = [
  '子流程', '控制编号', '控制名称', '详细控制描述', '受影响的交易/账户/余额/披露',
  '认定', 'WCGW', 'WCGW详细记录', '控制属性', '控制频率', 'IT应用名称',
  '预防性/检查性', '控制设计是否有效', '控制类型一级', '控制类型二级',
  '执行人', '执行人名称或服务机构', '是否有文件记录', '是否为关键控制点', '是否执行控制测试',
] as const

// ─── 纯函数：model ↔ row（供往返 PBT） ──────────────────────────────────────

export function controlPointToRow(cp: B23ControlPoint): string[] {
  return [
    cp.subProcess, cp.ctrlNo, cp.ctrlName, cp.ctrlDesc, cp.affectedItems,
    cp.assertion.join('、'), cp.wcgwRef, cp.wcgwDetail, cp.ctrlAttr, cp.frequency ?? '', cp.itApp,
    cp.preventDetect ?? '', cp.designEffective ?? '', cp.ctrlTypeL1 ?? '', cp.ctrlTypeL2 ?? '',
    cp.executor, cp.executorOrg, cp.hasDoc ?? '', cp.isKeyControl ?? '', cp.doControlTest ?? '',
  ]
}

function toYesNo(v: string): '是' | '否' | null {
  return v === '是' ? '是' : v === '否' ? '否' : null
}

export function rowToControlPoint(row: (string | null)[], index: number): B23ControlPoint {
  const s = (i: number) => (row[i] ?? '').toString().trim()
  const orNull = (i: number) => { const v = s(i); return v === '' ? null : v }
  return {
    index,
    subProcess: s(0), ctrlNo: s(1), ctrlName: s(2), ctrlDesc: s(3), affectedItems: s(4),
    assertion: s(5) ? s(5).split(/[、,，]/).filter(Boolean) : [],
    wcgwRef: s(6), wcgwDetail: s(7), ctrlAttr: s(8),
    frequency: orNull(9) as B23ControlPoint['frequency'],
    itApp: s(10),
    preventDetect: (s(11) === '预防性' || s(11) === '检查性') ? (s(11) as '预防性' | '检查性') : null,
    designEffective: toYesNo(s(12)),
    ctrlTypeL1: orNull(13), ctrlTypeL2: orNull(14),
    executor: s(15), executorOrg: s(16),
    hasDoc: toYesNo(s(17)), isKeyControl: toYesNo(s(18)), doControlTest: toYesNo(s(19)),
  }
}

/** 表头是否匹配控制矩阵模板（用于导入校验） */
export function isControlMatrixHeader(row: (string | null)[]): boolean {
  if (!row || row.length < CONTROL_MATRIX_HEADERS.length) return false
  return CONTROL_MATRIX_HEADERS.every((h, i) => (row[i] ?? '').toString().trim() === h)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface B23ImportExportDeps {
  /** 取某循环控制点 */
  getControlPoints: (code: string) => B23ControlPoint[]
  /** 取某循环适用性 */
  getApplicability: (code: string) => boolean
  /** 批量写某循环控制点字段（导入回写） */
  applyImportedControlPoints: (code: string, points: B23ControlPoint[], mode: 'overwrite' | 'skip') => void
}

export function useB23ImportExport(deps: B23ImportExportDeps) {
  async function exportData(clientName = 'B23'): Promise<void> {
    try {
      // 走 useExcelIO 单一入口（B5 批）。仍是 ExcelJS 引擎，建表逻辑逐行不变。
      const { wb } = await createExcelJsWorkbook()
      for (const def of B23_CYCLES) {
        if (!deps.getApplicability(def.code)) continue
        const ws = wb.addWorksheet(`${def.wpCode} ${def.name}`.slice(0, 31))
        ws.addRow([...CONTROL_MATRIX_HEADERS])
        for (const cp of deps.getControlPoints(def.code)) ws.addRow(controlPointToRow(cp))
      }
      if (wb.worksheets.length === 0) { ElMessage.warning('无适用循环可导出'); return }
      await downloadWorkbook(wb, `${clientName}_业务层面控制_${new Date().toISOString().slice(0, 10)}.xlsx`)
    } catch (e) {
      ElMessage.error('导出失败')
    }
  }

  async function exportTemplate(): Promise<void> {
    try {
      const { wb } = await createExcelJsWorkbook()
      for (const def of B23_CYCLES) {
        const ws = wb.addWorksheet(`${def.wpCode} ${def.name}`.slice(0, 31))
        ws.addRow([...CONTROL_MATRIX_HEADERS])
      }
      await downloadWorkbook(wb, `B23_业务层面控制_空白模板.xlsx`)
    } catch { ElMessage.error('导出模板失败') }
  }

  async function importData(file: File, mode: 'overwrite' | 'skip' = 'overwrite'): Promise<void> {
    try {
      const wb = await loadExcelJsWorkbook(file)
      let imported = 0
      let skippedSheets = 0
      for (const def of B23_CYCLES) {
        // 按 sheet 名前缀匹配循环
        const ws = wb.worksheets.find((w) => w.name.startsWith(def.wpCode))
        if (!ws) continue
        const headerRow: (string | null)[] = []
        ws.getRow(1).eachCell({ includeEmpty: true }, (cell) => headerRow.push(cell.value == null ? '' : String(cell.value)))
        if (!isControlMatrixHeader(headerRow)) { skippedSheets++; continue }
        const points: B23ControlPoint[] = []
        for (let r = 2; r <= ws.rowCount; r++) {
          const row: (string | null)[] = []
          ws.getRow(r).eachCell({ includeEmpty: true }, (cell) => row.push(cell.value == null ? '' : String(cell.value)))
          if (row.every((c) => !c || !c.toString().trim())) continue
          points.push(rowToControlPoint(row, points.length + 1))
        }
        if (points.length > 0) { deps.applyImportedControlPoints(def.code, points, mode); imported++ }
      }
      if (imported === 0 && skippedSheets > 0) {
        ElMessage.error('导入文件列结构不符合控制矩阵模板，已拒绝导入')
      } else {
        ElMessage.success(`导入完成：${imported} 个循环${skippedSheets ? `，${skippedSheets} 个 sheet 因格式不符跳过` : ''}`)
      }
    } catch {
      ElMessage.error('导入失败')
    }
  }

  return { exportData, exportTemplate, importData }
}

async function downloadWorkbook(wb: any, filename: string): Promise<void> {
  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default useB23ImportExport
