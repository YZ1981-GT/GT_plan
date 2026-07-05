<template>

  <div class="g14-disclosure">

    <div class="section-head">

      <h3 class="sheet-title">{{ dis.title.value }}</h3>

      <div class="head-actions">

        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly"

          @click="dis.generateAiConclusion()">🤖 AI辅助</el-button>

        <GtReviewTrigger section-id="G14-disclosure-listed" />

      </div>

    </div>



    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">

      已同步审定数（6702）：{{ fmt(dis.adjudicatedAmount.value) }}

      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>

    </el-alert>



    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      data-testid="g14-disclosure-listed-table"

      :row-class-name="rowClassName">

      <el-table-column label="项目" prop="label" min-width="200" fixed />

      <el-table-column label="本期发生额" width="140" align="right">

        <template #default="{ row }">

          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small"

            :controls="false" style="width:100%"

            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />

          <span v-else>{{ fmt(row.currentAmount) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="上期发生额" width="140" align="right">

        <template #default="{ row }">

          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small"

            :controls="false" style="width:100%"

            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />

          <span v-else>{{ fmt(row.priorAmount) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="变动额" width="120" align="right">

        <template #default="{ row }">

          <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="备注" min-width="100">

        <template #default="{ row }">

          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"

            @change="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />

          <span v-else>{{ row.remark }}</span>

        </template>

      </el-table-column>

    </el-table>



    <el-card shadow="never" class="note-card">

      <template #header>附注说明</template>

      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"

        :disabled="isReadonly" placeholder="信用减值损失附注披露说明…"

        @update:model-value="dis.updateNoteText" />

    </el-card>



    <GCycleDisclosureExtras

      cycle-label="G14 信用减值损失"

      :account-code="G14_ACCOUNT_CODE"

      :adjudicated-amount="dis.adjudicatedAmount.value"

      :disclosure-total="dis.totalRow.value.currentAmount"

      :formula-map="[...G14_DISCLOSURE_FORMULA_MAP]"

      :manual-formula-notes="['G14-2 各行与 D1/D2/D5/G4/G5 ECL 索引交叉验证']"

      :is-readonly="isReadonly"

      @refresh="dis.pullLatestAdjudicated()"

    />

  </div>

</template>



<script setup lang="ts">

import { toRef, computed } from 'vue'

import { useG14Disclosure } from '../composables/useG14Disclosure'

import { G14_ACCOUNT_CODE, G14_DISCLOSURE_FORMULA_MAP } from '../composables/g14Constants'

import type { ChecklistResponse } from '../composables/useF1FormData'

import GCycleDisclosureExtras from '../shared/GCycleDisclosureExtras.vue'

import GtReviewTrigger from '../GtReviewTrigger.vue'



const props = defineProps<{

  allResponses: Map<string, ChecklistResponse>

  wpId: string

  isReadonly: boolean

  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void

}>()



const dis = useG14Disclosure({

  variant: 'listed',

  allResponses: toRef(props, 'allResponses'),

  wpId: toRef(props, 'wpId'),

  isReadonly: computed(() => props.isReadonly),

  debouncedSave: props.debouncedSave,

})



function rowClassName({ row }: { row: { rowKey: string } }): string {

  return row.rowKey === 'total' ? 'g14-row-total' : ''

}



function fmt(v: number): string {

  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

}

</script>



<style scoped>

.g14-disclosure { padding: 12px; font-size: 13px; }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }

.sheet-title { margin: 0; font-size: 15px; }

.head-actions { display: flex; gap: 8px; }

.sync-hint { margin-bottom: 12px; }

.formula-cell { border-bottom: 1px dashed #909399; }

.note-card { margin-top: 12px; }

:deep(.g14-row-total) { font-weight: 700; background: #f5f7fa; }

</style>

