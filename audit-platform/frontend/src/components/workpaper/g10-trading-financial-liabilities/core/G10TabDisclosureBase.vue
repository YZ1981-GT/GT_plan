<template>
  <div class="g10-disclosure" :data-testid="variant === 'listed' ? 'g10-disclosure-listed-table' : 'g10-disclosure-soe-table'">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G10-disclosure-listed' : 'G10-disclosure-soe'" />
      </div>
    </div>
    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（2101）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>
    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px"
      :max-height="variant === 'soe' ? 400 : 480"
      :row-class-name="({ row }) => row.rowKey === 'total' ? 'total-row' : ''">
      <el-table-column label="项目" prop="label" min-width="220" fixed />
      <el-table-column label="期末余额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>
    <el-card shadow="never" class="note-card">
      <template #header>附注文本</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>依据 CAS 37《金融工具列报》编制附注；期末余额应与 G10-1 审定表审定数（2101）及试算平衡表勾稽。</p>
        <p>披露交易性金融负债的构成、公允价值层次、期末与期初变动原因；含衍生工具的须说明性质与风险。</p>
        <p>{{ variant === 'listed' ? '上市主体须按监管口径披露公允价值计量层次转移及重大不可观察输入值。' : '国有企业须结合国资监管要求披露相关金融负债管理情况。' }}</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG10Disclosure } from '../../composables/useG10Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useG10Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g10-disclosure { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.sync-hint { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
</style>
