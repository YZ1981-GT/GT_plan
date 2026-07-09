<template>
  <div class="h2-tab-stocktake-summary">
    <!-- 踏勘总体情况 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、踏勘总体情况</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('summary-overview')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-14')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.summary.value.overview" type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly"
        placeholder="本次监盘覆盖X个在建工程项目，账面价值合计XXX元。经现场踏勘..."
        @blur="onFieldChange('overview', state.summary.value.overview)" />
      <div class="stats-bar">
        <el-tag type="info" size="small">监盘工程: {{ state.stats.value.totalProjects }}</el-tag>
        <el-tag type="success" size="small">正常施工: {{ state.stats.value.normalCount }}</el-tag>
        <el-tag type="warning" size="small">停工/缓建: {{ state.stats.value.stopCount }}</el-tag>
        <el-tag type="danger" size="small" v-if="state.stats.value.missingCount > 0">
          不存在: {{ state.stats.value.missingCount }}
        </el-tag>
      </div>
    </el-card>

    <!-- 异常清单 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、异常情况清单</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('summary-anomaly')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <el-table v-if="state.anomalyRows.value.length > 0" :data="state.anomalyRows.value"
        border stripe size="small" class="anomaly-table">
        <el-table-column prop="name" label="工程项目" min-width="130" />
        <el-table-column prop="anomalyType" label="异常类型" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.anomalyType === '停工' ? 'danger' : 'warning'" size="small">
              {{ row.anomalyType }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面金额" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.bookValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="description" label="异常描述" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small"
              @change="onAnomalyChange(row.rowId, 'description', $event)" />
            <span v-else>{{ row.description || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="followUp" label="后续处理" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.followUp" size="small" style="width:100%"
              @change="onAnomalyChange(row.rowId, 'followUp', $event)">
              <el-option label="关注减值" value="关注减值" />
              <el-option label="追加说明" value="追加说明" />
              <el-option label="管理层书面说明" value="管理层书面说明" />
              <el-option label="建议调整" value="建议调整" />
            </el-select>
            <span v-else>{{ row.followUp || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="无异常情况" :image-size="60" />
    </el-card>

    <!-- 监盘结论 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、监盘结论</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('summary-conclusion')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.summary.value.conclusion" type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="经实施上述监盘程序，我们认为..."
        @blur="onFieldChange('conclusion', state.summary.value.conclusion)" />
    </el-card>

    <!-- 签署 -->
    <div class="sign-area">
      <div class="sign-row">
        <span>编制人：</span>
        <el-input v-if="!isReadonly" v-model="state.summary.value.preparedBy" size="small" style="width:120px"
          @change="onFieldChange('preparedBy', $event)" />
        <span v-else>{{ state.summary.value.preparedBy || '________' }}</span>
        <span style="margin-left:24px">日期：</span>
        <el-date-picker v-if="!isReadonly" v-model="state.summary.value.preparedDate" type="date" size="small"
          value-format="YYYY-MM-DD" @change="onFieldChange('preparedDate', $event)" />
        <span v-else>{{ state.summary.value.preparedDate || '____年__月__日' }}</span>
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>踏勘总体情况应概述监盘范围/方法/覆盖率</li>
        <li>异常清单从H2-13盘点检查表自动提取(停工/缓建/不存在)</li>
        <li>结论需明确监盘程序是否达到审计目标</li>
        <li>停工项目应说明是否需要关注减值(→H2-15)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakeSummary.vue — H2-14 监盘小结
 * 段落型+表格(踏勘总体+异常清单+结论)
 * Spec: Task 4.17 | Requirements: 11.3, 11.6
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'summary',
})

function onFieldChange(field: string, value: any) {
  state.updateSummaryField(field, value)
}

function onAnomalyChange(rowId: string, field: string, value: any) {
  state.updateAnomalyCell(rowId, field, value)
}

function handleAiGenerate(section: string) {
  console.log('AI generate H2-14:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-stocktake-summary { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.stats-bar { display: flex; gap: 8px; margin-top: 12px; }
.anomaly-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.sign-area { padding: 16px 0; }
.sign-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
