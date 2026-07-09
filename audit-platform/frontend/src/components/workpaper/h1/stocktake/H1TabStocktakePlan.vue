<template>
  <div class="h1-tab-stocktake-plan">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 确定盘点时间、地点、范围</div>
        <div class="guide-step"><span class="step-num">②</span> 确定盘点方法(全面/抽样)和样本选取标准</div>
        <div class="guide-step"><span class="step-num">③</span> 安排人员(观察员/点数员/记录员)</div>
        <div class="guide-step"><span class="step-num">④</span> 编制时间安排表</div>
      </div>
    </div>

    <!-- 基本信息 -->
    <el-card shadow="never" class="plan-card">
      <template #header>
        <div class="section-title">
          <span>一、监盘基本信息</span>
          <el-button size="small" type="default" link @click="handleReview('H1-9-basic')">💬 复核</el-button>
        </div>
      </template>
      <el-form :model="planInfo" label-width="100px" size="small">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="盘点日期">
              <el-date-picker v-model="planInfo.stocktakeDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点地点">
              <el-input v-model="planInfo.location" :disabled="isReadonly" placeholder="如：总部大楼/工厂车间" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="参与人员">
              <el-input v-model="planInfo.participants" :disabled="isReadonly" placeholder="盘点人/观察员/记录员" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点方法">
              <el-select v-model="planInfo.method" :disabled="isReadonly" style="width:100%">
                <el-option label="全面盘点" value="全面盘点" />
                <el-option label="抽样盘点" value="抽样盘点" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="盘点范围">
          <el-input v-model="planInfo.scope" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly"
            placeholder="说明盘点涵盖的资产类别/金额范围..." />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 样本选取 -->
    <el-card shadow="never" class="plan-card">
      <template #header>
        <div class="section-title">
          <span>二、样本选取标准</span>
          <el-button size="small" type="primary" @click="handleAddSample" :disabled="isReadonly">+ 新增</el-button>
        </div>
      </template>
      <el-table :data="state.sampleSelection.value" border stripe size="small">
        <el-table-column prop="category" label="资产分类" min-width="100" />
        <el-table-column prop="selectionCriteria" label="选取标准" min-width="160" />
        <el-table-column prop="sampleSize" label="样本量" width="80" align="right" />
        <el-table-column prop="coverageAmount" label="金额覆盖" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.coverageAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="coverageRate" label="覆盖率%" width="80" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.coverageRate }}%</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 时间安排 -->
    <el-card shadow="never" class="plan-card">
      <template #header><span>三、时间安排</span></template>
      <el-input v-model="scheduleNote" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="isReadonly"
        placeholder="具体时间安排（如：9:00集合→9:30开始→12:00午休→17:00结束清点）" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>盘点日尽量选择资产负债表日或临近日</li>
        <li>抽样盘点覆盖率建议≥70%（金额口径）</li>
        <li>完成计划后进入H1-10执行盘点检查</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, inject, toRef } from 'vue'
import { useH1Stocktake } from '../../composables/useH1Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const scheduleNote = ref('')

const state = useH1Stocktake(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

const planInfo = reactive({
  stocktakeDate: '', location: '', participants: '', scope: '', method: '抽样盘点',
})

function handleAddSample() { state.addSampleRow?.() }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-stocktake-plan { padding: 16px; font-size: 13px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.plan-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
