<template>
  <div class="g13-detail" data-testid="g13-detail">
    <div class="g13-toolbar tab-toolbar">
      <h3 class="g13-title">G13-2 公允价值变动明细表</h3>
      <div class="g13-actions">
        <el-input v-model="searchQuery" placeholder="搜索工具名/科目/类型…" size="small"
          clearable style="width:200px" data-testid="g13-detail-search" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">+ 新增行</el-button>
        <el-tag size="small" type="info" effect="plain" data-testid="g13-detail-count">共 {{ detail.rows.value.length }} 行</el-tag>
        <GtIndexChip value="wp:G13-2" :validate="false" />
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g13" sheet="G13-2"
          :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G13-2-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective"
      title="审计目标：验证以公允价值计量的金融工具其公允价值变动收益（6101）计量准确、期末计价恰当，并与 G1/G8/G9/G10 源科目 FV 变动勾稽一致（CAS 39 公允价值计量）" />

    <el-alert v-if="detail.hasFvMismatch.value" type="error" :closable="false" show-icon
      title="存在 FV变动与审定数不一致的行，请核查" style="margin-bottom:8px" />

    <el-alert
      v-if="extCross.crossMessage.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g13-detail-ext-cross-bar"
    >
      {{ extCross.crossMessage.value }}
    </el-alert>
    <el-alert
      v-else-if="extCross.isReconciled.value"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g13-detail-ext-cross-ok"
    >
      G13-2 与源科目（G1/G8/G9/G10）FV 变动一致
    </el-alert>

    <el-segmented v-model="activeTab" :options="tabOptions" size="small" data-testid="g13-detail-tab" />

    <el-table :data="displayRows" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      :row-class-name="rowClassName" data-testid="g13-detail-table">
      <el-table-column label="序号" prop="seq" width="56" align="center" fixed />

      <template v-if="activeTab === 'basic'">
        <el-table-column label="金融工具名称" min-width="140">
          <template #default="{ row }">
            <template v-if="row.rowId !== 'total'">
              <GtReviewDot row-prefix="G13-detail" :row-key="row.rowId" />
            </template>
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.instrumentName" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'instrumentName', v)" />
            <span v-else>{{ row.instrumentName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所属科目" width="168">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.belongAccount" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'belongAccount', v)">
              <el-option v-for="a in detail.G13_BELONG_ACCOUNTS" :key="a" :label="G13_BELONG_ACCOUNT_LABELS[a] ?? a" :value="a" />
              <el-option label="其他" value="" />
            </el-select>
            <span v-else>{{ row.belongAccount ? (G13_BELONG_ACCOUNT_LABELS[row.belongAccount] ?? row.belongAccount) : '其他' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金融工具类型" width="120">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.instrumentType" size="small" filterable allow-create
              @change="(v: string) => detail.updateCell(row.rowId, 'instrumentType', v)">
              <el-option v-for="t in G13_INSTRUMENT_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.instrumentType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="源科目索引" width="108">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.sourceIndex" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'sourceIndex', v)" />
            <GtIndexChip v-else-if="row.sourceIndex" :value="row.sourceIndex" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="期初FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.openingFairValue"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'openingFairValue', v ?? 0)" />
            <span v-else>{{ fmt(row.openingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.closingFairValue"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'closingFairValue', v ?? 0)" />
            <span v-else>{{ fmt(row.closingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="FV变动 = 期末 - 期初">{{ fmt(row.fvChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期未审" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.currentUnadjusted"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'currentUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.adjustment"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'adjustment', v ?? 0)" />
            <span v-else>{{ fmt(row.adjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'cell-error': row.rowId !== 'total' && !row.fvReconciled }]"
              title="审定 = 未审 + 调整">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="交叉验证" width="100">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.crossVerification" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'crossVerification', v)">
              <el-option v-for="o in G13_CROSS_VERIFY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-tag v-else-if="row.rowId !== 'total'" size="small"
              :type="row.crossVerification === 'consistent' ? 'success' : row.crossVerification === 'inconsistent' ? 'danger' : 'info'">
              {{ G13_CROSS_VERIFY_OPTIONS.find(o => o.value === row.crossVerification)?.label ?? '待验证' }}
            </el-tag>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="row.rowId !== 'total'" title="确认删除？" @confirm="detail.removeRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="Object.keys(detail.groupSubtotals.value).length" shadow="never" class="group-card">
      <template #header>按所属科目分组小计</template>
      <el-table :data="groupRows" border size="small" style="font-size:13px" data-testid="g13-detail-groups">
        <el-table-column label="分组" prop="label" min-width="140" />
        <el-table-column label="审定数合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.currentAudited) }}</template>
        </el-table-column>
        <el-table-column label="FV变动合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.fvChange) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：可概述公允价值变动明细的测试情况、FV 变动与源科目（G1/G8/G9/G10）交叉验证结果、拟调整/未调整事项及其影响。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应予调整外，其余未见异常。C、由于存在重大未调整事项，不可确认。"
        @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. 12 列拆为「基础信息 / FV与审定」两 Tab；FV变动 = 期末 - 期初，审定 = 未审 + 调整。</p>
      <p>2. 选择所属科目后自动填充源科目索引；与 G1/G8/G9/G10 交叉验证后汇总至 G13-1。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onMounted } from 'vue'
import { useG13Detail } from '../composables/useG13Detail'
import { useG13ExternalCross } from '../composables/useG13ExternalCross'
import {
  G13_BELONG_ACCOUNT_LABELS,
  G13_INSTRUMENT_TYPES,
  G13_CROSS_VERIFY_OPTIONS,
} from '../composables/g13Constants'
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

// ─── 审计说明 / 审计结论（走 checklist_responses，conclusion:null，remark 存文本） ───
const NOTE_KEY = 'G13-detail-audit-note'
const CONCLUSION_KEY = 'G13-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val } as ChecklistResponse)
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val } as ChecklistResponse)
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const activeTab = ref<'basic' | 'fv'>('basic')
const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: 'FV与审定', value: 'fv' },
]

const detail = useG13Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})
// 解构到顶层：searchQuery 为 ref，模板 v-model 需顶层 ref 才能自动解包
const searchQuery = detail.searchQuery

const extCross = useG13ExternalCross({
  allResponses: toRef(props, 'allResponses'),
  detailRows: computed(() => detail.rows.value),
  debouncedSave: props.debouncedSave,
})

const displayRows = computed(() => {
  const data = searchQuery.value.trim() ? detail.filteredRows.value : detail.rows.value
  return [...data, detail.totalRow.value]
})

const groupRows = computed(() =>
  Object.entries(detail.groupSubtotals.value)
    .filter(([, v]) => v.currentAudited !== 0 || v.fvChange !== 0)
    .map(([, v]) => v),
)

function rowClassName({ row }: { row: { rowId: string; fvReconciled?: boolean } }): string {
  if (row.rowId === 'total') return 'g13-row-total'
  if (row.fvReconciled === false) return 'g13-row-mismatch'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.cross-alert { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.audit-objective { margin-bottom: 8px; }
.g13-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g13-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.g13-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.g13-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; display: inline-block; width: 100%; }
.cell-error { color: #f56c6c; font-weight: 600; }
:deep(.g13-row-total) { font-weight: 700; background: #f5f7fa; }
:deep(.g13-row-mismatch) { background: #fef0f0 !important; }
.group-card { margin-top: 12px; }
.audit-note-card { margin-top: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
</style>
