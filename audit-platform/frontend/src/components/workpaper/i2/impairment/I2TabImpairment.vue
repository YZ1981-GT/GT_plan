<template>
  <div class="i2-impairment">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-15 减值准备测试表</span>
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
      <p>对各开发支出项目进行减值测试：比较账面价值与可收回金额，当账面＞可收回时应计提减值。差额≠0以红色高亮。可收回金额可从I2-16 DCF测试联动获取。</p>
    </div>

    <!-- 数据表 -->
    <el-table :data="impairmentRows" border size="small" class="impairment-table" max-height="420" :row-class-name="rowClassName">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="name" label="项目" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-model="row.name" size="small" placeholder="项目名称" @change="(v: string) => updateImpairmentField($index, 'name', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookValue" label="账面价值" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-model="row.bookValue" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateImpairmentField($index, 'bookValue', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="recoverableAmount" label="可收回金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <div class="recoverable-cell">
            <el-input-number v-model="row.recoverableAmount" size="small" :controls="false" :precision="2" :disabled="row.linkedToDcf" style="width:100%" @change="(v: number) => updateImpairmentField($index, 'recoverableAmount', v)" />
            <el-tag v-if="row.linkedToDcf" type="info" size="small" style="margin-left:4px" title="联动I2-16">DCF</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="shouldProvision" label="应计提" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="=MAX(账面-可收回,0)">{{ fmtNum(row.shouldProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="alreadyProvided" label="已计提" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-model="row.alreadyProvided" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateImpairmentField($index, 'alreadyProvided', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="difference" label="差额" min-width="100" align="right">
        <template #default="{ row }">
          <span :class="['formula-cell', { 'text-danger': Math.abs(row.difference) > 0.005 }]" title="=应计提-已计提">
            {{ fmtNum(row.difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" placeholder="结论" style="width:100%" @change="(v: string) => updateImpairmentField($index, 'conclusion', v)">
            <el-option label="无需计提" value="无需计提" />
            <el-option label="需补提" value="需补提" />
            <el-option label="多提转回" value="多提转回" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="removeImpairmentRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="totals-bar">
      <span class="totals-label">合计：</span>
      <el-tag type="info" size="small">账面 {{ fmtNum(impairmentSummary.totalBookValue) }}</el-tag>
      <el-tag type="info" size="small">应计提 {{ fmtNum(impairmentSummary.totalShouldProvision) }}</el-tag>
      <el-tag type="info" size="small">已计提 {{ fmtNum(impairmentSummary.totalAlreadyProvided) }}</el-tag>
      <el-tag :type="Math.abs(impairmentSummary.totalDifference) > 0.005 ? 'danger' : 'success'" size="small">
        差额 {{ fmtNum(impairmentSummary.totalDifference) }}
      </el-tag>
    </div>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="info" plain @click="emit('navigate-sheet', 'I2-16')">→ I2-16 DCF测试</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI2Impairment } from '../../../composables/useI2Impairment'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const wpIdRef = toRef(props, 'wpId')
const allResponsesRef = toRef(props, 'allResponses')

const {
  impairmentRows,
  impairmentSummary,
  highlightedRowIds,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
} = useI2Impairment(wpIdRef, allResponsesRef, {
  onSave: (itemId, value) => {
    props.saveResponse('I2-15', { [itemId]: JSON.stringify(value) })
  },
})

function rowClassName({ row }: { row: any }) {
  return highlightedRowIds.value.has(row.rowId) ? 'diff-highlight-row' : ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产项目名称', '新增减值测试行', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (value?.trim()) {
      addImpairmentRow({ name: value.trim(), bookValue: 0, linkedToDcf: false })
      ElMessage.success(`已添加：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

async function handleSave() {
  await props.saveResponse('I2-15', { 'I2-15-rows': JSON.stringify(impairmentRows.value) })
  emit('save')
  ElMessage.success('减值准备测试表已保存')
}

function handleAiAssist() { ElMessage.info('AI辅助减值迹象分析...') }
function handleReview() { openReviewDialog('I2-15-减值准备测试') }
function fmtNum(v: number): string { return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i2-impairment { font-size: 13px; padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.impairment-table { font-size: 13px; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.text-danger { color: #dc2626 !important; font-weight: 700; }
.recoverable-cell { display: flex; align-items: center; }
.totals-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 0; border-top: 1px solid #e5e7eb; margin-top: 8px; }
.totals-label { font-weight: 600; color: #374151; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
:deep(.diff-highlight-row) { background-color: #fef2f2 !important; }
:deep(.diff-highlight-row:hover > td) { background-color: #fee2e2 !important; }
</style>
