<!--
  AiContentPendingBanner — AI 内容待确认计数顶部 banner + 明细抽屉
  ================================================================================
  在 5 视图（WorkpaperEditor / Adjustments / Misstatements / DisclosureEditor / ReviewWorkbench）
  顶部展示 AI 待确认数量提示，点「查看明细」展开右侧抽屉逐条确认 / 修订 / 拒绝。

  端点：
    GET  /api/projects/{pid}/ai-content/pending   列表 + 计数
    POST /api/ai-content/{id}/confirm             确认
    POST /api/ai-content/{id}/revise              修订（body: revised_content）
    POST /api/ai-content/{id}/reject              拒绝

  用法：
    <AiContentPendingBanner :project-id="projectId" />

  Props:
    projectId: string  必需，传入当前项目 ID

  Emits:
    (e: 'view'): void       点「查看明细」时触发（抽屉已由组件内部打开，父视图可另做联动）
    (e: 'resolved'): void   任一条 AI 内容被确认/修订/拒绝后触发，父视图可重拉数据

  Expose:
    refresh(): Promise<void>  父组件可调用主动刷新计数（如保存底稿后）
-->
<template>
  <div v-if="pendingCount > 0" class="gt-ai-pending-banner">
    <span class="gt-ai-pending-banner__icon">🤖</span>
    <span class="gt-ai-pending-banner__text">
      该项目尚有 <strong>{{ pendingCount }}</strong> 段 AI 生成内容待确认
    </span>
    <el-button
      class="gt-ai-pending-banner__btn"
      size="small"
      text
      @click="onView"
    >
      查看明细 →
    </el-button>
  </div>

  <el-drawer
    v-model="drawerVisible"
    title="AI 生成内容待确认"
    size="600px"
    :close-on-click-modal="true"
  >
    <template #header>
      <div class="gt-aip-header">
        <span class="gt-aip-header__title">🤖 AI 生成内容待确认</span>
        <el-tag type="warning" size="small" effect="light">{{ pendingCount }} 段</el-tag>
      </div>
    </template>

    <div v-loading="listLoading" class="gt-aip-body">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="gt-aip-tip"
      >
        AI 仅负责起草。确认后内容视为已经人工复核，修订会以你填写的文本替换原文，拒绝则该段不予采用。
      </el-alert>

      <el-empty v-if="!listLoading && items.length === 0" description="暂无待确认的 AI 内容" />

      <div v-for="item in items" :key="item.id" class="gt-aip-card">
        <div class="gt-aip-card__meta">
          <el-tag size="small" type="warning" effect="plain">AI 生成</el-tag>
          <span v-if="item.instance_type" class="gt-aip-card__where">{{ instanceLabel(item.instance_type) }}</span>
          <code v-if="item.target_cell" class="gt-aip-card__cell">{{ item.target_cell }}</code>
          <span class="gt-aip-card__spacer"></span>
          <span v-if="item.model" class="gt-aip-card__dim">模型 {{ item.model }}</span>
          <span v-if="item.confidence != null" class="gt-aip-card__dim">置信度 {{ pct(item.confidence) }}</span>
        </div>

        <div class="gt-aip-card__time" v-if="item.generated_at">生成于 {{ fmtTime(item.generated_at) }}</div>

        <div class="gt-aip-card__content">{{ item.content || '（无内容）' }}</div>

        <div v-if="revisingId === item.id" class="gt-aip-card__revise">
          <el-input
            v-model="reviseText"
            type="textarea"
            :autosize="{ minRows: 4 }"
            placeholder="请输入修订后的内容"
          />
          <div class="gt-aip-card__revise-actions">
            <el-button size="small" type="primary" :loading="actingId === item.id" @click="submitRevise(item)">
              提交修订
            </el-button>
            <el-button size="small" @click="cancelRevise">取消</el-button>
          </div>
        </div>

        <div v-else class="gt-aip-card__actions">
          <el-button size="small" type="success" plain :loading="actingId === item.id" @click="act(item, 'confirm')">
            ✅ 确认
          </el-button>
          <el-button size="small" type="warning" plain @click="startRevise(item)">✏️ 修订</el-button>
          <el-button size="small" type="danger" plain :loading="actingId === item.id" @click="act(item, 'reject')">
            ❌ 拒绝
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface PendingAiItem {
  id: string
  instance_type?: string | null
  target_cell?: string | null
  model?: string | null
  confidence?: number | null
  generated_at?: string | null
  content?: string | null
}

const props = defineProps<{
  projectId: string | null | undefined
}>()

const emit = defineEmits<{
  (e: 'view'): void
  (e: 'resolved'): void
}>()

const pendingCount = ref(0)
const items = ref<PendingAiItem[]>([])
const drawerVisible = ref(false)
const listLoading = ref(false)
const actingId = ref('')
const revisingId = ref('')
const reviseText = ref('')

/** target_cell 前缀（instance_type）→ 中文来源标签 */
const INSTANCE_LABELS: Record<string, string> = {
  workpaper: '底稿',
  wp: '底稿',
  note: '附注',
  disclosure: '附注',
  report: '报表',
  adjustment: '调整分录',
  misstatement: '错报',
  confirmation: '函证',
  review: '复核意见',
}

function instanceLabel(t: string): string {
  return INSTANCE_LABELS[t.toLowerCase()] || t
}

function pct(c: number): string {
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- 置信度百分比，非金额
  return `${(c * 100).toFixed(0)}%`
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

async function load() {
  if (!props.projectId) {
    pendingCount.value = 0
    items.value = []
    return
  }
  listLoading.value = true
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/ai-content/pending`, { _silent: true } as any)
    // 兼容多种返回形态：{items: [...], count: N} 或 [...] 或 { pending: N }
    if (Array.isArray(data)) {
      items.value = data
      pendingCount.value = data.length
    } else if (data && Array.isArray(data.items)) {
      items.value = data.items
      pendingCount.value = typeof data.count === 'number' ? data.count : data.items.length
    } else if (data && typeof data.count === 'number') {
      items.value = []
      pendingCount.value = data.count
    } else if (data && typeof data.pending === 'number') {
      items.value = []
      pendingCount.value = data.pending
    } else {
      items.value = []
      pendingCount.value = 0
    }
  } catch {
    // 端点不可用时静默降级（banner 不显示）
    items.value = []
    pendingCount.value = 0
  } finally {
    listLoading.value = false
  }
}

function onView() {
  drawerVisible.value = true
  // 打开即重拉一次，避免展示 banner 挂载时的旧快照
  void load()
  emit('view')
}

function startRevise(item: PendingAiItem) {
  revisingId.value = item.id
  reviseText.value = item.content || ''
}

function cancelRevise() {
  revisingId.value = ''
  reviseText.value = ''
}

async function act(item: PendingAiItem, action: 'confirm' | 'reject') {
  actingId.value = item.id
  try {
    await api.post(`/api/ai-content/${item.id}/${action}`)
    ElMessage.success(action === 'confirm' ? 'AI 内容已确认' : 'AI 内容已拒绝')
    afterResolved(item.id)
  } catch (e) {
    handleApiError(e, action === 'confirm' ? '确认 AI 内容' : '拒绝 AI 内容')
  } finally {
    actingId.value = ''
  }
}

async function submitRevise(item: PendingAiItem) {
  const text = reviseText.value.trim()
  if (!text) {
    ElMessage.warning('修订内容不能为空')
    return
  }
  actingId.value = item.id
  try {
    await api.post(`/api/ai-content/${item.id}/revise`, { revised_content: text })
    ElMessage.success('AI 内容已修订')
    cancelRevise()
    afterResolved(item.id)
  } catch (e) {
    handleApiError(e, '修订 AI 内容')
  } finally {
    actingId.value = ''
  }
}

function afterResolved(id: string) {
  items.value = items.value.filter(i => i.id !== id)
  pendingCount.value = Math.max(0, pendingCount.value - 1)
  emit('resolved')
  if (pendingCount.value === 0) drawerVisible.value = false
}

onMounted(load)

watch(() => props.projectId, load)

defineExpose({ refresh: load })
</script>

<style scoped>
.gt-ai-pending-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px 16px;
  margin-bottom: 8px;
  background: linear-gradient(135deg, rgba(107, 63, 160, 0.08), rgba(107, 63, 160, 0.04));
  border: 1px solid var(--gt-color-primary-light, #b794f6);
  border-left: 3px solid var(--gt-color-primary, #6b3fa0);
  border-radius: 4px;
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  box-sizing: border-box;
}

.gt-ai-pending-banner__icon {
  font-size: 16px;
}

.gt-ai-pending-banner__text {
  flex: 1;
}

.gt-ai-pending-banner__text strong {
  color: var(--gt-color-primary, #6b3fa0);
  font-weight: 600;
  margin: 0 2px;
}

.gt-ai-pending-banner__btn {
  --el-button-text-color: var(--gt-color-primary, #6b3fa0);
  font-weight: 500;
}

/* ── 明细抽屉 ── */
.gt-aip-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-aip-header__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-aip-body {
  font-size: 13px;
}

.gt-aip-tip {
  margin-bottom: 12px;
}

.gt-aip-card {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-left: 3px solid var(--gt-color-primary, #6b3fa0);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: var(--gt-color-bg-white, #fff);
}

.gt-aip-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.gt-aip-card__spacer {
  flex: 1;
}

.gt-aip-card__where {
  font-weight: 600;
  color: var(--gt-color-primary, #6b3fa0);
}

.gt-aip-card__cell {
  background: var(--gt-color-bg, #f5f7fa);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}

.gt-aip-card__dim {
  color: var(--gt-color-text-secondary, #909399);
  font-size: 12px;
}

.gt-aip-card__time {
  color: var(--gt-color-text-secondary, #909399);
  font-size: 12px;
  margin-bottom: 6px;
}

.gt-aip-card__content {
  white-space: pre-wrap;
  line-height: 1.7;
  background: rgba(107, 63, 160, 0.04);
  border: 1px dashed var(--gt-color-primary-light, #b794f6);
  border-radius: 4px;
  padding: 8px 10px;
  max-height: 220px;
  overflow-y: auto;
}

.gt-aip-card__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.gt-aip-card__revise {
  margin-top: 8px;
}

.gt-aip-card__revise-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
