<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/** F2TabAdjustment — F2-14 调整分录 | Task 15.4 */
import { ref, toRef, inject, onMounted, computed, type Ref } from 'vue'
import { useF2Adjustment } from '../../composables/useF2Adjustment'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import type { F2InventoryAccountItem } from '../../composables/f2AccountModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  auditYear?: number
  /** render 输出的本项目实际存货科目清单（替代写死清单，缺失时组件内部自动回退） */
  inventoryAccounts?: F2InventoryAccountItem[] | null
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────
const NOTE_KEY = 'F2-adjustment-audit-note'
const CONCLUSION_KEY = 'F2-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const auditYearRef = computed(() => props.auditYear)

const {
  rows, debitTotal, creditTotal, balanceDiff, isBalanced, accountOptions,
  addRow, removeRow, updateCell, confirmAndSync,
  pushConfirmedToCentralModule, pushing,
} = useF2Adjustment({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  auditYear: auditYearRef,
  inventoryAccounts: computed(() => props.inventoryAccounts),
})

// ─── 同步到集中调整登记 ─────────────────────────────────────────────
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: () => props.auditYear ?? centralYear.value,
  wpId: () => props.wpId,
  wpCode: 'F2',
  itemId: 'F2-14-rows',
  buildLineItems: () => rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: rows.value.find((r) => r.summary)?.summary || 'F2 存货调整',
    adjustmentType: rows.value.length > 0 && rows.value.every((r) => r.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
refreshStatus()

async function runAdjAi(section: 'f2-14-note' | 'f2-14-conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = section === 'f2-14-note'
  const text = await generateAndConfirm(
    section,
    isNote ? auditNote.value : auditConclusion.value,
    {
      sheet: 'F2-14',
      rowCount: rows.value.length,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
    },
    isNote ? 'AI · 审计说明' : 'AI · 审计结论',
  )
  if (!text) return
  if (isNote) saveAuditNote(text)
  else saveAuditConclusion(text)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="f2-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录存货相关的审计调整分录：AJE（账项调整，影响科目余额）/ RJE（重分类调整，仅影响列报）。</p>
        <p>2. 借贷合计必须平衡（借方合计 = 贷方合计），不平衡时无法同步。</p>
        <p>3. 确认后点「同步至审定表」：EventBus 回写 F2-1，并自动将借贷平衡的未推送组分推送至集中调整表。</p>
        <p>4. 「推送集中调整表」可单独重试；已带同步标记（sourceGroupId）的行不会重复推送。</p>
        <p>5. 依《企业会计准则第 1 号——存货》，跌价准备计提/转回、成本结转差错等均通过本表调整。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：汇总存货相关的账项调整（AJE）与重分类调整（RJE），确保调整分录借贷平衡、依据充分，准确联动回写 F2-1 审定表账项调整列。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增分录</el-button>
        <el-button size="small" :disabled="isReadonly" :loading="pushing" @click="confirmAndSync">同步至审定表</el-button>
        <el-button
          size="small"
          type="success"
          plain
          :disabled="isReadonly || !isBalanced"
          :loading="pushing"
          @click="() => pushConfirmedToCentralModule()"
        >推送集中调整表</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        >同步到集中登记</el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}</el-tag>
        <F2ReviewChip section-id="F2-14-adjustment" />
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-14"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="rows" border size="small" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="调整事项说明" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountCode" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountCode', v)">
            <el-option v-for="a in accountOptions" :key="a.code" :label="a.code" :value="a.code" />
          </el-select>
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountName" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)">
            <el-option v-for="a in accountOptions" :key="a.name" :label="a.name" :value="a.name" />
          </el-select>
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.debitAmount" size="small" style="width:100%"
            @change="(v: number | undefined) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width:100%"
            @change="(v: number | undefined) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
          <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" @change="(v: string) => updateCell(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-bar" :class="{ unbalanced: !isBalanced }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(balanceDiff) }}
      <span v-if="!isBalanced"> — 借贷不平衡</span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAdjAi('f2-14-note')"
          >AI 填写说明</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述调整分录的编制依据、账项/重分类调整事项及其对审定数的影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAdjAi('f2-14-conclusion')"
          >AI 填写结论</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-tab-adjustment { font-size: var(--wp-font-size, 13px); padding: 12px; }
.f2-tab-adjustment :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-tab-adjustment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.balance-bar { margin-top: 8px; text-align: right; font-weight: 600; }
.balance-bar.unbalanced { color: #f56c6c; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
