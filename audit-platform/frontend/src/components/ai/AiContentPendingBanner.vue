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
  <el-alert
    v-if="loadError"
    class="gt-ai-pending-error"
    type="error"
    :closable="false"
    show-icon
    title="AI 待确认状态暂不可用，当前不能判定为零条"
  >
    <span>AI 待确认状态暂不可用，当前不能判定为零条</span>
    <el-button size="small" text @click="load">重试</el-button>
  </el-alert>
  <div v-if="!loadError && pendingCount > 0" class="gt-ai-pending-banner">
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
          <span v-if="item.target_label" class="gt-aip-card__where">{{ item.target_label }}</span>
          <code v-else-if="item.target_cell" class="gt-aip-card__cell">{{ item.target_cell }}</code>
          <span v-if="item.target_position" class="gt-aip-card__dim">目标 {{ item.target_position }}</span>
          <span class="gt-aip-card__spacer"></span>
          <span v-if="item.model" class="gt-aip-card__dim">模型 {{ item.model }}</span>
          <span v-if="item.confidence != null" class="gt-aip-card__dim">置信度 {{ pct(item.confidence) }}</span>
        </div>

        <div class="gt-aip-card__time" v-if="item.generated_at">生成于 {{ fmtTime(item.generated_at) }}</div>

        <el-alert
          v-if="item.is_stale || item.writeback_status === 'stale'"
          type="warning"
          :closable="false"
          show-icon
          :title="item.stale_reason || '目标内容已经变化，请重新生成后再确认'"
          class="gt-aip-card__stale"
        />

        <div v-if="item.proposed_content != null" class="gt-aip-card__diff">
          <div class="gt-aip-card__diff-col">
            <span class="gt-aip-card__diff-title">当前版本</span>
            <div class="gt-aip-card__content">{{ item.before_content || '（空）' }}</div>
          </div>
          <div class="gt-aip-card__diff-col gt-aip-card__diff-col--proposed">
            <span class="gt-aip-card__diff-title">应用后预览</span>
            <div class="gt-aip-card__content">{{ item.proposed_content || '（空）' }}</div>
          </div>
        </div>
        <div v-else class="gt-aip-card__content">{{ item.content || '（无内容）' }}</div>

        <div v-if="item.writeback_status === 'applied'" class="gt-aip-card__actions">
          <el-button size="small" type="warning" plain :loading="actingId === item.id" @click="undo(item)">
            撤销本次写入
          </el-button>
        </div>
        <div v-else-if="revisingId === item.id" class="gt-aip-card__revise">
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
          <el-button
            size="small"
            type="success"
            plain
            :disabled="item.is_stale || item.writeback_status === 'stale'"
            :loading="actingId === item.id"
            @click="act(item, 'confirm')"
          >
            ✅ 确认
          </el-button>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="item.is_stale || item.writeback_status === 'stale'"
            @click="startRevise(item)"
          >✏️ 修订</el-button>
          <el-button size="small" type="danger" plain :loading="actingId === item.id" @click="act(item, 'reject')">
            ❌ 拒绝
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { copyText } from '@/utils/clipboard'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { eventBus } from '@/utils/eventBus'

interface PendingAiItem {
  id: string
  instance_type?: string | null
  target_cell?: string | null
  target_label?: string | null
  target_position?: string | null
  model?: string | null
  confidence?: number | null
  generated_at?: string | null
  content?: string | null
  before_content?: string | null
  proposed_content?: string | null
  writeback_status?: 'pending' | 'applied' | 'rejected' | 'stale' | 'manual_copy' | 'undone'
  artifact_version?: number
  is_stale?: boolean
  stale_reason?: string | null
  can_undo?: boolean
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
const loadError = ref(false)
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
    loadError.value = false
    return
  }
  listLoading.value = true
  loadError.value = false
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
    // 治理状态读失败不能伪装成“0 条”；保留未知态并给用户重试入口。
    items.value = []
    pendingCount.value = 0
    loadError.value = true
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

/** 按后端 writeback 结果给提示并决定是否移出待确认（锁定/无权 → 保持 pending）。 */
function _handleConfirmResult(resp: any, fallbackMsg: string): boolean {
  const wb = resp?.writeback
  // 后端在「附注锁定 / 无编辑权限」时回传 writeback.skipped=true（见 ai_content._confirm_or_revise），
  // 该标志即待确认信号的唯一权威来源，无需再比较 confirm_action 字面量。
  if (wb && wb.skipped) {
    // 内容保持待确认，告诉用户原因，不移出列表
    ElMessage.warning(wb.reason || '内容保持待确认')
    return false
  }
  if (wb && wb.written) {
    ElMessage.success(`已确认并写入「${wb.note_section || '附注'}」`)
  } else if (wb && wb.written === false) {
    // 底稿类：确认成功但不自动写，提示复制
    ElMessage.success(wb.reason || fallbackMsg)
  } else {
    ElMessage.success(fallbackMsg)
  }
  return true
}

async function act(item: PendingAiItem, action: 'confirm' | 'reject') {
  actingId.value = item.id
  try {
    const resp: any = await api.post(`/api/ai-content/${item.id}/${action}`)
    if (action === 'reject') {
      ElMessage.success('AI 内容已拒绝')
      afterResolved(item.id)
    } else if (_handleConfirmResult(resp, 'AI 内容已确认')) {
      if (resp?.artifact?.can_undo) {
        afterApplied(item.id, resp.artifact)
      } else {
        afterResolved(item.id)
      }
    }
    // 确认未生效（保持 pending）时不移出列表、不发 resolved
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
    const resp: any = await api.post(`/api/ai-content/${item.id}/revise`, { revised_content: text })
    if (_handleConfirmResult(resp, 'AI 内容已修订')) {
      cancelRevise()
      if (resp?.artifact?.can_undo) {
        afterApplied(item.id, resp.artifact)
      } else {
        afterResolved(item.id)
      }
    }
  } catch (e) {
    handleApiError(e, '修订 AI 内容')
  } finally {
    actingId.value = ''
  }
}

async function undo(item: PendingAiItem) {
  actingId.value = item.id
  try {
    await api.post(`/api/ai-content/${item.id}/undo`)
    ElMessage.success('已撤销本次 AI 写入')
    items.value = items.value.filter(i => i.id !== item.id)
    emit('resolved')
  } catch (e) {
    handleApiError(e, '撤销 AI 写入')
  } finally {
    actingId.value = ''
  }
}

function afterApplied(id: string, artifact: PendingAiItem) {
  const index = items.value.findIndex(item => item.id === id)
  if (index >= 0) items.value[index] = { ...items.value[index], ...artifact }
  pendingCount.value = Math.max(0, pendingCount.value - 1)
  emit('resolved')
}

async function copyContent(item: { content?: string }) {
  try {
    await copyText(item.content || '')
    ElMessage.success('已复制 AI 内容到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function afterResolved(id: string) {
  items.value = items.value.filter(i => i.id !== id)
  pendingCount.value = Math.max(0, pendingCount.value - 1)
  emit('resolved')
  if (pendingCount.value === 0 && items.value.length === 0) drawerVisible.value = false
}

function onContentAdopted(payload: { projectId?: string }) {
  if (!payload?.projectId || payload.projectId === props.projectId) void load()
}

onMounted(() => {
  void load()
  eventBus.on('ai-content:adopted', onContentAdopted)
})
onUnmounted(() => eventBus.off('ai-content:adopted', onContentAdopted))

watch(() => props.projectId, load)

defineExpose({ refresh: load })
</script>

<style scoped>
.gt-ai-pending-error { margin-bottom: 8px; }
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

.gt-aip-card__stale {
  margin: 8px 0;
}

.gt-aip-card__diff {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
}

.gt-aip-card__diff-col {
  min-width: 0;
}

.gt-aip-card__diff-col--proposed .gt-aip-card__content {
  background: rgba(103, 194, 58, 0.08);
  border-color: rgba(103, 194, 58, 0.45);
}

.gt-aip-card__diff-title {
  display: block;
  margin-bottom: 4px;
  color: var(--gt-color-text-secondary, #606266);
  font-size: 12px;
  font-weight: 600;
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

@media (max-width: 700px) {
  .gt-aip-card__diff {
    grid-template-columns: 1fr;
  }
}
</style>
