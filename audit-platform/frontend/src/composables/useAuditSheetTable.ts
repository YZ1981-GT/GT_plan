/**
 * useAuditSheetTable — 审定表数据构建 + 自动计算 + 保存 + 导入导出 + 行操作
 * （spec workpaper-frontend-large-component-split, Req 3）
 *
 * 从 GtAuditSheet.vue 抽出所有围绕 tableData 的逻辑簇：
 * - tableData ref + buildTableData（audit_rows 浅拷贝 + 合并 tb_values 只读字段）
 * - 行类型判定：isBoldRow / isEditableRow
 * - TB 取数 + 自动计算：openingAudited / effectiveAdj / effectiveReclass / auditedAmount /
 *   changeAmount / changeRate + 合计汇总 detailRows / sumOverDetails
 * - 列展示值（合计行汇总）：displayOpeningUnadjusted / displayCurrentUnadjusted / displayAdj / displayReclass
 * - 显示格式化：fmtNum / fmtRate；系统参考值 placeholder：adjPlaceholder / reclassPlaceholder
 * - 编辑事件：onFieldChange（emit 经 emitFieldChange 回调）
 * - 保存（持久化分层）：buildSavePayload / onSave（emit 经 emitSave 回调）
 * - 一键刷新：onRefreshFromLedger
 * - 导入导出（复用 useExcelIO）：onExportTemplate / onExportData / triggerImport / onFileSelected / confirmImport
 * - 行操作：tableRef / selectedRows / nextRowId / isRowSelectable / onSelectionChange / addRow / batchDelete
 *
 * 铁律：行为零变更、保响应式（ref/computed）；不在 composable 内 emit（field-change / save
 *       由主组件 emit，经 emitFieldChange / emitSave 回调通知）；依赖单向（主组件 → composable →
 *       util/api）；composable 之间不互相 import（isDynamicColumns / dynamicColumnDefs /
 *       auditSections 由主组件持有并传入）。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import type { AuditSheetRow, AuditSheetHtmlData, AuditSheetSections, AuditSheetColumnDef } from '@/components/workpaper/auditSheetTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

export function useAuditSheetTable(options: {
  /** wpId 取值（getter，保持响应式） */
  wpId: () => string
  /** sheetName 取值（getter，保持响应式） */
  sheetName: () => string
  /** htmlData 取值（getter，保持响应式） */
  htmlData: () => AuditSheetHtmlData | undefined
  /** readonly 取值（getter，保持响应式） */
  readonly: () => boolean
  /** 是否动态列模式（由 useAuditSheetColumns 提供，主组件持有） */
  isDynamicColumns: Ref<boolean>
  /** 动态列定义（由 useAuditSheetColumns 提供，主组件持有） */
  dynamicColumnDefs: Ref<AuditSheetColumnDef[]>
  /** 审计说明 / 结论区（由 useAuditSheetSections 提供，主组件持有，保存载荷用） */
  auditSections: Ref<Required<AuditSheetSections>>
  /** field-change emit 回调（主组件 emit('field-change')） */
  emitFieldChange: (payload: { rowId: string; field: string; value: unknown }) => void
  /** save emit 回调（主组件 emit('save')） */
  emitSave: (data: AuditSheetHtmlData) => void
}) {
  const { htmlData, isDynamicColumns, dynamicColumnDefs, auditSections, emitFieldChange, emitSave } = options
  const prefs = useDisplayPrefsStore()

  // ─── 响应式表数据 ───
  const tableData = ref<AuditSheetRow[]>([])

  /**
   * 从 htmlData 构建 tableData：
   *   audit_rows 的浅拷贝 + 合并对应的 tb_values[row.id] 只读展示字段。
   *
   * 简单合并版本（Task 9）：直接把 tb_values 的 TB 字段挂到行上供 computed 使用。
   * 完整的 adj_amount ?? sys_aje ?? 0 回退逻辑在 Task 14 细化，这里保持干净。
   */
  function buildTableData() {
    const rows = Array.isArray(htmlData()?.audit_rows) ? htmlData()!.audit_rows! : []
    const tbValues = htmlData()?.tb_values || {}
    tableData.value = rows.map((row) => {
      const tb = tbValues[row.id] || {}
      return {
        ...row,
        indent: row.indent ?? 0,
        isCustom: row.isCustom ?? false,
        adj_amount: row.adj_amount ?? null,
        reclass_amount: row.reclass_amount ?? null,
        reason: row.reason ?? '',
        // 合并 TB 只读展示字段（行内已有值优先，避免覆盖测试/持久化注入）
        opening_unadjusted: row.opening_unadjusted ?? tb.opening_unadjusted ?? null,
        current_unadjusted: row.current_unadjusted ?? tb.current_unadjusted ?? null,
        sys_aje: row.sys_aje ?? tb.sys_aje ?? null,
        sys_rje: row.sys_rje ?? tb.sys_rje ?? null,
      }
    }).filter((row) => {
      // 过滤空白占位行：item 为空且非分节/非合计/非自定义 = 模板生成的空行，不展示
      if (!row.item && !row.isSection && !row.isComputed && !row.isCustom) return false
      return true
    })
  }

  // ─── 行类型判定 ───
  /** 分节行/合计行/标记 bold 的行加粗 */
  function isBoldRow(row: AuditSheetRow): boolean {
    return !!(row.bold || row.isSection || row.isComputed)
  }

  /** 可编辑行：非分节行、非合计行（合计行由 computed 汇总，不可编辑） */
  function isEditableRow(row: AuditSheetRow): boolean {
    return !row.isSection && !row.isComputed
  }

  // ─── 数值工具 ───
  function num(v: unknown): number {
    if (v == null || v === '') return 0
    const n = typeof v === 'number' ? v : Number(v)
    return Number.isFinite(n) ? n : 0
  }

  // ─── 自动计算（per row）───
  /**
   * 明细行集合（非分节、非合计）——合计行（isComputed）汇总的来源。
   * isEditableRow 同义（分节/合计行不可编辑也不参与被汇总）。
   */
  function detailRows(): AuditSheetRow[] {
    return tableData.value.filter((r) => !r.isSection && !r.isComputed)
  }

  /** 对所有明细行套用 accessor 求和（合计行汇总用）。 */
  function sumOverDetails(accessor: (row: AuditSheetRow) => number): number {
    return detailRows().reduce((acc, r) => acc + num(accessor(r)), 0)
  }

  /**
   * 期初审定 = 期初未审 ?? 0（简单方案；Task 14 增强跨年审定取值）。
   * 合计行（isComputed）→ 汇总所有明细行的期初审定（Task 17）。
   */
  function openingAudited(row: AuditSheetRow): number {
    if (row.isComputed) return sumOverDetails((r) => openingAudited(r))
    return num(row.opening_unadjusted)
  }

  /**
   * 有效账项调整值（Task 14 用户覆盖回退逻辑）：
   *   用户编辑值优先，未编辑（null/undefined）时回退系统汇总 AJE（sys_aje），仍无则 0。
   * 用 ?? 链而非 ||：保证「用户显式填 0」覆盖系统值（0 不是 nullish，不会回退到 sys_aje）。
   *   - adj_amount === null/undefined → 用 sys_aje
   *   - adj_amount === 0（用户显式填 0）→ 用 0（不回退）
   *   - sys_aje === null/undefined → 用 0
   */
  function effectiveAdj(row: AuditSheetRow): number {
    return row.adj_amount ?? row.sys_aje ?? 0
  }

  /** 有效重分类调整值：同 effectiveAdj，回退系统汇总 RJE（sys_rje）。 */
  function effectiveReclass(row: AuditSheetRow): number {
    return row.reclass_amount ?? row.sys_rje ?? 0
  }

  /**
   * 审定数 = 本期未审 + 有效账项调整 + 有效重分类
   *   有效调整 = 用户编辑值 ?? 系统汇总值 ?? 0（Task 14）
   * 注意：不能用 num() 预先归一 adj_amount/sys_aje——num 把 null 归 0 会丢失
   *   「未编辑」与「显式填 0」的区别，破坏 ?? 回退语义。必须先走 ?? 链再用 num 兜底。
   * 合计行（isComputed）→ 汇总所有明细行的审定数（Task 17）。
   */
  function auditedAmount(row: AuditSheetRow): number {
    if (row.isComputed) return sumOverDetails((r) => auditedAmount(r))
    return num(row.current_unadjusted) + num(effectiveAdj(row)) + num(effectiveReclass(row))
  }

  /** 变动额 = 审定数 - 期初审定 */
  function changeAmount(row: AuditSheetRow): number {
    return auditedAmount(row) - openingAudited(row)
  }

  /** 变动率 = 变动额 ÷ 期初审定（期初审定为 0 时返回 null，显示 —） */
  function changeRate(row: AuditSheetRow): number | null {
    const base = openingAudited(row)
    if (base === 0) return null
    return changeAmount(row) / base
  }

  // ─── 列展示值（合计行 Task 17 汇总，明细行取本行原值）───
  /**
   * 合计行（isComputed）的列展示对明细行求和；其余行返回原值（可能 null → 显示 —）。
   * 注意：账项调整/重分类汇总用 effectiveAdj/effectiveReclass（含系统 AJE/RJE 回退），
   * 与 auditedAmount 的汇总口径一致，保证合计行「审定数 = 本期未审 + 调整 + 重分类」成立。
   */
  function displayOpeningUnadjusted(row: AuditSheetRow): number | null {
    if (row.isComputed) return sumOverDetails((r) => num(r.opening_unadjusted))
    return row.opening_unadjusted ?? null
  }

  function displayCurrentUnadjusted(row: AuditSheetRow): number | null {
    if (row.isComputed) return sumOverDetails((r) => num(r.current_unadjusted))
    return row.current_unadjusted ?? null
  }

  function displayAdj(row: AuditSheetRow): number | null {
    if (row.isComputed) return sumOverDetails((r) => effectiveAdj(r))
    return row.adj_amount ?? null
  }

  function displayReclass(row: AuditSheetRow): number | null {
    if (row.isComputed) return sumOverDetails((r) => effectiveReclass(r))
    return row.reclass_amount ?? null
  }

  // ─── 显示格式化 ───
  /** 千分位 + 会计风格：null/undefined 显示 —（0 正常显示） */
  function fmtNum(v: number | null | undefined): string {
    if (v == null || (typeof v === 'number' && Number.isNaN(v))) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (!Number.isFinite(n)) return '—'
    return prefs.fmt(n)
  }

  /** 变动率百分比：null 显示 — */
  function fmtRate(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(Number(v))) return '—'
    return (Number(v) * 100).toFixed(2) + '%'
  }

  // ─── 系统参考值提示（Task 14）───
  /**
   * 账项调整 el-input-number 的 placeholder：用户未填时显示系统汇总 AJE 作参考。
   *   - 有 sys_aje（含 0）→ 显示该值（用户可见正在被回退使用的系统参考值）
   *   - 无 sys_aje → 显示 '—'
   * 说明：placeholder 仅提示，不写入 v-model；实际回退由 effectiveAdj 的 ?? 链完成。
   */
  function adjPlaceholder(row: AuditSheetRow): string {
    return row.sys_aje == null ? '—' : fmtNum(row.sys_aje)
  }

  /** 重分类 el-input-number 的 placeholder：用户未填时显示系统汇总 RJE 作参考。 */
  function reclassPlaceholder(row: AuditSheetRow): string {
    return row.sys_rje == null ? '—' : fmtNum(row.sys_rje)
  }

  // ─── 编辑事件 ───
  function onFieldChange(row: AuditSheetRow, field: string, value: unknown) {
    if (options.readonly()) return
    // el-input-number 清空时回传 undefined，统一归一为 null
    const normalized = value === undefined ? null : value
    ;(row as Record<string, unknown>)[field] = normalized
    emitFieldChange({ rowId: row.id, field, value: normalized })
  }

  // ─── 保存（持久化分层）───
  /**
   * 仅持久化的行结构字段（保存时保留）。
   * 显式 **剔除** TB 实时值（opening_unadjusted/current_unadjusted/sys_aje/sys_rje）
   * 与任何 computed/transient 字段——下次加载时由后端重新从 trial_balance 查。
   */
  const PERSISTED_ROW_KEYS = [
    // 行结构
    'id',
    'item',
    'indent',
    'bold',
    'isSection',
    'isComputed',
    'isCustom',
    'account_code',
    // 用户编辑列
    'adj_amount',
    'reclass_amount',
    'reason',
  ] as const

  /**
   * 构建保存载荷：把 tableData 映射为「剥离 TB 实时值」的 audit_rows。
   *
   * 返回的对象即写入 parsed_data.html_data[sheet_name] 的内容（design Req 4.2）。
   * 注意：不含 sheet_name——GtWpRenderer.onSave 会用 activeSheetName 包装成
   * SavePayload（避免子组件持有过期 sheet_name）；也不含 tb_values（TB 加载时重查）。
   */
  function buildSavePayload(): AuditSheetHtmlData {
    const auditRows: AuditSheetRow[] = tableData.value.map((row) => {
      const stripped: Record<string, unknown> = {}
      for (const key of PERSISTED_ROW_KEYS) {
        if (row[key] !== undefined) stripped[key] = row[key]
      }
      // 动态列字段也持久化
      if (isDynamicColumns.value) {
        for (const col of dynamicColumnDefs.value) {
          if (row[col.key] !== undefined) stripped[col.key] = row[col.key]
        }
      }
      return stripped as AuditSheetRow
    })
    const payload: AuditSheetHtmlData = {
      audit_rows: auditRows,
      audit_sections: { ...auditSections.value },
    }
    if (isDynamicColumns.value) {
      payload.column_defs = dynamicColumnDefs.value
    }
    return payload
  }

  /** 保存：emit 剥离后的 audit_rows，落库（POST /save）由父组件链路完成。 */
  function onSave() {
    if (options.readonly()) return
    emitSave(buildSavePayload())
  }

  /**
   * 一键刷新：从四表库（辅助余额表/试算表）预填充数据到当前表格。
   * 调用后端 POST /api/workpapers/{wpId}/audit-sheet-refresh，返回预填充行，
   * 合并到 tableData（在合计行之前插入，替换现有空白占位行）。
   */
  async function onRefreshFromLedger() {
    if (options.readonly()) return
    try {
      const result: any = await (await import('@/services/apiProxy')).api.post(
        `/api/workpapers/${options.wpId()}/audit-sheet-refresh`,
      )
      const rows = result?.rows ?? []
      if (!rows.length) {
        ElMessage.info(result?.message || '四表库中未找到可预填充的数据')
        return
      }
      // 找到合计行位置，在其之前插入预填充行（替换空白占位行）
      const totalIdx = tableData.value.findIndex(r => r.isComputed)
      // 移除已有的空白占位行（isCustom 且 item 为空）
      tableData.value = tableData.value.filter(r => !(r.isCustom && !r.item))
      // 重新定位合计行
      const newTotalIdx = tableData.value.findIndex(r => r.isComputed)
      const insertAt = newTotalIdx >= 0 ? newTotalIdx : tableData.value.length
      // 插入预填充行
      const newRows: AuditSheetRow[] = rows.map((r: any, i: number) => ({
        id: r.id || `refresh-${Date.now()}-${i}`,
        item: r.item || '',
        indent: 0,
        bold: false,
        isSection: false,
        isComputed: false,
        isCustom: true,
        account_code: null,
        adj_amount: null,
        reclass_amount: null,
        reason: '',
        ...r,
      }))
      tableData.value.splice(insertAt, 0, ...newRows)
      ElMessage.success(result?.message || `已预填充 ${rows.length} 行数据，请核对后保存`)
    } catch (e: any) {
      ElMessage.error(`刷新失败：${e?.message || '网络错误'}`)
    }
  }

  // ─── 导入导出（Task 16，复用 useExcelIO）───────────────────────────────────
  const { exportTemplate: _exportTemplate, onFileSelected: _onFileSelected } = useExcelIO()

  /** 导入用 sheet 名（导出模板与解析都用同一名，保证按名匹配） */
  const IMPORT_SHEET_NAME = '审定表'

  /** 导出模板/数据时的列定义（行项目名 + 列标题）。
   *  项目列承载行名（导入按此匹配），数值列即三个可编辑列 + 参考性的未审/审定列。
   *  注意：导入仅写回可编辑列（账项调整/重分类/原因），其余列导出仅供离线查看。 */
  const EXPORT_COLUMNS: ExcelColumn[] = [
    { key: 'seq', header: '序号', width: 6 },
    { key: 'item', header: '项目', width: 28, note: '请勿修改，系统按项目名匹配导入' },
    { key: 'opening_unadjusted', header: '期初未审数', width: 14 },
    { key: 'opening_audited', header: '期初审定数', width: 14 },
    { key: 'current_unadjusted', header: '本期未审数', width: 14 },
    { key: 'adj_amount', header: '账项调整', width: 14, note: '可填写' },
    { key: 'reclass_amount', header: '重分类调整', width: 14, note: '可填写' },
    { key: 'audited_amount', header: '审定数', width: 14 },
    { key: 'reason', header: '原因分析', width: 24, note: '可填写' },
  ]

  /** 文件选择器 ref */
  const fileInputRef = ref<HTMLInputElement | null>(null)

  /** 导入预览弹窗状态 */
  const importVisible = ref(false)
  const importStats = ref<{ matched: number; skipped: number } | null>(null)
  const importPreviewRows = ref<Array<{ item: string; adj_amount: number | null; reclass_amount: number | null; reason: string }>>([])
  /** 项目名 → 解析出的可编辑列值，确认导入时按行名写回 */
  const importParsedMap = ref<Map<string, { adj_amount: number | null; reclass_amount: number | null; reason: string }>>(new Map())

  /** 解析数值：空/非法 → null（保留 0），用于导入单元格 */
  function parseNum(v: unknown): number | null {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : Number(String(v).replace(/,/g, ''))
    return Number.isFinite(n) ? n : null
  }

  /**
   * 导出模板：生成 xlsx（行项目名 + 列标题）供离线填写。
   * 复用 useExcelIO.exportTemplate——把当前 tableData 作为现有数据行写入（含 TB 实时值与
   * computed 派生列供查看），项目名在第 2 列，导入时按此匹配。
   * 只读操作，readonly 下仍可用。
   */
  async function onExportTemplate() {
    const existingData: any[][] = tableData.value.map((row, idx) => [
      row.isSection ? '' : String(idx + 1),
      row.item ?? '',
      row.opening_unadjusted ?? '',
      row.isSection ? '' : openingAudited(row),
      row.current_unadjusted ?? '',
      row.adj_amount ?? '',
      row.reclass_amount ?? '',
      row.isSection ? '' : auditedAmount(row),
      row.reason ?? '',
    ])
    await _exportTemplate({
      columns: EXPORT_COLUMNS,
      sheetName: IMPORT_SHEET_NAME,
      fileName: `审定表_${options.sheetName() || '模板'}.xlsx`,
      existingData,
      includeNoteRow: false,
      includeInstructions: true,
      instructionTitle: '审定表 — 填写说明',
      instructionRows: [
        ['1. 在「审定表」工作表填写，不要修改 sheet 名称'],
        ['2. 「项目」列文字不要修改，系统按项目名匹配导入'],
        ['3. 仅「账项调整 / 重分类调整 / 原因分析」三列会被导入，其余列为只读/自动计算'],
        ['4. 金额填数字，不要带逗号或货币符号'],
      ],
    })
  }

  /**
   * 导出数据：完整底稿 xlsx（含表头编制信息 + 列标题 + 当前金额数据 + 审计说明/结论）。
   * 导出格式贴近致同模板样式，可直接归档或提交复核。
   */
  async function onExportData() {
    const allRows: any[][] = []
    // 表头区（编制信息）
    allRows.push(['致同会计师事务所'])
    allRows.push([options.sheetName() || '审定表'])
    allRows.push([`被审计单位：`, '', '', `编制人：`, '', `编制日期：`, '', `索引号：${options.sheetName() || ''}`])
    allRows.push([])
    // 列标题行
    if (isDynamicColumns.value) {
      allRows.push(['项目', ...dynamicColumnDefs.value.map(c => c.label)])
    } else {
      allRows.push(EXPORT_COLUMNS.map(c => c.header))
    }
    // 数据行
    for (const row of tableData.value) {
      if (isDynamicColumns.value) {
        allRows.push([row.item ?? '', ...dynamicColumnDefs.value.map(c => row[c.key] ?? '')])
      } else {
        allRows.push([
          row.item ?? '',
          row.opening_unadjusted ?? '',
          openingAudited(row),
          row.current_unadjusted ?? '',
          row.adj_amount ?? '',
          row.reclass_amount ?? '',
          auditedAmount(row),
          changeAmount(row),
          changeRate(row) != null ? (changeRate(row)! * 100).toFixed(2) + '%' : '',
          row.reason ?? '',
        ])
      }
    }
    // 审计说明/结论
    allRows.push([])
    if (auditSections.value.notes) {
      allRows.push(['审计说明：'])
      allRows.push([auditSections.value.notes])
    }
    if (auditSections.value.conclusion) {
      allRows.push(['审计结论：'])
      allRows.push([auditSections.value.conclusion])
    }
    // 构建列定义（按实际最大宽度）
    const maxCols = Math.max(...allRows.map(r => r.length), 1)
    // 补齐每行长度
    for (const row of allRows) {
      while (row.length < maxCols) row.push('')
    }
    const columns: ExcelColumn[] = Array.from({ length: maxCols }, (_, i) => ({
      key: String.fromCharCode(65 + (i % 26)) + (i >= 26 ? String(Math.floor(i / 26)) : ''),
      header: '',
      width: i === 0 ? 24 : 14,
    }))
    await _exportTemplate({
      columns,
      sheetName: options.sheetName() || '审定表',
      fileName: `${options.sheetName() || '审定表'}_数据导出.xlsx`,
      existingData: allRows,
      includeNoteRow: false,
      includeInstructions: false,
      applyStyles: false,
    })
  }

  /** 触发隐藏文件选择器 */
  function triggerImport() {
    if (options.readonly()) return
    fileInputRef.value?.click()
  }

  /**
   * 文件选择 → 解析 → 构建匹配预览。
   * 按行名（项目列）匹配 tableData 中可编辑行（非分节/非合计），匹配成功累加 matched，
   * 否则 skipped。解析结果暂存 importParsedMap，确认后才写回（confirmImport）。
   */
  async function onFileSelected(e: Event) {
    if (options.readonly()) return
    await _onFileSelected(
      e,
      (result) => {
        const parsed = new Map<string, { adj_amount: number | null; reclass_amount: number | null; reason: string }>()
        let matched = 0
        let skipped = 0
        // headers 顺序与 EXPORT_COLUMNS 一致：[序号, 项目, 期初未审, 期初审定, 本期未审, 账项调整, 重分类调整, 审定数, 原因分析]
        const H = result.headers
        const col = (label: string) => H.find((h) => h === label) || ''
        const itemKey = col('项目')
        const adjKey = col('账项调整')
        const reclassKey = col('重分类调整')
        const reasonKey = col('原因分析')
        for (const r of result.rows) {
          const itemName = String(r[itemKey] ?? '').trim()
          if (!itemName) {
            skipped++
            continue
          }
          const target = tableData.value.find((row) => row.item === itemName)
          if (!target || !isEditableRow(target)) {
            skipped++
            continue
          }
          parsed.set(itemName, {
            adj_amount: parseNum(r[adjKey]),
            reclass_amount: parseNum(r[reclassKey]),
            reason: String(r[reasonKey] ?? '').trim(),
          })
          matched++
        }
        importParsedMap.value = parsed
        importStats.value = { matched, skipped }
        importPreviewRows.value = Array.from(parsed.entries())
          .slice(0, 10)
          .map(([item, v]) => ({ item, ...v }))
        importVisible.value = true
      },
      { sheetName: IMPORT_SHEET_NAME, skipRows: 1 },
    )
  }

  /**
   * 确认导入：按行名把解析值写回 tableData 的可编辑列（仅 adj_amount/reclass_amount/reason）。
   * 不触碰 TB 只读列与 computed 列。写回后逐行 emit field-change（与手动编辑一致），
   * 不自动保存——用户仍需点「保存」落库。
   */
  function confirmImport() {
    if (options.readonly()) return
    let count = 0
    for (const row of tableData.value) {
      if (!isEditableRow(row)) continue
      const entry = importParsedMap.value.get(row.item)
      if (!entry) continue
      row.adj_amount = entry.adj_amount
      row.reclass_amount = entry.reclass_amount
      row.reason = entry.reason
      emitFieldChange({ rowId: row.id, field: 'adj_amount', value: entry.adj_amount })
      emitFieldChange({ rowId: row.id, field: 'reclass_amount', value: entry.reclass_amount })
      emitFieldChange({ rowId: row.id, field: 'reason', value: entry.reason })
      count++
    }
    importVisible.value = false
    importStats.value = null
    importParsedMap.value = new Map()
    importPreviewRows.value = []
    ElMessage.success(`已导入 ${count} 行数据，请点击「保存」生效`)
  }

  // ─── 行操作（Task 17：新增行 / 多选 / 批量删除）──────────────────────────
  /** el-table 实例 ref（批量删除后清空勾选用） */
  const tableRef = ref<any>(null)

  /** 当前多选选中的行（仅可编辑行可被选中，见 isRowSelectable） */
  const selectedRows = ref<AuditSheetRow[]>([])

  /** 自增计数器：保证新增行 id 唯一，避免与现有 row-{n} 及多次新增冲突 */
  let rowSeq = 0

  /**
   * 生成唯一行 id：row-custom-{timestamp}-{seq}。
   * 用 timestamp + 自增 seq 双保险——同一毫秒内连续新增也不会撞 id。
   * 前缀 custom 与模板行 row-{n} 区分，便于排查。
   */
  function nextRowId(): string {
    rowSeq += 1
    return `row-custom-${Date.now()}-${rowSeq}`
  }

  /** 多选可选性：仅可编辑行（非分节、非合计）可勾选——保护汇总/分节结构不被删 */
  function isRowSelectable(row: AuditSheetRow): boolean {
    return isEditableRow(row)
  }

  /** el-table selection-change 回调：同步选中行集合 */
  function onSelectionChange(rows: AuditSheetRow[]) {
    selectedRows.value = Array.isArray(rows) ? rows : []
  }

  /**
   * 新增行（Req 6.1）：在表格尾部追加一个空的可编辑自定义行。
   * - isCustom=true → 项目名可编辑、保存时持久化完整数据（区别于 TB 来源行）
   * - 不带 account_code（无 TB 取数），未审列显示 —，用户手填调整/原因
   * readonly 时不生效。
   */
  function addRow() {
    if (options.readonly()) return
    const row: AuditSheetRow = {
      id: nextRowId(),
      item: '',
      indent: 1,
      bold: false,
      isSection: false,
      isComputed: false,
      isCustom: true,
      account_code: null,
      adj_amount: null,
      reclass_amount: null,
      reason: '',
      opening_unadjusted: null,
      current_unadjusted: null,
      sys_aje: null,
      sys_rje: null,
    }
    tableData.value.push(row)
  }

  /**
   * 批量删除（Req 6.2）：删除当前选中的可编辑行（合计/分节行不可选 → 不会被删）。
   * 二次确认（confirmDangerous）→ 按 id 集合过滤 tableData → 清空勾选。
   * 删除仅改内存 tableData，用户仍需点「保存」落库。readonly / 无选中时不生效。
   */
  async function batchDelete() {
    if (options.readonly()) return
    if (!selectedRows.value.length) return
    try {
      await confirmDangerous(
        `确定删除选中的 ${selectedRows.value.length} 行？删除后需点击「保存」生效。`,
        '批量删除确认',
      )
    } catch {
      // 用户取消
      return
    }
    const removeIds = new Set(selectedRows.value.map((r) => r.id))
    const before = tableData.value.length
    tableData.value = tableData.value.filter((r) => !removeIds.has(r.id))
    const removed = before - tableData.value.length
    selectedRows.value = []
    // 清空 el-table 内部勾选状态（避免残留高亮）
    tableRef.value?.clearSelection?.()
    ElMessage.success(`已删除 ${removed} 行，请点击「保存」生效`)
  }

  return {
    // state
    tableData,
    // build
    buildTableData,
    // 行类型
    isBoldRow,
    isEditableRow,
    // 计算/汇总
    num,
    detailRows,
    sumOverDetails,
    openingAudited,
    effectiveAdj,
    effectiveReclass,
    auditedAmount,
    changeAmount,
    changeRate,
    // 列展示
    displayOpeningUnadjusted,
    displayCurrentUnadjusted,
    displayAdj,
    displayReclass,
    // 格式化 / placeholder
    fmtNum,
    fmtRate,
    adjPlaceholder,
    reclassPlaceholder,
    // 编辑 / 保存
    onFieldChange,
    buildSavePayload,
    onSave,
    onRefreshFromLedger,
    // 导入导出
    EXPORT_COLUMNS,
    IMPORT_SHEET_NAME,
    fileInputRef,
    importVisible,
    importStats,
    importPreviewRows,
    importParsedMap,
    parseNum,
    onExportTemplate,
    onExportData,
    triggerImport,
    onFileSelected,
    confirmImport,
    // 行操作
    tableRef,
    selectedRows,
    nextRowId,
    isRowSelectable,
    onSelectionChange,
    addRow,
    batchDelete,
  }
}
