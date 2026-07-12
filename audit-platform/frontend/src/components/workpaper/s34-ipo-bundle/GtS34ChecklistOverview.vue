<script setup lang="ts">
/**
 * GtS34ChecklistOverview — S34-0 核查事项清单总览面板
 *
 * 以 el-table 呈现 S34-1~S34-41 各专项底稿的：
 * - 底稿编号、名称、对应监管条目（证监会/上交所/深交所/北交所）
 * - 适用状态、完成状态
 *
 * 点击底稿名称列 → emit('navigate', wpCode) → 父组件切换 Tab
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/
 * Task: 6.1, 6.2, 6.3
 * Requirements: 3.2, 3.3, 3.4, 5.5, 9.2, 9.3, 9.5, 10.2, 12.3
 * Property 6: 法规溯源映射稳定性 — 无对应条目显示 em-dash 而非空白
 */
import { ref, computed } from 'vue'
import type { S34ChecklistItem, Applicability, CompletionStatus } from '../composables/useS34BundleState'

// ─── Props ───
const props = withDefaults(defineProps<{
  checklist: S34ChecklistItem[]
  readonly?: boolean
  /** 项目上市板块（主板/科创板/创业板/北交所），用于高亮对应监管列 (Req 5.5, 9.5) */
  exchangeType?: string
}>(), {
  readonly: false,
  exchangeType: '',
})

// ─── Emits ───
const emit = defineEmits<{
  (e: 'navigate', wpCode: string): void
  (e: 'updateReason', wpCode: string, reason: string): void
}>()

// ─── 「仅显示适用」筛选 (Req 9.3) ───
const showApplicableOnly = ref(false)

/** 筛选后的清单数据：启用后隐藏 applicability === 'not_applicable' 的行 */
const filteredChecklist = computed(() => {
  if (!showApplicableOnly.value) return props.checklist
  return props.checklist.filter(item => item.applicability !== 'not_applicable')
})

// ─── 整体完成进度统计 (Req 3.4, 10.2) ───
const progressStats = computed(() => {
  const items = props.checklist
  return {
    completed: items.filter(i => i.status === 'completed' && i.applicability === 'applicable').length,
    inProgress: items.filter(i => i.status === 'in_progress' && i.applicability === 'applicable').length,
    notStarted: items.filter(i => i.status === 'not_started' && i.applicability === 'applicable').length,
    notApplicable: items.filter(i => i.applicability === 'not_applicable').length,
    total: items.length,
  }
})

// ─── 不适用理由 (Req 9.2) ───
/** 本地暂存各底稿的不适用理由（wpCode → reason） */
const naReasons = ref<Record<string, string>>({})

/** 更新不适用理由并 emit 给父组件 */
function handleReasonChange(wpCode: string, reason: string) {
  naReasons.value[wpCode] = reason
  emit('updateReason', wpCode, reason)
}

// ─── 板块高亮逻辑 (Req 5.5, 9.5) ───

/**
 * 根据 exchangeType 确定需高亮的监管列。
 * - 主板 / 科创板 → csrc + sse
 * - 创业板 → csrc + szse
 * - 北交所 → bse
 */
const highlightedColumns = computed<Set<string>>(() => {
  const type = props.exchangeType
  if (!type) return new Set()
  switch (type) {
    case '主板':
    case '科创板':
      return new Set(['csrc', 'sse'])
    case '创业板':
      return new Set(['csrc', 'szse'])
    case '北交所':
      return new Set(['bse'])
    default:
      return new Set()
  }
})

/** 获取列的高亮 class */
function getColumnHighlightClass(col: string): string {
  return highlightedColumns.value.has(col) ? 'checklist-col--highlighted' : ''
}

// ─── Visual helpers ───

/** 适用状态标签配置 */
function getApplicabilityTag(val: Applicability): { label: string; type: string } {
  switch (val) {
    case 'applicable':
      return { label: '适用', type: 'success' }
    case 'not_applicable':
      return { label: '不适用', type: 'info' }
    case 'unknown':
    default:
      return { label: '待确认', type: 'warning' }
  }
}

/** 完成状态标签配置 */
function getStatusTag(val: CompletionStatus): { label: string; type: string } {
  switch (val) {
    case 'completed':
      return { label: '已完成', type: 'success' }
    case 'in_progress':
      return { label: '进行中', type: 'warning' }
    case 'not_started':
    default:
      return { label: '未开始', type: 'info' }
  }
}

/** 监管条目单元格内容：空值显示 em-dash（Property 6, Req 12.4） */
function regDisplay(val: string | null | undefined): string {
  return val || '—'
}

/** 点击底稿名称 → navigate (Req 3.3) */
function handleNameClick(wpCode: string) {
  emit('navigate', wpCode)
}
</script>

<template>
  <div class="gt-s34-checklist-overview" data-testid="s34-checklist-overview">
    <!-- 工具栏：筛选 (Req 9.3) -->
    <div class="checklist-toolbar" data-testid="s34-checklist-toolbar">
      <el-checkbox v-model="showApplicableOnly" data-testid="s34-filter-applicable">
        仅显示适用
      </el-checkbox>
    </div>

    <!-- 整体完成进度统计 (Req 3.4, 10.2) -->
    <div class="checklist-progress" data-testid="s34-checklist-progress">
      <span class="progress-stat progress-stat--success">已完成 {{ progressStats.completed }}</span>
      <span class="progress-stat progress-stat--warning">进行中 {{ progressStats.inProgress }}</span>
      <span class="progress-stat progress-stat--info">未开始 {{ progressStats.notStarted }}</span>
      <span class="progress-stat progress-stat--disabled">不适用 {{ progressStats.notApplicable }}</span>
      <span class="progress-stat progress-stat--total">共 {{ progressStats.total }} 项</span>
    </div>

    <el-table
      :data="filteredChecklist"
      stripe
      border
      style="width: 100%"
      max-height="calc(100vh - 280px)"
      class="checklist-table"
      data-testid="s34-checklist-table"
    >
      <!-- 序号 -->
      <el-table-column
        prop="seq"
        label="序号"
        width="60"
        align="center"
        header-align="center"
      />

      <!-- 底稿编号 -->
      <el-table-column
        prop="wpCode"
        label="底稿编号"
        width="90"
        align="center"
        header-align="center"
      />

      <!-- 核查事项（可点击） -->
      <el-table-column
        prop="name"
        label="核查事项"
        min-width="160"
        header-align="center"
      >
        <template #default="{ row }">
          <span
            class="checklist-name-link"
            @click="handleNameClick(row.wpCode)"
          >
            {{ row.name }}
          </span>
        </template>
      </el-table-column>

      <!-- 证监会 (Req 5.5: 板块高亮) -->
      <el-table-column
        label="证监会"
        width="100"
        align="center"
        header-align="center"
        :class-name="getColumnHighlightClass('csrc')"
      >
        <template #default="{ row }">
          {{ regDisplay(row.regRef?.csrc) }}
        </template>
      </el-table-column>

      <!-- 上交所 -->
      <el-table-column
        label="上交所"
        width="100"
        align="center"
        header-align="center"
        :class-name="getColumnHighlightClass('sse')"
      >
        <template #default="{ row }">
          {{ regDisplay(row.regRef?.sse) }}
        </template>
      </el-table-column>

      <!-- 深交所 -->
      <el-table-column
        label="深交所"
        width="100"
        align="center"
        header-align="center"
        :class-name="getColumnHighlightClass('szse')"
      >
        <template #default="{ row }">
          {{ regDisplay(row.regRef?.szse) }}
        </template>
      </el-table-column>

      <!-- 北交所 -->
      <el-table-column
        label="北交所"
        width="100"
        align="center"
        header-align="center"
        :class-name="getColumnHighlightClass('bse')"
      >
        <template #default="{ row }">
          {{ regDisplay(row.regRef?.bse) }}
        </template>
      </el-table-column>

      <!-- 适用状态 + 不适用理由 (Req 9.2) -->
      <el-table-column
        label="适用状态"
        width="180"
        align="center"
        header-align="center"
      >
        <template #default="{ row }">
          <el-tag
            :type="getApplicabilityTag(row.applicability).type as any"
            size="small"
            disable-transitions
          >
            {{ getApplicabilityTag(row.applicability).label }}
          </el-tag>
          <!-- 不适用理由输入 (Req 9.2, 11.4) -->
          <el-input
            v-if="row.applicability === 'not_applicable'"
            :model-value="naReasons[row.wpCode] || ''"
            :disabled="props.readonly"
            placeholder="填写理由"
            size="small"
            class="na-reason-input"
            data-testid="s34-na-reason-input"
            @update:model-value="(val: string) => handleReasonChange(row.wpCode, val)"
          />
        </template>
      </el-table-column>

      <!-- 完成状态 -->
      <el-table-column
        label="完成状态"
        width="90"
        align="center"
        header-align="center"
      >
        <template #default="{ row }">
          <el-tag
            :type="getStatusTag(row.status).type as any"
            size="small"
            disable-transitions
          >
            {{ getStatusTag(row.status).label }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.gt-s34-checklist-overview {
  padding: 0;
}

/* 工具栏：「仅显示适用」筛选 (Req 9.3) */
.checklist-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px;
  margin-bottom: 8px;
}

/* 铁律：表格字体 13px */
.checklist-table {
  font-size: var(--wp-font-size, 13px);
}
.checklist-table :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.checklist-table :deep(.el-table__body td) {
  font-size: var(--wp-font-size, 13px);
}

/* 板块高亮：浅蓝背景 (Req 5.5, 9.5) */
.checklist-table :deep(.checklist-col--highlighted) {
  background-color: var(--el-color-primary-light-9, #ecf5ff) !important;
}

/* 底稿名称可点击：蓝色下划线 + cursor:pointer (Req 3.3) */
.checklist-name-link {
  color: var(--el-color-primary, #409eff);
  text-decoration: underline;
  cursor: pointer;
  transition: color 0.2s;
}
.checklist-name-link:hover {
  color: var(--el-color-primary-dark-2, #337ecc);
}

/* 整体完成进度统计 (Req 3.4, 10.2) */
.checklist-progress {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 4px;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
}

.progress-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.progress-stat--success { color: var(--gt-color-success, #67c23a); font-weight: 500; }
.progress-stat--warning { color: var(--gt-color-warning, #e6a23c); font-weight: 500; }
.progress-stat--info { color: var(--gt-color-text-tertiary, #909399); }
.progress-stat--disabled { color: var(--gt-color-text-placeholder, #c0c4cc); }
.progress-stat--total {
  margin-left: auto;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 500;
}

/* 不适用理由输入 (Req 9.2) */
.na-reason-input {
  margin-top: 4px;
  width: 100%;
}
</style>
