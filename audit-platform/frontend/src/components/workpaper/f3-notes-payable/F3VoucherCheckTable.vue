<script setup lang="ts">
/** F3VoucherCheckTable — F3-7 借/贷检查区表格（>50 行启用固定表头滚动） */
import { ref, computed, watch } from 'vue'
import type { F3VoucherCheckRow } from '../composables/useF3VoucherCheck'
import GtIndexChip from '../GtIndexChip.vue'

const SCROLL_THRESHOLD = 50
const TABLE_MAX_HEIGHT = 480

const props = defineProps<{
  side: 'credit' | 'debit'
  rows: F3VoucherCheckRow[]
  isReadonly: boolean
  projectId?: string
  allResponses?: Map<string, any>
}>()

const emit = defineEmits<{
  (e: 'update-cell', rowId: string, field: string, value: unknown): void
  (e: 'remove-row', rowId: string): void
}>()

const useScroll = computed(() => props.rows.length > SCROLL_THRESHOLD)
const sideLabel = computed(() => (props.side === 'credit' ? '贷方（本期增加·开票承兑）' : '借方（本期减少·到期兑付/背书转让）'))

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onUpdate(field: string, rowId: string, value: unknown): void {
  emit('update-cell', rowId, field, value)
}

// ─── 分区审计说明（按借/贷区分；F3 约定：写入 allResponses + f3:save-items 事件持久化） ───
const NOTE_KEY = computed(() => `F3-7-${props.side}-check-note`)
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses?.set(NOTE_KEY.value, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
watch(
  () => props.allResponses?.get(NOTE_KEY.value)?.remark,
  (v) => { if (typeof v === 'string') auditNote.value = v },
  { immediate: true },
)
</script>

<template>
  <div class="f3-voucher-table-wrap">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本区为{{ sideLabel }}抽凭检查，逐笔核对凭证与票据要素（出票人、面值、到期日、对方科目）一致性。</p>
        <p>2. 逐行"审计结论"列记录该笔凭证的检查结果，异常凭证在下方"审计说明"中汇总说明并考虑追加程序。</p>
        <p>3. 关注无真实交易背景的融资性票据、关联方票据及到期未兑付票据的后续处理。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      :title="`审计目标：验证应付票据${sideLabel}变动真实、完整、准确，凭证具有真实交易背景。`"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F3-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="useScroll" class="scroll-hint">共 {{ rows.length }} 行 · 固定表头滚动</div>
    <el-table
      :data="rows"
      border
      size="small"
      style="font-size:13px"
      :max-height="useScroll ? TABLE_MAX_HEIGHT : undefined"
    >
      <el-table-column prop="seq" label="序号" width="55" fixed />
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="`来自${row.sampleSource}`" placement="top">
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              @change="(v: string) => onUpdate('summary', row.rowId, v)"
            />
            <span v-else>{{ row.summary }}</span>
          </el-tooltip>
          <template v-else>
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              @change="(v: string) => onUpdate('summary', row.rowId, v)"
            />
            <span v-else>{{ row.summary }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.counterAccount"
            size="small"
            @change="(v: string) => onUpdate('counterAccount', row.rowId, v)"
          />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => onUpdate('amount', row.rowId, v ?? 0)"
          />
          <span v-else>{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证日期" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherDate"
            size="small"
            @change="(v: string) => onUpdate('voucherDate', row.rowId, v)"
          />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherNo"
            size="small"
            @change="(v: string) => onUpdate('voucherNo', row.rowId, v)"
          />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计结论" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.auditConclusion"
            size="small"
            @change="(v: string) => onUpdate('auditConclusion', row.rowId, v)"
          />
          <span v-else>{{ row.auditConclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="emit('remove-row', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明（本区） -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        :placeholder="`填写本区（${sideLabel}）审计说明：凭证核对情况、异常凭证及处理、追加程序说明。`"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f3-voucher-table-wrap { margin-bottom: 8px; }
.f3-voucher-table-wrap :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-voucher-table-wrap :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.scroll-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  text-align: right;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
