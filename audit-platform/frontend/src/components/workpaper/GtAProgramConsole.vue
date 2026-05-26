<!--
  GtAProgramConsole.vue — A 类程序表中控台组件

  按 design §3.3 实现：
  - 程序行展开显示完整描述 + 历史决策
  - 状态切换（执行/裁剪/已完成）+ 必填理由
  - 关联底稿索引号渲染为 GtIndexChip 可点击
  - 类别筛选（常规★/IPO 加项/备选程序/舞弊应对）
  - 批量裁剪（多选 + 填理由 → 写回 ProcedureInstance.status='not_applicable'）
  - 进度条（17/20 完成 / 2 已裁 / 1 进行中）
  - 5 项认定 checkmark 展示（存在/完整性/权利义务/准确性/列报）

  锚定 spec workpaper-html-renderer Task 3.9
  Validates: Requirements 1.1（D2A 痛点 7 项）+ 3.2（A 程序表详细需求）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
  Layer 4 联动复用 `useStaleImpact` composable（WorkpaperEditor 已接入）。
-->

<template>
  <div class="gt-a-program-console">
    <!-- ─── 顶部：进度条 + 工具栏 ─── -->
    <div class="gt-a-program-console__header">
      <!-- 进度条 -->
      <div class="gt-a-program-console__progress">
        <el-progress
          :percentage="progressPercentage"
          :stroke-width="18"
          :text-inside="true"
          :format="progressFormat"
        />
        <div class="gt-a-program-console__progress-detail">
          <el-tag type="success" size="small" effect="plain">
            {{ completedCount }} 已完成
          </el-tag>
          <el-tag type="info" size="small" effect="plain">
            {{ trimmedCount }} 已裁剪
          </el-tag>
          <el-tag type="warning" size="small" effect="plain">
            {{ inProgressCount }} 进行中
          </el-tag>
          <el-tag size="small" effect="plain">
            {{ pendingCount }} 待执行
          </el-tag>
        </div>
      </div>

      <!-- 工具栏：类别筛选 + 批量操作 -->
      <div class="gt-a-program-console__toolbar">
        <div class="gt-a-program-console__filters">
          <el-radio-group v-model="activeCategory" size="small">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button
              v-for="cat in availableCategories"
              :key="cat"
              :label="cat"
            >
              {{ cat }}
            </el-radio-button>
          </el-radio-group>
        </div>

        <div class="gt-a-program-console__actions">
          <el-button
            v-if="!readonly && selectedIds.length > 0"
            type="warning"
            size="small"
            @click="openBatchTrimDialog"
          >
            批量裁剪 ({{ selectedIds.length }})
          </el-button>
        </div>
      </div>
    </div>

    <!-- ─── 程序清单表格 ─── -->
    <el-table
      ref="tableRef"
      :data="filteredPrograms"
      border
      row-key="id"
      :expand-row-keys="expandedRowKeys"
      @expand-change="handleExpandChange"
      @selection-change="handleSelectionChange"
      class="gt-a-program-console__table"
    >
      <!-- 多选列 -->
      <el-table-column
        v-if="!readonly"
        type="selection"
        width="40"
        :selectable="isRowSelectable"
      />

      <!-- 展开列 -->
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="gt-a-program-console__expand-content">
            <div class="gt-a-program-console__expand-desc">
              <h4>程序描述</h4>
              <p>{{ row.program_desc }}</p>
            </div>
            <div
              v-if="row.history && row.history.length > 0"
              class="gt-a-program-console__expand-history"
            >
              <h4>历史决策</h4>
              <el-timeline>
                <el-timeline-item
                  v-for="(item, idx) in row.history"
                  :key="idx"
                  :timestamp="item.timestamp"
                  :type="historyItemType(item.action)"
                  placement="top"
                >
                  <span>{{ item.user }} — {{ item.action }}</span>
                  <span v-if="item.reason" class="gt-a-program-console__history-reason">
                    （{{ item.reason }}）
                  </span>
                </el-timeline-item>
              </el-timeline>
            </div>
          </div>
        </template>
      </el-table-column>

      <!-- 序号 -->
      <el-table-column
        label="序号"
        prop="program_no"
        width="60"
        align="center"
      />

      <!-- 程序描述（截断显示） -->
      <el-table-column
        label="程序描述"
        prop="program_desc"
        min-width="300"
        show-overflow-tooltip
      />

      <!-- 类别 -->
      <el-table-column
        label="类别"
        prop="program_category"
        width="110"
        align="center"
      >
        <template #default="{ row }">
          <el-tag
            :type="categoryTagType(row.program_category)"
            size="small"
            effect="plain"
          >
            {{ row.program_category }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 5 项认定列 -->
      <el-table-column label="存在" width="55" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions?.existence" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column label="完整性" width="65" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions?.completeness" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column label="权利义务" width="75" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions?.rights" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column label="准确性" width="65" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions?.accuracy" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column label="列报" width="55" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions?.presentation" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>

      <!-- 关联底稿（I 列 GtIndexChip） -->
      <el-table-column label="关联底稿" min-width="140">
        <template #default="{ row }">
          <div v-if="row.linked_workpapers" class="gt-a-program-console__chips">
            <GtIndexChip
              v-for="(ref, idx) in parseLinkedWorkpapers(row.linked_workpapers)"
              :key="idx"
              :value="ref"
              :validate="true"
              @click="handleIndexChipClick"
            />
          </div>
        </template>
      </el-table-column>

      <!-- 状态 -->
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-dropdown
            v-if="!readonly"
            trigger="click"
            @command="(cmd: string) => handleStatusChange(row, cmd)"
          >
            <el-tag
              :type="statusTagType(row.status)"
              size="small"
              class="gt-a-program-console__status-tag"
            >
              {{ statusLabel(row.status) }}
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="in_progress">执行中</el-dropdown-item>
                <el-dropdown-item command="completed">已完成</el-dropdown-item>
                <el-dropdown-item command="not_applicable" divided>裁剪</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag v-else :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 裁剪理由（仅裁剪状态显示） -->
      <el-table-column label="裁剪理由" min-width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'not_applicable'" class="gt-a-program-console__trim-reason">
            {{ row.trim_reason || '—' }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 裁剪理由弹窗（单条） ─── -->
    <el-dialog
      v-model="trimDialogVisible"
      title="裁剪理由"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="trimForm" label-width="80px">
        <el-form-item label="程序">
          <span>{{ trimForm.programDesc }}</span>
        </el-form-item>
        <el-form-item label="理由" required>
          <el-input
            v-model="trimForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入裁剪理由（必填）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="trimDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!trimForm.reason.trim()"
          @click="confirmTrim"
        >
          确认裁剪
        </el-button>
      </template>
    </el-dialog>

    <!-- ─── 批量裁剪弹窗 ─── -->
    <el-dialog
      v-model="batchTrimDialogVisible"
      title="批量裁剪"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form :model="batchTrimForm" label-width="80px">
        <el-form-item label="选中程序">
          <span>共 {{ selectedIds.length }} 条程序</span>
        </el-form-item>
        <el-form-item label="理由" required>
          <el-input
            v-model="batchTrimForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入批量裁剪理由（必填，将应用到所有选中程序）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchTrimDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!batchTrimForm.reason.trim()"
          @click="confirmBatchTrim"
        >
          确认批量裁剪 ({{ selectedIds.length }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

// ─── Types ───
interface ProgramAssertions {
  existence?: boolean
  completeness?: boolean
  rights?: boolean
  accuracy?: boolean
  presentation?: boolean
}

interface ProgramHistoryItem {
  timestamp: string
  user: string
  action: string
  reason?: string
}

interface ProgramRow {
  id: string
  program_no: number
  program_desc: string
  program_category: string
  assertions?: ProgramAssertions
  linked_workpapers?: string
  status: string
  trim_reason?: string
  history?: ProgramHistoryItem[]
}

interface TrimDecision {
  programId: string
  reason: string
  timestamp?: string
  user?: string
}

interface AProgramSchema {
  fixed_cells?: Record<string, string>
  programs?: Array<Record<string, any>>
  assertions?: string[]
  [key: string]: any
}

interface AProgramHtmlData {
  programs: ProgramRow[]
  trim_decisions: TrimDecision[]
  signatures?: Array<{ role: string; name: string; date: string }>
}

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: AProgramSchema
  htmlData: AProgramHtmlData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'program-trim': [payload: { programId: string; reason: string }]
  'program-status-change': [payload: { programId: string; status: string }]
  'jump-to-workpaper': [wpCode: string]
  'save': [data: AProgramHtmlData]
}>()

// ─── State ───
const programs = ref<ProgramRow[]>([])
const activeCategory = ref('')
const selectedIds = ref<string[]>([])
const expandedRowKeys = ref<string[]>([])
const tableRef = ref<any>(null)

// Trim dialog (single)
const trimDialogVisible = ref(false)
const trimForm = ref({
  programId: '',
  programDesc: '',
  reason: '',
})

// Batch trim dialog
const batchTrimDialogVisible = ref(false)
const batchTrimForm = ref({
  reason: '',
})

// Auto-save debounce
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Initialize data from props ───
function initData() {
  if (props.htmlData?.programs) {
    programs.value = JSON.parse(JSON.stringify(props.htmlData.programs))
  } else {
    programs.value = []
  }
}

initData()

watch(() => props.htmlData, () => {
  initData()
}, { deep: true })

// ─── Computed ───
const availableCategories = computed(() => {
  const cats = new Set<string>()
  programs.value.forEach(p => {
    if (p.program_category) cats.add(p.program_category)
  })
  return Array.from(cats)
})

const filteredPrograms = computed(() => {
  if (!activeCategory.value) return programs.value
  return programs.value.filter(p => p.program_category === activeCategory.value)
})

const completedCount = computed(() =>
  programs.value.filter(p => p.status === 'completed').length
)

const trimmedCount = computed(() =>
  programs.value.filter(p => p.status === 'not_applicable').length
)

const inProgressCount = computed(() =>
  programs.value.filter(p => p.status === 'in_progress').length
)

const pendingCount = computed(() =>
  programs.value.filter(p => !p.status || p.status === 'pending').length
)

const progressPercentage = computed(() => {
  const total = programs.value.length
  if (total === 0) return 0
  const done = completedCount.value + trimmedCount.value
  return Math.round((done / total) * 100)
})

// ─── Methods ───
function progressFormat(percentage: number): string {
  const total = programs.value.length
  const done = completedCount.value + trimmedCount.value
  return `${done}/${total} (${percentage}%)`
}

function categoryTagType(category: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (category) {
    case '常规★': return ''
    case 'IPO 加项': return 'warning'
    case '备选程序': return 'info'
    case '舞弊应对': return 'danger'
    default: return 'info'
  }
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'not_applicable': return 'info'
    default: return ''
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '执行中'
    case 'not_applicable': return '已裁剪'
    default: return '待执行'
  }
}

function historyItemType(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (action.includes('完成')) return 'success'
  if (action.includes('裁剪')) return 'info'
  if (action.includes('执行')) return 'warning'
  return 'primary'
}

function isRowSelectable(row: ProgramRow): boolean {
  // Only allow selecting rows that are not already trimmed
  return row.status !== 'not_applicable' && row.status !== 'completed'
}

function parseLinkedWorkpapers(value: string): string[] {
  if (!value) return []
  // Split by common separators: / , ; or newline
  return value.split(/[/,;\n]/).map(s => s.trim()).filter(Boolean)
}

function handleExpandChange(row: ProgramRow, expandedRows: ProgramRow[]) {
  expandedRowKeys.value = expandedRows.map(r => r.id)
}

function handleSelectionChange(selection: ProgramRow[]) {
  selectedIds.value = selection.map(r => r.id)
}

function handleStatusChange(row: ProgramRow, newStatus: string) {
  if (newStatus === 'not_applicable') {
    // Open trim reason dialog
    trimForm.value = {
      programId: row.id,
      programDesc: row.program_desc?.slice(0, 80) + (row.program_desc?.length > 80 ? '...' : ''),
      reason: '',
    }
    trimDialogVisible.value = true
    return
  }

  // Direct status change (no reason required for non-trim)
  const idx = programs.value.findIndex(p => p.id === row.id)
  if (idx >= 0) {
    programs.value[idx].status = newStatus
    emit('program-status-change', { programId: row.id, status: newStatus })
    debounceSave()
  }
}

function confirmTrim() {
  const { programId, reason } = trimForm.value
  if (!reason.trim()) return

  const idx = programs.value.findIndex(p => p.id === programId)
  if (idx >= 0) {
    programs.value[idx].status = 'not_applicable'
    programs.value[idx].trim_reason = reason.trim()
  }

  emit('program-trim', { programId, reason: reason.trim() })
  trimDialogVisible.value = false
  debounceSave()
}

function openBatchTrimDialog() {
  batchTrimForm.value.reason = ''
  batchTrimDialogVisible.value = true
}

function confirmBatchTrim() {
  const reason = batchTrimForm.value.reason.trim()
  if (!reason) return

  selectedIds.value.forEach(id => {
    const idx = programs.value.findIndex(p => p.id === id)
    if (idx >= 0) {
      programs.value[idx].status = 'not_applicable'
      programs.value[idx].trim_reason = reason
    }
    emit('program-trim', { programId: id, reason })
  })

  selectedIds.value = []
  batchTrimDialogVisible.value = false
  debounceSave()
}

function handleIndexChipClick(resolved: ResolvedIndexRef) {
  if (resolved.ns === 'wp' && resolved.target) {
    emit('jump-to-workpaper', resolved.target)
  }
}

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    const data: AProgramHtmlData = {
      programs: programs.value,
      trim_decisions: programs.value
        .filter(p => p.status === 'not_applicable' && p.trim_reason)
        .map(p => ({
          programId: p.id,
          reason: p.trim_reason!,
        })),
      signatures: props.htmlData?.signatures,
    }
    emit('save', data)
  }, 1500)
}
</script>

<style scoped>
.gt-a-program-console {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a-program-console__header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-a-program-console__progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-a-program-console__progress-detail {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-a-program-console__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-a-program-console__filters {
  flex: 1;
}

.gt-a-program-console__table {
  width: 100%;
}

.gt-a-program-console__check {
  color: var(--el-color-success);
  font-weight: bold;
  font-size: 16px;
}

.gt-a-program-console__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.gt-a-program-console__status-tag {
  cursor: pointer;
}

.gt-a-program-console__trim-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gt-a-program-console__expand-content {
  padding: 12px 24px;
}

.gt-a-program-console__expand-content h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.gt-a-program-console__expand-content p {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.gt-a-program-console__expand-history {
  margin-top: 12px;
}

.gt-a-program-console__history-reason {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
