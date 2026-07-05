<template>
  <div class="g5-reversal-writeoff">
    <div class="segment-tabs">
      <el-segmented v-model="rw.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-11" @imported="onImported" />
        <el-button v-if="rw.activeTab.value === 'reversal'" size="small" type="primary" plain @click="rw.addReversalRow()" :disabled="props.readonly">+ 新增转回</el-button>
        <el-button v-else size="small" type="primary" plain @click="rw.addWriteoffRow()" :disabled="props.readonly">+ 新增核销</el-button>
      </div>
    </div>

    <el-table v-show="rw.activeTab.value === 'reversal'" :data="rw.reversalRows.value" border stripe style="width:100%;font-size:13px" max-height="450"
      highlight-current-row @current-change="onRowChange"
      :row-class-name="({ row }) => !row.isValid ? 'row-error' : row.isRelatedParty ? 'row-related' : ''">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="债务人" min-width="120">
        <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="累计计提" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.accumulatedProvision" size="small" :controls="false" :disabled="props.readonly" @change="rw.recalcReversal(row)" /></template>
      </el-table-column>
      <el-table-column label="转回金额" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.reversalAmount" size="small" :controls="false" :disabled="props.readonly" @change="rw.recalcReversal(row)" /></template>
      </el-table-column>
      <el-table-column label="关联交易" width="80">
        <template #default="{ row }"><el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="原因" min-width="120">
        <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
    </el-table>

    <el-table v-show="rw.activeTab.value === 'writeoff'" :data="rw.writeoffRows.value" border stripe style="width:100%;font-size:13px" max-height="450"
      highlight-current-row @current-change="onRowChange"
      :row-class-name="({ row }) => row.isRelatedParty ? 'row-related' : ''">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="债务人" min-width="120">
        <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="核销金额" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.writeoffAmount" size="small" :controls="false" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="审批状态" width="100">
        <template #default="{ row }"><el-input v-model="row.approvalStatus" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="关联交易" width="80">
        <template #default="{ row }"><el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="原因" min-width="120">
        <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
    </el-table>

    <div v-if="rw.invalidReversals.value.length" class="error-bar">
      ⚠ {{ rw.invalidReversals.value.length }} 条转回金额超过累计计提
    </div>
  </div>
</template>

<script setup lang="ts">
import { useG5ReversalWriteoff } from '../../composables/useG5ReversalWriteoff'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const rw = useG5ReversalWriteoff()
const tabOptions = [{ label: '转回检查', value: 'reversal' }, { label: '核销检查', value: 'writeoff' }]

function onRowChange(row: any) {
  if (!row) return
  const idx = rw.activeTab.value === 'reversal'
    ? rw.reversalRows.value.findIndex(r => r.id === row.id)
    : rw.writeoffRows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) rw.activeRowIndex.value = idx
}

function onImported(rows: unknown[]) {
  const reversal = (rows as any[]).filter(r => r.section === 'reversal' || r.checkZone === 'reversal')
  const writeoff = (rows as any[]).filter(r => r.section === 'writeoff' || r.checkZone === 'writeoff')
  if (reversal.length) rw.loadReversalRows(reversal)
  if (writeoff.length) rw.loadWriteoffRows(writeoff)
  if (!reversal.length && !writeoff.length && Array.isArray(rows)) rw.loadReversalRows(rows as any)
}
</script>

<style scoped>
.g5-reversal-writeoff { font-size: 13px; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; display: flex; gap: 8px; }
.error-bar { margin-top: 8px; padding: 8px 12px; background: #fef0f0; color: #f56c6c; font-size: 12px; border-radius: 4px; }
:deep(.row-error) { background-color: #fef0f0 !important; }
:deep(.row-related) { background-color: #fdf6ec !important; }
</style>
