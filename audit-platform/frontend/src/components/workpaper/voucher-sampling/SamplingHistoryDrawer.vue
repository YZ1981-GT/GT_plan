<script setup lang="ts">
/**
 * SamplingHistoryDrawer — 抽凭历史+版本对比侧栏
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 9.1
 *
 * 功能：
 * - el-drawer（direction=rtl，width=520px）
 * - el-timeline 展示历史（按时间倒序）
 * - 每条：操作时间 | 操作人 | 抽样方法 | 样本量 | 覆盖率 | 阶段标签
 * - el-collapse 展开完整 extraction_criteria JSON
 * - 最新非撤销记录显示"撤销"按钮
 * - 已撤销记录灰色删除线 + is_undone 标记
 * - "对比"功能：el-checkbox 选择两条记录 → 点击"对比"打开 ComparePanel
 *
 * Requirements: 6.1, 6.2, 6.4, 6.5, 6.6, 8.5
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { ExtractionLogEntry } from '../composables/useVoucherSampling'
import type { SamplingMethod, Phase } from '../composables/useSamplingAlgorithms'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  historyList: ExtractionLogEntry[]
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'undo', logId: string): void
  (e: 'compare', logIdA: string, logIdB: string): void
}>()

// ─── 方法名中文映射 ──────────────────────────────────────────────────────────

const METHOD_LABEL_MAP: Record<SamplingMethod, string> = {
  random: '随机抽样',
  stratified: '金额分层',
  specific_item: '特定项目',
  systematic: '系统抽样',
  mus: 'MUS',
}

function getMethodLabel(method: SamplingMethod): string {
  return METHOD_LABEL_MAP[method] || method
}

// ─── 阶段标签类型 ────────────────────────────────────────────────────────────

function getPhaseTagType(phase: Phase): '' | 'success' | 'info' | 'warning' | 'danger' {
  return phase === 'preliminary' ? 'info' : 'success'
}

function getPhaseLabel(phase: Phase): string {
  return phase === 'preliminary' ? '预审' : '年审'
}

// ─── 时间格式化 ──────────────────────────────────────────────────────────────

function formatTime(isoStr: string): string {
  if (!isoStr) return '—'
  const d = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z')
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ─── 对比选择逻辑 ────────────────────────────────────────────────────────────

const selectedForCompare = ref<string[]>([])

function handleCheckChange(logId: string, checked: boolean) {
  if (checked) {
    if (selectedForCompare.value.length >= 2) {
      ElMessage.warning('最多选择两条记录进行对比')
      return
    }
    selectedForCompare.value.push(logId)
  } else {
    selectedForCompare.value = selectedForCompare.value.filter(id => id !== logId)
  }
}

function isChecked(logId: string): boolean {
  return selectedForCompare.value.includes(logId)
}

const canCompare = computed(() => selectedForCompare.value.length === 2)

function handleCompare() {
  if (selectedForCompare.value.length !== 2) {
    ElMessage.warning('请选择两条不同的记录进行对比')
    return
  }
  emit('compare', selectedForCompare.value[0], selectedForCompare.value[1])
}

// ─── 撤销逻辑 ────────────────────────────────────────────────────────────────

/** 最新非撤销记录的 id（仅该记录可撤销） */
const latestUndoableId = computed(() => {
  for (const entry of props.historyList) {
    if (!entry.isUndone) return entry.id
  }
  return null
})

function handleUndo(logId: string) {
  emit('undo', logId)
}

// ─── Drawer 关闭 ─────────────────────────────────────────────────────────────

function handleClose() {
  emit('update:visible', false)
  selectedForCompare.value = []
}

// ─── Collapse 展示 extraction_criteria ───────────────────────────────────────

function formatCriteria(criteria: Record<string, unknown>): string {
  try {
    return JSON.stringify(criteria, null, 2)
  } catch {
    return '{}'
  }
}

// ─── QC 合规标记（Requirement 8.5） ─────────────────────────────────────────

function isMethodCompliant(method: SamplingMethod): boolean {
  const compliantMethods: SamplingMethod[] = ['random', 'stratified', 'specific_item', 'systematic', 'mus']
  return compliantMethods.includes(method)
}

function isSeedObjective(entry: ExtractionLogEntry): boolean {
  // 种子由系统生成（非用户手动指定）视为客观
  const criteria = entry.extractionCriteria
  return criteria?.random_seed !== undefined && criteria?.random_seed !== null
}

function isCoverageSufficient(entry: ExtractionLogEntry): boolean {
  const rate = parseFloat(entry.coverageStats?.amountCoverageRate || '0')
  return rate >= 60
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    direction="rtl"
    :size="520"
    title="抽凭历史记录"
    :before-close="handleClose"
    @close="handleClose"
  >
    <!-- ═══ 对比操作栏 ═══ -->
    <div class="compare-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="!canCompare"
        @click="handleCompare"
      >
        对比 ({{ selectedForCompare.length }}/2)
      </el-button>
      <span v-if="selectedForCompare.length === 1" class="compare-hint">
        再选择一条记录即可对比
      </span>
    </div>

    <!-- ═══ 历史时间线 ═══ -->
    <el-timeline v-if="historyList.length > 0" class="history-timeline">
      <el-timeline-item
        v-for="entry in historyList"
        :key="entry.id"
        :timestamp="formatTime(entry.createdAt)"
        placement="top"
        :type="entry.isUndone ? 'info' : 'primary'"
      >
        <div
          class="history-entry"
          :class="{ 'entry-undone': entry.isUndone }"
        >
          <!-- 头部信息 -->
          <div class="entry-header">
            <span class="entry-user">{{ entry.userId }}</span>
            <el-tag size="small" :type="getPhaseTagType(entry.phase)">
              {{ getPhaseLabel(entry.phase) }}
            </el-tag>
            <el-tag v-if="entry.isUndone" size="small" type="info" class="tag-undone">
              已撤销
            </el-tag>
          </div>

          <!-- 主要信息 -->
          <div class="entry-body">
            <div class="entry-row">
              <span class="entry-field">抽样方法：</span>
              <span class="entry-value">{{ getMethodLabel(entry.samplingMethod) }}</span>
            </div>
            <div class="entry-row">
              <span class="entry-field">样本量：</span>
              <span class="entry-value">{{ entry.sampleCount }} 笔</span>
            </div>
            <div class="entry-row">
              <span class="entry-field">覆盖率：</span>
              <span class="entry-value">
                笔数 {{ entry.coverageStats?.countCoverageRate || '—' }}% /
                金额 {{ entry.coverageStats?.amountCoverageRate || '—' }}%
              </span>
            </div>
            <!-- ── 方法学增强回显（R22 seed/重抽原因；R17 间隔；R18 结论）── -->
            <div v-if="entry.randomSeed != null" class="entry-row">
              <span class="entry-field">随机种子：</span>
              <span class="entry-value entry-seed">{{ entry.randomSeed }}</span>
            </div>
            <div v-if="entry.samplingInterval" class="entry-row">
              <span class="entry-field">抽样间隔：</span>
              <span class="entry-value">{{ entry.samplingInterval }} 元</span>
            </div>
            <div v-if="entry.resampleReason" class="entry-row">
              <span class="entry-field">重抽原因：</span>
              <span class="entry-value entry-resample">{{ entry.resampleReason }}</span>
            </div>
            <div v-if="entry.conclusion" class="entry-row">
              <span class="entry-field">抽样结论：</span>
              <span class="entry-value">{{ entry.conclusion }}</span>
            </div>
          </div>

          <!-- QC 合规标记（Requirement 8.5） -->
          <div class="entry-compliance">
            <el-tag
              :type="isMethodCompliant(entry.samplingMethod) ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              {{ isMethodCompliant(entry.samplingMethod) ? '方法合规' : '方法不合规' }}
            </el-tag>
            <el-tag
              :type="isSeedObjective(entry) ? 'success' : 'warning'"
              size="small"
              effect="plain"
            >
              {{ isSeedObjective(entry) ? '种子客观' : '无种子' }}
            </el-tag>
            <el-tag
              :type="isCoverageSufficient(entry) ? 'success' : 'warning'"
              size="small"
              effect="plain"
            >
              {{ isCoverageSufficient(entry) ? '覆盖充分' : '覆盖不足' }}
            </el-tag>
          </div>

          <!-- 展开 extraction_criteria JSON -->
          <el-collapse class="entry-collapse">
            <el-collapse-item title="抽样参数详情">
              <pre class="criteria-json">{{ formatCriteria(entry.extractionCriteria) }}</pre>
            </el-collapse-item>
          </el-collapse>

          <!-- 操作区：对比选择 + 撤销按钮 -->
          <div class="entry-actions">
            <!-- 对比勾选（非撤销记录才可选） -->
            <el-checkbox
              v-if="!entry.isUndone"
              :model-value="isChecked(entry.id)"
              @change="(val: string | number | boolean) => handleCheckChange(entry.id, !!val)"
            >
              选择对比
            </el-checkbox>

            <!-- 撤销按钮（仅最新非 undone 记录） -->
            <el-button
              v-if="!entry.isUndone && entry.id === latestUndoableId"
              type="danger"
              size="small"
              plain
              @click="handleUndo(entry.id)"
            >
              撤销
            </el-button>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>

    <!-- 空状态 -->
    <el-empty v-else description="暂无抽凭历史记录" />
  </el-drawer>
</template>

<style scoped>
.compare-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 0 4px;
}

.compare-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.history-timeline {
  padding: 0 4px;
}

/* ── 单条历史记录 ── */
.history-entry {
  padding: 8px 0;
}

.entry-undone {
  opacity: 0.55;
}

.entry-undone .entry-body {
  text-decoration: line-through;
  color: var(--el-text-color-placeholder, #a8abb2);
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.entry-user {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
}

.tag-undone {
  margin-left: auto;
}

.entry-body {
  margin-bottom: 8px;
}

.entry-row {
  display: flex;
  align-items: center;
  font-size: 13px;
  line-height: 22px;
}

.entry-field {
  color: var(--el-text-color-secondary, #909399);
  min-width: 70px;
}

.entry-value {
  color: var(--el-text-color-regular, #606266);
}

.entry-seed {
  font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
  color: var(--el-color-primary, #409eff);
}

.entry-resample {
  color: var(--el-color-warning, #e6a23c);
}

/* ── QC 合规标记 ── */
.entry-compliance {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

/* ── Collapse 样式 ── */
.entry-collapse {
  margin-bottom: 8px;
}

.entry-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  height: 28px;
  line-height: 28px;
  color: var(--el-text-color-secondary, #909399);
}

.entry-collapse :deep(.el-collapse-item__content) {
  padding: 8px 0;
}

.criteria-json {
  font-size: 11px;
  font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
  background: var(--el-fill-color-lighter, #fafafa);
  border-radius: 4px;
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
  color: var(--el-text-color-regular, #606266);
}

/* ── 操作区 ── */
.entry-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
