<template>
  <div class="h2-tab-impairment">
    <!-- 区域1: 减值迹象判断 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、减值迹象判断（CAS8六项）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-13" label="→ H2-13盘点" />
            <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-sign')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-15')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.signRows.value" border stripe size="small" class="sign-table">
        <el-table-column prop="seq" label="序号" width="50" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="indicator" label="减值迹象" min-width="250">
          <template #default="{ row }">
            <span>{{ row.indicator }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.exists" size="small" style="width:80px"
              @change="onSignChange(row.rowId, 'exists', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="row.exists === '是' ? 'danger' : row.exists === '否' ? 'success' : 'info'" size="small">
              {{ row.exists || '待判' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据/说明" min-width="250">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.evidence" type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }" size="small"
              @blur="onSignChange(row.rowId, 'evidence', row.evidence)" />
            <span v-else>{{ row.evidence || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 判断结论 -->
      <div class="sign-conclusion">
        <el-tag :type="state.hasImpairmentSign.value ? 'danger' : 'success'" size="default">
          {{ state.hasImpairmentSign.value ? '存在减值迹象，需进行减值测算' : '未发现减值迹象' }}
        </el-tag>
      </div>
    </el-card>

    <!-- 区域2: 减值测算表 -->
    <el-card v-if="state.hasImpairmentSign.value" shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、减值测算</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-16" label="→ H2-16可收回" />
            <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-calc')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.calcRows.value" border stripe size="small" class="calc-table">
        <el-table-column prop="name" label="工程项目" min-width="130" fixed />
        <el-table-column prop="bookValue" label="账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false"
              size="small" class="amt-input" @change="onCalcChange(row.rowId, 'bookValue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recoverableAmount" label="可收回金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.recoverableAmount" :controls="false"
              size="small" class="amt-input" @change="onCalcChange(row.rowId, 'recoverableAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值金额" min-width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.impairmentAmount > 0 }]"
              :title="`=MAX(账面-可收回, 0)`">
              {{ fmtAmt(row.impairmentAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="method" label="评估方法" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.method" size="small" style="width:100%"
              @change="onCalcChange(row.rowId, 'method', $event)">
              <el-option label="DCF" value="DCF" />
              <el-option label="市场比较" value="市场比较" />
              <el-option label="评估报告" value="评估报告" />
            </el-select>
            <span v-else>{{ row.method || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCalcChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveCalc(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-line">
        减值合计: <strong class="error-amount">{{ fmtAmt(state.totalImpairment.value) }}</strong>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddCalc">+ 新增测算项目</el-button>
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>减值结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写减值测算结论..." :disabled="isReadonly"
        @blur="state.saveConclusion(state.conclusion.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>CAS8减值迹象6项：市价下跌/技术淘汰/经济环境变化/利率上升/净资产>市值/内部证据</li>
        <li>存在减值迹象时才需进行减值测算</li>
        <li>可收回金额=MAX(公允价值-处置费用, 预计未来现金流现值)</li>
        <li>减值金额=MAX(账面价值-可收回金额, 0)</li>
        <li>减值一经计提不得转回(CAS8规定)</li>
        <li>DCF模型详见H2-16可收回金额表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabImpairment.vue — H2-15 减值测算
 * 双区域(迹象判断6项+测算表) + GtIndexChip→H2-16/H2-13
 * Spec: Task 4.18 | Requirements: 12.1-12.2, 12.5-12.7
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Impairment } from '../../composables/useH2Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Impairment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  section: 'impairment',
})

function onSignChange(rowId: string, field: string, value: any) {
  state.updateSignCell(rowId, field, value)
}

function onCalcChange(rowId: string, field: string, value: any) {
  state.updateCalcCell(rowId, field, value)
}

function handleAddCalc() {
  state.addCalcRow()
}

function handleRemoveCalc(rowId: string) {
  state.removeCalcRow(rowId)
}

function handleAiGenerate(section: string) {
  console.log('AI generate H2-15:', section)
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
.h2-tab-impairment { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.sign-table { font-size: 13px; }
.calc-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.sign-conclusion { margin-top: 12px; text-align: center; }
.summary-line { padding: 12px 0; font-size: 13px; border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
