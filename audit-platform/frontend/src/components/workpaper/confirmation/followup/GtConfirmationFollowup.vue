<template>
  <div class="gt-confirmation-followup">
    <!-- Legacy fallback -->
    <template v-if="isLegacyFormat">
      <div class="gt-confirmation-followup__legacy-notice">
        <el-alert
          title="旧格式数据"
          description="当前数据非 confirmation-followup-v1 格式，以只读网格模式展示"
          type="info"
          show-icon
          :closable="false"
        />
      </div>
    </template>

    <!-- Modern confirmation-followup-v1 layout -->
    <template v-else>
      <!-- Dashboard -->
      <FollowupDashboard :metrics="progressMetrics" />

      <!-- View switch -->
      <div class="gt-confirmation-followup__view-switch">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="list">列表视图</el-radio-button>
          <el-radio-button value="grid">全量表格</el-radio-button>
        </el-radio-group>
      </div>

      <!-- List view: Master + Detail -->
      <div v-if="viewMode === 'list'" class="gt-confirmation-followup__list-view">
        <div class="gt-confirmation-followup__master">
          <FollowupMaster
            :rows="rows"
            :readonly="readonly"
            :selected-ids="selectedIds"
            :is-dirty="isDirty"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @import="handleImport"
            @export-template="handleExportTemplate"
            @export-data="handleExportData"
            @row-click="handleRowClick"
            @update:selected-ids="selectedIds = $event"
          />
        </div>
        <div class="gt-confirmation-followup__detail">
          <FollowupDetail
            :row="currentRow"
            :readonly="readonly"
            @update="handleFieldUpdate"
          >
            <template #memo-preview>
              <FollowupMemoPreview
                :row="currentRow"
                :readonly="readonly"
                @update="handleFieldUpdate"
                @regenerate="handleRegenerate"
              />
            </template>
          </FollowupDetail>
        </div>
      </div>

      <!-- Grid view: 全量表格（可行内编辑） -->
      <div v-else class="gt-confirmation-followup__grid-view">
        <div v-if="!readonly" class="gt-confirmation-followup__grid-toolbar">
          <el-button type="primary" size="small" @click="handleAdd">+ 新增</el-button>
          <el-button type="success" size="small" @click="handleSave">保存</el-button>
          <el-button size="small" @click="handleImport">导入</el-button>
          <el-button size="small" @click="handleExportData">导出数据</el-button>
        </div>
        <el-table
          :data="rows"
          border
          size="small"
          :max-height="500"
          highlight-current-row
          style="width:100%"
          table-layout="auto"
          class="gt-confirmation-followup__full-table"
        >
          <el-table-column prop="seq" label="序号" min-width="45" align="center" />
          <el-table-column label="函证索引号" min-width="85">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.confirm_index" size="small" placeholder="D0-" />
              <span v-else>{{ row.confirm_index }}</span>
            </template>
          </el-table-column>
          <el-table-column label="被函证单位" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.entity_name" size="small" placeholder="单位名称" />
              <span v-else>{{ row.entity_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="跟函人员" min-width="80">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.followup_person" size="small" />
              <span v-else>{{ row.followup_person }}</span>
            </template>
          </el-table-column>
          <el-table-column label="跟函日期" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.followup_date" size="small" placeholder="YYYY-MM-DD" />
              <span v-else>{{ row.followup_date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="确认场景" min-width="100" align="center">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.scenario" size="small" placeholder="—">
                <el-option value="immediate" label="现场即时确认" />
                <el-option value="later_follow" label="留函跟踪" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.scenario === 'immediate'" type="success" size="small">现场即时</el-tag>
                <el-tag v-else-if="row.scenario === 'later_follow'" type="warning" size="small">留函跟踪</el-tag>
                <span v-else>—</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="控制结论" min-width="80" align="center">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.control_conclusion" size="small" placeholder="—">
                <el-option value="pass" label="通过" />
                <el-option value="fail" label="未通过" />
                <el-option value="pending" label="未完成" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.control_conclusion === 'pass'" type="success" size="small">通过</el-tag>
                <el-tag v-else-if="row.control_conclusion === 'fail'" type="danger" size="small">未通过</el-tag>
                <span v-else style="color:#909399;font-size:11px">未完成</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="签名状态" min-width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.sign_status === 'signed' ? 'success' : 'info'" size="small">
                {{ row.sign_status === 'signed' ? '已签' : '未签' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FollowupRow } from './followupTypes'
import { useFollowupData } from './composables/useFollowupData'
import { useMemoCompose } from './composables/useMemoCompose'
import FollowupDashboard from './FollowupDashboard.vue'
import FollowupMaster from './FollowupMaster.vue'
import FollowupDetail from './FollowupDetail.vue'
import FollowupMemoPreview from './FollowupMemoPreview.vue'

// ─── Props & Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── Readonly computed ────────────────────────────────────────────────────────

const readonly = computed(() => props.readonly ?? false)

// ─── Legacy format check ──────────────────────────────────────────────────────

const isLegacyFormat = computed(() => {
  const data = props.htmlData
  // 无数据或空对象 → 新底稿，走现代布局
  if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) return false
  // 有 _format → 现代格式（followup-v1 或 confirmation-followup-v1 都接受）
  if (data._format) return false
  // 无 _format 但有 cells/grid 等旧数据 → 旧格式
  return !!(data.cells || data.grid)
})

// ─── Data composable ─────────────────────────────────────────────────────────

const {
  rows,
  isDirty,
  addRow,
  deleteRows,
  updateField,
  importRows,
  progressMetrics,
  buildPayload,
} = useFollowupData({
  htmlData: () => props.htmlData,
  readonly: readonly.value,
})

// ─── Memo compose ────────────────────────────────────────────────────────────

const { applyToRow, regenerate } = useMemoCompose()

// ─── UI state ────────────────────────────────────────────────────────────────

const viewMode = ref<'list' | 'grid'>('list')
const selectedIds = ref<string[]>([])
const currentRow = ref<FollowupRow | null>(null)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAdd() {
  const newRow = addRow()
  currentRow.value = newRow
}

function handleDelete() {
  deleteRows(selectedIds.value)
  selectedIds.value = []
  if (currentRow.value && !rows.value.find((r) => r._row_id === currentRow.value?._row_id)) {
    currentRow.value = null
  }
}

function handleSave() {
  // Auto-apply memo to all non-overridden rows before saving
  rows.value.forEach((row, idx) => {
    if (!row.memo_overridden) {
      const updated = applyToRow(row)
      rows.value[idx] = { ...row, memo_text: updated.memo_text }
    }
  })
  const payload = buildPayload()
  emit('save', payload)
}

function handleImport() {
  // Stub: open import dialog
  console.info('[FollowupD03] Import triggered')
}

async function handleExportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()
    const headers = ['序号', '函证索引号', '被函证单位', '单位地址', '跟函人员', '跟函日期', '确认场景']
    const example = ['1', 'D0-001', '示例公司（请删除）', '北京市XX区', '张三', '2025-12-31', '现场即时确认']
    const ws = utils.aoa_to_sheet([headers, example])
    ws['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 20 }, { wch: 25 }, { wch: 10 }, { wch: 12 }, { wch: 14 }]
    utils.book_append_sheet(wb, ws, '跟函记录')
    writeFileXLSX(wb, 'D0-3跟函记录导入模板.xlsx')
  } catch (e: any) {
    console.error('[FollowupD03] Export template error:', e)
  }
}

async function handleExportData() {
  if (rows.value.length === 0) return
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const headers = ['序号', '函证索引号', '被函证单位', '跟函人员', '跟函日期', '确认场景', '控制结论', '签名状态']
    const data = rows.value.map(r => [
      r.seq ?? '', r.confirm_index ?? '', r.entity_name ?? '',
      r.followup_person ?? '', r.followup_date ?? '',
      r.scenario === 'immediate' ? '现场即时确认' : '留函跟踪',
      r.control_conclusion === 'pass' ? '通过' : r.control_conclusion === 'fail' ? '未通过' : '未完成',
      r.sign_status === 'signed' ? '已签' : '未签',
    ])
    const ws = utils.aoa_to_sheet([headers, ...data])
    ws['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 20 }, { wch: 10 }, { wch: 12 }, { wch: 14 }, { wch: 10 }, { wch: 8 }]
    const wb = utils.book_new()
    utils.book_append_sheet(wb, ws, '跟函数据')
    writeFileXLSX(wb, 'D0-3跟函数据导出.xlsx')
  } catch (e: any) {
    console.error('[FollowupD03] Export data error:', e)
  }
}

function handleRowClick(row: FollowupRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  updateField(currentRow.value._row_id, field, value)
}

function handleRegenerate() {
  if (!currentRow.value) return
  const regenerated = regenerate(currentRow.value)
  // Apply regenerated fields back
  updateField(currentRow.value._row_id!, 'memo_text', regenerated.memo_text)
  updateField(currentRow.value._row_id!, 'memo_overridden', false)
}
</script>

<style scoped>
.gt-confirmation-followup {
  padding: 12px;
}

.gt-confirmation-followup__legacy-notice {
  margin-bottom: 16px;
}

.gt-confirmation-followup__view-switch {
  margin-bottom: 12px;
}

.gt-confirmation-followup__list-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-confirmation-followup__grid-view {
  width: 100%;
}

.gt-confirmation-followup__grid-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

/* 全量表格：表头折行 + 紧凑字号 */
.gt-confirmation-followup__full-table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
}

.gt-confirmation-followup__full-table :deep(.el-table__body td .cell) {
  font-size: 12px;
  padding: 2px 4px;
}

@media (min-width: 1400px) {
  .gt-confirmation-followup__list-view {
    gap: 12px;
  }
}
</style>
