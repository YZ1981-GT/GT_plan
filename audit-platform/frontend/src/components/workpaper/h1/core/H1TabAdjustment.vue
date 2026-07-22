<template>
  <div class="h1-tab-adjustment">
    <!-- 编制提示（对齐 Excel H1-3） -->
    <details class="compile-hint">
      <summary>📋 编制提示（对齐 Excel 固定资产调整分录汇总表 H1-3）</summary>
      <div class="hint-content">
        <p>1. 本表对齐 Excel「固定资产调整分录汇总表」：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / 借贷 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报；「其他」按账项调整处理。</p>
        <p>3. 仅列示与固定资产相关的审计调整；一笔完整分录通常需多行（本科目 + 对方科目）且整表借贷平衡。</p>
        <p>4. 索引应交叉引用来源底稿（如 H1-7 增加、H1-8 减少、H1-12 折旧、H1-14 减值）。</p>
        <p>5. 「推送 A13」将账项调整行送入未更正错报汇总（报表调整默认不推）。</p>
        <p class="excel-tip">提示：本底稿适用于调整分录较多、较复杂的项目，项目组可根据实际情况选择是否使用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：复核固定资产相关账项调整（AJE）与报表重分类（RJE）依据充分、借贷平衡，同步至 H1-1 审定并推送 A13 错报汇总。"
    />

    <!-- 工具栏 -->
    <div class="adj-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow">
          + 新增调整分录
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRowIds.length === 0"
          @click="handlePushSelected"
        >
          推送至A13（{{ selectedRowIds.length }}条）
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || state.rows.value.length === 0"
          @click="handlePushAll"
        >
          推送账项调整
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info" effect="plain">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag v-if="state.ajeNet.value !== 0" type="success" size="small" effect="plain">
          账项净额 {{ fmtAmt(state.ajeNet.value) }}
        </el-tag>
        <el-tag v-if="state.rjeNet.value !== 0" type="warning" size="small" effect="plain">
          报表调整净额 {{ fmtAmt(state.rjeNet.value) }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-3" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-1" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div v-if="state.lastPushMsg.value" class="push-msg">{{ state.lastPushMsg.value }}</div>

    <!-- 主表（Excel 列序） -->
    <el-table
      :data="state.rows.value"
      border
      stripe
      size="small"
      class="adj-table"
      empty-text="暂无调整分录。点击「新增」录入；账项净额将同步 H1-1。"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="40" :selectable="() => !isReadonly" />
      <el-table-column type="index" label="序" width="44" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="如：补提本期折旧 / 重分类闲置资产"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="118">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => state.updateCell(row.rowId, 'category', v)"
          >
            <el-option
              v-for="opt in state.categoryOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目" width="168">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="科目"
            @change="(v: string) => state.updateRow(row.rowId, { accountCode: v })"
          >
            <el-option
              v-for="opt in state.accountOptions"
              :key="opt.code"
              :label="`${opt.code} ${opt.name}`"
              :value="opt.code"
            />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :min="0"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :min="0"
            style="width:100%"
            @update:model-value="(v: number | undefined) => state.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="H1-7"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @update:model-value="(v: string) => state.updateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="state.removeRow(row.rowId)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡 -->
    <div
      class="balance-bar"
      :class="{ 'balance-ok': state.isBalanced.value, 'balance-err': !state.isBalanced.value }"
    >
      <span>借方合计：{{ fmtAmt(state.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmtAmt(state.creditTotal.value) }}</span>
      <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
        {{ state.isBalanced.value ? '借贷平衡' : `差额 ${fmtAmt(Math.abs(state.balanceDiff.value))}` }}
      </el-tag>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="概述调整分录编制依据、账项/报表调整事项及其对固定资产审定数的影响；交叉索引来源检查表。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="auditConclusionText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabAdjustment.vue — H1-3 固定资产调整分录汇总表
 * 对齐 Excel 列结构 + G14/F1 工具栏范式 + 持久化落库
 */
import { ref, computed, toRef, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useH1Adjustment } from '../../composables/useH1Adjustment'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const allResponsesRef = computed(() => props.allResponses)
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const NOTE_KEY = 'H1-3-audit-note'
const CONCLUSION_KEY = 'H1-3-audit-conclusion'
const auditNote = ref('')
const auditConclusionText = ref('')
const selectedRowIds = ref<string[]>([])

function saveAuditNote() {
  if (props.isReadonly) return
  saveResponse(NOTE_KEY, auditNote.value)
}
function saveAuditConclusion() {
  if (props.isReadonly) return
  saveResponse(CONCLUSION_KEY, auditConclusionText.value)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

const state = useH1Adjustment(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

function onSelectionChange(selection: any[]) {
  selectedRowIds.value = selection.map((r: any) => r.rowId)
}

function handlePushSelected() {
  state.pushToA13(selectedRowIds.value)
  ElMessage.success(state.lastPushMsg.value || '已推送')
}

function handlePushAll() {
  state.pushToA13()
  ElMessage.info(state.lastPushMsg.value || '已处理')
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.h1-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.h1-tab-adjustment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.compile-hint {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.hint-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.hint-content p { margin: 2px 0; }
.excel-tip { color: #409eff; margin-top: 6px !important; }

.objective-alert { margin-bottom: 12px; }

.adj-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.push-msg { font-size: 12px; color: #67c23a; margin-bottom: 8px; }

.adj-table { margin-bottom: 0; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }

.balance-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 12px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.balance-ok { background: var(--el-color-success-light-9); }
.balance-err { background: var(--el-color-danger-light-9); }

.note-card { margin-top: 12px; }
</style>
