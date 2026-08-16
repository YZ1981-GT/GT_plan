<template>
  <div class="g5-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G5-4 调整分录汇总</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-4" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-4"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-tag size="small" type="info">共 {{ adj.entries.value.length }} 行</el-tag>
        <el-button
          size="small"
          type="success"
          :disabled="!!props.readonly || !adj.isBalanced.value || adj.entries.value.length === 0"
          @click="adj.confirmWriteback()"
        >
          确认调整
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="!!props.readonly || !adj.isBalanced.value || adj.entries.value.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
        <GtReviewTrigger section-id="g5-4-adjustment" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：汇总长期应收款相关账项/报表调整，校验借贷平衡，确认回写 G5-1 审定表。列结构对齐模板：调整事项说明 / 类别（报表调整·账项调整·其他）/ 报表项目 / 科目名称 / 附注项目 / 借贷金额 / 索引 / 备注。
    </el-alert>

    <div v-if="!adj.isBalanced.value" class="balance-alert">
      <el-alert type="error" :closable="false">
        借贷不平衡！差额：{{ fmt(adj.balanceDiff.value) }}
      </el-alert>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" plain @click="adj.addEntry()" :disabled="props.readonly">
        + 新增调整分录
      </el-button>
      <span class="totals">
        借方合计: {{ fmt(adj.debitTotal.value) }} | 贷方合计: {{ fmt(adj.creditTotal.value) }}
        <el-tag v-if="adj.isBalanced.value" size="small" type="success">借贷平衡</el-tag>
        <el-tag v-if="adj.netAjeToG5.value !== 0" size="small" type="info" class="net-tag">
          1531 净 AJE {{ fmt(adj.netAjeToG5.value) }}
        </el-tag>
        <el-tag v-if="adj.netRjeToG5.value !== 0" size="small" type="warning" class="net-tag">
          1531 净 RJE {{ fmt(adj.netRjeToG5.value) }}
        </el-tag>
      </span>
    </div>

    <!-- 对齐 Excel G5-4 / D4-4 -->
    <el-table
      :data="adj.entries.value"
      border
      stripe
      size="small"
      style="width: 100%; font-size: 13px"
      :height="420"
      empty-text="暂无调整分录。点击「新增调整分录」添加。"
    >
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!props.readonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(v: string) => adj.updateCell(row.id, 'description', v)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!props.readonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'category', v)"
          >
            <el-option
              v-for="c in adj.categoryOptions"
              :key="c"
              :value="c"
              :label="c"
            />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!props.readonly"
            :model-value="row.reportItem"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="160">
        <template #default="{ row }">
          <el-select
            v-if="!props.readonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            @change="(v: string) => adj.updateCell(row.id, 'accountCode', v)"
          >
            <el-option
              v-for="opt in adj.accountOptions"
              :key="opt.code"
              :value="opt.code"
              :label="`${opt.code} ${opt.name}`"
            />
          </el-select>
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!props.readonly"
            :model-value="row.noteItem"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!props.readonly"
            :model-value="row.debitAmount"
            size="small"
            style="width: 100%"
            @change="(v: number | undefined) => adj.updateCell(row.id, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!props.readonly"
            :model-value="row.creditAmount"
            size="small"
            style="width: 100%"
            @change="(v: number | undefined) => adj.updateCell(row.id, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!props.readonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!props.readonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!props.readonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="adj.removeEntry(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="auditConclusion"
      note-ai-section="adjustment-note"
      conclusion-ai-section="adjustment-conclusion"
      note-placeholder="填写审计说明：调整分录的依据、事由、影响科目及回写审定表情况。"
      conclusion-placeholder="填写审计结论：A、调整分录借贷平衡且依据充分。B、除下述事项外未见异常。C、存在未决调整事项。"
      @update:note="saveAuditNote"
      @update:conclusion="saveAuditConclusion"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>列结构对齐 Excel：调整事项说明、类别（账项调整/报表调整/其他）、报表项目、科目名称、附注项目、借贷金额、索引、备注</li>
        <li>「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报</li>
        <li>借贷合计必须平衡，否则无法「确认调整」回写 G5-1</li>
        <li>点「确认调整」后，相关科目净 AJE/RJE 回写 G5-1「业务类型组合」行期末调整列</li>
        <li>本底稿适用于调整分录较多、较复杂的项目；项目组可按实际情况选用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, computed, onMounted } from 'vue'
import { useG5Adjustment } from '../../composables/useG5Adjustment'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const readonlyRef = computed(() => !!props.readonly)

const adj = useG5Adjustment({
  allResponses: g5Notes.allResponses,
  debouncedSave: g5Notes.debouncedSave,
  saveImmediate: g5Notes.saveImmediate,
  isReadonly: readonlyRef,
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G5',
  itemId: 'G5-4-rows',
  buildLineItems: () => adj.entries.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.entries.value.find((r) => r.description)?.description || 'G5 长期应收款调整',
    adjustmentType: adj.entries.value.length > 0 && adj.entries.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-4-audit-note'
const G5_CONCLUSION_KEY = 'G5-4-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  adj.loadEntries()
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  adj.loadEntries()
  emit('imported')
}

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.balance-alert { margin-bottom: 8px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.totals { font-size: 12px; color: #606266; margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.net-tag { margin-left: 4px; }
</style>
