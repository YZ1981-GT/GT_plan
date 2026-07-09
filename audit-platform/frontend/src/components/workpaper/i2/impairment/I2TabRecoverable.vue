<template>
  <div class="i2-recoverable">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-16 可收回金额测试（DCF）</span>
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
      <p>通过DCF模型测算各开发支出项目的使用价值：预测期5年现金流 + 折现率 + 终值(Gordon模型)。可收回金额=MAX(公允价值-处置费用, DCF使用价值)。计算结果联动I2-15减值测试表。</p>
    </div>

    <!-- 项目列表 -->
    <div v-for="(row, rowIdx) in recoverableRows" :key="row.rowId" class="dcf-card">
      <el-card shadow="never">
        <template #header>
          <div class="dcf-card-header">
            <el-input v-model="row.name" size="small" placeholder="项目名称" style="width:260px" />
            <el-button size="small" type="danger" text @click="removeRecoverableRow(rowIdx)">删除</el-button>
          </div>
        </template>

        <!-- DCF参数 -->
        <div class="dcf-params">
          <div class="param-item">
            <span class="param-label">折现率</span>
            <el-input-number v-model="row.discountRate" size="small" :step="0.01" :min="0" :max="1" :precision="4" @change="(v: number) => updateRecoverableField(rowIdx, 'discountRate', v)" />
            <span class="param-hint">{{ (row.discountRate * 100).toFixed(2) }}%</span>
          </div>
          <div class="param-item">
            <span class="param-label">永续增长率</span>
            <el-input-number v-model="row.growthRate" size="small" :step="0.005" :min="0" :max="0.1" :precision="4" @change="(v: number) => updateRecoverableField(rowIdx, 'growthRate', v)" />
            <span class="param-hint">{{ (row.growthRate * 100).toFixed(2) }}%</span>
          </div>
          <div class="param-item">
            <span class="param-label">公允-处置费</span>
            <el-input-number v-model="row.fairValueLessDisposal" size="small" :controls="false" :precision="2" @change="(v: number) => updateRecoverableField(rowIdx, 'fairValueLessDisposal', v)" />
          </div>
        </div>

        <!-- 5年现金流 -->
        <div class="cashflow-table">
          <span class="cf-label">预测期现金流（5年）：</span>
          <div class="cf-inputs">
            <div v-for="yr in 5" :key="yr" class="cf-year">
              <span class="cf-year-label">第{{ yr }}年</span>
              <el-input-number
                :model-value="row.cashFlows[yr - 1]"
                size="small"
                :controls="false"
                :precision="2"
                style="width:110px"
                @change="(v: number) => updateCashFlow(rowIdx, yr - 1, v)"
              />
            </div>
          </div>
        </div>

        <!-- 计算结果 -->
        <div class="dcf-results">
          <div class="result-item">
            <span class="result-label">终值(TV)</span>
            <span class="result-value formula-cell" title="=CF5*(1+g)/(r-g)">{{ fmtNum(row.terminalValue) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">DCF使用价值</span>
            <span class="result-value formula-cell" title="=PV(预测期)+PV(终值)">{{ fmtNum(row.valueInUse) }}</span>
          </div>
          <div class="result-item result-highlight">
            <span class="result-label">可收回金额</span>
            <span class="result-value formula-cell" title="=MAX(公允-处置,DCF)">{{ fmtNum(row.recoverableAmount) }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 空态 -->
    <el-empty v-if="recoverableRows.length === 0" description="暂无DCF测试项目，请点击新增" />

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增DCF测试</el-button>
      <el-button size="small" type="info" plain @click="emit('navigate-sheet', 'I2-15')">← I2-15 减值表</el-button>
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
  recoverableRows,
  addRecoverableRow,
  removeRecoverableRow,
  updateCashFlow,
  updateRecoverableField,
  recalcAllRecoverable,
} = useI2Impairment(wpIdRef, allResponsesRef, {
  onSave: (itemId, value) => {
    props.saveResponse('I2-16', { [itemId]: JSON.stringify(value) })
  },
})

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产项目名称（将联动I2-15）', '新增DCF测试', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (value?.trim()) {
      addRecoverableRow({ name: value.trim(), discountRate: 0.08, growthRate: 0.02 })
      ElMessage.success(`已添加DCF测试：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

async function handleSave() {
  recalcAllRecoverable()
  await props.saveResponse('I2-16', { 'I2-16-dcf-params': JSON.stringify(recoverableRows.value) })
  emit('save')
  ElMessage.success('可收回金额测试已保存（已联动I2-15）')
}

function handleAiAssist() { ElMessage.info('AI辅助DCF参数合理性分析...') }
function handleReview() { openReviewDialog('I2-16-可收回金额测试') }
function fmtNum(v: number): string { return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i2-recoverable { font-size: 13px; padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }

.dcf-card { margin-bottom: 16px; }
.dcf-card-header { display: flex; align-items: center; justify-content: space-between; }

.dcf-params { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 14px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-weight: 500; color: #374151; font-size: 12px; white-space: nowrap; }
.param-hint { font-size: 11px; color: #6b7280; }

.cashflow-table { margin-bottom: 14px; }
.cf-label { font-weight: 500; color: #374151; font-size: 12px; display: block; margin-bottom: 8px; }
.cf-inputs { display: flex; gap: 12px; flex-wrap: wrap; }
.cf-year { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.cf-year-label { font-size: 11px; color: #6b7280; }

.dcf-results { display: flex; gap: 24px; padding: 12px 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; }
.result-item { display: flex; flex-direction: column; }
.result-label { font-size: 11px; color: #6b7280; }
.result-value { font-size: 15px; font-weight: 600; color: #1f2937; }
.result-highlight .result-value { color: #059669; font-size: 17px; }

.formula-cell { border-bottom: 1px dashed #a5b4fc; cursor: help; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
