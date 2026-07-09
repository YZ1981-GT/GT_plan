/**
 * useI2Detail — I2-2 开发支出明细表 composable
 *
 * 61列宽表拆分为4区段Tab：
 *   Segment0 基础 (10 cols): 项目名/编号/立项日/阶段/负责人/起止日期/预算/进度/资本化起点/状态
 *   Segment1 本期投入 (15 cols): 材料/人工/折旧/摊销/其他/合计 × (本期/累计) + 投入验证
 *   Segment2 资本化 (12 cols): 资本化起点日期/金额期初/本期增加/本期减少/期末/转入I1/转入日期/摊销/减值/净值/完工比例/验收日
 *   Segment3 期末汇总 (10 cols): 审定期末/调整后余额/同比变动/预期值/差异/超标标记/结论/备注
 *
 * 核心功能：
 * - Tab切换行同步（activeRowIndex跨4区段共享）
 * - 公式自动计算：
 *   · 投入合计(本期) = 材料+人工+折旧+摊销+其他
 *   · 投入合计(累计) = 材料累计+人工累计+折旧累计+摊销累计+其他累计
 *   · 资本化期末 = 期初 + 增加 - 减少 (calcAssetEndBalance)
 *   · 净值 = 期末 - 摊销 - 减值 (calcNetValue)
 *   · 差异 = 审定期末 - 预期值
 * - 合计行（不可编辑）：每列numeric SUM (calcSubtotal)
 * - 联动审定表I2-1（交叉验证）
 * - 动态行CRUD（ElMessageBox.prompt输入项目名称）
 * - 导入导出支持
 * - 持久化：rows JSON → checklist_responses item_id "I2-2-rows"
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.4
 * Requirements: 3.1-3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistItem } from './useI2FormData'
import {
  calcAssetEndBalance,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcVarianceFromExpected,
} from './useI2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I2-2 明细行完整结构（61列拆分到4区段） */
export interface I2DetailRow {
  rowId: string

  // ── Segment0 基础 (10 cols) ──
  projectName: string              // 项目名称
  projectCode: string              // 项目编号
  approvalDate: string             // 立项日期（YYYY-MM-DD）
  phase: string                    // 阶段（研究/开发/已资本化）
  manager: string                  // 负责人
  startDate: string                // 起始日期
  endDate: string                  // 终止日期
  budget: number                   // 预算金额
  progress: number                 // 进度（0~100%）
  capitalizationStart: string      // 资本化起点日期
  status: string                   // 状态（进行中/已完成/已暂停/已终止）

  // ── Segment1 本期投入 (15 cols) ──
  materialCurrent: number          // 材料投入-本期
  materialAccum: number            // 材料投入-累计
  laborCurrent: number             // 人工投入-本期
  laborAccum: number               // 人工投入-累计
  depreciationCurrent: number      // 折旧投入-本期
  depreciationAccum: number        // 折旧投入-累计
  amortizationCurrent: number      // 摊销投入-本期
  amortizationAccum: number        // 摊销投入-累计
  otherCurrent: number             // 其他投入-本期
  otherAccum: number               // 其他投入-累计
  totalCurrent: number             // 投入合计-本期（公式）
  totalAccum: number               // 投入合计-累计（公式）
  // 3 extra for alignment: investmentRemark + validationFlag + investmentSource
  investmentRemark: string         // 投入说明
  validationFlag: string           // 验证标记（✓/✗）
  investmentSource: string         // 投入来源

  // ── Segment2 资本化 (12 cols) ──
  capStartDate: string             // 资本化起点日期（联动I2-6）
  capBeginAmount: number           // 资本化金额期初
  capIncrease: number              // 本期增加
  capDecrease: number              // 本期减少
  capEndAmount: number             // 期末（公式：期初+增加-减少）
  transferToI1: number             // 转入I1金额
  transferDate: string             // 转入日期
  capAmortization: number          // 摊销
  capImpairment: number            // 减值
  capNetValue: number              // 净值（公式：期末-摊销-减值）
  completionRate: number           // 完工比例（0~100%）
  acceptanceDate: string           // 验收日

  // ── Segment3 期末汇总 (10 cols) ──
  auditedEnd: number               // 审定期末
  adjustedBalance: number          // 调整后余额
  yoyChange: number | null         // 同比变动率（公式）
  expectedValue: number            // 预期值
  variance: number                 // 差异（公式：审定期末-预期值）
  exceedFlag: string               // 超标标记（✓/空）
  conclusion: string               // 结论
  priorEnd: number                 // 上期期末（计算同比用）
  remark: string                   // 备注
  adjReference: string             // 审定表引用编号
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I2-2-rows'

const PHASE_OPTIONS = ['研究', '开发', '已资本化']
const STATUS_OPTIONS = ['进行中', '已完成', '已暂停', '已终止']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Detail(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  /** 审定表期末合计（用于交叉验证） */
  adjEndSubtotal?: Ref<number>
}) {
  const { allResponses, saveResponses } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  /** 明细行数据 */
  const rows = ref<I2DetailRow[]>([])

  /** 当前激活的区段索引 0-3 */
  const activeSegment = ref<number>(0)

  /** 当前选中行索引（跨Tab同步） */
  const activeRowIndex = ref<number>(-1)

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(_normalizeRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _normalizeRow(raw: any): I2DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      // Segment0 基础
      projectName: raw.projectName ?? '',
      projectCode: raw.projectCode ?? '',
      approvalDate: raw.approvalDate ?? '',
      phase: raw.phase ?? '',
      manager: raw.manager ?? '',
      startDate: raw.startDate ?? '',
      endDate: raw.endDate ?? '',
      budget: Number(raw.budget) || 0,
      progress: Number(raw.progress) || 0,
      capitalizationStart: raw.capitalizationStart ?? '',
      status: raw.status ?? '',
      // Segment1 本期投入
      materialCurrent: Number(raw.materialCurrent) || 0,
      materialAccum: Number(raw.materialAccum) || 0,
      laborCurrent: Number(raw.laborCurrent) || 0,
      laborAccum: Number(raw.laborAccum) || 0,
      depreciationCurrent: Number(raw.depreciationCurrent) || 0,
      depreciationAccum: Number(raw.depreciationAccum) || 0,
      amortizationCurrent: Number(raw.amortizationCurrent) || 0,
      amortizationAccum: Number(raw.amortizationAccum) || 0,
      otherCurrent: Number(raw.otherCurrent) || 0,
      otherAccum: Number(raw.otherAccum) || 0,
      totalCurrent: Number(raw.totalCurrent) || 0,
      totalAccum: Number(raw.totalAccum) || 0,
      investmentRemark: raw.investmentRemark ?? '',
      validationFlag: raw.validationFlag ?? '',
      investmentSource: raw.investmentSource ?? '',
      // Segment2 资本化
      capStartDate: raw.capStartDate ?? '',
      capBeginAmount: Number(raw.capBeginAmount) || 0,
      capIncrease: Number(raw.capIncrease) || 0,
      capDecrease: Number(raw.capDecrease) || 0,
      capEndAmount: Number(raw.capEndAmount) || 0,
      transferToI1: Number(raw.transferToI1) || 0,
      transferDate: raw.transferDate ?? '',
      capAmortization: Number(raw.capAmortization) || 0,
      capImpairment: Number(raw.capImpairment) || 0,
      capNetValue: Number(raw.capNetValue) || 0,
      completionRate: Number(raw.completionRate) || 0,
      acceptanceDate: raw.acceptanceDate ?? '',
      // Segment3 期末汇总
      auditedEnd: Number(raw.auditedEnd) || 0,
      adjustedBalance: Number(raw.adjustedBalance) || 0,
      yoyChange: raw.yoyChange != null ? Number(raw.yoyChange) : null,
      expectedValue: Number(raw.expectedValue) || 0,
      variance: Number(raw.variance) || 0,
      exceedFlag: raw.exceedFlag ?? '',
      priorEnd: Number(raw.priorEnd) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      adjReference: raw.adjReference ?? '',
    }
  }

  // ─── Formula Recalculation ─────────────────────────────────────────────────

  /**
   * 对指定行重算所有公式列：
   * - totalCurrent = 材料+人工+折旧+摊销+其他（本期）
   * - totalAccum = 材料+人工+折旧+摊销+其他（累计）
   * - capEndAmount = capBeginAmount + capIncrease - capDecrease（资产类借方1717）
   * - capNetValue = capEndAmount - capAmortization - capImpairment
   * - yoyChange = (auditedEnd - priorEnd) / priorEnd
   * - variance = auditedEnd - expectedValue
   */
  function _recalcRow(row: I2DetailRow): void {
    // 投入合计-本期
    row.totalCurrent = calcSubtotal([
      row.materialCurrent,
      row.laborCurrent,
      row.depreciationCurrent,
      row.amortizationCurrent,
      row.otherCurrent,
    ])
    // 投入合计-累计
    row.totalAccum = calcSubtotal([
      row.materialAccum,
      row.laborAccum,
      row.depreciationAccum,
      row.amortizationAccum,
      row.otherAccum,
    ])
    // 资本化期末 = 期初 + 增加 - 减少（资产类借方1717）
    row.capEndAmount = calcAssetEndBalance(row.capBeginAmount, row.capIncrease, row.capDecrease)
    // 净值 = 期末 - 摊销 - 减值
    row.capNetValue = calcNetValue(row.capEndAmount, row.capAmortization + row.capImpairment)
    // 同比变动率
    row.yoyChange = calcChangeRate(row.auditedEnd, row.priorEnd)
    // 差异 = 审定期末 - 预期值
    row.variance = calcVarianceFromExpected(row.auditedEnd, row.expectedValue)
  }

  /** 对所有行重算公式 */
  function recalcAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
  }

  // ─── Computed: 合计行（Req 3.2: 合计行）──────────────────────────────────

  /** 合计行：所有numeric列的SUM */
  const totalRow: ComputedRef<I2DetailRow> = computed(() => {
    const r = rows.value
    return {
      rowId: '__total__',
      // Segment0 基础（文本列置空，数值列合计）
      projectName: '合计',
      projectCode: '',
      approvalDate: '',
      phase: '',
      manager: '',
      startDate: '',
      endDate: '',
      budget: calcSubtotal(r.map((x) => x.budget)),
      progress: 0,
      capitalizationStart: '',
      status: '',
      // Segment1 本期投入
      materialCurrent: calcSubtotal(r.map((x) => x.materialCurrent)),
      materialAccum: calcSubtotal(r.map((x) => x.materialAccum)),
      laborCurrent: calcSubtotal(r.map((x) => x.laborCurrent)),
      laborAccum: calcSubtotal(r.map((x) => x.laborAccum)),
      depreciationCurrent: calcSubtotal(r.map((x) => x.depreciationCurrent)),
      depreciationAccum: calcSubtotal(r.map((x) => x.depreciationAccum)),
      amortizationCurrent: calcSubtotal(r.map((x) => x.amortizationCurrent)),
      amortizationAccum: calcSubtotal(r.map((x) => x.amortizationAccum)),
      otherCurrent: calcSubtotal(r.map((x) => x.otherCurrent)),
      otherAccum: calcSubtotal(r.map((x) => x.otherAccum)),
      totalCurrent: calcSubtotal(r.map((x) => x.totalCurrent)),
      totalAccum: calcSubtotal(r.map((x) => x.totalAccum)),
      investmentRemark: '',
      validationFlag: '',
      investmentSource: '',
      // Segment2 资本化
      capStartDate: '',
      capBeginAmount: calcSubtotal(r.map((x) => x.capBeginAmount)),
      capIncrease: calcSubtotal(r.map((x) => x.capIncrease)),
      capDecrease: calcSubtotal(r.map((x) => x.capDecrease)),
      capEndAmount: calcSubtotal(r.map((x) => x.capEndAmount)),
      transferToI1: calcSubtotal(r.map((x) => x.transferToI1)),
      transferDate: '',
      capAmortization: calcSubtotal(r.map((x) => x.capAmortization)),
      capImpairment: calcSubtotal(r.map((x) => x.capImpairment)),
      capNetValue: calcSubtotal(r.map((x) => x.capNetValue)),
      completionRate: 0,
      acceptanceDate: '',
      // Segment3 期末汇总
      auditedEnd: calcSubtotal(r.map((x) => x.auditedEnd)),
      adjustedBalance: calcSubtotal(r.map((x) => x.adjustedBalance)),
      yoyChange: null,
      expectedValue: calcSubtotal(r.map((x) => x.expectedValue)),
      variance: calcSubtotal(r.map((x) => x.variance)),
      exceedFlag: '',
      priorEnd: calcSubtotal(r.map((x) => x.priorEnd)),
      conclusion: '',
      remark: '',
      adjReference: '',
    }
  })

  // ─── Cross Validation: vs I2-1 审定表 ──────────────────────────────────────

  /** 交叉验证：明细表资本化期末合计 vs 审定表期末合计 */
  const crossValidation = computed(() => {
    const adjEnd = params.adjEndSubtotal?.value ?? 0
    const detailEnd = totalRow.value.capEndAmount
    const diff = detailEnd - adjEnd
    return {
      detailEndTotal: detailEnd,
      adjEndTotal: adjEnd,
      difference: diff,
      hasWarning: Math.abs(diff) > 0.01,
    }
  })

  // ─── Segment 切换 + 行同步（Req 3.2）──────────────────────────────────────

  /** 切换区段（0-3），保持行同步 */
  function switchSegment(segIndex: number): void {
    if (segIndex >= 0 && segIndex <= 3) {
      activeSegment.value = segIndex
    }
  }

  /** 设置当前选中行 */
  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  // ─── updateField: 编辑单元格 ───────────────────────────────────────────────

  /**
   * 更新明细表某行某字段值，自动重算公式列。
   * Req 3.4: 联动审定表 — 修改资本化相关字段时重算。
   */
  function updateField(rowIndex: number, field: string, value: any): void {
    const row = rows.value[rowIndex]
    if (!row) return

    // 设置值
    ;(row as any)[field] = value

    // 重算公式列
    _recalcRow(row)
  }

  // ─── addRow: 动态行添加（Req 3.4: 动态行+导入导出）────────────────────────

  /**
   * 添加动态行：传入项目名称后创建。
   * 调用方负责先通过 ElMessageBox.prompt 获取项目名称。
   */
  function addRow(projectName: string): void {
    if (!projectName?.trim()) return

    const newRow: I2DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      // Segment0 基础
      projectName: projectName.trim(),
      projectCode: '',
      approvalDate: '',
      phase: '',
      manager: '',
      startDate: '',
      endDate: '',
      budget: 0,
      progress: 0,
      capitalizationStart: '',
      status: '进行中',
      // Segment1 本期投入
      materialCurrent: 0,
      materialAccum: 0,
      laborCurrent: 0,
      laborAccum: 0,
      depreciationCurrent: 0,
      depreciationAccum: 0,
      amortizationCurrent: 0,
      amortizationAccum: 0,
      otherCurrent: 0,
      otherAccum: 0,
      totalCurrent: 0,
      totalAccum: 0,
      investmentRemark: '',
      validationFlag: '',
      investmentSource: '',
      // Segment2 资本化
      capStartDate: '',
      capBeginAmount: 0,
      capIncrease: 0,
      capDecrease: 0,
      capEndAmount: 0,
      transferToI1: 0,
      transferDate: '',
      capAmortization: 0,
      capImpairment: 0,
      capNetValue: 0,
      completionRate: 0,
      acceptanceDate: '',
      // Segment3 期末汇总
      auditedEnd: 0,
      adjustedBalance: 0,
      yoyChange: null,
      expectedValue: 0,
      variance: 0,
      exceedFlag: '',
      priorEnd: 0,
      conclusion: '',
      remark: '',
      adjReference: '',
    }

    rows.value.push(newRow)
    activeRowIndex.value = rows.value.length - 1
  }

  // ─── removeRow: 删除行 ─────────────────────────────────────────────────────

  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    // 修正 activeRowIndex
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
  }

  // ─── importRows: 批量导入行数据（供 useI2ImportExport 调用）────────────────

  /**
   * 批量导入行数据（覆盖现有行），自动重算公式。
   */
  function importRows(importedRows: Partial<I2DetailRow>[]): void {
    rows.value = importedRows.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
  }

  /** 获取当前行数据（供导出使用） */
  function exportRows(): I2DetailRow[] {
    return [...rows.value]
  }

  // ─── save: 持久化到 checklist_responses ────────────────────────────────────

  /**
   * JSON打包保存到 'I2-2-rows' key（Req 3.4 持久化）。
   * 遵循"禁止逐行存储大量数据"铁律，整体JSON打包。
   */
  async function save(): Promise<void> {
    const data: Record<string, any> = {
      [ITEM_ID_ROWS]: JSON.stringify(rows.value),
    }
    await saveResponses('I2-2', data)
  }

  // ─── Segment 列配置（4区段）────────────────────────────────────────────────

  /** Segment0 基础列定义 */
  const segmentBasicColumns = [
    { key: 'projectName', label: '项目名称', width: 180, editable: true, type: 'text' as const },
    { key: 'projectCode', label: '项目编号', width: 120, editable: true, type: 'text' as const },
    { key: 'approvalDate', label: '立项日期', width: 120, editable: true, type: 'date' as const },
    { key: 'phase', label: '阶段', width: 100, editable: true, type: 'select' as const, options: PHASE_OPTIONS },
    { key: 'manager', label: '负责人', width: 100, editable: true, type: 'text' as const },
    { key: 'startDate', label: '起始日期', width: 120, editable: true, type: 'date' as const },
    { key: 'endDate', label: '终止日期', width: 120, editable: true, type: 'date' as const },
    { key: 'budget', label: '预算', width: 130, editable: true, type: 'number' as const },
    { key: 'progress', label: '进度(%)', width: 90, editable: true, type: 'number' as const },
    { key: 'capitalizationStart', label: '资本化起点', width: 120, editable: true, type: 'date' as const },
    { key: 'status', label: '状态', width: 100, editable: true, type: 'select' as const, options: STATUS_OPTIONS },
  ]

  /** Segment1 本期投入列定义 */
  const segmentInvestmentColumns = [
    { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' as const },
    { key: 'materialCurrent', label: '材料-本期', width: 110, editable: true, type: 'number' as const },
    { key: 'materialAccum', label: '材料-累计', width: 110, editable: true, type: 'number' as const },
    { key: 'laborCurrent', label: '人工-本期', width: 110, editable: true, type: 'number' as const },
    { key: 'laborAccum', label: '人工-累计', width: 110, editable: true, type: 'number' as const },
    { key: 'depreciationCurrent', label: '折旧-本期', width: 110, editable: true, type: 'number' as const },
    { key: 'depreciationAccum', label: '折旧-累计', width: 110, editable: true, type: 'number' as const },
    { key: 'amortizationCurrent', label: '摊销-本期', width: 110, editable: true, type: 'number' as const },
    { key: 'amortizationAccum', label: '摊销-累计', width: 110, editable: true, type: 'number' as const },
    { key: 'otherCurrent', label: '其他-本期', width: 110, editable: true, type: 'number' as const },
    { key: 'otherAccum', label: '其他-累计', width: 110, editable: true, type: 'number' as const },
    { key: 'totalCurrent', label: '合计-本期', width: 120, editable: false, type: 'formula' as const, tooltip: '材料+人工+折旧+摊销+其他(本期)' },
    { key: 'totalAccum', label: '合计-累计', width: 120, editable: false, type: 'formula' as const, tooltip: '材料+人工+折旧+摊销+其他(累计)' },
    { key: 'investmentRemark', label: '投入说明', width: 150, editable: true, type: 'text' as const },
    { key: 'investmentSource', label: '投入来源', width: 120, editable: true, type: 'text' as const },
  ]

  /** Segment2 资本化列定义 */
  const segmentCapitalizationColumns = [
    { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' as const },
    { key: 'capStartDate', label: '资本化起点', width: 120, editable: true, type: 'date' as const },
    { key: 'capBeginAmount', label: '期初', width: 130, editable: true, type: 'number' as const },
    { key: 'capIncrease', label: '本期增加', width: 130, editable: true, type: 'number' as const },
    { key: 'capDecrease', label: '本期减少', width: 130, editable: true, type: 'number' as const },
    { key: 'capEndAmount', label: '期末', width: 130, editable: false, type: 'formula' as const, tooltip: '期末=期初+增加-减少' },
    { key: 'transferToI1', label: '转入I1', width: 130, editable: true, type: 'number' as const },
    { key: 'transferDate', label: '转入日期', width: 120, editable: true, type: 'date' as const },
    { key: 'capAmortization', label: '摊销', width: 120, editable: true, type: 'number' as const },
    { key: 'capImpairment', label: '减值', width: 120, editable: true, type: 'number' as const },
    { key: 'capNetValue', label: '净值', width: 130, editable: false, type: 'formula' as const, tooltip: '净值=期末-摊销-减值' },
    { key: 'completionRate', label: '完工比例(%)', width: 110, editable: true, type: 'number' as const },
    { key: 'acceptanceDate', label: '验收日', width: 120, editable: true, type: 'date' as const },
  ]

  /** Segment3 期末汇总列定义 */
  const segmentSummaryColumns = [
    { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' as const },
    { key: 'auditedEnd', label: '审定期末', width: 130, editable: true, type: 'number' as const },
    { key: 'adjustedBalance', label: '调整后余额', width: 130, editable: true, type: 'number' as const },
    { key: 'priorEnd', label: '上期期末', width: 130, editable: true, type: 'number' as const },
    { key: 'yoyChange', label: '同比变动', width: 110, editable: false, type: 'formula' as const, tooltip: '(审定期末-上期)/上期' },
    { key: 'expectedValue', label: '预期值', width: 130, editable: true, type: 'number' as const },
    { key: 'variance', label: '差异', width: 130, editable: false, type: 'formula' as const, tooltip: '审定期末-预期值' },
    { key: 'exceedFlag', label: '超标标记', width: 90, editable: true, type: 'text' as const },
    { key: 'conclusion', label: '结论', width: 150, editable: true, type: 'text' as const },
    { key: 'remark', label: '备注', width: 180, editable: true, type: 'text' as const },
  ]

  /** 4区段Tab定义 */
  const segments = [
    { index: 0, key: 'basic', label: '基础', columns: segmentBasicColumns },
    { index: 1, key: 'investment', label: '本期投入', columns: segmentInvestmentColumns },
    { index: 2, key: 'capitalization', label: '资本化', columns: segmentCapitalizationColumns },
    { index: 3, key: 'summary', label: '期末汇总', columns: segmentSummaryColumns },
  ]

  /** 当前Segment对应的列配置 */
  const activeColumns = computed(() => {
    return segments[activeSegment.value]?.columns ?? segmentBasicColumns
  })

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return (Task spec interface) ──────────────────────────────────────────

  return {
    // State
    rows,
    activeSegment,
    activeRowIndex,

    // Computed
    totalRow,
    crossValidation,
    activeColumns,

    // Segment定义
    segments,
    segmentBasicColumns,
    segmentInvestmentColumns,
    segmentCapitalizationColumns,
    segmentSummaryColumns,

    // Actions — Segment & Row同步
    switchSegment,
    setActiveRow,

    // Actions — Field编辑
    updateField,
    recalcAll,

    // Actions — 动态行
    addRow,
    removeRow,

    // Actions — 导入导出
    importRows,
    exportRows,

    // Actions — 持久化
    save,
  }
}

export default useI2Detail
