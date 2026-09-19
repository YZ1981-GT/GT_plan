/**
 * useK1WriteoffImportExport — K1-9 客户端 Excel 导入导出
 *
 * 双区段单表：类别=转回|核销，与致同 K1-9 模板列对齐。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import type { K1ReversalRow, K1WriteoffRow } from './useK1WriteoffCheck'

const REVERSAL_COLUMNS: ExcelColumn[] = [
  { key: 'section', header: '类别', note: '填「转回」或「核销」' },
  { key: 'unit', header: '单位名称' },
  { key: 'reason', header: '转回原因/核销原因' },
  { key: 'method', header: '收回方式', note: '转回行填写' },
  { key: 'basis', header: '原确定坏账准备的依据', note: '转回行填写' },
  { key: 'amount', header: '收回或转回金额/核销金额' },
  { key: 'accumProvision', header: '收回/转回前累计已计提', note: '转回行填写' },
  { key: 'nature', header: '其他应收款的性质', note: '核销行填写' },
  { key: 'procedure', header: '履行的核销程序', note: '核销行填写' },
  { key: 'relatedParty', header: '是否关联方往来', note: '核销行填 是/否' },
  { key: 'isReasonable', header: '合理性', note: '合理/不合理/待核实' },
  { key: 'analysis', header: '合理性分析' },
  { key: 'indexNo', header: '索引号' },
]

const SECTION_MAP: Record<string, 'reversal' | 'writeoff'> = {
  转回: 'reversal',
  收回: 'reversal',
  核销: 'writeoff',
  reversal: 'reversal',
  writeoff: 'writeoff',
}

function rowsToExport(reversalRows: K1ReversalRow[], writeoffRows: K1WriteoffRow[]): Record<string, any>[] {
  const out: Record<string, any>[] = []
  for (const r of reversalRows) {
    out.push({
      section: '转回',
      unit: r.unit,
      reason: r.reason,
      method: r.method,
      basis: r.basis,
      amount: r.amount,
      accumProvision: r.accumProvision,
      nature: '',
      procedure: '',
      relatedParty: '',
      isReasonable: r.isReasonable,
      analysis: r.analysis,
      indexNo: r.indexNo,
    })
  }
  for (const r of writeoffRows) {
    out.push({
      section: '核销',
      unit: r.unit,
      reason: r.reason,
      method: '',
      basis: '',
      amount: r.amount,
      accumProvision: '',
      nature: r.nature,
      procedure: r.procedure,
      relatedParty: r.relatedParty,
      isReasonable: r.isReasonable,
      analysis: r.analysis,
      indexNo: r.indexNo,
    })
  }
  return out
}

function parseImportedRows(rows: Record<string, any>[]): {
  reversal: K1ReversalRow[]
  writeoff: K1WriteoffRow[]
} {
  const reversal: K1ReversalRow[] = []
  const writeoff: K1WriteoffRow[] = []
  const newId = () => `k1wo-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`

  for (const r of rows) {
    const sectionLabel = String(r.section ?? r.类别 ?? '').trim()
    const section = SECTION_MAP[sectionLabel]
    if (!section) continue
    const unit = String(r.unit ?? r.单位名称 ?? '').trim()
    const amount = Number(r.amount ?? r['收回或转回金额/核销金额'] ?? 0) || 0
    if (!unit && amount <= 0) continue

    if (section === 'reversal') {
      reversal.push({
        id: newId(),
        unit,
        reason: String(r.reason ?? r['转回原因/核销原因'] ?? ''),
        method: String(r.method ?? r.收回方式 ?? ''),
        basis: String(r.basis ?? r['原确定坏账准备的依据'] ?? ''),
        amount,
        accumProvision: Number(r.accumProvision ?? r['收回/转回前累计已计提'] ?? 0) || 0,
        isReasonable: String(r.isReasonable ?? r.合理性 ?? ''),
        analysis: String(r.analysis ?? r.合理性分析 ?? ''),
        indexNo: String(r.indexNo ?? r.索引号 ?? ''),
      })
    } else {
      writeoff.push({
        id: newId(),
        unit,
        nature: String(r.nature ?? r.其他应收款的性质 ?? ''),
        amount,
        reason: String(r.reason ?? r['转回原因/核销原因'] ?? ''),
        procedure: String(r.procedure ?? r.履行的核销程序 ?? ''),
        relatedParty: String(r.relatedParty ?? r.是否关联方往来 ?? ''),
        isReasonable: String(r.isReasonable ?? r.合理性 ?? ''),
        analysis: String(r.analysis ?? r.合理性分析 ?? ''),
        indexNo: String(r.indexNo ?? r.索引号 ?? ''),
      })
    }
  }
  return { reversal, writeoff }
}

export interface UseK1WriteoffImportExportOpts {
  getRows: () => { reversal: K1ReversalRow[]; writeoff: K1WriteoffRow[] }
  setRows: (reversal: K1ReversalRow[], writeoff: K1WriteoffRow[]) => void
}

export function useK1WriteoffImportExport(_opts: UseK1WriteoffImportExportOpts) {
  const { exportTemplate, exportData, parseFile } = useExcelIO()
  const importing = ref(false)

  async function onExportTemplate(): Promise<void> {
    await exportTemplate({
      columns: REVERSAL_COLUMNS,
      sheetName: 'K1-9',
      fileName: 'K1-9-转回核销检查-模板.xlsx',
      includeInstructions: true,
      instructionTitle: 'K1-9 坏账准备转回（收回）、核销检查表',
      instructionRows: [
        ['1. 「类别」填「转回」或「核销」，分别对应两个检查区段。'],
        ['2. 转回行须填收回方式、原计提依据、收回/转回前累计已计提。'],
        ['3. 核销行须填款项性质、核销程序、是否关联方往来。'],
        ['4. 导入将覆盖本表现有明细行（审计说明/结论保留）。'],
      ],
      exampleRows: [
        ['转回', '示例单位A', '债务人还款', '银行转账', '账龄超期全额计提', 50000, 50000, '', '', '', '合理', '期后收回银行回单', 'K1-12'],
        ['核销', '示例单位B', '破产无法收回', '', '', 30000, '', '往来款', '经管理层审批', '否', '合理', '已取得破产裁定', 'K1-12'],
      ],
    })
  }

  async function onExportData(): Promise<void> {
    const { reversal, writeoff } = _opts.getRows()
    await exportData({
      data: rowsToExport(reversal, writeoff),
      columns: REVERSAL_COLUMNS,
      sheetName: 'K1-9',
      fileName: 'K1-9-转回核销检查-数据.xlsx',
      numericColumnKeys: ['amount', 'accumProvision'],
    })
  }

  async function onImportFile(file: File): Promise<boolean> {
    importing.value = true
    try {
      const { rows } = await parseFile<Record<string, any>>(file, { skipRows: 1 })
      const parsed = parseImportedRows(rows)
      if (parsed.reversal.length === 0 && parsed.writeoff.length === 0) {
        ElMessage.warning('未解析到有效数据行，请检查「类别」列是否为转回/核销')
        return false
      }
      _opts.setRows(parsed.reversal, parsed.writeoff)
      ElMessage.success(`已导入 ${parsed.reversal.length} 行转回、${parsed.writeoff.length} 行核销`)
      return true
    } catch {
      ElMessage.error('导入失败，请检查文件格式')
      return false
    } finally {
      importing.value = false
    }
  }

  return { importing, onExportTemplate, onExportData, onImportFile }
}
