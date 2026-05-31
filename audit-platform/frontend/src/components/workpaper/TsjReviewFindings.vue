<!--
  TsjReviewFindings.vue — TSJ 复核发现列表

  spec wp-tsj-llm-review task 4.2

  - 显示 pending 发现列表（issue_type + severity 色标 + 描述 + sheet/cell + 整改建议）
  - 每条发现有 ✅ 确认 / ❌ 驳回 按钮
  - 确认/驳回后视觉标记为已处理（灰色 + 删除线）
-->
<template>
  <div class="gt-tsj-findings">
    <div v-if="!findings || findings.length === 0" class="gt-tsj-findings-empty">
      暂无复核发现
    </div>
    <el-card
      v-for="(item, idx) in findings"
      :key="item.id || idx"
      shadow="hover"
      class="gt-tsj-finding-card"
      :class="{ 'gt-tsj-finding--processed': processedIds.has(item.id) }"
    >
      <template #header>
        <div class="gt-tsj-finding-header">
          <el-tag :type="severityTagType(item.severity)" size="small" effect="dark">
            {{ severityLabel(item.severity) }}
          </el-tag>
          <el-tag size="small" type="info">{{ item.issue_type || '未分类' }}</el-tag>
          <span v-if="item.sheet" class="gt-tsj-finding-location">
            📄 {{ item.sheet }}
            <code v-if="item.cell_range">{{ item.cell_range }}</code>
          </span>
        </div>
      </template>

      <p class="gt-tsj-finding-desc">{{ item.description || item.content_text }}</p>

      <p v-if="item.remediation" class="gt-tsj-finding-remediation">
        💡 <strong>整改建议：</strong>{{ item.remediation }}
      </p>

      <!-- Task 5.1: 定位跳转按钮 -->
      <div v-if="item.sheet && item.cell_range" class="gt-tsj-finding-locate">
        <el-link type="primary" :underline="false" @click="handleLocateCell(item)">
          📍 定位
        </el-link>
      </div>

      <!-- Task 5.2: 关联附件/证据显示 -->
      <div v-if="item.evidence_ref" class="gt-tsj-finding-evidence">
        <el-link type="warning" :underline="false" @click="handleOpenEvidence(item.evidence_ref!)">
          📎 证据: {{ item.evidence_ref }}
        </el-link>
      </div>

      <div class="gt-tsj-finding-actions">
        <el-button-group>
          <el-button
            type="success"
            size="small"
            :disabled="processedIds.has(item.id) || loadingIds.has(item.id)"
            :loading="loadingIds.has(item.id) && loadingAction === 'confirm'"
            @click="handleConfirm(item)"
          >
            ✅ 确认
          </el-button>
          <el-button
            type="danger"
            size="small"
            :disabled="processedIds.has(item.id) || loadingIds.has(item.id)"
            :loading="loadingIds.has(item.id) && loadingAction === 'reject'"
            @click="handleReject(item)"
          >
            ❌ 驳回
          </el-button>
        </el-button-group>
        <el-tag
          v-if="processedIds.has(item.id)"
          size="small"
          :type="processedActions.get(item.id) === 'confirm' ? 'success' : 'danger'"
        >
          {{ processedActions.get(item.id) === 'confirm' ? '已确认' : '已驳回' }}
        </el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface TsjFinding {
  id: string
  content_type: string
  content_text: string
  confidence_level?: string
  confirmation_status: string
  issue_type: string
  severity: string
  sheet: string
  cell_range: string
  description: string
  remediation: string
  evidence_ref?: string
}

const props = defineProps<{
  findings: TsjFinding[]
  wpId: string
  wpCode?: string
}>()

const emit = defineEmits<{
  (e: 'finding-confirmed', finding: TsjFinding): void
  (e: 'finding-rejected', finding: TsjFinding): void
  // TODO: 依赖 wp-locate-foundation 的 useCellLocate 实现实际跳转
  (e: 'locate-cell', target: { wpCode: string; sheet: string; cellRange: string }): void
  (e: 'open-evidence', evidenceRef: string): void
}>()

const processedIds = reactive(new Set<string>())
const processedActions = reactive(new Map<string, string>())
const loadingIds = reactive(new Set<string>())
const loadingAction = ref<'confirm' | 'reject' | ''>('')

function severityTagType(severity: string): 'danger' | 'warning' | 'info' {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'info'
}

function severityLabel(severity: string): string {
  if (severity === 'high') return '高风险'
  if (severity === 'medium') return '中风险'
  return '低风险'
}

// TODO: 依赖 wp-locate-foundation 的 useCellLocate 实现实际跳转
function handleLocateCell(item: TsjFinding) {
  emit('locate-cell', {
    wpCode: props.wpCode || '',
    sheet: item.sheet,
    cellRange: item.cell_range,
  })
}

function handleOpenEvidence(evidenceRef: string) {
  emit('open-evidence', evidenceRef)
}

async function handleConfirm(item: TsjFinding) {
  if (!item.id) {
    ElMessage.warning('该发现缺少 ID，无法确认')
    return
  }
  loadingIds.add(item.id)
  loadingAction.value = 'confirm'
  try {
    await api.post(`/api/ai-content/${item.id}/confirm`)
    processedIds.add(item.id)
    processedActions.set(item.id, 'confirm')
    ElMessage.success('已确认该复核发现')
    emit('finding-confirmed', item)
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '操作失败'
    ElMessage.error(`确认失败：${msg}`)
  } finally {
    loadingIds.delete(item.id)
    loadingAction.value = ''
  }
}

async function handleReject(item: TsjFinding) {
  if (!item.id) {
    ElMessage.warning('该发现缺少 ID，无法驳回')
    return
  }
  loadingIds.add(item.id)
  loadingAction.value = 'reject'
  try {
    await api.post(`/api/ai-content/${item.id}/reject`)
    processedIds.add(item.id)
    processedActions.set(item.id, 'reject')
    ElMessage.success('已驳回该复核发现')
    emit('finding-rejected', item)
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '操作失败'
    ElMessage.error(`驳回失败：${msg}`)
  } finally {
    loadingIds.delete(item.id)
    loadingAction.value = ''
  }
}
</script>

<style scoped>
.gt-tsj-findings {
  padding: var(--gt-space-2) 0;
}

.gt-tsj-findings-empty {
  text-align: center;
  color: var(--gt-color-text-tertiary);
  padding: var(--gt-space-4);
  font-size: var(--gt-font-size-sm);
}

.gt-tsj-finding-card {
  margin-bottom: var(--gt-space-2);
}

.gt-tsj-finding-card.gt-tsj-finding--processed {
  opacity: 0.55;
}

.gt-tsj-finding-card.gt-tsj-finding--processed .gt-tsj-finding-desc {
  text-decoration: line-through;
  color: var(--gt-color-text-tertiary);
}

.gt-tsj-finding-header {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  flex-wrap: wrap;
}

.gt-tsj-finding-location {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.gt-tsj-finding-location code {
  font-family: 'Consolas', 'Courier New', monospace;
  background: var(--gt-color-bg-elevated);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
}

.gt-tsj-finding-desc {
  margin: 0 0 8px;
  font-size: var(--gt-font-size-sm);
  line-height: 1.6;
  color: var(--gt-color-text);
}

.gt-tsj-finding-remediation {
  margin: 0 0 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  background: var(--gt-color-bg-elevated);
  padding: 6px 10px;
  border-radius: var(--gt-radius-sm);
  line-height: 1.5;
}

.gt-tsj-finding-actions {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding-top: 4px;
}

.gt-tsj-finding-locate {
  margin: 4px 0;
  font-size: var(--gt-font-size-xs);
}

.gt-tsj-finding-evidence {
  margin: 4px 0;
  font-size: var(--gt-font-size-xs);
}
</style>
