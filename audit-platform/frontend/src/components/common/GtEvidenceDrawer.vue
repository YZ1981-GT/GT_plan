<script setup lang="ts">
/**
 * GtEvidenceDrawer — 证据关系抽屉（Task 4.4, Wave 3）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R2, R3, R4
 * Design: §6.2 / §3.2
 *
 * 功能：
 *  - 展示指定源或目标的所有 EvidenceRef（R4.3: 双向查询同一引用）
 *  - 显示：版本、content_hash（截断）、actor、locator 链接、影响路径
 *  - 跨项目错误显示通用 "目标不可访问"（R4.2）
 *  - 元数据完整门禁状态标识（R2.1）
 */
import { ref, computed, watch, toRef } from 'vue'
import { useEvidenceRefs, type EvidenceRefItem, type ImpactNode } from '@/composables/useEvidenceRefs'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
  /** 查询方向: source=从源端查, evidence=从目标端查 */
  direction?: 'source' | 'evidence'
  sourceType?: string
  sourceId?: string
  evidenceType?: string
  evidenceId?: string
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'navigate', ref: EvidenceRefItem): void
}>()

const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const {
  loading,
  error,
  refs,
  hasMore,
  queryRefs,
  queryImpact,
} = useEvidenceRefs(projectIdRef, yearRef)

const showImpact = ref(false)
const impactNodes = ref<ImpactNode[]>([])
const impactLoading = ref(false)

const drawerTitle = computed(() => props.title || '证据关系')
const drawerVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

// 当抽屉打开时加载数据
watch(() => props.visible, async (v) => {
  if (v) {
    await loadRefs()
  }
}, { immediate: true })

async function loadRefs() {
  await queryRefs({
    direction: props.direction || 'source',
    source_type: props.sourceType,
    source_id: props.sourceId,
    evidence_type: props.evidenceType,
    evidence_id: props.evidenceId,
    status: 'active',
    limit: 100,
  })
}

async function loadImpact() {
  if (!props.sourceType || !props.sourceId) return
  impactLoading.value = true
  const result = await queryImpact({
    source_type: props.sourceType,
    source_id: props.sourceId,
    max_depth: 10,
    limit: 100,
  })
  if (result) {
    impactNodes.value = result.nodes
  }
  impactLoading.value = false
  showImpact.value = true
}

function truncateHash(hash: string | null): string {
  if (!hash) return '-'
  if (hash.length <= 16) return hash
  return hash.slice(0, 8) + '…' + hash.slice(-8)
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z')
    return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
  } catch {
    return dateStr
  }
}

function handleNavigate(item: EvidenceRefItem) {
  emit('navigate', item)
}

function statusTag(status: string) {
  return status === 'active' ? 'success' : 'info'
}
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    :title="drawerTitle"
    direction="rtl"
    size="480px"
    :destroy-on-close="false"
  >
    <!-- 错误提示（R4.2: 跨项目脱敏） -->
    <el-alert
      v-if="error"
      type="error"
      :title="error"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
    />

    <!-- 加载状态 -->
    <div v-if="loading" style="text-align: center; padding: 40px 0">
      <el-icon class="is-loading" :size="24"><i class="el-icon-loading" /></el-icon>
      <p style="color: #909399; margin-top: 8px">加载中…</p>
    </div>

    <!-- 引用列表 -->
    <div v-else-if="refs.length > 0">
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
        <span style="font-size: 13px; color: #606266">
          共 {{ refs.length }} 条{{ hasMore ? '+' : '' }}引用
        </span>
        <el-button
          v-if="props.sourceType && props.sourceId"
          size="small"
          type="primary"
          text
          @click="loadImpact"
          :loading="impactLoading"
        >
          查看影响路径
        </el-button>
      </div>

      <el-card
        v-for="item in refs"
        :key="item.id"
        shadow="hover"
        class="evidence-ref-card"
      >
        <template #header>
          <div class="ref-card-header">
            <el-tag :type="statusTag(item.status)" size="small">
              {{ item.status === 'active' ? '有效' : '已停用' }}
            </el-tag>
            <span class="ref-type">{{ item.evidence_type }}</span>
            <el-button
              size="small"
              type="primary"
              text
              @click="handleNavigate(item)"
            >
              定位 →
            </el-button>
          </div>
        </template>

        <div class="ref-card-body">
          <!-- 版本 -->
          <div class="ref-field">
            <span class="ref-label">版本</span>
            <span class="ref-value">v{{ item.target_version ?? '-' }}</span>
          </div>

          <!-- Content Hash（截断） -->
          <div class="ref-field">
            <span class="ref-label">Hash</span>
            <el-tooltip :content="item.target_hash || '无'" placement="top">
              <span class="ref-value ref-hash">{{ truncateHash(item.target_hash) }}</span>
            </el-tooltip>
          </div>

          <!-- Actor -->
          <div class="ref-field">
            <span class="ref-label">创建者</span>
            <span class="ref-value">{{ item.context || '-' }}</span>
          </div>

          <!-- 来源 -->
          <div class="ref-field">
            <span class="ref-label">来源</span>
            <span class="ref-value">{{ item.source_type }}:{{ item.source_id }}</span>
          </div>

          <!-- 标签 -->
          <div v-if="item.label" class="ref-field">
            <span class="ref-label">标签</span>
            <el-tag size="small" type="info">{{ item.label }}</el-tag>
          </div>

          <!-- 创建时间 -->
          <div class="ref-field">
            <span class="ref-label">创建</span>
            <span class="ref-value ref-time">{{ formatDate(item.created_at) }}</span>
          </div>
        </div>
      </el-card>

      <!-- 分页提示 -->
      <div v-if="hasMore" style="text-align: center; padding: 12px 0">
        <el-text type="info" size="small">更多引用请缩小查询范围</el-text>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else description="暂无证据引用" />

    <!-- 影响路径面板 -->
    <template v-if="showImpact">
      <el-divider content-position="left">影响路径</el-divider>
      <div v-if="impactNodes.length === 0">
        <el-text type="info">无下游影响</el-text>
      </div>
      <el-timeline v-else>
        <el-timeline-item
          v-for="node in impactNodes"
          :key="`${node.target_type}:${node.target_id}`"
          :color="node.distance === 1 ? '#409eff' : '#e6a23c'"
          :hollow="node.distance > 1"
        >
          <div class="impact-node">
            <span class="impact-type">{{ node.target_type }}</span>
            <span class="impact-id">{{ node.target_id }}</span>
            <el-tag size="small" :type="node.distance === 1 ? '' : 'warning'">
              {{ node.distance === 1 ? '直接' : `传递(${node.distance}层)` }}
            </el-tag>
          </div>
        </el-timeline-item>
      </el-timeline>
    </template>
  </el-drawer>
</template>

<style scoped>
.evidence-ref-card {
  margin-bottom: 10px;
}
.evidence-ref-card :deep(.el-card__header) {
  padding: 8px 12px;
}
.evidence-ref-card :deep(.el-card__body) {
  padding: 10px 12px;
}
.ref-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ref-type {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}
.ref-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ref-field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.ref-label {
  min-width: 48px;
  color: #909399;
  flex-shrink: 0;
}
.ref-value {
  color: #606266;
  word-break: break-all;
}
.ref-hash {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 2px;
}
.ref-time {
  font-size: 11px;
  color: #909399;
}
.impact-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.impact-type {
  color: #606266;
  font-weight: 500;
}
.impact-id {
  color: #909399;
  font-family: monospace;
  font-size: 11px;
}
</style>
