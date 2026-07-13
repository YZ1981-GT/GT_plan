<template>
  <div class="g14-detail" data-testid="g14-detail">
    <div class="g14-toolbar tab-toolbar">
      <h3 class="g14-title">G14-2 信用减值损失明细表</h3>
      <div class="g14-actions">
        <GtIndexChip value="wp:G14-2" />
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g14" sheet="G14-2"
          :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G14-2-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：核对 9 类减值来源本期计提/转回/转销与减值准备滚动勾稽（期末=期初+计提+转回−转销），
        验证审定数=计入损益，并与各源科目（D1/D2/D5/G4/G5）ECL 交叉一致（CAS 22 预期信用损失 ECL）。
      </template>
    </el-alert>

    <el-alert v-if="detail.detailTotalMismatch.value" type="error" :closable="false" show-icon
      title="明细表合计审定数与计入损益合计不一致，请核查各行核对列" style="margin-bottom:8px" />

    <el-alert
      v-if="extCross.crossMessage.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g14-detail-ext-cross-bar"
    >
      {{ extCross.crossMessage.value }}
    </el-alert>
    <el-alert
      v-else-if="extCross.isReconciled.value"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g14-detail-ext-cross-ok"
    >
      G14-2 与源科目 ECL 数据一致
    </el-alert>

    <el-segmented v-model="activeTab" :options="tabOptions" size="small" data-testid="g14-detail-tab" />

    <el-table :data="displayRows" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      :row-class-name="rowClassName" data-testid="g14-detail-table">
      <el-table-column label="项目" prop="label" width="156" fixed>
        <template #default="{ row }">
          <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G14-detail" :row-key="row.rowKey" />
          {{ row.label }}
        </template>
      </el-table-column>

      <template v-if="activeTab === 'current'">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentUnadjusted"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAdjustment"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentAdjustment', v ?? 0)" />
            <span v-else>{{ fmt(row.currentAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + 调整">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对应科目" prop="provisionAccount" min-width="140" />
        <el-table-column label="ECL来源" width="108" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.rowKey !== 'total' && eclRef(row.rowKey)" :value="eclRef(row.rowKey)" />
            <span v-else-if="row.rowKey === 'total'">—</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => detail.updateCell(row.rowKey, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="期初余额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.openingProvision"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'openingProvision', v ?? 0)" />
            <span v-else>{{ fmt(row.openingProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentProvision"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentProvision', v ?? 0)" />
            <span v-else>{{ fmt(row.currentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转回" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentReversal"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentReversal', v ?? 0)" />
            <span v-else>{{ fmt(row.currentReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转销" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentWriteoff"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentWriteoff', v ?? 0)" />
            <span v-else>{{ fmt(row.currentWriteoff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.closingProvision"
              size="small" :controls="false" style="width:100%"
              :class="{ 'cell-error': !row.rollForwardBalanced }"
              @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'closingProvision', v ?? 0)" />
            <span v-else :class="{ 'cell-error': !row.rollForwardBalanced }"
              :title="!row.rollForwardBalanced ? '滚动不平衡' : ''">
              {{ fmt(row.closingProvision) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="计入损益" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="计提+转回（转回可录入负数）">{{ fmt(row.profitLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对" width="72" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rowKey !== 'total'" :type="row.reconciled ? 'success' : 'danger'" size="small">
              {{ row.reconciled ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="录入本期各减值来源计提/转回的审计说明…" @update:model-value="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="录入审计结论…" @update:model-value="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. 13 列拆为「本期数 / 减值准备滚动」两 Tab；固定 9 类行 + 合计，与 G14-1 一一对应。</p>
      <p>2. 期末 = 期初 + 计提 + 转回(带符号) - 转销；核对列验证审定数 = 计入损益。</p>
      <p>3. CAS 22 预期信用损失（ECL）：坏账/减值准备按三阶段（12 个月 / 整个存续期 ECL）计量，本期计提计入信用减值损失（6702，借方），转回冲减（贷方）。</p>
      <p>4. 各行「ECL 来源」chip 指向 D1/D2/D5/G4/G5 等源科目底稿，用于交叉验证减值基数一致性。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onMounted } from 'vue'
import { useG14Detail } from '../composables/useG14Detail'
import { useG14ExternalCross } from '../composables/useG14ExternalCross'
import { G14_ECL_CROSS_REF } from '../composables/g14Constants'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const activeTab = ref<'current' | 'provision'>('current')
const tabOptions = [
  { label: '本期数', value: 'current' },
  { label: '减值准备', value: 'provision' },
]

const detail = useG14Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const extCross = useG14ExternalCross({
  allResponses: toRef(props, 'allResponses'),
  detailRows: computed(() => detail.rows.value),
  debouncedSave: props.debouncedSave,
})

const displayRows = computed(() => [...detail.rows.value, detail.totalRow.value])

const NOTE_KEY = 'G14-2-detail-audit-note'
const CONCLUSION_KEY = 'G14-2-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function rowClassName({ row }: { row: { rowKey: string; reconciled?: boolean; rollForwardBalanced?: boolean } }): string {
  if (row.rowKey === 'total') return 'g14-row-total'
  if (row.reconciled === false || row.rollForwardBalanced === false) return 'g14-row-warn'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function eclRef(rowKey: string): string {
  return G14_ECL_CROSS_REF[rowKey] ?? ''
}
</script>

<style scoped>
.cross-alert { margin-bottom: 8px; }
.audit-objective { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.g14-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g14-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.g14-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.g14-title { margin: 0; font-size: 15px; font-weight: 600; }
.audit-note-card { margin-top: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.cell-error { color: #f56c6c; font-weight: 600; }
:deep(.g14-row-total) { font-weight: 700; background: #f5f7fa; }
:deep(.g14-row-warn) { background: #fef0f0 !important; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
</style>
