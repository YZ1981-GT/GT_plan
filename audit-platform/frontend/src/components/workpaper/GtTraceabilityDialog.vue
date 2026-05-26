<!--
  GtTraceabilityDialog.vue — 报表/附注溯源弹窗

  按 design §3.9 实现：
  - 两路调用：反向溯源（upstream）+ 正向影响（downstream）
  - 反向：报表行/附注 section/底稿 cell → 哪些底稿 cell 喂入
  - 正向：底稿 cell → 哪些报表行/附注 section 引用了它
  - 结果以 GtIndexChip 列表展示，点击 chip 跳转

  锚定 spec workpaper-html-renderer Task 12.3
  Validates: Requirements 3.11.6（报表附注溯源链路）
-->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="720px"
    append-to-body
    :close-on-click-modal="false"
    @close="onClose"
  >
    <div class="gt-trace-dialog">
      <!-- 上下文信息 -->
      <header class="gt-trace-dialog__header">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="溯源对象">
            <el-tag :type="sourceTagType" size="small" effect="plain">
              {{ sourceLabel }}
            </el-tag>
            <code class="gt-trace-dialog__identifier">{{ identifier }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="项目 ID">
            <span class="gt-trace-dialog__project">{{ projectId }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </header>

      <!-- 双 tab：反向溯源 / 正向影响 -->
      <el-tabs v-model="activeTab" class="gt-trace-dialog__tabs">
        <el-tab-pane name="upstream">
          <template #label>
            <span>
              <el-icon><Top /></el-icon>
              反向溯源
              <el-tag v-if="upstreamCount" size="small" type="info">{{ upstreamCount }}</el-tag>
            </span>
          </template>

          <div class="gt-trace-dialog__panel">
            <p class="gt-trace-dialog__hint">
              <el-icon><InfoFilled /></el-icon>
              展示喂入此{{ sourceLabel }}的上游底稿单元格（哪些底稿数据汇成此值）
            </p>

            <el-skeleton v-if="upstreamLoading" :rows="3" animated />
            <el-alert
              v-else-if="upstreamError"
              :title="upstreamError"
              type="error"
              :closable="false"
              show-icon
            />
            <el-empty
              v-else-if="!upstreamItems.length"
              description="未找到上游引用"
              :image-size="60"
            />
            <ul v-else class="gt-trace-dialog__list">
              <li
                v-for="(item, idx) in upstreamItems"
                :key="`upstream-${idx}`"
                class="gt-trace-dialog__item"
              >
                <GtIndexChip
                  :value="formatIndexRef(item)"
                  :context-project-id="projectId"
                  @click="onChipClick"
                />
                <span v-if="item.label" class="gt-trace-dialog__item-label">
                  {{ item.label }}
                </span>
                <span v-if="item.value !== undefined && item.value !== null" class="gt-trace-dialog__item-value">
                  = {{ formatValue(item.value) }}
                </span>
              </li>
            </ul>
          </div>
        </el-tab-pane>

        <el-tab-pane name="downstream">
          <template #label>
            <span>
              <el-icon><Bottom /></el-icon>
              正向影响
              <el-tag v-if="downstreamCount" size="small" type="info">{{ downstreamCount }}</el-tag>
            </span>
          </template>

          <div class="gt-trace-dialog__panel">
            <p class="gt-trace-dialog__hint">
              <el-icon><InfoFilled /></el-icon>
              展示引用此{{ sourceLabel }}的下游底稿/报表/附注（修改此值会影响哪些位置）
            </p>

            <el-skeleton v-if="downstreamLoading" :rows="3" animated />
            <el-alert
              v-else-if="downstreamError"
              :title="downstreamError"
              type="error"
              :closable="false"
              show-icon
            />
            <el-empty
              v-else-if="!downstreamItems.length"
              description="未找到下游引用"
              :image-size="60"
            />
            <ul v-else class="gt-trace-dialog__list">
              <li
                v-for="(item, idx) in downstreamItems"
                :key="`downstream-${idx}`"
                class="gt-trace-dialog__item"
              >
                <GtIndexChip
                  :value="formatIndexRef(item)"
                  :context-project-id="projectId"
                  @click="onChipClick"
                />
                <span v-if="item.label" class="gt-trace-dialog__item-label">
                  {{ item.label }}
                </span>
              </li>
            </ul>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="reload">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Top, Bottom, InfoFilled, Refresh } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

// ─── Types ───
export type TraceSource = 'report' | 'disclosure' | 'workpaper'

export interface TraceItem {
  wp_code: string
  sheet?: string | null
  cell?: string | null
  value?: number | string | null
  label?: string | null
  /** 当 source = workpaper 时，下游可能是 report/disclosure */
  target_type?: 'report' | 'disclosure' | 'workpaper' | null
  target_identifier?: string | null
}

export interface TraceResponse {
  source: TraceSource
  identifier: string
  direction: 'upstream' | 'downstream'
  items: TraceItem[]
}

// ─── Props / Emits ───
const props = defineProps<{
  modelValue: boolean
  source: TraceSource
  identifier: string
  projectId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'chip-click': [resolved: ResolvedIndexRef]
}>()

// ─── State ───
const activeTab = ref<'upstream' | 'downstream'>('upstream')

const upstreamItems = ref<TraceItem[]>([])
const upstreamLoading = ref(false)
const upstreamError = ref('')

const downstreamItems = ref<TraceItem[]>([])
const downstreamLoading = ref(false)
const downstreamError = ref('')

// ─── Computed ───
const visible = computed<boolean>({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const sourceLabel = computed(() => {
  switch (props.source) {
    case 'report': return '报表行'
    case 'disclosure': return '附注章节'
    case 'workpaper': return '底稿单元格'
    default: return '对象'
  }
})

const sourceTagType = computed<'success' | 'warning' | 'info'>(() => {
  switch (props.source) {
    case 'report': return 'success'
    case 'disclosure': return 'warning'
    case 'workpaper': return 'info'
    default: return 'info'
  }
})

const dialogTitle = computed(() => `溯源链路：${sourceLabel.value} ${props.identifier}`)

const upstreamCount = computed(() => upstreamItems.value.length)
const downstreamCount = computed(() => downstreamItems.value.length)

// ─── Methods ───
function formatIndexRef(item: TraceItem): string {
  // 下游是 report/disclosure：渲染为 Note: 或 Report: 命名空间
  if (item.target_type === 'report' && item.target_identifier) {
    return item.target_identifier  // 报表行 row_code 显示为 plain text（无独立命名空间）
  }
  if (item.target_type === 'disclosure' && item.target_identifier) {
    return `Note:${item.target_identifier}`
  }
  // 其它情况：渲染为底稿/cell 引用
  if (item.cell && item.sheet) {
    return `cell:${item.sheet}!${item.cell}`
  }
  if (item.sheet) {
    return `sheet:${item.sheet}`
  }
  return `wp:${item.wp_code}`
}

function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  return String(value)
}

async function loadUpstream() {
  upstreamLoading.value = true
  upstreamError.value = ''
  try {
    const res = await api.get<TraceResponse>('/api/workpapers/trace', {
      params: {
        source: props.source,
        identifier: props.identifier,
        direction: 'upstream',
        project_id: props.projectId,
      },
    })
    upstreamItems.value = Array.isArray(res?.items) ? res.items : []
  } catch (e: any) {
    upstreamError.value = e?.message ?? '加载上游溯源失败'
    upstreamItems.value = []
  } finally {
    upstreamLoading.value = false
  }
}

async function loadDownstream() {
  downstreamLoading.value = true
  downstreamError.value = ''
  try {
    const res = await api.get<TraceResponse>('/api/workpapers/trace', {
      params: {
        source: props.source,
        identifier: props.identifier,
        direction: 'downstream',
        project_id: props.projectId,
      },
    })
    downstreamItems.value = Array.isArray(res?.items) ? res.items : []
  } catch (e: any) {
    downstreamError.value = e?.message ?? '加载下游溯源失败'
    downstreamItems.value = []
  } finally {
    downstreamLoading.value = false
  }
}

function reload() {
  loadUpstream()
  loadDownstream()
}

function onClose() {
  visible.value = false
}

function onChipClick(resolved: ResolvedIndexRef) {
  emit('chip-click', resolved)
}

// ─── Lifecycle ───
// 弹窗打开 + 必要参数齐备时触发双路加载
watch(
  () => [props.modelValue, props.source, props.identifier, props.projectId],
  ([open, src, id, pid]) => {
    if (open && src && id && pid) {
      activeTab.value = 'upstream'
      loadUpstream()
      loadDownstream()
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.gt-trace-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-trace-dialog__header {
  width: 100%;
}

.gt-trace-dialog__identifier {
  margin-left: 8px;
  padding: 2px 8px;
  background: var(--gt-color-bg-page, #f5f5f5);
  border-radius: 4px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}

.gt-trace-dialog__project {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-trace-dialog__tabs {
  width: 100%;
}

.gt-trace-dialog__panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 240px;
  padding: 8px 0 0;
}

.gt-trace-dialog__hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 8px 12px;
  background: var(--gt-color-bg-page, #f7f6f9);
  border-left: 3px solid var(--gt-color-primary, #6750a4);
  border-radius: 3px;
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
}

.gt-trace-dialog__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-trace-dialog__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 4px;
  transition: border-color 0.15s;
}

.gt-trace-dialog__item:hover {
  border-color: var(--gt-color-primary, #6750a4);
}

.gt-trace-dialog__item-label {
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
}

.gt-trace-dialog__item-value {
  margin-left: auto;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  color: var(--gt-color-primary, #6750a4);
}
</style>
