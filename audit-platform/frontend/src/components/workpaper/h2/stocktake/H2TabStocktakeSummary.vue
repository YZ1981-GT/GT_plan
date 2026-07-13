<template>
  <div class="h2-tab-stocktake-summary">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：汇总在建工程监盘结果，评价监盘程序是否达到审计目标，登记停工/进度异常/不存在等异常事项及后续处理建议（如关注减值）。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-14" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">异常 {{ state.summary.value.abnormalProjects.length }} 项</el-tag>
      </div>
    </div>

    <!-- 踏勘总体情况 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、审计说明（踏勘总体情况）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-14')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.summary.value.overallSituation" type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly"
        placeholder="本次监盘覆盖X个在建工程项目，账面价值合计XXX元。经现场踏勘..."
        @blur="onFieldChange('overallSituation', state.summary.value.overallSituation)" />
      <div class="stats-bar">
        <el-tag type="info" size="small">监盘工程: {{ state.checkStats.value.total }}</el-tag>
        <el-tag type="success" size="small">施工中: {{ state.checkStats.value.inProgress }}</el-tag>
        <el-tag type="warning" size="small">停工: {{ state.checkStats.value.stopped }}</el-tag>
        <el-tag type="primary" size="small">完工: {{ state.checkStats.value.completed }}</el-tag>
      </div>
    </el-card>

    <!-- 异常清单 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、异常情况清单</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddAnomaly">+ 新增异常</el-button>
          </div>
        </div>
      </template>

      <el-table v-if="state.summary.value.abnormalProjects.length > 0"
        :data="state.summary.value.abnormalProjects" border stripe size="small" class="anomaly-table">
        <el-table-column prop="name" label="工程项目" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onAnomalyChange()" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="abnormalType" label="异常类型" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.abnormalType" size="small" style="width:100%"
              @change="onAnomalyChange()">
              <el-option label="停工" value="停工" />
              <el-option label="进度异常" value="进度异常" />
              <el-option label="质量问题" value="质量问题" />
              <el-option label="不存在" value="不存在" />
              <el-option label="其他" value="其他" />
            </el-select>
            <el-tag v-else :type="row.abnormalType === '停工' ? 'danger' : 'warning'" size="small">
              {{ row.abnormalType || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="异常描述" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small"
              @change="onAnomalyChange()" />
            <span v-else>{{ row.description || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="后续处理建议" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.suggestion" size="small" style="width:100%"
              @change="onAnomalyChange()">
              <el-option label="关注减值" value="关注减值" />
              <el-option label="追加说明" value="追加说明" />
              <el-option label="管理层书面说明" value="管理层书面说明" />
              <el-option label="建议调整" value="建议调整" />
            </el-select>
            <span v-else>{{ row.suggestion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveAnomaly($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="无异常情况" :image-size="60" />
    </el-card>

    <!-- 监盘结论 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、审计结论（监盘结论）</span>
          <div class="section-header-actions">
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
          @change="onFieldChange('preparedBy', state.summary.value.preparedBy)" />
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
        <li>异常清单登记停工/进度异常/不存在等情况</li>
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
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'summary',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)

function onFieldChange(field: string, value: any) {
  state.updateSummary(field as any, value)
}

/** 异常清单行内编辑后整体持久化 */
function onAnomalyChange() {
  state.updateSummary('abnormalProjects', state.summary.value.abnormalProjects)
}

async function handleAddAnomaly() {
  try {
    const { value } = await ElMessageBox.prompt('请输入异常工程名称', '新增异常', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addAbnormalProject(value)
  } catch { /* cancelled */ }
}

function handleRemoveAnomaly(index: number) {
  const list = [...state.summary.value.abnormalProjects]
  list.splice(index, 1)
  state.updateSummary('abnormalProjects', list)
}


function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-stocktake-summary { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.stats-bar { display: flex; gap: 8px; margin-top: 12px; }
.anomaly-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.sign-area { padding: 16px 0; }
.sign-row { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
