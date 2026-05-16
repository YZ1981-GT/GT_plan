<script setup lang="ts">
/**
 * 查看修改历史 — 单元格级时间线（右键菜单触发）
 * Sprint 11 Task 11.8
 */
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'

interface HistoryEntry {
  id: string
  action: string
  user_id: string
  details: Record<string, any>
  created_at: string
}

const props = defineProps<{
  visible: boolean
  wpId: string
  cellRef: string
}>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const history = ref<HistoryEntry[]>([])
const loading = ref(false)

watch(() => props.visible, async (v) => {
  if (v && props.cellRef) {
    await loadHistory()
  }
})

async function loadHistory() {
  loading.value = true
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/audit-trail`, {
      params: { cell_ref: props.cellRef },
    })
    history.value = (data as any) || []
  } catch {
    history.value = []
  } finally {
    loading.value = false
  }
}

function actionLabel(action: string) {
  const map: Record<string, string> = {
    'workpaper.audited_modified': '审定数修改',
    'workpaper.procedure_marked': '程序标记',
    'workpaper.procedure_trimmed': '程序裁剪',
    'workpaper.prefill_executed': '预填充',
    'workpaper.cell_edited': '单元格编辑',
    'workpaper.formula_changed': '公式变更',
  }
  return map[action] || action
}

function close() {
  emit('update:visible', false)
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    title="单元格修改历史"
    direction="rtl"
    size="360px"
    @close="close"
  >
    <div class="cell-ref-label">{{ cellRef }}</div>
    <el-timeline v-loading="loading">
      <el-timeline-item
        v-for="entry in history"
        :key="entry.id"
        :timestamp="entry.created_at?.slice(0, 16)"
        placement="top"
      >
        <div class="history-entry">
          <el-tag size="small" type="info">{{ actionLabel(entry.action) }}</el-tag>
          <div v-if="entry.details?.old_value" class="change-detail">
            <span class="old-val">{{ entry.details.old_value }}</span>
            →
            <span class="new-val">{{ entry.details.new_value }}</span>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
    <div v-if="!loading && history.length === 0" class="empty-tip">暂无修改记录</div>
  </el-drawer>
</template>

<style scoped>
.cell-ref-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); margin-bottom: 12px; padding: 4px 8px; background: var(--gt-bg-subtle); border-radius: 4px; }
.history-entry { display: flex; flex-direction: column; gap: 4px; }
.change-detail { font-size: var(--gt-font-size-xs); }
.old-val { color: var(--gt-color-coral); text-decoration: line-through; }
.new-val { color: var(--gt-color-success); }
.empty-tip { text-align: center; padding: 24px; color: var(--gt-color-info); }
</style>
