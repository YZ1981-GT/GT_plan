<!--
  合并试算平衡表 Tab 组件（从 ConsolidationIndex.vue 拆分）
-->
<template>
  <div class="gt-ctb">
    <!-- 报表类型切换标签 -->
    <div class="gt-ctb-type-bar">
      <span v-for="item in tbReportTypes" :key="item.key"
        class="gt-report-type-tag" :class="{ 'gt-report-type-tag--active': consolTbType === item.key }"
        @click="consolTbType = item.key; loadConsolTb()">
        {{ item.label }}
      </span>
    </div>

    <!-- 工具栏卡片 -->
    <div class="gt-ctb-toolbar">
      <div class="gt-ctb-toolbar-left">
        <el-button-group size="small">
          <el-button :type="tbEditMode ? 'primary' : ''" @click="tbEditMode = true">✏️ 编辑</el-button>
          <el-button :type="tbEditMode ? '' : 'primary'" @click="tbEditMode = false">📋 查看</el-button>
        </el-button-group>
        <span class="gt-ctb-sep" />
        <el-radio-group v-model="tbPeriod" size="small">
          <el-radio-button value="closing">期末</el-radio-button>
          <el-radio-button value="opening">期初</el-radio-button>
        </el-radio-group>
        <el-button v-if="tbPeriod === 'opening'" size="small" @click="importPriorYearTb">📥 提取上年数</el-button>
      </div>
      <div class="gt-ctb-toolbar-right">
        <el-button size="small" @click="loadConsolTb(true)" :loading="consolTbLoading">🔄 刷新</el-button>
        <el-tooltip content="从子企业试算表和工作底稿自动提取填充" placement="bottom">
          <el-button size="small" type="primary" @click="fillConsolTb" :loading="consolTbLoading">▶ 提取填充</el-button>
        </el-tooltip>
        <span class="gt-ctb-sep" />
        <el-button size="small" @click="exportConsolTb">📤 导出</el-button>
        <el-button size="small" @click="saveConsolTb">💾 保存</el-button>
        <span class="gt-ctb-sep" />
        <el-button size="small" @click="auditConsolTb">✅ 审核</el-button>
        <el-button size="small" type="warning" @click="generateReportFromTb" :loading="consolTbLoading">📋 生成报表</el-button>
      </div>
    </div>

    <!-- 信息栏 -->
    <div class="gt-ctb-info">
      <span>{{ consolTbRows.length }} 行</span>
      <span class="gt-ctb-info-formula">审定数 = 汇总 + 抵消借 - 抵消贷 + 调整借 - 调整贷</span>
    </div>

    <!-- 试算平衡表 — el-table -->
    <div class="gt-ctb-table-wrap" v-loading="consolTbLoading">
      <el-table :data="consolTbRows" border size="small" max-height="calc(100vh - 240px)" style="width:100%"
        :header-cell-style="{ whiteSpace: 'nowrap', fontSize: '12px' }"
        :cell-style="{ padding: '2px 8px', fontSize: '13px' }"
        :row-class-name="tbRowClassName"
        @row-contextmenu="onRowContextMenu">
        <el-table-column prop="row_code" label="行次" width="70" align="center">
          <template #default="{ row }">
            <span style="font-size:12px;color:#999">{{ row.row_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="row_name" label="项目" fixed="left" min-width="220">
          <template #default="{ row }">
            <span style="white-space:nowrap" :style="{ paddingLeft: (row.indent || 0) * 16 + 'px' }">{{ row.row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定汇总" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 0)" v-model="row.summary" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
            <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 0)">{{ fmtAmt(row.summary) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="权益抵消">
          <el-table-column label="借方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#4b2d77">借方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 1)" v-model="row.equity_dr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 1)">{{ fmtAmt(row.equity_dr) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#4b2d77">贷方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 2)" v-model="row.equity_cr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 2)">{{ fmtAmt(row.equity_cr) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="往来交易抵消">
          <el-table-column label="借方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#1a3a5c">借方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 3)" v-model="row.trade_dr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 3)">{{ fmtAmt(row.trade_dr) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#1a3a5c">贷方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 4)" v-model="row.trade_cr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 4)">{{ fmtAmt(row.trade_cr) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="报表调整">
          <el-table-column label="借方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#1e6e1e">借方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 5)" v-model="row.adj_dr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 5)">{{ fmtAmt(row.adj_dr) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方" min-width="100" align="right" header-align="center">
            <template #header><span style="color:#1e6e1e">贷方</span></template>
            <template #default="{ row, $index }">
              <el-input-number v-if="tbEditMode && tbLazyEdit.isEditing($index, 6)" v-model="row.adj_cr" size="small" :controls="false" style="width:100%" @blur="tbLazyEdit.stopEdit()" autofocus />
              <span v-else class="gt-amt" :class="{ 'gt-tb-editable': tbEditMode }" @click="tbEditMode && tbLazyEdit.startEdit($index, 6)">{{ fmtAmt(row.adj_cr) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="audited" label="合并审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="gt-amt gt-tb-audited">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-empty v-if="!consolTbRows.length && !consolTbLoading" :image-size="80">
      <template #description>
        <div style="text-align:center;line-height:2">
          <p style="font-size:14px;color:#666">选择报表类型后点击 <b>🔄 刷新</b> 加载行结构</p>
          <p style="font-size:12px;color:#999">然后点击 <b>▶ 提取填充</b> 从子企业试算表自动汇总数据</p>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { fmtAmount } from '@/utils/formatters'
import * as P from '@/services/apiPaths'

const props = defineProps<{
  projectId: string
  year: number
  templateType: string
  entityCode: string
}>()

const emit = defineEmits<{
  (e: 'audit', data: any[]): void
  (e: 'generate-report-done'): void
  (e: 'cell-context-menu', event: MouseEvent, row: any, ri: number): void
}>()

const tbLazyEdit = useLazyEdit()

function fmtAmt(v: any): string {
  if (v == null) return '-'
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return fmtAmount(n)
}

// ─── 合并试算平衡表 ──────────────────────────────────────────────────────────
const consolTbType = ref('balance_sheet')
const consolTbLoading = ref(false)
const consolTbRows = ref<any[]>([])
const tbEditMode = ref(false)
// Note: tbEditMode kept as simple ref for backward compatibility.
// useEditMode is available via GtEditableTable for new modules.
const tbPeriod = ref<'closing' | 'opening'>('closing')
const tbCache = new Map<string, any[]>()

function recalcTbAudited() {
  for (const r of consolTbRows.value) {
    const s = Number(r.summary) || 0
    const ed = Number(r.equity_dr) || 0
    const ec = Number(r.equity_cr) || 0
    const td = Number(r.trade_dr) || 0
    const tc = Number(r.trade_cr) || 0
    const ad = Number(r.adj_dr) || 0
    const ac = Number(r.adj_cr) || 0
    const result = s + ed - ec + td - tc + ad - ac
    r.audited = result !== 0 ? Math.round(result * 100) / 100 : null
  }
}

// 监听数值变化自动重算审定数
watch(consolTbRows, recalcTbAudited, { deep: true })

const tbReportTypes = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
]

function tbCacheKey(): string {
  return `${props.entityCode || '_root'}_${consolTbType.value}_${tbPeriod.value}_${props.templateType}`
}

async function loadConsolTb(forceRefresh = false) {
  const key = tbCacheKey()
  if (!forceRefresh && tbCache.has(key)) {
    consolTbRows.value = tbCache.get(key)!
    return
  }
  consolTbLoading.value = true
  try {
    // 从 report_config 加载行结构
    const standard = `${props.templateType}_consolidated`
    const data = await api.get(P.reportConfig.list, {
      params: { report_type: consolTbType.value, applicable_standard: standard, project_id: props.projectId },
      validateStatus: (s: number) => s < 600,
    })
    const rows = Array.isArray(data) ? (data) : []
    consolTbRows.value = rows.map((r: any) => ({
      row_code: r.row_code || '',
      row_name: r.row_name || '',
      indent: r.indent_level || 0,
      is_total: r.is_total_row || false,
      is_category: (r.indent_level === 0 && !r.is_total_row),
      // 数值列
      summary: null as number | null,      // 审定汇总
      equity_dr: null as number | null,    // 权益抵消-借
      equity_cr: null as number | null,    // 权益抵消-贷
      trade_dr: null as number | null,     // 往来抵消-借
      trade_cr: null as number | null,     // 往来抵消-贷
      adj_dr: null as number | null,       // 报表调整-借
      adj_cr: null as number | null,       // 报表调整-贷
      audited: null as number | null,      // 审定数（由 watch 计算）
    }))
    tbCache.set(key, consolTbRows.value)
    recalcTbAudited()

    // 尝试加载已保存的数据
    try {
      const { loadWorksheetData } = await import('@/services/consolWorksheetDataApi')
      const saved = await loadWorksheetData(props.projectId, props.year, `consol_tb_${consolTbType.value}_${tbPeriod.value}`)
      if (saved?.rows?.length) {
        for (const sr of saved.rows) {
          const target = consolTbRows.value.find((r: any) => r.row_code === sr.row_code)
          if (target) {
            target.summary = sr.summary ?? null
            target.equity_dr = sr.equity_dr ?? null
            target.equity_cr = sr.equity_cr ?? null
            target.trade_dr = sr.trade_dr ?? null
            target.trade_cr = sr.trade_cr ?? null
            target.adj_dr = sr.adj_dr ?? null
            target.adj_cr = sr.adj_cr ?? null
          }
        }
      }
    } catch { /* 首次无数据 */ }
  } catch { consolTbRows.value = [] }
  finally { consolTbLoading.value = false }
}

async function saveConsolTb() {
  if (!props.projectId) return
  const rows = consolTbRows.value.map((r: any) => ({
    row_code: r.row_code, row_name: r.row_name,
    summary: r.summary, equity_dr: r.equity_dr, equity_cr: r.equity_cr,
    trade_dr: r.trade_dr, trade_cr: r.trade_cr, adj_dr: r.adj_dr, adj_cr: r.adj_cr,
  }))
  try {
    const { saveWorksheetData } = await import('@/services/consolWorksheetDataApi')
    await saveWorksheetData(props.projectId, props.year, `consol_tb_${consolTbType.value}_${tbPeriod.value}`, { rows })
    ElMessage.success('试算平衡表已保存')
  } catch { ElMessage.error('保存失败') }
}

async function exportConsolTb() {
  if (!consolTbRows.value.length) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['行次', '项目', '审定汇总', '权益抵消-借', '权益抵消-贷', '往来抵消-借', '往来抵消-贷', '报表调整-借', '报表调整-贷', '合并审定数']
  const rows = consolTbRows.value.map((r: any) => [
    r.row_code, r.row_name, r.summary, r.equity_dr, r.equity_cr,
    r.trade_dr, r.trade_cr, r.adj_dr, r.adj_cr, r.audited,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  ws['!cols'] = headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 }))
  XLSX.utils.book_append_sheet(wb, ws, '试算平衡表')
  const label = tbReportTypes.find(t => t.key === consolTbType.value)?.label || ''
  XLSX.writeFile(wb, `合并试算平衡表_${label}_${tbPeriod.value}.xlsx`)
  ElMessage.success('已导出')
}

async function importPriorYearTb() {
  if (!props.projectId) return
  consolTbLoading.value = true
  try {
    const sheetKey = `consol_tb_${consolTbType.value}_opening`
    const data = await api.get(
      `/api/consol-worksheet-data/${props.projectId}/${props.year}/prior-year/${sheetKey}`,
      { validateStatus: (s: number) => s < 600 }
    )
    const result = data
    if (!result?.found) {
      ElMessage.warning(result?.message || `未找到 ${props.year - 1} 年度的期末数据`)
      return
    }
    const priorRows = result.content?.rows
    if (!priorRows?.length) {
      ElMessage.warning(`${props.year - 1} 年度期末数据为空`)
      return
    }
    // 用上年期末数据填充本年期初
    let matched = 0
    for (const sr of priorRows) {
      const target = consolTbRows.value.find((r: any) => r.row_code === sr.row_code)
      if (target) {
        target.summary = sr.summary ?? null
        target.equity_dr = sr.equity_dr ?? null
        target.equity_cr = sr.equity_cr ?? null
        target.trade_dr = sr.trade_dr ?? null
        target.trade_cr = sr.trade_cr ?? null
        target.adj_dr = sr.adj_dr ?? null
        target.adj_cr = sr.adj_cr ?? null
        matched++
      }
    }
    ElMessage.success(`已从 ${result.source_year} 年度期末数据提取 ${matched} 行作为本年期初`)
  } catch (err: any) {
    ElMessage.error(`提取上年数失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { consolTbLoading.value = false }
}

async function fillConsolTb() {
  if (!props.projectId) return
  consolTbLoading.value = true
  try {
    const entityCode = props.entityCode || ''
    const data = await api.post(`/api/consol-note-sections/fill-tb/${props.projectId}/${props.year}`, {
      report_type: consolTbType.value,
      period: tbPeriod.value,
      company_code: entityCode,
      standard: props.templateType,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data
    if (result?.rows?.length) {
      // 用提取的数据填充到当前行
      for (const fr of result.rows) {
        const target = consolTbRows.value.find((r: any) => r.row_code === fr.row_code)
        if (target) {
          if (fr.summary != null) target.summary = fr.summary
          if (fr.equity_dr != null) target.equity_dr = fr.equity_dr
          if (fr.equity_cr != null) target.equity_cr = fr.equity_cr
          if (fr.trade_dr != null) target.trade_dr = fr.trade_dr
          if (fr.trade_cr != null) target.trade_cr = fr.trade_cr
          if (fr.adj_dr != null) target.adj_dr = fr.adj_dr
          if (fr.adj_cr != null) target.adj_cr = fr.adj_cr
        }
      }
      ElMessage.success(`已提取填充：汇总匹配 ${result.matched_summary} 行，抵消匹配 ${result.matched_elim} 行（${result.child_count} 家子企业）`)
    } else {
      ElMessage.info('未提取到数据，请确认子企业已有试算表数据')
    }
  } catch (err: any) {
    ElMessage.error(`提取填充失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { consolTbLoading.value = false }
}

// onTbCellContextMenu 由父组件通过 @cell-context-menu 事件处理

async function generateReportFromTb() {
  if (!consolTbRows.value.length) { ElMessage.warning('请先加载试算平衡表数据'); return }
  consolTbLoading.value = true
  try {
    // 将审定数回填到合并报表
    const standard = `${props.templateType}_consolidated`
    const updates: { row_code: string; current_period_amount: number }[] = []
    for (const r of consolTbRows.value) {
      if (r.audited != null && r.row_code) {
        updates.push({ row_code: r.row_code, current_period_amount: r.audited })
      }
    }
    if (!updates.length) { ElMessage.warning('无审定数可回填'); consolTbLoading.value = false; return }

    // 调用后端批量更新报表数据
    const data = await api.post(`/api/report-config/batch-update`, {
      project_id: props.projectId,
      report_type: consolTbType.value,
      applicable_standard: standard,
      updates,
    }, { validateStatus: (s: number) => s < 600 })

    const result = data
    const updated = result?.updated || updates.length
    ElMessage.success(`已将 ${updated} 行审定数回填到合并报表（${tbReportTypes.find(t => t.key === consolTbType.value)?.label}）`)

    // 通知父组件清除报表缓存
    emit('generate-report-done')
  } catch (err: any) {
    ElMessage.error(`报表生成失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { consolTbLoading.value = false }
}

async function auditConsolTb() {
  if (!consolTbRows.value.length) { ElMessage.warning('请先加载数据'); return }
  const results: any[] = []
  const label = tbReportTypes.find(t => t.key === consolTbType.value)?.label || ''

  // 规则1：借贷平衡（所有行的借方合计 = 贷方合计）
  let totalDr = 0, totalCr = 0
  for (const r of consolTbRows.value) {
    totalDr += (Number(r.equity_dr) || 0) + (Number(r.trade_dr) || 0) + (Number(r.adj_dr) || 0)
    totalCr += (Number(r.equity_cr) || 0) + (Number(r.trade_cr) || 0) + (Number(r.adj_cr) || 0)
  }
  const drCrDiff = Math.round((totalDr - totalCr) * 100) / 100
  results.push({
    section_title: label, rule_name: '借贷平衡校验',
    level: Math.abs(drCrDiff) > 0.01 ? 'error' : 'pass',
    expected: fmtAmt(totalDr), actual: fmtAmt(totalCr),
    difference: drCrDiff ? fmtAmt(drCrDiff) : '', message: Math.abs(drCrDiff) > 0.01 ? '借贷不平衡' : '通过',
  })

  // 规则2：合计行校验
  for (const r of consolTbRows.value) {
    if (!r.is_total || !r.audited) continue
    results.push({
      section_title: label, rule_name: `审定数校验 - ${r.row_name}`,
      level: 'pass', expected: '', actual: fmtAmt(r.audited),
      difference: '', message: '审定数=汇总+调整-抵消 自动计算',
    })
  }

  emit('audit', results)
}

defineExpose({ loadConsolTb, consolTbRows, consolTbType, consolTbLoading })

function tbRowClassName({ row }: { row: any }): string {
  if (row.is_total) return 'gt-cm-total-row'
  if (row.is_category) return 'gt-cm-category'
  return ''
}

function onRowContextMenu(row: any, _col: any, event: MouseEvent) {
  event.preventDefault()
  const ri = consolTbRows.value.indexOf(row)
  emit('cell-context-menu', event, row, ri)
}
</script>

<style scoped>
.gt-ctb {
  display: flex; flex-direction: column; height: calc(100vh - 120px); padding: 0 16px;
}
.gt-ctb-type-bar {
  display: flex; gap: 0; border-bottom: 2px solid var(--gt-color-border-light, #f0f0f5);
  margin-bottom: 8px; flex-shrink: 0;
}
.gt-ctb-info {
  display: flex; align-items: center; gap: 12px;
  padding: 2px 0 6px; font-size: 12px; color: var(--gt-color-text-secondary, #6e6e73);
  flex-shrink: 0;
}
.gt-ctb-info-formula {
  padding: 2px 8px; background: var(--gt-color-primary-bg, #f4f0fa);
  border-radius: var(--gt-radius-sm, 4px); font-size: 11px; color: var(--gt-color-primary, #4b2d77);
}
.gt-ctb-table-wrap { flex: 1; min-height: 0; overflow: hidden; }
/* 工具栏在此组件中 flex-shrink: 0 */
.gt-ctb :deep(.gt-ctb-toolbar) { flex-shrink: 0; }
/* el-table 行样式 */
:deep(.gt-cm-total-row td) { font-weight: 700; background: #f0edf5 !important; }
:deep(.gt-cm-category td) { font-weight: 600; color: #4b2d77; }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed var(--gt-color-border, #e5e5ea); padding: 2px 6px; border-radius: 2px; display: inline-block; min-width: 70px; text-align: right; }
.gt-tb-editable:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-tb-audited { font-weight: 700; color: #4b2d77; background: rgba(75,45,119,0.06); }
</style>
