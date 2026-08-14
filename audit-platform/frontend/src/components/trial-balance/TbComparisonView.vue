<template>
  <div class="gt-tb-comparison">
    <!-- 顶部工具栏 -->
    <div class="gt-tb-comparison__toolbar">
      <el-button size="small" @click="$emit('close')">← 返回试算表</el-button>
      <el-segmented v-model="mode" :options="[{label:'跨年度',value:'cross_year'},{label:'跨项目',value:'cross_project'}]" size="small" />
      <!-- 跨年度：选年度 -->
      <template v-if="mode === 'cross_year'">
        <el-select v-model="selectedYear" size="small" placeholder="选择对比年度" style="width:120px" @change="onAddYear">
          <el-option v-for="y in availableYears" :key="y" :label="y + '年'" :value="y" :disabled="comparison.targets.value.some(t => t.key === String(y))" />
        </el-select>
      </template>
      <!-- 跨项目：选项目 -->
      <template v-if="mode === 'cross_project'">
        <el-select v-model="selectedProject" size="small" placeholder="选择子公司" style="width:180px" filterable value-key="id" @change="onAddProject">
          <el-option v-for="p in availableProjects" :key="p.id" :label="p.name" :value="p" :disabled="comparison.targets.value.some(t => t.key === p.id)" />
        </el-select>
        <span v-if="comparison.targets.value.length >= 5" style="font-size:11px;color:var(--el-color-warning)">最多对比5个</span>
      </template>
      <span style="flex:1" />
      <!-- 已选对比目标 tags -->
      <el-tag v-for="t in comparison.targets.value" :key="t.key" size="small" closable @close="comparison.removeTarget(t.key)" style="margin-left:4px">
        {{ t.label }}
        <span v-if="comparison.errors.value.get(t.key)" style="color:var(--el-color-danger)"> ({{ comparison.errors.value.get(t.key) }})</span>
      </el-tag>
    </div>

    <!-- 筛选栏 -->
    <div class="gt-tb-comparison__filter" v-if="comparison.joinedRows.value.length">
      <span style="font-size:12px;color:var(--gt-color-text-tertiary)">{{ comparison.joinedRows.value.length }} 行</span>
      <el-input v-model="filterThreshold" size="small" placeholder="变动额阈值" style="width:120px;margin-left:8px" type="number" />
      <el-button size="small" @click="doExport">📤 导出对比报告</el-button>
    </div>

    <!-- 对比表格 -->
    <el-table v-if="filteredRows.length" :data="filteredRows" size="small" :max-height="tableMaxHeight" style="width:100%;margin-top:8px" :row-class-name="compRowClassName" class="gt-tb-comp-table" highlight-current-row>
      <el-table-column prop="standard_account_code" label="科目编码" width="110" fixed class-name="gt-tb-comp-code-col" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" fixed />
      <el-table-column label="本年审定" width="140" align="right" class-name="gt-tb-comp-current-col">
        <template #default="{ row }"><span class="gt-amt">{{ fmt(row.current_audited) }}</span></template>
      </el-table-column>
      <el-table-column v-for="t in comparison.targets.value" :key="t.key" :label="t.label + ' 审定'" width="140" align="right" class-name="gt-tb-comp-target-col">
        <template #default="{ row }">
          <span v-if="row.targets[t.key] != null" class="gt-amt">{{ fmt(row.targets[t.key]) }}</span>
          <span v-else class="gt-tb-comp-na">—</span>
        </template>
      </el-table-column>
      <el-table-column v-for="t in comparison.targets.value" :key="'var_' + t.key" :label="'变动(' + t.label + ')'" width="150" align="right" class-name="gt-tb-comp-variance-col">
        <template #default="{ row }">
          <span v-if="row.variances[t.key]" :class="varianceClass(row.variances[t.key].rate)">
            {{ fmt(row.variances[t.key].amount) }}
            <template v-if="row.variances[t.key].rate != null">
              <span class="gt-tb-comp-rate">({{ (row.variances[t.key].rate * 100).toFixed(1) }}%)</span>
            </template>
          </span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else-if="comparison.targets.value.length" description="无匹配数据或全部已被筛除" />
    <el-empty v-else description="请选择对比目标（年度或项目）" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useTbComparison } from '@/composables/useTbComparison'
import { exportMultiSheetData } from '@/composables/useExcelIO'
import http from '@/utils/http'
import type { Ref } from 'vue'

const props = defineProps<{ projectId: string; year: number; currentRows: any[]; initialMode?: 'cross_year' | 'cross_project' }>()
defineEmits<{ close: [] }>()

const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmtAmount(v)

const mode = ref<'cross_year' | 'cross_project'>(props.initialMode || 'cross_year')
const selectedYear = ref<number | null>(null)
const selectedProject = ref<any>(null)
const filterThreshold = ref<string>('')
const tableMaxHeight = computed(() => window.innerHeight - 260)

// 可用年度（当前年±3年）
const availableYears = computed(() => {
  const y = props.year
  return [y - 3, y - 2, y - 1, y + 1].filter(v => v > 2000 && v !== y)
})

// 可用项目（从合并范围或同组项目获取）
const availableProjects = ref<{ id: string; name: string }[]>([])

async function loadAvailableProjects() {
  try {
    // 优先从合并范围获取（子公司清单）
    const { data } = await http.get(`/api/consolidation/scope`, { params: { project_id: props.projectId, year: props.year }, _silent: true } as any)
    const items = data?.companies || data?.items || data || []
    if (Array.isArray(items) && items.length) {
      availableProjects.value = items
        .filter((c: any) => c.project_id && c.project_id !== props.projectId)
        .map((c: any) => ({ id: c.project_id, name: c.company_name || c.name || c.project_id }))
      return
    }
  } catch { /* fail-open */ }
  // 回退：从项目列表获取同组织其他项目
  try {
    const { data } = await http.get(`/api/projects`, { params: { page_size: 50 }, _silent: true } as any)
    const items = data?.items || data || []
    if (Array.isArray(items)) {
      availableProjects.value = items
        .filter((p: any) => p.id !== props.projectId)
        .map((p: any) => ({ id: p.id, name: p.project_name || p.name || p.id }))
    }
  } catch { /* fail-open */ }
}

watch(mode, (v) => {
  if (v === 'cross_project' && !availableProjects.value.length) {
    loadAvailableProjects()
  }
}, { immediate: true })
const comparison = useTbComparison(
  computed(() => props.projectId) as unknown as Ref<string>,
  computed(() => props.year) as unknown as Ref<number>,
  computed(() => props.currentRows) as unknown as Ref<any[]>,
)

function onAddYear() {
  if (selectedYear.value && comparison.targets.value.length < 5) {
    comparison.loadComparisonYear(selectedYear.value)
    selectedYear.value = null
  }
}

function onAddProject() {
  if (selectedProject.value && comparison.targets.value.length < 5) {
    comparison.loadComparisonProject(selectedProject.value.id, selectedProject.value.name)
    selectedProject.value = null
  }
}

const filteredRows = computed(() => {
  const threshold = Number(filterThreshold.value) || 0
  if (!threshold) return comparison.joinedRows.value
  return comparison.joinedRows.value.filter(r => {
    return Object.values(r.variances).some(v => Math.abs(v.amount) >= threshold)
  })
})

function varianceClass(rate: number | null) {
  if (rate == null) return ''
  const abs = Math.abs(rate)
  if (abs > 0.5) return 'gt-tb-var-danger'
  if (abs > 0.3) return 'gt-tb-var-warn'
  return ''
}

function compRowClassName({ row }: { row: any }) {
  if (row.onlyCurrent) return 'gt-tb-comp-only-current'
  if (row.onlyTarget?.length) return 'gt-tb-comp-only-target'
  return ''
}

async function doExport() {
  const headers = ['科目编码', '科目名称', '本年审定', ...comparison.targets.value.flatMap(t => [t.label + ' 审定', '变动额', '变动率(%)'])]
  const dataRows = filteredRows.value.map(r => {
    const row: any[] = [r.standard_account_code, r.account_name, r.current_audited]
    for (const t of comparison.targets.value) {
      row.push(r.targets[t.key] ?? '', r.variances[t.key]?.amount ?? '', r.variances[t.key]?.rate != null ? (r.variances[t.key].rate! * 100).toFixed(1) : '')
    }
    return row
  })
  // 走 useExcelIO 单一入口（B7 批）。原本无 !cols，故不传 colWidths。
  await exportMultiSheetData({
    sheets: [{ sheetName: '对比报告', rows: [headers, ...dataRows] }],
    fileName: `试算表对比_${props.year}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
}
</script>

<style scoped>
.gt-tb-comparison { padding: 12px 0; }
.gt-tb-comparison__toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(75, 45, 119, 0.03); border-radius: 6px;
}
.gt-tb-comparison__filter {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}

/* 表格整体：复用 gt-compact-table 行高 + 12px 字号 + 无边框 */
:deep(.gt-tb-comp-table) {
  --el-table-border-color: transparent;
}
:deep(.gt-tb-comp-table td.el-table__cell),
:deep(.gt-tb-comp-table th.el-table__cell) {
  padding: 0 !important;
  height: 24px !important;
}
:deep(.gt-tb-comp-table .cell) {
  padding: 1px 6px !important;
  line-height: 20px !important;
  font-size: 12px !important;
}
:deep(.gt-tb-comp-table .el-table__header th) {
  background: rgba(75, 45, 119, 0.05) !important;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 600;
  border-bottom: 1px solid #ebeef5;
}
:deep(.gt-tb-comp-table .el-table__body td) {
  border-bottom: 1px solid #f5f5f5;
}
:deep(.gt-tb-comp-table .el-table__body tr:hover > td) {
  background: rgba(75, 45, 119, 0.04) !important;
}

/* 科目编码列 */
:deep(.gt-tb-comp-code-col .cell) {
  color: var(--gt-color-text-tertiary, #909399);
}
/* 本年审定列：主色加粗 */
:deep(.gt-tb-comp-current-col .cell) {
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
:deep(.gt-tb-comp-current-col) {
  background: rgba(75, 45, 119, 0.04) !important;
}
/* 变动列淡底 */
:deep(.gt-tb-comp-variance-col) {
  background: rgba(245, 245, 245, 0.5) !important;
}

/* 金额数值：与科目明细主表 .gt-amt 完全一致 */
.gt-amt {
  font-family: 'Arial Narrow', Arial, monospace;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.gt-tb-comp-na {
  color: var(--gt-color-text-quaternary, #c0c4cc);
  font-style: italic;
}
.gt-tb-comp-rate {
  font-size: 11px;
  margin-left: 2px;
  opacity: 0.7;
}

/* 变动高亮 */
.gt-tb-var-warn { color: var(--el-color-warning, #e6a23c); font-weight: 600; }
.gt-tb-var-danger { color: var(--gt-color-coral, #f56c6c); font-weight: 700; }

/* 仅当前有/仅对比有 行底色 */
:deep(.gt-tb-comp-only-current td) { background: rgba(103, 194, 58, 0.06) !important; }
:deep(.gt-tb-comp-only-target td) { background: rgba(245, 108, 108, 0.06) !important; }

/* 选中行 */
:deep(.el-table__body tr.current-row > td) {
  background: rgba(75, 45, 119, 0.08) !important;
}
</style>
