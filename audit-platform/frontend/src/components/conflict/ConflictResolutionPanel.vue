<!--
  ConflictResolutionPanel — 跨模块冲突调解面板（spec global-refinement-v3 Task 7.4）
  =============================================================================
  以 el-drawer 形态展示 pending 冲突列表 + 详情对比 + 三选一调解。

  调用：
    GET  /api/projects/{pid}/conflicts/pending  加载列表
    POST /api/conflicts/{id}/resolve            调解

  Props:
    projectId: string  必需，传入当前项目 ID
    modelValue?: boolean  v-model 控制 drawer 显隐（可选）

  Emits:
    (e: 'update:modelValue', v: boolean)  v-model 双向绑定
    (e: 'resolved', conflictId: string, resolution: string)  调解成功
    (e: 'view-detail', conflict: any)  父组件可监听打开详情
    (e: 'close')

  Expose:
    refresh(): Promise<void>  父组件主动刷新列表
    open(): void              主动打开 drawer
-->
<template>
  <el-drawer
    v-model="visible"
    title="跨模块冲突调解"
    direction="rtl"
    size="60%"
    append-to-body
    :before-close="handleClose"
    class="gt-conflict-panel"
  >
    <div v-loading="loading" class="gt-conflict-panel__body">
      <!-- 空态 -->
      <div v-if="!loading && conflicts.length === 0" class="gt-conflict-panel__empty">
        <el-empty description="暂无未调解的冲突" />
      </div>

      <!-- 列表 + 详情 -->
      <div v-else class="gt-conflict-panel__layout">
        <!-- 左侧列表 -->
        <div class="gt-conflict-panel__list">
          <h4 class="gt-conflict-panel__list-title">
            待调解（<strong>{{ conflicts.length }}</strong>）
          </h4>
          <div
            v-for="c in conflicts"
            :key="c.id"
            :class="[
              'gt-conflict-panel__item',
              { active: selected?.id === c.id },
            ]"
            @click="onSelect(c)"
          >
            <div class="gt-conflict-panel__item-title">
              {{ moduleZh(c.target_module) }} · {{ c.target_field }}
            </div>
            <div class="gt-conflict-panel__item-meta">
              来源：{{ moduleZh(c.source_module) }}
            </div>
            <div class="gt-conflict-panel__item-time">
              {{ formatTime(c.created_at) }}
            </div>
          </div>
        </div>

        <!-- 右侧详情 -->
        <div class="gt-conflict-panel__detail" v-if="selected">
          <h4>差异对比</h4>
          <div class="gt-conflict-panel__diff">
            <div class="gt-conflict-panel__diff-side upstream">
              <div class="gt-conflict-panel__diff-label">上游新值</div>
              <div class="gt-conflict-panel__diff-value">
                {{ selected.upstream_value ?? '（空值）' }}
              </div>
            </div>
            <div class="gt-conflict-panel__diff-arrow">⇄</div>
            <div class="gt-conflict-panel__diff-side manual">
              <div class="gt-conflict-panel__diff-label">手动值</div>
              <div class="gt-conflict-panel__diff-value">
                {{ selected.manual_value ?? '（空值）' }}
              </div>
            </div>
          </div>

          <div class="gt-conflict-panel__actions">
            <el-button
              type="primary"
              :loading="resolving"
              @click="onResolve('keep_manual')"
            >
              保留手动
            </el-button>
            <el-button
              type="warning"
              :loading="resolving"
              @click="onResolve('accept_new')"
            >
              接受新值
            </el-button>
            <el-button
              :loading="resolving"
              @click="onMergeClick"
            >
              合并
            </el-button>
          </div>

          <!-- merge 输入 -->
          <div v-if="showMergeInput" class="gt-conflict-panel__merge">
            <el-input
              v-model="mergeValue"
              type="textarea"
              :rows="3"
              placeholder="请输入合并后的值"
            />
            <div class="gt-conflict-panel__merge-actions">
              <el-button
                type="primary"
                size="small"
                :loading="resolving"
                @click="onResolve('merge')"
              >
                确认合并
              </el-button>
              <el-button size="small" @click="showMergeInput = false">取消</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface ConflictItem {
  id: string
  source_module: string
  source_id: string
  target_module: string
  target_id: string
  target_field: string
  upstream_value: string | null
  manual_value: string | null
  status: string
  created_at: string | null
}

const props = withDefaults(
  defineProps<{
    projectId: string | null | undefined
    modelValue?: boolean
  }>(),
  {
    modelValue: false,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'resolved', conflictId: string, resolution: string): void
  (e: 'view-detail', conflict: ConflictItem): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const loading = ref(false)
const resolving = ref(false)
const conflicts = ref<ConflictItem[]>([])
const selected = ref<ConflictItem | null>(null)
const showMergeInput = ref(false)
const mergeValue = ref('')

const MODULE_LABELS: Record<string, string> = {
  workpaper: '底稿',
  adjustment: '调整分录',
  misstatement: '错报',
  disclosure: '附注披露',
  report: '报表',
  trial_balance: '试算表',
  system_recompute: '系统重算',
}

function moduleZh(mod: string): string {
  return MODULE_LABELS[mod] || mod
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function load() {
  if (!props.projectId) {
    conflicts.value = []
    selected.value = null
    return
  }
  loading.value = true
  try {
    const data: any = await api.get(
      `/api/projects/${props.projectId}/conflicts/pending`,
    )
    const items: ConflictItem[] = Array.isArray(data?.items) ? data.items : []
    conflicts.value = items
    if (selected.value) {
      const stillThere = items.find((c) => c.id === selected.value!.id)
      selected.value = stillThere || items[0] || null
    } else {
      selected.value = items[0] || null
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载冲突列表失败')
    conflicts.value = []
    selected.value = null
  } finally {
    loading.value = false
  }
}

function onSelect(c: ConflictItem) {
  selected.value = c
  showMergeInput.value = false
  mergeValue.value = ''
  emit('view-detail', c)
}

function onMergeClick() {
  showMergeInput.value = true
  mergeValue.value = ''
}

async function onResolve(resolution: 'keep_manual' | 'accept_new' | 'merge') {
  if (!selected.value) return
  if (resolution === 'merge' && !mergeValue.value.trim()) {
    ElMessage.warning('请输入合并后的值')
    return
  }
  const cid = selected.value.id
  resolving.value = true
  try {
    const payload: Record<string, any> = { resolution }
    if (resolution === 'merge') payload.merge_value = mergeValue.value
    await api.post(`/api/conflicts/${cid}/resolve`, payload)
    ElMessage.success('调解成功')
    emit('resolved', cid, resolution)
    // 从列表移除已调解项
    conflicts.value = conflicts.value.filter((c) => c.id !== cid)
    selected.value = conflicts.value[0] || null
    showMergeInput.value = false
    mergeValue.value = ''
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '调解失败'
    ElMessage.error(detail)
  } finally {
    resolving.value = false
  }
}

function handleClose(done: () => void) {
  emit('close')
  done()
}

onMounted(() => {
  if (props.modelValue) load()
})

watch(
  () => props.modelValue,
  (v) => {
    if (v) load()
  },
)

watch(
  () => props.projectId,
  () => {
    if (props.modelValue) load()
  },
)

defineExpose({
  refresh: load,
  open: () => emit('update:modelValue', true),
})
</script>

<style scoped>
.gt-conflict-panel__body {
  min-height: 300px;
}

.gt-conflict-panel__empty {
  padding: 40px 0;
}

.gt-conflict-panel__layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  height: 100%;
}

.gt-conflict-panel__list {
  border-right: 1px solid var(--el-border-color-lighter, #ebeef5);
  padding-right: 12px;
  max-height: calc(100vh - 160px);
  overflow-y: auto;
}

.gt-conflict-panel__list-title {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--gt-color-text-primary, #303133);
}

.gt-conflict-panel__list-title strong {
  color: var(--gt-color-primary, #6b3fa0);
}

.gt-conflict-panel__item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 4px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.gt-conflict-panel__item:hover {
  background: rgba(107, 63, 160, 0.04);
}

.gt-conflict-panel__item.active {
  background: rgba(107, 63, 160, 0.08);
  border-left: 3px solid var(--gt-color-primary, #6b3fa0);
}

.gt-conflict-panel__item-title {
  font-weight: 500;
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  margin-bottom: 4px;
}

.gt-conflict-panel__item-meta {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-conflict-panel__item-time {
  font-size: 11px;
  color: var(--gt-color-text-placeholder, #a8abb2);
  margin-top: 4px;
}

.gt-conflict-panel__detail {
  padding: 0 8px;
}

.gt-conflict-panel__detail h4 {
  margin: 0 0 12px;
  font-size: 14px;
}

.gt-conflict-panel__diff {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.gt-conflict-panel__diff-side {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 4px;
  padding: 12px;
}

.gt-conflict-panel__diff-side.upstream {
  background: rgba(230, 162, 60, 0.04);
  border-color: rgba(230, 162, 60, 0.5);
}

.gt-conflict-panel__diff-side.manual {
  background: rgba(107, 63, 160, 0.04);
  border-color: rgba(107, 63, 160, 0.5);
}

.gt-conflict-panel__diff-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  margin-bottom: 6px;
}

.gt-conflict-panel__diff-value {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  word-break: break-all;
  white-space: pre-wrap;
}

.gt-conflict-panel__diff-arrow {
  font-size: 18px;
  color: var(--gt-color-text-placeholder, #a8abb2);
}

.gt-conflict-panel__actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-conflict-panel__merge {
  border: 1px dashed var(--el-border-color, #dcdfe6);
  border-radius: 4px;
  padding: 12px;
  background: var(--el-fill-color-extra-light, #fafafa);
}

.gt-conflict-panel__merge-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
