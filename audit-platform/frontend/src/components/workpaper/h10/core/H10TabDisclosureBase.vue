<template>
  <div class="h10-disclosure" :data-testid="variant === 'listed' ? 'h10-disclosure-listed' : 'h10-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" data-testid="h10-disclosure-ai-btn" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'H10-disclosure-listed' : 'H10-disclosure-soe'" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 资产处置损益（6115）本期/上期发生额应与 H10-1 审定表一致，可点击"刷新"同步审定数。</p>
        <p>2. 依据财会〔2017〕30 号《一般企业财务报表格式》，资产处置损益在利润表单独列示；附注应披露处置资产的类别、金额及计算方式。</p>
        <p v-if="variant === 'soe'">3. 国企/上市口径需按《公开发行证券的公司信息披露解释性公告第 1 号——非经常性损益》区分是否计入非经常性损益（处置长期资产的损益通常属非经常性损益）。</p>
        <p v-else>3. 上市公司口径需关注处置损益对每股收益、扣非净利润的影响及重大处置事项的单独披露。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      :title="`审计目标：核实资产处置损益附注披露的完整性与准确性，本期/上期发生额与审定表一致${variant === 'soe' ? '，非经常性损益列示恰当' : '，重大处置事项披露充分'}。`" />

    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6115 发生额）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>
    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      :row-class-name="({ row }) => row.rowKey === 'total' ? 'total-row' : ''">
      <el-table-column label="项目" prop="label" min-width="220" fixed />
      <el-table-column label="本期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="variant === 'soe'" label="非经常性" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.nonRecurringAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'nonRecurringAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.nonRecurringAmount ?? 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
    </el-table>
    <el-card shadow="never" class="note-card">
      <template #header>附注文本</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述附注披露与审定表的核对情况、披露项目的完整性及口径判断。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：附注披露完整、准确，与审定表勾稽一致，列报口径恰当。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted, watch } from 'vue'
import { useH10Disclosure } from '../../composables/useH10Disclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useH10Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
})

// 多变体（listed/soe）后缀区分 item_id，防串写
const auditNote = ref('')
const auditConclusion = ref('')
const noteKey = () => `H10-disclosure-${props.variant}-audit-note`
const conclusionKey = () => `H10-disclosure-${props.variant}-audit-conclusion`

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const key = noteKey()
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: val })
  props.debouncedSave(key, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const key = conclusionKey()
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: val })
  props.debouncedSave(key, { conclusion: null, remark: val })
}

function hydrate(): void {
  const n = props.allResponses.get(noteKey())
  auditNote.value = n?.remark ?? ''
  const c = props.allResponses.get(conclusionKey())
  auditConclusion.value = c?.remark ?? ''
}

onMounted(hydrate)
watch(() => props.variant, hydrate)

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-disclosure { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; }
.sync-hint { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
.guidance-details { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
</style>
