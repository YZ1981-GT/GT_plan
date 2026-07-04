<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>{{ ic.title }}</h3><span class="code">{{ ic.sheetCode }}</span></div>
      <span :class="['coverage', { warn: ic.isCoverageLow.value }]">覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%</span>
    </header>
    <div class="meta-bar">
      <span>账面总额<el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly" @change="(v: number) => ic.updateBookTotal(v ?? 0)" /></span>
      <span>已查 {{ ic.checkedTotal.value.toLocaleString() }}</span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="ic.addRow()">+ 新增</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-35"
        :disabled="isReadonly"
        ai-section="inspection-conclusion"
        :existing-content="ic.auditNote.value"
        :related-context="{ coverageRatio: ic.coverageRatio.value }"
        ai-title="AI 生成 · 委外加工检查结论"
        review-section="F2-35-conclusion"
        @ai-filled="(t: string) => { ic.auditNote.value = t }"
      />
    </div>
    <el-table :data="ic.rows.value" border size="small" max-height="440">
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column label="委托方" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.party" size="small" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
          <span v-else>{{ row.party }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.docNo" size="small" @change="(v: string) => ic.updateRow(row.id, { docNo: v })" />
          <span v-else>{{ row.docNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="账龄(天)" width="85">
        <template #default="{ row }">
          <el-input-number :model-value="row.daysOutstanding ?? 0" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ic.updateRow(row.id, { daysOutstanding: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="95">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <footer class="footer"><h4>检查结论</h4><el-input v-model="ic.auditNote.value" type="textarea" :rows="2" :disabled="isReadonly" /></footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2SubcontractCheck } from '../../composables/useF2InspectionCheck'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const ic = useF2SubcontractCheck({ allResponses: toRef(props, 'allResponses'), isReadonly: toRef(props, 'isReadonly') })
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.meta-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.coverage { font-weight: 600; }
.coverage.warn { color: #e6a23c; }
</style>
