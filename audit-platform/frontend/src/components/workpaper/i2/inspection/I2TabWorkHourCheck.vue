<template>
  <div class="i2-workhour-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-10 研发人员工时检查表</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>核查研发人员工时分配的合理性：验证工时记录是否与项目实际投入一致，占比是否合理，避免虚报工时。</p>
    </div>

    <!-- 数据表 -->
    <el-table :data="rows" border size="small" class="check-table" max-height="500">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="staffName" label="人员" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.staffName" size="small" placeholder="姓名" />
        </template>
      </el-table-column>
      <el-table-column prop="projectName" label="项目" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.projectName" size="small" placeholder="研发项目" />
        </template>
      </el-table-column>
      <el-table-column prop="month" label="月份" min-width="100">
        <template #default="{ row }">
          <el-date-picker v-model="row.month" type="month" size="small" value-format="YYYY-MM" placeholder="月份" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="hours" label="工时(h)" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.hours" size="small" :controls="false" :precision="1" @change="recalcRatio(row)" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="totalHours" label="月总工时" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.totalHours" size="small" :controls="false" :precision="1" @change="recalcRatio(row)" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="ratio" label="占比" min-width="80" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="`工时/总工时=${row.hours}/${row.totalHours}`">{{ fmtPercent(row.ratio) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="📎" width="50" align="center">
        <template #default="{ $index }">
          <el-button size="small" text @click="handleOcr($index)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="110">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
            <el-option label="合理" value="合理" />
            <el-option label="偏高" value="偏高" />
            <el-option label="偏低" value="偏低" />
            <el-option label="待核实" value="待核实" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="warning" plain @click="handleSampling">抽凭引擎</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

interface WorkHourRow {
  staffName: string; projectName: string; month: string
  hours: number; totalHours: number; ratio: number; conclusion: string
}

const STORAGE_KEY = 'I2-10-rows'
const rows = ref<WorkHourRow[]>([])

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) rows.value = parsed.map(normRow)
  } catch { rows.value = [] }
}

function normRow(r: any): WorkHourRow {
  const hours = Number(r.hours) || 0
  const totalHours = Number(r.totalHours) || 0
  return {
    staffName: r.staffName || '', projectName: r.projectName || '',
    month: r.month || '', hours, totalHours,
    ratio: totalHours > 0 ? hours / totalHours : 0,
    conclusion: r.conclusion || '',
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function recalcRatio(row: WorkHourRow) {
  row.ratio = row.totalHours > 0 ? row.hours / row.totalHours : 0
}

function handleAddRow() {
  rows.value.push({ staffName: '', projectName: '', month: '', hours: 0, totalHours: 0, ratio: 0, conclusion: '' })
}

async function handleSave() {
  const persist = rows.value.map(r => ({ staffName: r.staffName, projectName: r.projectName, month: r.month, hours: r.hours, totalHours: r.totalHours, conclusion: r.conclusion }))
  await props.saveResponse('I2-10', { [STORAGE_KEY]: JSON.stringify(persist) })
  emit('save'); ElMessage.success('工时检查表已保存')
}

function handleOcr(idx: number) { ElMessage.info('OCR识别工时记录...') }
function handleSampling() { ElMessage.info('抽凭引擎(GtVoucherSamplingEngine)加载中...') }
function handleAiAssist() { ElMessage.info('AI辅助工时合理性分析...') }
function handleReview() { openReviewDialog('I2-10-研发人员工时检查') }
function fmtPercent(v: number): string { return v == null || isNaN(v) ? '—' : `${(v * 100).toFixed(1)}%` }
</script>

<style scoped>
.i2-workhour-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.check-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
