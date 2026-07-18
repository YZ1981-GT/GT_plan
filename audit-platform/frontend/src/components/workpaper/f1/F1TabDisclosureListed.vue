<template>
<div class="f1-disclosure-listed">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. （1）账龄分析：期末/上年年末金额与比例，自 F1-2 审定账龄聚合（与 F1-1 按账龄勾稽）。</p>
        <p>2. （2）账龄超过1年的重要预付款项：自 F1-2 筛选；填写未偿还原因；占比分母为账龄合计。</p>
        <p>3. （3）前五名：汇总披露格式自动生成；分别披露表按期末余额降序取前五。</p>
        <p>4. 「同步到附注」推送至附注模块「{{ noteSectionId }} 预付款项」。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按上市公司列报要求披露预付款项账龄、超1年重要款项及前五名，确保与 F1-1/F1-2 勾稽并同步附注。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" text type="primary" @click="showGuide = true">使用手册</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <F1SheetAttachments
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F1-listed"
      label="上市附注附件"
    />

    <!-- (1) 账龄分析 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付款项按账龄披露
        <el-tooltip content="数据来源：F1-2 审定账龄聚合 → 与 F1-1 按账龄勾稽" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
        <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
      </h4>
      <el-table :data="[...agingRows, agingTotal]" size="small" border stripe>
        <el-table-column prop="label" label="账龄" width="120">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例%" width="100" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtPct(row.endPct) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上年年末数" align="center">
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.priorAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例%" width="100" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtPct(row.priorPct) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <div class="impairment-row">
        <span class="lab">减：减值准备</span>
        <el-input-number
          :model-value="impairmentProvision"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @change="(v: number | undefined) => persistImpairment(v ?? 0)"
        />
        <span class="muted">净额 {{ fmtAmount(agingNet.endAmount) }}</span>
      </div>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input
          v-model="note1"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄披露说明..."
        />
      </div>
    </div>

    <!-- (2) 超1年重要 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预付款项
        <el-button size="small" :disabled="isReadonly" @click="addOver1Row()">+ 添加</el-button>
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <el-table :data="[...over1YearRows, over1TotalRow]" size="small" border stripe>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else-if="row.fromCrossSheet">
              <span class="cross-sheet-cell">{{ row.debtorName }}</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.debtorName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'debtorName', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__' || row.fromCrossSheet">
              <span :class="{ 'cross-sheet-cell': row.fromCrossSheet, 'subtotal-val': row.rowId === '__total__' }">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row.endBalance"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateOver1Field(row.rowId, 'endBalance', v ?? 0)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项合计的比例(%)" width="160" align="right">
          <template #default="{ row }">
            <span>{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未偿还原因" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__total__'"
              :model-value="row.reason"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateOver1Reason(row.rowId, v)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56">
          <template #default="{ row }">
            <el-popconfirm
              v-if="!row.fromCrossSheet && row.rowId !== '__total__'"
              title="删除？"
              @confirm="removeOver1Row(row.rowId)"
            >
              <template #reference>
                <el-button size="small" type="danger" link>删</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input
          v-model="note2"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄超过1年的金额重要预付账款，应说明未及时结算的原因。"
        />
      </div>
    </div>

    <!-- (3) 前五名 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 按预付对象归集的预付款项期末余额前五名单位情况
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <p class="sub-label">汇总披露格式</p>
      <el-input
        type="textarea"
        :rows="2"
        :model-value="top5SummaryText"
        :disabled="isReadonly"
        placeholder="本期按预付对象归集的期末余额前五名预付款项汇总金额……"
        @change="(v: string) => persistTop5Summary(v)"
      />
      <p class="hint">留空则使用自动汇总：{{ top5SummaryAuto }}</p>

      <p class="sub-label">分别披露格式</p>
      <el-table :data="[...top5Rows, top5TotalRow]" size="small" border stripe>
        <el-table-column label="单位名称" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__total__' }">
              {{ row.rowId === '__total__' ? '合计' : row.entityName }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预付款项期末余额" width="150" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.rowId === '__total__' }">
              {{ fmtAmount(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项期末余额合计数的比例%" width="200" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell">{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input
          v-model="note3"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="前五名披露说明..."
        />
      </div>
    </div>
  </template>

  <F1DisclosureUsageGuide v-model="showGuide" variant="listed" />
</div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useF1DisclosureListed } from '../composables/useF1DisclosureListed'
import {
  buildF1ListedSubTableData,
  buildF1SyncPayload,
} from '../composables/f1DisclosureSyncPayload'
import { F1_NOTE_SECTION } from '../composables/f1NoteSectionMap'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'
import F1DisclosureUsageGuide from './F1DisclosureUsageGuide.vue'

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  applicableStandards?: string[]
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>(), {
  applicableStandards: () => [],
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const noteSectionId = F1_NOTE_SECTION.listed
const showGuide = ref(false)
const isSyncing = ref(false)

const {
  isApplicable,
  agingRows,
  agingTotal,
  agingNet,
  impairmentProvision,
  persistImpairment,
  over1YearRows,
  over1YearTotal,
  addOver1Row,
  removeOver1Row,
  updateOver1Reason,
  updateOver1Field,
  top5Rows,
  top5Total,
  top5SummaryText,
  top5SummaryAuto,
  persistTop5Summary,
  note1,
  note2,
  note3,
  getSyncSnapshot,
} = useF1DisclosureListed({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as unknown as Ref<string[]>,
})

const over1TotalRow = computed(() => ({
  rowId: '__total__',
  debtorName: '合计',
  endBalance: over1YearTotal.value.endBalance,
  proportionPct: over1YearTotal.value.proportionPct,
  impairment: over1YearTotal.value.impairment,
  reason: '',
  fromCrossSheet: false,
}))

const top5TotalRow = computed(() => ({
  rowId: '__total__',
  entityName: '合计',
  endBalance: top5Total.value.endBalance,
  proportionPct: top5Total.value.proportionPct,
}))

async function syncToDisclosureNotes() {
  const payload = buildF1SyncPayload(
    'listed',
    props.wpId,
    props.applicableStandards,
    buildF1ListedSubTableData(getSyncSnapshot()),
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市公司附注同步')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${noteSectionId} 预付款项」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || !isFinite(val) || val === 0) return '-'
  return `${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}
</script>

<style scoped>
.f1-disclosure-listed { padding: 16px; }
.f1-disclosure-listed :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.disclosure-card {
  margin-bottom: 20px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sub-label { margin: 12px 0 6px; font-size: 13px; font-weight: 600; color: #606266; }
.hint { margin: 4px 0 12px; font-size: 12px; color: #909399; }
.subtotal-label, .subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.impairment-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  font-size: 13px;
}
.impairment-row .lab { color: #606266; min-width: 100px; }
.muted { color: #909399; }
.note-area { margin-top: 12px; display: flex; align-items: flex-start; gap: 8px; }
.note-prefix { font-size: 13px; color: #606266; white-space: nowrap; padding-top: 6px; }
</style>
