<script setup lang="ts">
/**
 * GtWpVersionTrail — 底稿版本历史侧栏（el-drawer）
 *
 * Spec: .kiro/specs/workpaper-version-trail/
 * Task: 6.1
 *
 * 职责：
 * - 展示版本时间线（el-timeline，按时间倒序）
 * - 顶部操作栏：手动保存版本（描述输入 + 按钮）
 * - 每条记录：时间戳 | 操作人 | snapshot_type 彩色标签 | 描述 | change_summary
 * - 展开详细变更列表
 * - 版本对比：两个 radio 选择 → "对比"按钮 → VersionDiffPanel
 * - 回滚（仅 canRollback 时显示）+ ElMessageBox 确认
 * - 分页加载更多
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.5, 7.1, 7.2, 7.3, 7.4
 */
import { ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fmtDateTime } from '@/utils/formatters'
import useVersionTrail from '../composables/useVersionTrail'
import type { SnapshotMeta, SnapshotType } from '../composables/useVersionTrail'
import VersionDiffPanel from './VersionDiffPanel.vue'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  workpaperId: string
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'rollback-completed'): void
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  versions,
  loading,
  drawerVisible,
  diffResult,
  diffLoading,
  selectedVersions,
  canRollback,
  hasMore,
  currentPage,
  loadVersions,
  createSnapshot,
  compareDiff,
  rollback,
  openDrawer,
  closeDrawer,
} = useVersionTrail({
  projectId: toRef(props, 'projectId'),
  workpaperId: toRef(props, 'workpaperId'),
})

// ─── Local State ─────────────────────────────────────────────────────────────

const snapshotDescription = ref('')
const expandedIds = ref<Set<string>>(new Set())
const compareVersionA = ref<string | null>(null)
const compareVersionB = ref<string | null>(null)
const showDiffPanel = ref(false)

// ─── Snapshot Type 配置 ──────────────────────────────────────────────────────

const SNAPSHOT_TYPE_CONFIG: Record<SnapshotType, { label: string; color: string }> = {
  manual: { label: '手动保存', color: '#409eff' },
  auto_sampling: { label: '抽凭快照', color: '#e6a23c' },
  auto_import: { label: '导入快照', color: '#9b59b6' },
  review_sign: { label: '签字快照', color: '#67c23a' },
  status_change: { label: '状态变更', color: '#909399' },
  rollback: { label: '回滚', color: '#f56c6c' },
}

function getTypeLabel(type: SnapshotType): string {
  return SNAPSHOT_TYPE_CONFIG[type]?.label ?? type
}

function getTypeColor(type: SnapshotType): string {
  return SNAPSHOT_TYPE_CONFIG[type]?.color ?? '#909399'
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleSaveVersion() {
  const desc = snapshotDescription.value.trim()
  await createSnapshot(desc || undefined)
  snapshotDescription.value = ''
}

function toggleExpand(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

async function handleCompare() {
  if (!compareVersionA.value || !compareVersionB.value) {
    ElMessage.warning('请选择两个版本进行对比')
    return
  }
  if (compareVersionA.value === compareVersionB.value) {
    ElMessage.warning('不能对比相同版本')
    return
  }
  showDiffPanel.value = true
  await compareDiff(compareVersionA.value, compareVersionB.value)
}

async function handleRollback(versionId: string) {
  await rollback(versionId)
  // composable 内部处理了 ElMessageBox 确认弹窗
  // 如果用户确认并成功，emit 通知父组件
  emit('rollback-completed')
}

async function handleLoadMore() {
  await loadVersions(currentPage.value + 1)
}

function handleDrawerClose() {
  closeDrawer()
  showDiffPanel.value = false
  compareVersionA.value = null
  compareVersionB.value = null
  expandedIds.value.clear()
}

// ─── 获取对比版本元数据 ─────────────────────────────────────────────────────

function getVersionMeta(id: string | null): SnapshotMeta | undefined {
  if (!id) return undefined
  return versions.value.find(v => v.id === id)
}

// ─── Expose openDrawer for parent ────────────────────────────────────────────

defineExpose({ openDrawer, drawerVisible })
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    direction="rtl"
    :size="520"
    title="版本历史"
    :before-close="handleDrawerClose"
    class="version-trail-drawer"
  >
    <!-- 顶部操作栏：保存版本 -->
    <div class="vt-action-bar">
      <el-input
        v-model="snapshotDescription"
        placeholder="输入版本描述（可选）"
        :maxlength="200"
        clearable
        class="vt-desc-input"
        @keyup.enter="handleSaveVersion"
      />
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSaveVersion"
      >
        保存版本
      </el-button>
    </div>

    <!-- 版本对比区域 -->
    <div v-if="versions.length >= 2" class="vt-compare-bar">
      <span class="vt-compare-label">版本对比：</span>
      <el-radio-group v-model="compareVersionA" size="small" class="vt-radio-group">
        <el-radio
          v-for="v in versions"
          :key="'a-' + v.id"
          :value="v.id"
        >
          {{ fmtDateTime(v.createdAt) }}
        </el-radio>
      </el-radio-group>
      <span class="vt-compare-vs">VS</span>
      <el-radio-group v-model="compareVersionB" size="small" class="vt-radio-group">
        <el-radio
          v-for="v in versions"
          :key="'b-' + v.id"
          :value="v.id"
        >
          {{ fmtDateTime(v.createdAt) }}
        </el-radio>
      </el-radio-group>
      <el-button
        type="primary"
        size="small"
        :loading="diffLoading"
        :disabled="!compareVersionA || !compareVersionB"
        @click="handleCompare"
      >
        对比
      </el-button>
    </div>

    <!-- Diff 对比面板 -->
    <VersionDiffPanel
      v-if="showDiffPanel && diffResult"
      :diff-result="diffResult"
      :version-a="getVersionMeta(compareVersionA)!"
      :version-b="getVersionMeta(compareVersionB)!"
      class="vt-diff-panel"
    />

    <!-- 时间线 -->
    <div v-loading="loading" class="vt-timeline-container">
      <el-timeline v-if="versions.length > 0">
        <el-timeline-item
          v-for="version in versions"
          :key="version.id"
          :timestamp="fmtDateTime(version.createdAt)"
          placement="top"
          :color="getTypeColor(version.snapshotType)"
        >
          <div class="vt-item-header">
            <el-tag
              size="small"
              :color="getTypeColor(version.snapshotType)"
              effect="dark"
              class="vt-type-tag"
            >
              {{ getTypeLabel(version.snapshotType) }}
            </el-tag>
            <span class="vt-operator">{{ version.userName || '系统' }}</span>
            <span v-if="version.description" class="vt-desc">{{ version.description }}</span>
          </div>

          <div v-if="version.changeSummary" class="vt-change-summary">
            {{ version.changeSummary }}
          </div>

          <div class="vt-item-meta">
            <span class="vt-item-count">{{ version.itemCount }} 条目</span>
            <el-button
              link
              size="small"
              @click="toggleExpand(version.id)"
            >
              {{ expandedIds.has(version.id) ? '收起' : '详情' }}
            </el-button>
            <el-button
              v-if="canRollback"
              link
              size="small"
              type="danger"
              @click="handleRollback(version.id)"
            >
              回滚
            </el-button>
          </div>

          <!-- 展开详细信息 -->
          <div v-if="expandedIds.has(version.id)" class="vt-expanded-detail">
            <div class="vt-detail-row">
              <span class="vt-detail-label">版本ID：</span>
              <span class="vt-detail-value">{{ version.id.slice(0, 8) }}...</span>
            </div>
            <div class="vt-detail-row">
              <span class="vt-detail-label">数据大小：</span>
              <span class="vt-detail-value">{{ (version.dataSizeBytes / 1024).toFixed(1) }} KB</span>
            </div>
            <div class="vt-detail-row">
              <span class="vt-detail-label">快照类型：</span>
              <span class="vt-detail-value">{{ version.snapshotType }}</span>
            </div>
            <div v-if="version.changeSummary" class="vt-detail-row">
              <span class="vt-detail-label">变更摘要：</span>
              <span class="vt-detail-value">{{ version.changeSummary }}</span>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>

      <!-- 空状态 -->
      <el-empty
        v-else-if="!loading"
        description="暂无版本记录"
      />

      <!-- 加载更多 -->
      <div v-if="hasMore" class="vt-load-more">
        <el-button
          :loading="loading"
          @click="handleLoadMore"
        >
          加载更多
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.vt-action-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  padding: 0 4px;
}

.vt-desc-input {
  flex: 1;
}

.vt-compare-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.vt-compare-label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.vt-radio-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 120px;
  overflow-y: auto;
  padding: 4px;
}

.vt-compare-vs {
  font-size: 12px;
  font-weight: bold;
  color: #909399;
  margin: 0 4px;
}

.vt-diff-panel {
  margin-bottom: 16px;
}

.vt-timeline-container {
  min-height: 200px;
}

.vt-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.vt-type-tag {
  border: none;
  font-size: 12px;
}

.vt-operator {
  font-size: 13px;
  color: #606266;
}

.vt-desc {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
}

.vt-change-summary {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.vt-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.vt-item-count {
  font-size: 12px;
  color: #c0c4cc;
}

.vt-expanded-detail {
  margin-top: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
  border-left: 3px solid #e4e7ed;
}

.vt-detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}

.vt-detail-label {
  color: #909399;
  min-width: 70px;
}

.vt-detail-value {
  color: #606266;
}

.vt-load-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
