<template>
  <div class="h1-tab-impairment">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS8资产减值：当存在减值迹象时，应估计可收回金额。可收回金额 = MAX(公允价值-处置费用, 预计未来现金流量现值DCF)。减值金额 = MAX(账面价值-可收回金额, 0)。固定资产减值一经计提不得转回。</p>
    </div>

    <!-- 区域1: 减值迹象6项判断 -->
    <el-card shadow="never" class="indication-card">
      <template #header>
        <div class="section-title">
          <span>一、减值迹象判断（CAS8第5条6项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-conclusion')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-14-indications')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.indications.value" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="description" label="减值迹象描述（CAS8）" min-width="350" />
        <el-table-column prop="result" label="判断" width="120" align="center">
          <template #default="{ row }">
            <el-radio-group v-model="row.result" :disabled="isReadonly" size="small" @change="onIndicationChange(row, 'result')">
              <el-radio-button value="Y">有</el-radio-button>
              <el-radio-button value="N">无</el-radio-button>
              <el-radio-button value="NA">N/A</el-radio-button>
            </el-radio-group>
          </template>
        </el-table-column>
        <el-table-column prop="explanation" label="说明" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.explanation" size="small" placeholder="判断依据..." @change="onIndicationChange(row, 'explanation')" />
            <span v-else>{{ row.explanation }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="indication-summary">
        <el-alert :type="hasImpairmentSign ? 'warning' : 'success'" :closable="false" show-icon>
          {{ hasImpairmentSign ? `存在减值迹象（${signCount}项），需进行减值测试` : '未发现明显减值迹象' }}
        </el-alert>
      </div>
    </el-card>

    <!-- 区域2: 减值测算表 -->
    <el-card shadow="never" class="calc-card" v-if="hasImpairmentSign">
      <template #header>
        <div class="section-title">
          <span>二、减值测算</span>
          <el-button size="small" type="primary" @click="handleAddCalcRow" :disabled="isReadonly">+ 新增资产组</el-button>
        </div>
      </template>

      <el-table :data="state.calcRows.value" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="assetGroup" label="资产组" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetGroup" size="small" @change="onCalcChange(row, 'assetGroup')" />
            <span v-else>{{ row.assetGroup }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCalcChange(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairValueLessDisposal" label="公允-处置费" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.fairValueLessDisposal" :controls="false" size="small" @change="onCalcChange(row, 'fairValueLessDisposal')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fairValueLessDisposal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="dcfValue" label="DCF现值" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源H1-15 DCF模型">{{ fmtAmt(row.dcfValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可收回金额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="MAX(公允-处置,DCF)">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值金额" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.impairmentAmount > 0 }]" title="MAX(账面-可收回,0)">
              {{ fmtAmt(row.impairmentAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="alreadyProvided" label="已计提" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.alreadyProvided" :controls="false" size="small" @change="onCalcChange(row, 'alreadyProvided')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.alreadyProvided) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="totals-bar">
        <span>应计提减值合计: <b class="amount-cell">{{ fmtAmt(state.impairmentTotal.value) }}</b></span>
        <span>已计提合计: <b class="amount-cell">{{ fmtAmt(state.alreadyProvidedTotal.value) }}</b></span>
        <span>差异: <b :class="['amount-cell', { 'error-amount': Math.abs(state.totalDiff.value) > 0.01 }]">{{ fmtAmt(state.totalDiff.value) }}</b></span>
      </div>
    </el-card>

    <!-- 审计说明/结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input v-model="impairmentConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="减值测试审计结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>6项迹象全选"N"→无需测试→直接结论"不存在减值"</li>
        <li>任一选"Y"→必须进行测试→填写测算表→联动H1-15 DCF</li>
        <li>可收回金额 = MAX(公允-处置费, DCF现值)，取两者较大</li>
        <li>减值金额 = MAX(账面-可收回, 0)，不可为负</li>
        <li>闲置资产清单从H1-4自动带入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Impairment } from '../../composables/useH1Impairment'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const impairmentConclusion = ref('')

const state = useH1Impairment(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

const hasImpairmentSign = computed(() => state.indications.value.some((i: any) => i.result === 'Y'))
const signCount = computed(() => state.indications.value.filter((i: any) => i.result === 'Y').length)

function onIndicationChange(row: any, field: string) { state.updateIndication(row.key, field as any, row[field]) }
function onCalcChange(row: any, field: string) { state.updateCalcRow(row.rowId, field as any, row[field]) }

async function handleAddCalcRow() {
  const { value: name } = await ElMessageBox.prompt('资产组名称', '新增减值测算', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addCalcRow(name)
}
function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.indication-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.indication-summary { margin-top: 12px; }
.calc-card { margin-bottom: 16px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
