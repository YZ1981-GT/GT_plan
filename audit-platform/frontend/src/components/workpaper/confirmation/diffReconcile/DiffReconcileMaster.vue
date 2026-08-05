<template>
  <div class="diff-reconcile-master">
    <!-- 工具栏 -->
    <div class="diff-reconcile-master__toolbar">
      <el-button-group>
        <el-button size="small" type="primary" :icon="Plus" :disabled="readonly" @click="$emit('add')">
          新增
        </el-button>
        <el-button size="small" type="danger" :icon="Delete" :disabled="readonly || !selectedIds.length" @click="handleDeleteClick">
          删除
        </el-button>
        <el-button size="small" :icon="Download" :disabled="readonly" @click="$emit('import-d01')">
          从 D0-1 带入
        </el-button>
      </el-button-group>
      <!--
        超重要性差异 → A13 未更正错报汇总（走平台既有 `a13:push-misstatement`）。
        无重要性水平配置时禁用并提示 —— 没有阈值就判不出「超重要性」，
        此时应走单行「推送」按钮由审计师自行判断。
      -->
      <el-tooltip :content="batchPushHint" placement="top" :disabled="!batchPushHint">
        <span>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="readonly || overMaterialityRowIds.length === 0"
            @click="$emit('push-a13', [...overMaterialityRowIds])"
          >
            推送 {{ overMaterialityRowIds.length }} 笔超重要性差异至 A13
          </el-button>
        </span>
      </el-tooltip>
      <el-button-group>
        <el-button size="small" :disabled="readonly" @click="$emit('import-excel')">
          导入
        </el-button>
        <el-button size="small" @click="$emit('export-template')">
          导出模板
        </el-button>
        <el-button size="small" @click="$emit('export-excel')">
          导出数据
        </el-button>
      </el-button-group>
      <div class="diff-reconcile-master__toolbar-right">
        <el-switch
          v-model="groupBySubject"
          active-text="按科目分组"
          inactive-text=""
          size="small"
        />
        <el-button size="small" type="success" :disabled="readonly || !isDirty" @click="$emit('save')">
          保存
        </el-button>
      </div>
    </div>

    <!-- 网格表 -->
    <el-table
      ref="tableRef"
      :data="displayRows"
      border
      stripe
      size="small"
      highlight-current-row
      show-summary
      :summary-method="getSummaries"
      :row-class-name="getRowClassName"
      table-layout="auto"
      max-height="560"
      @selection-change="handleSelectionChange"
      class="diff-reconcile-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="36" align="center" />
      <el-table-column label="序号" prop="seq" min-width="45" align="center" />
      <el-table-column label="函证索引号" prop="confirm_index" min-width="90">
        <template #default="{ row }">
          <div v-if="!readonly" style="display:flex;align-items:center;gap:4px">
            <el-input
              :model-value="row.confirm_index"
              size="small"
              placeholder="D0-"
              @change="(val: string) => $emit('update', row._row_id, 'confirm_index', val)"
            />
            <el-icon v-if="row.confirm_index" style="cursor:pointer;color:var(--el-color-primary);flex-shrink:0" @click="$emit('jump-d01', row.confirm_index)"><Link /></el-icon>
          </div>
          <span v-else class="diff-reconcile-master__link" @click="$emit('jump-d01', row.confirm_index)">
            {{ row.confirm_index || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="被询证单位" prop="entity_name" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.entity_name"
            size="small"
            placeholder="单位名称"
            @change="(val: string) => $emit('update', row._row_id, 'entity_name', val)"
          />
          <span v-else>{{ row.entity_name || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 科目列：下拉 + allow-create -->
      <el-table-column label="科目" prop="subject" min-width="100">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.subject"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="选择科目"
            @change="(val: string) => $emit('update', row._row_id, 'subject', val)"
          >
            <el-option
              v-for="opt in subjectOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ row.subject || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 金额列 -->
      <el-table-column label="发函金额" prop="sent_amount" min-width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!readonly"
            :model-value="row.sent_amount"
            size="small"
            :controls="false"
            :precision="2"
            class="diff-reconcile-master__amount-input"
            @change="(val: number) => $emit('update', row._row_id, 'sent_amount', val)"
          />
          <span v-else class="diff-reconcile-master__amount">{{ formatAmount(row.sent_amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="回函金额" prop="reply_amount" min-width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!readonly"
            :model-value="row.reply_amount"
            size="small"
            :controls="false"
            :precision="2"
            class="diff-reconcile-master__amount-input"
            @change="(val: number) => $emit('update', row._row_id, 'reply_amount', val)"
          />
          <span v-else class="diff-reconcile-master__amount">{{ formatAmount(row.reply_amount) }}</span>
        </template>
      </el-table-column>

      <!-- 差异列：只读自动 -->
      <el-table-column label="差异金额" prop="difference" min-width="90" align="right">
        <template #header>
          <span>差异金额</span>
          <el-tooltip content="自动计算：发函金额 − 回函金额" placement="top">
            <el-icon :size="12" style="margin-left:2px"><InfoFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="[
              'diff-reconcile-master__amount',
              { 'diff-reconcile-master__amount--over': isOverMateriality(row) },
              { 'diff-reconcile-master__amount--negative': (row.difference ?? 0) < 0 },
            ]"
          >
            {{ formatAmount(row.difference) }}
            <el-icon v-if="isOverMateriality(row)" color="var(--el-color-danger)" :size="12">
              <WarningFilled />
            </el-icon>
          </span>
        </template>
      </el-table-column>

      <!-- 差异类型 -->
      <el-table-column label="差异类型" prop="diff_type" min-width="95">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.diff_type"
            size="small"
            clearable
            placeholder="选择类型"
            @change="(val: string) => $emit('update', row._row_id, 'diff_type', val)"
          >
            <el-option
              v-for="opt in diffTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-tag v-else-if="row.diff_type" size="small" :type="diffTypeColor(row.diff_type)">
            {{ diffTypeLabel(row.diff_type) }}
          </el-tag>
          <span v-else class="diff-reconcile-master__empty">未分类</span>
        </template>
      </el-table-column>

      <!-- 是否调整 -->
      <el-table-column label="是否调整" prop="needs_adjustment" min-width="70" align="center">
        <template #header>
          <span>是否调整</span>
          <el-tooltip content="需调整→关联 AJE；未达账项→链接替代程序 D0-5/D0-6" placement="top">
            <el-icon :size="12" style="margin-left:2px"><InfoFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-switch
            v-if="!readonly"
            :model-value="row.needs_adjustment"
            size="small"
            @change="(val: boolean) => $emit('update', row._row_id, 'needs_adjustment', val)"
          />
          <el-tag v-else :type="row.needs_adjustment ? 'danger' : 'info'" size="small">
            {{ row.needs_adjustment ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 差异说明 -->
      <el-table-column label="差异说明" prop="diff_note" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.diff_note"
            size="small"
            placeholder="说明差异原因"
            @change="(val: string) => $emit('update', row._row_id, 'diff_note', val)"
          />
          <span v-else>{{ row.diff_note || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 相关支持性证据（源模板 X0-4 第 9 列） -->
      <el-table-column label="支持性证据" prop="support_evidence" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.support_evidence"
            size="small"
            placeholder="相关支持性证据索引/说明"
            @change="(val: string) => $emit('update', row._row_id, 'support_evidence', val)"
          />
          <span v-else>{{ row.support_evidence || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 来源标识 -->
      <el-table-column label="来源" min-width="50" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._source === 'auto'" size="small" type="primary" effect="plain">
            自动
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>

      <!-- 错报推送（源模板第 9 列「是否调整」的下游动作） -->
      <el-table-column v-if="!readonly" label="错报" min-width="72" align="center">
        <template #header>
          <span>错报</span>
          <el-tooltip
            content="推送至 A13 未更正错报汇总；金额取差异绝对值（错报只关心差多少）"
            placement="top"
          >
            <el-icon :size="12" style="margin-left:2px"><InfoFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-button
            v-if="(row.difference ?? 0) !== 0"
            :type="isOverMateriality(row) ? 'danger' : 'primary'"
            text
            size="small"
            @click="$emit('push-a13', [row._row_id])"
          >
            {{ isOverMateriality(row) ? '推送错报' : '推送' }}
          </el-button>
          <span v-else class="diff-reconcile-master__empty">无差异</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Delete, Download, InfoFilled, WarningFilled, Link } from '@element-plus/icons-vue'
import type { DiffReconcileRow, DiffSummaryBySubject } from './diffReconcileTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  rows: DiffReconcileRow[]
  readonly: boolean
  isDirty: boolean
  subjectOptions: { value: string; label: string }[]
  diffTypeOptions: { value: string; label: string }[]
  subjectSummary: DiffSummaryBySubject[]
  isOverMateriality: (row: DiffReconcileRow) => boolean
}>()

const emit = defineEmits<{
  /** 🔴 携带勾选行 ID：选中态在本组件内（selectedIds），父组件拿不到 → 不带载荷父层无法实装删除 */
  (e: 'add'): void
  (e: 'delete', rowIds: string[]): void
  (e: 'save'): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import-d01'): void
  (e: 'import-excel'): void
  (e: 'export-excel'): void
  (e: 'export-template'): void
  (e: 'jump-d01', confirmIndex: string): void
  /**
   * 推送错报至 A13 未更正错报汇总（走平台既有 `a13:push-misstatement`）。
   * 携带行 ID 数组：单行按钮传 `[row._row_id]`，工具栏批量传全部超重要性行。
   */
  (e: 'push-a13', rowIds: string[]): void
}>()

const tableRef = ref()
const selectedIds = ref<string[]>([])
const groupBySubject = ref(false)

// ─── 分组显示 ────────────────────────────────────────────────────────────────

const displayRows = computed(() => {
  if (!groupBySubject.value) return props.rows
  // 按科目排序（分组视觉效果）
  return [...props.rows].sort((a, b) => (a.subject ?? '').localeCompare(b.subject ?? ''))
})

// ─── 超重要性差异（A13 批量推送） ────────────────────────────────────────────

const overMaterialityRowIds = computed(() =>
  props.rows
    .filter((r) => (r.difference ?? 0) !== 0 && props.isOverMateriality(r))
    .map((r) => r._row_id!)
    .filter(Boolean),
)

const batchPushHint = computed(() => {
  if (props.readonly) return '只读模式下不可推送'
  if (overMaterialityRowIds.value.length > 0) return ''
  // 区分「没配阈值」与「配了但没有超阈值的行」—— 两者的下一步动作完全不同
  if (!props.rows.some((r) => props.isOverMateriality(r))) {
    return '暂无超过实际执行重要性的差异（未配置重要性水平时请用单行「推送」按钮自行判断）'
  }
  return ''
})

// ─── Selection ───────────────────────────────────────────────────────────────

function handleSelectionChange(selection: DiffReconcileRow[]) {
  selectedIds.value = selection.map((r) => r._row_id!).filter(Boolean)
}

function handleDeleteClick() {
  if (!selectedIds.value.length) return
  emit('delete', [...selectedIds.value])
  selectedIds.value = []
  tableRef.value?.clearSelection?.()
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns, data }: { columns: any[]; data: DiffReconcileRow[] }) {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (['sent_amount', 'reply_amount', 'difference'].includes(col.property)) {
      const total = data.reduce((s, row) => s + ((row as any)[col.property] ?? 0), 0)
      sums[index] = formatAmount(total)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: DiffReconcileRow }) {
  if ((row.difference ?? 0) === 0) return 'diff-reconcile-master__row--zero'
  if (props.isOverMateriality(row)) return 'diff-reconcile-master__row--alert'
  return ''
}

// ─── 格式化工具 ──────────────────────────────────────────────────────────────

const prefs = useDisplayPrefsStore()

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

const DIFF_TYPE_MAP: Record<string, { label: string; color: string }> = {
  time: { label: '时间性差异', color: 'info' },
  accounting: { label: '记账差异', color: 'warning' },
  unrecorded: { label: '未达账项', color: 'danger' },
  other: { label: '其他差异', color: '' },
}

function diffTypeLabel(type: string): string {
  return DIFF_TYPE_MAP[type]?.label ?? type
}

function diffTypeColor(type: string): string {
  return DIFF_TYPE_MAP[type]?.color ?? ''
}
</script>

<style scoped>
.diff-reconcile-master__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.diff-reconcile-master__toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 表头折行 + 紧凑 */
.diff-reconcile-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: var(--wp-font-size, 13px);
}

.diff-reconcile-master__table :deep(.el-table__body td .cell) {
  font-size: var(--wp-font-size, 13px);
}

/* 合计行不折行 */
.diff-reconcile-master__table :deep(.el-table__footer td .cell) {
  white-space: nowrap;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* 勾选列居中 */
.diff-reconcile-master__table :deep(.el-table-column--selection .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0;
}

.diff-reconcile-master__amount {
  font-variant-numeric: tabular-nums;
}

.diff-reconcile-master__amount--over {
  color: var(--el-color-danger);
  font-weight: 600;
}

.diff-reconcile-master__amount--negative {
  color: var(--el-color-danger);
}

.diff-reconcile-master__amount-input {
  width: 100%;
}

.diff-reconcile-master__link {
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.diff-reconcile-master__empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

:deep(.diff-reconcile-master__row--zero) {
  opacity: 0.5;
}

:deep(.diff-reconcile-master__row--alert) {
  background-color: var(--el-color-danger-light-9) !important;
}
</style>
