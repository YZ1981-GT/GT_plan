<template>
  <div class="h5-tab-impairment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：测算油气资产组减值损失与本期补提，确认减值确认充分且一经确认不得转回(CAS8)。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-14" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.testRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-14 减值测算（本期补提 {{ fmtAmt(state.totalAdditionalImpairment.value) }}）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-14')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.testRows.value" border stripe size="small" class="impair-table">
        <el-table-column prop="assetGroup" label="资产组" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetGroup" size="small" @change="state.updateTestRow(row.rowId, 'assetGroup', $event)" />
            <span v-else>{{ row.assetGroup }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田" min-width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oilField" size="small" @change="state.updateTestRow(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.bookValue" size="small" @change="state.updateTestRow(row.rowId, 'bookValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recoverableAmount" label="可收回金额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.recoverableAmount" size="small" @change="state.updateTestRow(row.rowId, 'recoverableAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值损失" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'has-loss': row.impairmentLoss > 0 }" title="=max(0, 账面-可收回)">{{ fmtAmt(row.impairmentLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorImpairment" label="已确认减值" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.priorImpairment" size="small" @change="state.updateTestRow(row.rowId, 'priorImpairment', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorImpairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期补提" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'has-loss': row.additionalImpairment > 0 }" title="=max(0, 减值损失-已确认)">{{ fmtAmt(row.additionalImpairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateTestRow(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="填写减值测算审计结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值损失=max(0, 账面价值-可收回金额)</li>
        <li>本期补提=max(0, 减值损失-已确认减值)</li>
        <li>油气资产减值一经确认不得转回(CAS8)</li>
        <li>可收回金额详见H5-15可收回金额测试表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Impairment } from '../../composables/useH5Impairment'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Impairment({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.impair-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.has-loss { color: var(--el-color-danger); font-weight: 600; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
