<template>
  <div class="h5-tab-disposal-check">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-8 减少检查（联动H10）— 处置损益合计 {{ fmtAmt(state.totalGainLoss.value) }}</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-8')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalReason" label="处置原因" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalReason" size="small" @change="state.updateCell(row.rowId, 'disposalReason', $event)">
              <el-option label="报废" value="报废" /><el-option label="出售" value="出售" /><el-option label="转让" value="转让" />
            </el-select>
            <span v-else>{{ row.disposalReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="state.updateCell(row.rowId, 'originalCost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepletion" label="累计折耗" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accDepletion" :controls="false" size="small" @change="state.updateCell(row.rowId, 'accDepletion', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletion) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.netValue" :controls="false" size="small" @change="state.updateCell(row.rowId, 'netValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalIncome" label="处置收入" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.disposalIncome" :controls="false" size="small" @change="state.updateCell(row.rowId, 'disposalIncome', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'loss': row.disposalGainLoss < 0 }" title="损益=收入-净值">{{ fmtAmt(row.disposalGainLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="联动H10" width="80" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.linkedH10" value="H10" :validate="false" @click="state.navigateToH10(row.rowId)" />
            <el-switch v-if="!isReadonly" v-model="row.linkedH10" size="small" @change="state.updateCell(row.rowId, 'linkedH10', $event)" />
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增减少项</el-button>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>处置损益=处置收入-净值(原值-累计折耗)</li>
        <li>联动H10：标记后可一键跳转到H10资产处置损益底稿</li>
        <li>减少合计应与H5-2明细表/H5-1审定表贷方发生一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5DisposalCheck } from '../../composables/useH5DisposalCheck'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5DisposalCheck({
  allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'),
  onSave: () => {}, onNavigateSheet: (s) => emit('navigate-sheet', s),
})

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增减少项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addRow(value)
}
function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.loss { color: var(--el-color-danger); }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
