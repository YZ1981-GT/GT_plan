<template>
<div class="f1-disclosure-soe">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. （1）按账龄列示：期末/期初账面余额（金额+比例）及坏账准备，自 F1-2 审定账龄聚合。</p>
        <p>2. （2）账龄超过1年的重要预付款项：债权单位可填；债务单位/余额/账龄自 F1-2 带入，补未结算原因。</p>
        <p>3. （3）前五名：按期末余额降序；坏账准备可手工录入。</p>
        <p>4. 「同步到附注」推送至附注模块「{{ noteSectionId }} 预付款项」。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按国有企业财务报告及国资监管要求披露预付款项账龄、超1年大额及前五名，与 F1-1/F1-2 勾稽并同步附注。"
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

    <!-- (1) 账龄列示 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付款项按账龄列示
        <el-tooltip content="账面余额自 F1-2 审定账龄聚合；坏账准备可手工录入" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
        <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
      </h4>
      <el-table :data="agingTableData" size="small" border stripe>
        <el-table-column prop="label" label="账龄" width="140">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.endAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例%" width="90" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtPct(row.endPct) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId === '__subtotal__'">
                <span class="subtotal-val">{{ fmtAmount(row.endBadDebt) }}</span>
              </template>
              <template v-else>
                <el-input-number
                  :model-value="row.endBadDebt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateAgingBadDebt(row.key, 'end', v ?? 0)"
                />
              </template>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.priorAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例%" width="90" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtPct(row.priorPct) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId === '__subtotal__'">
                <span class="subtotal-val">{{ fmtAmount(row.priorBadDebt) }}</span>
              </template>
              <template v-else>
                <el-input-number
                  :model-value="row.priorBadDebt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateAgingBadDebt(row.key, 'prior', v ?? 0)"
                />
              </template>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input
          v-model="note1"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄列示说明..."
        />
      </div>
    </div>

    <!-- (2) 超1年 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预付款项
        <el-button size="small" :disabled="isReadonly" @click="addOver1Row()">+ 添加</el-button>
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <el-table :data="over1TableData" size="small" border stripe>
        <el-table-column label="债权单位" min-width="120">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.creditorUnit"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'creditorUnit', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="债务单位" min-width="140">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'" />
            <template v-else-if="row.fromCrossSheet">
              <span class="cross-sheet-cell">{{ row.debtorUnit }}</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.debtorUnit"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'debtorUnit', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
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
        <el-table-column label="账龄" width="140">
          <template #default="{ row }">
            <el-select
              v-if="row.rowId !== '__total__'"
              :model-value="row.agingLabel"
              size="small"
              :disabled="isReadonly"
              filterable
              allow-create
              clearable
              placeholder="选择账龄"
              @change="(v: string) => updateOver1Field(row.rowId, 'agingLabel', v ?? '')"
            >
              <el-option v-for="opt in over1AgingOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="未结算的原因" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__total__'"
              :model-value="row.reason"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateOver1Field(row.rowId, 'reason', v)"
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
          placeholder="超1年重要预付款项说明..."
        />
      </div>
    </div>

    <!-- (3) 前五名 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 按欠款方归集的期末余额前五名的预付款项情况
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <el-table :data="top5TableData" size="small" border stripe>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__total__' }">
              {{ row.rowId === '__total__' ? '合计' : row.debtorName }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="账面余额" width="130" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.rowId === '__total__' }">
              {{ fmtAmount(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项合计的比例(%)" width="170" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell">{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="坏账准备" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-val">{{ fmtAmount(row.badDebt) }}</span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row.badDebt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateTop5BadDebt(row.debtorName, v ?? 0)"
              />
            </template>
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

  <F1DisclosureUsageGuide v-model="showGuide" variant="soe" />
</div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useF1DisclosureSoe } from '../composables/useF1DisclosureSoe'
import {
  buildF1SoeSubTableData,
  buildF1SyncPayload,
} from '../composables/f1DisclosureSyncPayload'
import { F1_NOTE_SECTION } from '../composables/f1NoteSectionMap'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from '../composables/agingPresets'
import GtIndexChip from '../GtIndexChip.vue'
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
const noteSectionId = F1_NOTE_SECTION.soe
const showGuide = ref(false)
const isSyncing = ref(false)

/** 超1年行账龄下拉：跟项目/明细枚举（排除 1年以内） */
const over1AgingOptions = computed(() => {
  const segs = props.crossSheet.agingSegments?.value || []
  const labels = segs
    .filter((s) => s.key !== 'within1' && s.dayFrom >= 366)
    .map((s) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[s.key] || s.label)
  if (labels.length) return labels
  return segs
    .filter((s) => s.key !== 'within1')
    .map((s) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[s.key] || s.label)
})

const {
  isApplicable,
  agingRows,
  agingTotal,
  updateAgingBadDebt,
  over1YearRows,
  over1YearTotal,
  addOver1Row,
  removeOver1Row,
  updateOver1Field,
  top5Rows,
  top5Total,
  updateTop5BadDebt,
  note1,
  note2,
  note3,
  getSyncSnapshot,
} = useF1DisclosureSoe({
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
  creditorUnit: '',
  debtorUnit: '',
  endBalance: over1YearTotal.value.endBalance,
  agingLabel: '',
  reason: '',
  fromCrossSheet: false,
}))

const top5TotalRow = computed(() => ({
  rowId: '__total__',
  debtorName: '合计',
  endBalance: top5Total.value.endBalance,
  proportionPct: top5Total.value.proportionPct,
  badDebt: top5Total.value.badDebt,
}))

/** 避免模板 spread 在 Ref 未就绪时抛出 “X is not iterable” */
const agingTableData = computed(() => [...(agingRows.value ?? []), agingTotal.value])
const over1TableData = computed(() => [...(over1YearRows.value ?? []), over1TotalRow.value])
const top5TableData = computed(() => [...(top5Rows.value ?? []), top5TotalRow.value])

async function syncToDisclosureNotes() {
  const payload = buildF1SyncPayload(
    'soe',
    props.wpId,
    props.applicableStandards,
    buildF1SoeSubTableData(getSyncSnapshot()),
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
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
.f1-disclosure-soe { padding: 16px; }
.f1-disclosure-soe :deep(.el-table) {
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
.subtotal-label, .subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.note-area { margin-top: 12px; display: flex; align-items: flex-start; gap: 8px; }
.note-prefix { font-size: 13px; color: #606266; white-space: nowrap; padding-top: 6px; }
</style>
