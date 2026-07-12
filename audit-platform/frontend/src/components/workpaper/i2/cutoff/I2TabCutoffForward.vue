<template>
  <div class="i2-cutoff-forward">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-13 截止性测试（账簿→单据）</span>
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
      <p>正向截止测试：从账簿记录出发，核对原始单据日期（期末±5天）。验证开发支出是否记录在正确的会计期间。跨期交易以红色高亮标记。</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-card">
      <div class="stat-item">
        <span class="stat-label">样本总数</span>
        <span class="stat-value">{{ forwardRows.length }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期笔数</span>
        <span class="stat-value stat-danger">{{ forwardCrossPeriodCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期比例</span>
        <span class="stat-value" :class="{ 'stat-danger': forwardCrossPeriodCount > 0 }">
          {{ forwardRows.length > 0 ? ((forwardCrossPeriodCount / forwardRows.length) * 100).toFixed(1) + '%' : '—' }}
        </span>
      </div>
    </div>

    <!-- 数据表 -->
    <el-table :data="forwardRows" border size="small" class="cutoff-table" max-height="460" :row-class-name="rowClassName">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="voucherNo" label="凭证号" min-width="110">
        <template #default="{ row, $index }">
          <el-input v-model="row.voucherNo" size="small" placeholder="凭证号" @change="(v: string) => updateForwardRow($index, 'voucherNo', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="recordDate" label="记账日期" min-width="130">
        <template #default="{ row, $index }">
          <el-date-picker v-model="row.recordDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="记账日期" style="width:100%" @change="(v: string) => updateForwardRow($index, 'recordDate', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-model="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateForwardRow($index, 'amount', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="documentDate" label="单据日期" min-width="130">
        <template #default="{ row, $index }">
          <el-date-picker v-model="row.documentDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="单据日期" style="width:100%" @change="(v: string) => updateForwardRow($index, 'documentDate', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="dateDiff" label="日期差(天)" min-width="95" align="center">
        <template #default="{ row }">
          <span class="formula-cell" title="=|记账日期-单据日期|">{{ row.dateDiff }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isCrossPeriod" label="是否跨期" min-width="85" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isCrossPeriod ? 'danger' : 'success'" size="small">
            {{ row.isCrossPeriod ? '跨期' : '正常' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="80" align="center">
        <template #default="{ row }">
          <span :class="{ 'text-danger': row.isCrossPeriod }">{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="removeForwardRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="addForwardRow()">+ 新增行</el-button>
      <el-button size="small" type="warning" plain @click="handleAutoSampling">自动提取</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI2Cutoff } from '../../composables/useI2Cutoff'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const allResponsesRef = toRef(props, 'allResponses')
const projectIdRef = toRef(props, 'projectId')

const {
  forwardRows,
  forwardCrossPeriodCount,
  addForwardRow,
  removeForwardRow,
  updateForwardRow,
  loadFromAutoSampling,
  save: saveCutoff,
} = useI2Cutoff({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
  projectId: projectIdRef,
})

function rowClassName({ row }: { row: any }) {
  return row.isCrossPeriod ? 'cross-period-row' : ''
}

async function handleAutoSampling() {
  await loadFromAutoSampling('forward')
}

async function handleSave() {
  await saveCutoff()
  emit('save')
  ElMessage.success('正向截止性测试已保存')
}

function handleAiAssist() { ElMessage.info('AI辅助截止性测试分析...') }
function handleReview() { openReviewDialog('I2-13-截止性测试-正向') }
</script>

<style scoped>
.i2-cutoff-forward { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; }
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.cutoff-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.text-danger { color: #dc2626; font-weight: 600; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
:deep(.cross-period-row:hover > td) { background-color: #fee2e2 !important; }
</style>
