<template>
  <div class="g12-adj-sheet" data-testid="g12-adjustment">
    <div class="toolbar">
      <div class="title-block">
        <h3>G12-3 调整分录汇总</h3>
        <p class="sheet-sub">登记 6103 相关调整 → 借贷平衡 → 回写 G12-1 审定表</p>
      </div>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G12-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G12-2" /></span>
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-3" :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G12-3-adjustment" />
      </div>
    </div>

    <GCycleGuideStrip
      label="主闭环"
      :steps="[...G12_CORE_WORKFLOW_STEPS]"
      :active-index="wf.activeIndex.value"
      :completed-indices="wf.completedIndices.value"
    />
    <G12CoreWorkflowChecklist :readiness="wf.readiness.value" compact />

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><strong>本页在主闭环中的位置：第 2 步</strong> — {{ G12_CORE_WORKFLOW_HINT }}</p>
        <p>1. 对齐 Excel「调整分录汇总 G12-3」：按调整事项说明逐行登记，类别区分账项调整（AJE）/报表调整（RJE）。</p>
        <p>2. 6103 净敞口套期收益为损益类（贷方余额）；公允价值套期 Dr/Cr 6103 ↔ 被套期项目；现金流量套期 Dr/Cr 6103 ↔ 4002/存货。</p>
        <p>3. 整表借贷须平衡；同步后 G12-1「净敞口套期收益/损失」调整数 overlay 自动更新。</p>
        <p>4. 可从 G12-2 明细差异一键生成成对分录；可与中央调整分录模块双向同步（6103/6101/4002 等）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="录入净敞口套期收益相关 AJE/RJE，验证借贷平衡后同步至 G12-1 审定表，确保审定数口径一致、可追溯。"
    />

    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert" data-testid="g12-adj-balance-error">
      借贷不平衡：借方 {{ fmt(adj.debitTotal.value) }} ≠ 贷方 {{ fmt(adj.creditTotal.value) }}，差额 {{ fmt(Math.abs(adj.balanceDiff.value)) }}
    </el-alert>
    <el-alert
      v-else-if="adj.needsSyncToAdjudication.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-reminder"
      data-testid="g12-adj-sync-reminder"
    >
      <template #title>主闭环第 2 步：请先同步至 G12-1</template>
      调整分录已借贷平衡，但 G12-1 调整数尚未更新（6103 净额 {{ fmt(adj.writebackPreview.value.net6103) }}，
      AJE {{ fmt(adj.writebackPreview.value.aje) }} / RJE {{ fmt(adj.writebackPreview.value.rje) }}）。
      <el-button size="small" type="warning" class="sync-btn" :disabled="isReadonly" @click="adj.syncToAdjudication()">
        立即同步至 G12-1
      </el-button>
    </el-alert>
    <el-alert
      v-else-if="adj.isSyncedToAdjudication.value && Math.abs(adj.writebackPreview.value.net6103) > 0.01"
      type="success"
      :closable="false"
      class="balance-alert"
      data-testid="g12-adj-writeback-ok"
    >
      已同步至 G12-1：6103 净额 {{ fmt(adj.writebackPreview.value.net6103) }}
    </el-alert>

    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow()">+ 新增分录</el-button>
      <el-button size="small" :disabled="isReadonly || !detailVariance" @click="pushFromG12_2">
        从 G12-2 差异推送
      </el-button>
      <el-button
        size="small"
        :loading="adj.syncing.value"
        :disabled="isReadonly || !projectId"
        data-testid="g12-adj-sync-module"
        @click="onSyncFromModule"
      >
        从调整分录模块同步
      </el-button>
      <el-button
        size="small"
        type="success"
        plain
        :disabled="isReadonly || !adj.isBalanced.value || !projectId"
        data-testid="g12-adj-push-module"
        @click="onPushToModule"
      >
        推送至调整分录模块
      </el-button>
      <el-button size="small" type="success" plain :disabled="isReadonly || !adj.isBalanced.value" @click="adj.syncToAdjudication()">
        同步至审定表
      </el-button>
      <el-segmented v-model="viewMode" :options="viewOptions" size="small" />
      <span class="row-count">共 {{ adj.summary.value.rowCount }} 行 · {{ adj.groups.value.length }} 组</span>
      <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>
    </div>

    <template v-if="viewMode === 'grouped'">
      <div v-for="g in adj.groups.value" :key="g.key" class="adj-group" data-testid="g12-adj-group">
        <div class="group-head" :class="{ 'group-unbalanced': !g.balanced }">
          <span class="group-title">{{ g.adjustmentDesc }}</span>
          <span class="group-meta">
            {{ g.rows.length }} 行 · 借 {{ fmt(g.totalDebit) }} / 贷 {{ fmt(g.totalCredit) }}
            <el-tag size="small" :type="g.balanced ? 'success' : 'danger'">{{ g.balanced ? '组内平衡' : '组内不平衡' }}</el-tag>
          </span>
          <el-button v-if="!isReadonly" size="small" link @click="adj.addRowToGroup(g.adjustmentDesc)">+ 追加行</el-button>
        </div>
        <el-table :data="g.rows" border size="small" stripe style="font-size:13px;margin-bottom:12px"
          :row-class-name="adjRowClassName">
          <el-table-column prop="seq" label="#" width="44" align="center" />
          <el-table-column label="类别" width="100">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.category" size="small"
                @change="(v: string) => adj.updateCell(row.rowId, 'category', v)">
                <el-option v-for="o in adj.G12_ADJ_CATEGORY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <span v-else>{{ categoryLabel(row.category) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="报表项目" width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.fsItem" size="small"
                @change="(v: string) => adj.updateCell(row.rowId, 'fsItem', v)" />
              <span v-else>{{ row.fsItem || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="科目" width="160">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.accountCode" size="small"
                @change="(v: string) => adj.updateCell(row.rowId, 'accountCode', v)">
                <el-option v-for="a in adj.G12_ADJ_ACCOUNT_OPTIONS" :key="a.code" :label="`${a.code} ${a.name}`" :value="a.code" />
              </el-select>
              <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="附注项目" width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.noteItem" size="small"
                @change="(v: string) => adj.updateCell(row.rowId, 'noteItem', v)" />
              <span v-else>{{ row.noteItem || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方" width="100" align="right">
            <template #default="{ row }">{{ fmt(row.debitAmount) }}</template>
          </el-table-column>
          <el-table-column label="贷方" width="100" align="right">
            <template #default="{ row }">{{ fmt(row.creditAmount) }}</template>
          </el-table-column>
          <el-table-column label="索引" width="80">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-if="!adj.groups.value.length" description="暂无调整分录" />
    </template>

    <el-table v-else :data="adj.rows.value" border size="small" stripe style="font-size:13px" max-height="480"
      empty-text="暂无调整分录。可新增分录，或从 G12-2 明细差异推送。"
      :row-class-name="adjRowClassName">
      <el-table-column prop="seq" label="#" width="44" align="center" />
      <el-table-column label="调整事项说明" min-width="140">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G12-aje" :row-key="row.rowId" />
          <el-input v-if="!isReadonly" v-model="row.adjustmentDesc" size="small" placeholder="调整事由"
            @change="(v: string) => adj.updateCell(row.rowId, 'adjustmentDesc', v)" />
          <span v-else>{{ row.adjustmentDesc || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.category" size="small"
            @change="(v: string) => adj.updateCell(row.rowId, 'category', v)">
            <el-option v-for="o in adj.G12_ADJ_CATEGORY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <span v-else>{{ categoryLabel(row.category) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.fsItem" size="small" filterable allow-create
            @change="(v: string) => adj.updateCell(row.rowId, 'fsItem', v)">
            <el-option v-for="item in fsItems" :key="item" :label="item" :value="item" />
          </el-select>
          <span v-else>{{ row.fsItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="168">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.accountCode" size="small"
            @change="(v: string) => adj.updateCell(row.rowId, 'accountCode', v)">
            <el-option v-for="a in adj.G12_ADJ_ACCOUNT_OPTIONS" :key="a.code" :label="`${a.code} ${a.name}`" :value="a.code" />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="120">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.noteItem" size="small" filterable allow-create
            @change="(v: string) => adj.updateCell(row.rowId, 'noteItem', v)">
            <el-option v-for="item in noteItems" :key="item" :label="item" :value="item" />
          </el-select>
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small" :controls="false" style="width:100%"
            @change="(v: number) => adj.updateCell(row.rowId, 'debitAmount', v)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small" :controls="false" style="width:100%"
            @change="(v: number) => adj.updateCell(row.rowId, 'creditAmount', v)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
            @change="(v: string) => adj.updateCell(row.rowId, 'indexRef', v)" />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small"
            @change="(v: string) => adj.updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="adj.removeRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-row">
      <span>借方合计：{{ fmt(adj.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmt(adj.creditTotal.value) }}</span>
      <span :class="adj.isBalanced.value ? 'balanced' : 'unbalanced'">
        {{ adj.isBalanced.value ? '✓ 借贷平衡' : `✗ 差额：${fmt(Math.abs(adj.balanceDiff.value))}` }}
      </span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly"
        placeholder="调整分录的依据、拟调整/未调整事项及其影响。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useG12Adjustment } from '../../composables/useG12Adjustment'
import { useG12HedgeDetail } from '../../composables/useG12HedgeDetail'
import { G12_ADJ_FS_ITEMS, G12_ADJ_NOTE_ITEMS, G12_ADJ_CATEGORY_OPTIONS } from '../../composables/g12AdjStorage'
import { G12_CORE_WORKFLOW_HINT, G12_CORE_WORKFLOW_STEPS } from '../../composables/g12Constants'
import { useG12CoreWorkflow } from '../../composables/useG12CoreWorkflow'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'
import G12CoreWorkflowChecklist from '../shared/G12CoreWorkflowChecklist.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()

const viewMode = ref<'flat' | 'grouped'>('grouped')
const viewOptions = [
  { label: '分组视图', value: 'grouped' },
  { label: '平铺视图', value: 'flat' },
]

const adj = useG12Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  projectId: computed(() => props.projectId || ''),
})

const wf = useG12CoreWorkflow({ allResponses: toRef(props, 'allResponses'), pageCode: 'G12-3' })

const hd = useG12HedgeDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const fsItems = G12_ADJ_FS_ITEMS
const noteItems = G12_ADJ_NOTE_ITEMS
const detailVariance = computed(() => Math.abs(hd.totals.value.netHedgePnl) > 0.01)

const NOTE_KEY = 'G12-adjustment-audit-note'
const CONCLUSION_KEY = 'G12-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark ?? ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark ?? ''
})

function categoryLabel(v: string): string {
  return G12_ADJ_CATEGORY_OPTIONS.find((o) => o.value === v)?.label ?? v
}

function adjRowClassName({ row }: { row: { sourceGroupId?: string; remark?: string } }) {
  if (row.sourceGroupId) return 'row-from-module'
  if (/G12-2|G12-4|G12-6/.test(row.remark ?? '')) return 'row-from-peer'
  return ''
}

function pushFromG12_2() {
  adj.addBalancedPair(hd.totals.value.netHedgePnl, 'G12-2 净敞口套期损益与账面差异调整', 'G12-2')
}

async function onSyncFromModule() {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else if (adj.lastSyncMsg.value) ElMessage.info(adj.lastSyncMsg.value)
}

async function onPushToModule() {
  const { ok, pushed } = await adj.confirmAndPush()
  if (!ok) {
    ElMessage.warning('请先保证借贷平衡后再推送')
    return
  }
  if (pushed > 0) ElMessage.success(`已推送 ${pushed} 笔至调整分录模块`)
  else ElMessage.info(adj.lastSyncMsg.value || '无可推送分录（可能已同步）')
}

function fmt(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g12-adj-sheet { padding: 12px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.title-block h3 { margin: 0; }
.sheet-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.guidance-details { margin-bottom: 8px; padding: 8px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 12px; }
.balance-alert { margin-bottom: 8px; }
.adj-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.row-count, .sync-msg { font-size: 12px; color: #909399; }
.sync-reminder { margin-bottom: 12px; }
.sync-reminder :deep(.el-alert__content) { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.sync-btn { margin-left: 4px; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { font-weight: 500; }
.adj-group { margin-bottom: 8px; }
.group-head { display: flex; align-items: center; gap: 12px; padding: 8px 10px; background: #f5f7fa; border-radius: 4px 4px 0 0; border: 1px solid #ebeef5; border-bottom: none; flex-wrap: wrap; }
.group-head.group-unbalanced { background: #fef0f0; }
.group-title { font-weight: 600; flex: 1; min-width: 120px; }
.group-meta { font-size: 12px; color: #606266; display: flex; align-items: center; gap: 8px; }
:deep(.row-from-module) { background: #f0f9eb !important; }
:deep(.row-from-peer) { background: #fdf6ec !important; }
</style>
