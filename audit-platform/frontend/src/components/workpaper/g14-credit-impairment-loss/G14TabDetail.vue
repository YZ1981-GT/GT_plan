<template>
  <div class="g14-detail" data-testid="g14-detail">
    <div class="g14-toolbar tab-toolbar">
      <h3 class="g14-title">G14-2 信用减值损失明细表</h3>
      <div class="g14-actions">
        <GtIndexChip value="wp:G14-2" />
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g14-fill-closing"
          @click="detail.fillClosingFromRollForward()"
        >
          推算期末
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g14-fill-unaudited"
          @click="detail.fillUnauditedFromProfitLoss()"
        >
          回填未审
        </el-button>
        <el-button
          size="small"
          :loading="detail.tbLoading.value"
          data-testid="g14-fetch-tb-closing"
          @click="detail.fetchProvisionClosingFromTb(true)"
        >
          取数对账
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g14-apply-tb-closing"
          @click="detail.applyTbClosingToProvision()"
        >
          写入期末
        </el-button>
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g14" sheet="G14-2"
          :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G14-2-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        <div class="obj-title">一、审计目标</div>
        <ol class="obj-list">
          <li>确认损益表中记录的信用减值损失确已发生、与被审计单位有关，且记录于恰当的账户。</li>
          <li>确认所有应记录的信用减值损失均已记录，相关披露已包含在财务报表中。</li>
          <li>确认与信用减值损失有关的金额及其他数据已恰当记录，计量与披露描述恰当。</li>
        </ol>
      </template>
    </el-alert>

    <el-alert v-if="detail.detailTotalMismatch.value" type="error" :closable="false" show-icon
      title="明细表合计审定数与计入损益合计不一致，请核查各行核对列" style="margin-bottom:8px" />
    <el-alert v-if="detail.anyRollForwardUnbalanced.value" type="warning" :closable="false" show-icon
      title="存在减值准备滚动不平衡行（期末≠期初+计提−转回−转销+其他变动），期末单元格已标红"
      style="margin-bottom:8px" data-testid="g14-rollforward-warn" />
    <el-alert v-if="detail.anyTbClosingMismatch.value" type="warning" :closable="false" show-icon
      title="存在期末余额与试算准备/OCI 期末不一致的行，「试算期末」列已标红"
      style="margin-bottom:8px" data-testid="g14-tb-closing-warn" />

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

    <el-table :data="displayRows" border size="small" style="font-size:13px;margin-top:8px" max-height="560"
      :row-class-name="rowClassName" data-testid="g14-detail-table">
      <el-table-column label="项目" prop="label" width="168" fixed>
        <template #default="{ row }">
          <GtReviewDot v-if="row.rowKey !== 'total'" row-prefix="G14-detail" :row-key="row.rowKey" />
          <span>{{ row.label }}</span>
          <el-tooltip v-if="isG14OciCounterpart(row.rowKey)" :content="ociHint(row.rowKey)" placement="top">
            <el-tag size="small" type="warning" class="oci-tag" data-testid="g14-oci-tag">OCI</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 全表 / 本期数：损益侧 -->
      <template v-if="activeTab === 'all' || activeTab === 'current'">
        <el-table-column label="本期数" align="center">
          <el-table-column label="未审数" width="96" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentUnadjusted"
                size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentUnadjusted', v ?? 0)" />
              <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整数" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAdjustment"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentAdjustment', v ?? 0)" />
              <span v-else>{{ fmt(row.currentAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定 = 未审 + 调整">{{ fmt(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="对应科目" min-width="140">
          <template #default="{ row }">
            <span>{{ row.provisionAccount || '—' }}</span>
            <div v-if="isG14OciCounterpart(row.rowKey)" class="oci-hint">{{ ociHint(row.rowKey) }}</div>
          </template>
        </el-table-column>
      </template>

      <!-- 全表 / 减值准备：资产侧滚动 -->
      <template v-if="activeTab === 'all' || activeTab === 'provision'">
        <el-table-column label="对应科目-减值准备" align="center">
          <el-table-column label="期初余额" width="92" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.openingProvision"
                size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'openingProvision', v ?? 0)" />
              <span v-else>{{ fmt(row.openingProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期计提" width="88" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentProvision"
                size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentProvision', v ?? 0)" />
              <span v-else>{{ fmt(row.currentProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期转回" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentReversal"
                size="small" :controls="false" style="width:100%" placeholder="正数"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentReversal', v ?? 0)" />
              <span v-else>{{ fmt(row.currentReversal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期转销" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentWriteoff"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'currentWriteoff', v ?? 0)" />
              <span v-else>{{ fmt(row.currentWriteoff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他变动" width="88" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.otherMovement"
                size="small" :controls="false" style="width:100%"
                title="合并转入/转出、重分类等不影响损益的准备变动"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'otherMovement', v ?? 0)" />
              <span v-else>{{ fmt(row.otherMovement) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="96" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.closingProvision"
                size="small" style="width:100%"
                :class="{ 'cell-error': !row.rollForwardBalanced || (row.tbClosing != null && !row.tbClosingMatched) }"
                :title="closingTitle(row)"
                @update:model-value="(v: number) => detail.updateCell(row.rowKey, 'closingProvision', v ?? 0)" />
              <span v-else :class="{ 'cell-error': !row.rollForwardBalanced || (row.tbClosing != null && !row.tbClosingMatched) }"
                :title="closingTitle(row)">
                {{ fmt(row.closingProvision) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="试算期末" width="96" align="right">
            <template #default="{ row }">
              <span
                v-if="row.rowKey !== 'total'"
                :class="{ 'cell-error': row.tbClosing != null && !row.tbClosingMatched, 'formula-cell': true }"
                :title="row.tbClosing == null ? '未取数或未匹配科目' : `试算准备/OCI期末；差 ${fmt(row.tbClosingVariance)}`"
                data-testid="g14-tb-closing-cell"
              >
                {{ row.tbClosing == null ? '—' : fmt(row.tbClosing) }}
              </span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="计入损益" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="计提 − 转回（转回正数）">{{ fmt(row.profitLoss) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="核对" width="64" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rowKey !== 'total'" :type="row.reconciled ? 'success' : 'danger'" size="small"
              :title="row.reconciled ? '审定数 = 计入损益' : `审定 ${fmt(row.currentAudited)} ≠ 损益 ${fmt(row.profitLoss)}`">
              {{ row.reconciled ? '✓' : '✗' }}
            </el-tag>
            <el-tag v-else :type="row.reconciled ? 'success' : 'danger'" size="small">
              {{ row.reconciled ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="activeTab === 'all' || activeTab === 'current'" label="ECL来源" width="100" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.rowKey !== 'total' && eclRef(row.rowKey)" :value="eclRef(row.rowKey)" />
          <span v-else-if="row.rowKey === 'total'">—</span>
        </template>
      </el-table-column>
      <el-table-column v-if="activeTab === 'all' || activeTab === 'current'" label="索引号" width="96">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.indexRef" size="small"
            @change="(v: string) => detail.updateCell(row.rowKey, 'indexRef', v)" />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header>三、审计说明</template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="说明各减值来源计提/转回依据、与源科目 ECL 交叉差异及重大转销事项…"
        @update:model-value="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header>四、审计结论</template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="经审计，信用减值损失列报是否在所有重大方面公允反映…"
        @update:model-value="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>📋 编制提示（二、审计过程）</summary>
      <p>1. 默认「全表」视图对齐致同 xlsx：损益侧本期数与资产侧减值准备滚动同屏，核对列验证 <b>审定数 = 计入损益</b>。</p>
      <p>2. 公式：计入损益 = 计提 − 转回（转回正数）；期末 = 期初 + 计提 − 转回 − 转销 + 其他变动。</p>
      <p>3. 「合同资产减值损失」单独成行（1142）；「取数对账」从试算拉取准备/OCI/预计负债期末，「写入期末」可回填。</p>
      <p>4. 带 OCI 标签的行（其他债权投资）：对方计入其他综合收益-信用减值准备，而非坏账准备贷方。</p>
      <p>5. 建议路径：取数对账 → 填计提/转回 → 推算期末 → 回填未审 → 与 D1/D2/D5/D6/F1/G4/G5/G6 ECL 交叉。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { computed, ref, toRef, onMounted } from 'vue'
import { useG14Detail, type G14DetailRow } from '../composables/useG14Detail'
import { useG14ExternalCross } from '../composables/useG14ExternalCross'
import { G14_ECL_CROSS_REF, g14CounterpartHint, isG14OciCounterpart } from '../composables/g14Constants'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const activeTab = ref<'all' | 'current' | 'provision'>('all')
const tabOptions = [
  { label: '全表', value: 'all' },
  { label: '本期数', value: 'current' },
  { label: '减值准备', value: 'provision' },
]

const detail = useG14Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  projectId: toRef(props, 'projectId'),
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

function rowClassName({ row }: { row: G14DetailRow }): string {
  if (row.rowKey === 'total') return 'g14-row-total'
  if (row.reconciled === false || row.rollForwardBalanced === false) return 'g14-row-warn'
  if (row.tbClosing != null && !row.tbClosingMatched) return 'g14-row-warn'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function eclRef(rowKey: string): string {
  return G14_ECL_CROSS_REF[rowKey] ?? ''
}

function ociHint(rowKey: string): string {
  return g14CounterpartHint(rowKey)
}

function closingTitle(row: G14DetailRow): string {
  const parts: string[] = []
  if (!row.rollForwardBalanced) {
    parts.push(`滚动差 ${fmt(row.rollForwardVariance)}（推算 ${fmt(row.closingComputed)}）`)
  }
  if (row.tbClosing != null && !row.tbClosingMatched) {
    parts.push(`与试算差 ${fmt(row.tbClosingVariance)}`)
  }
  return parts.join('；') || '与滚动公式及试算准备期末对账'
}
</script>

<style scoped>
.cross-alert { margin-bottom: 8px; }
.audit-objective { margin-bottom: 8px; }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 0; padding-left: 1.2em; font-size: 12px; line-height: 1.55; font-weight: 400; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.g14-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g14-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.g14-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.g14-title { margin: 0; font-size: 15px; font-weight: 600; }
.audit-note-card { margin-top: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.cell-error { color: #f56c6c; font-weight: 600; }
.oci-tag { margin-left: 4px; vertical-align: middle; }
.oci-hint { font-size: 11px; color: #e6a23c; line-height: 1.3; margin-top: 2px; }
:deep(.g14-row-total) { font-weight: 700; background: #f5f7fa; }
:deep(.g14-row-warn) { background: #fef0f0 !important; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
</style>
