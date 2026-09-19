<script setup lang="ts">
/**
 * GtKamWorkpaper — A17-2-1 关键审计事项 (KAM)
 *
 * 结构化表单组件，管理 KAM 条目的 CRUD。
 * 5 区域：识别过程 / KAM 列表 / 3 要素描述 / 措辞审核 / 治理层确认。
 * 数据存储：checklist_responses 表，item_id = A17-2-1-KAM-001 ~ NNN。
 * remark 字段存 JSON 字符串化的 KamRemarkSchema。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  type KamEntry,
  type KamRemarkSchema,
  type KamWordingReviewStatus,
  createDefaultKamRemark,
  validateKamRemark,
} from '@/types/kam'

// ─── Props / Emits ───
const props = defineProps<{ projectId: string; wpId: string; wpCode?: string }>()
const emit = defineEmits<{ (e: 'save'): void }>()

// ─── State ───
const kamList = ref<KamEntry[]>([])
const activeIndex = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const pushing = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── AI Assist State ───
const aiEnabled = ref(false)
const aiLoading = ref(false)
const aiDialogVisible = ref(false)
const aiDraft = ref('')
const aiError = ref('')

// ─── Computed ───
const activeKam = computed(() =>
  activeIndex.value !== null ? kamList.value[activeIndex.value] : null,
)
const kamCount = computed(() => kamList.value.length)

// ─── Data Loading ───
async function loadKamEntries() {
  if (!props.projectId || !props.wpId) return
  loading.value = true
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, {
      params: { project_id: props.projectId },
    })
    const records = (data as Array<{
      item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null
    }>) || []
    kamList.value = records
      .filter((r) => r.item_id?.startsWith('A17-2-1-KAM'))
      .sort((a, b) => a.item_id.localeCompare(b.item_id))
      .map((r) => {
        let remark: KamRemarkSchema
        try {
          const parsed = JSON.parse(r.remark || '{}')
          remark = validateKamRemark(parsed) ? parsed : createDefaultKamRemark()
        } catch { remark = createDefaultKamRemark() }
        return {
          item_id: r.item_id,
          title: r.conclusion || '',
          wp_ref: r.wp_ref || '',
          remark,
        }
      })
    if (kamList.value.length > 0 && activeIndex.value === null) activeIndex.value = 0
  } catch (err: any) {
    ElMessage.error('加载 KAM 数据失败: ' + (err?.message || ''))
  } finally { loading.value = false }
}

// ─── CRUD ───
function generateNextItemId(): string {
  const existing = kamList.value.map((k) => {
    const match = k.item_id.match(/KAM-(\d+)$/)
    return match ? parseInt(match[1], 10) : 0
  })
  const next = Math.max(0, ...existing) + 1
  return `A17-2-1-KAM-${String(next).padStart(3, '0')}`
}

function addKam() {
  const newEntry: KamEntry = {
    item_id: generateNextItemId(),
    title: '',
    wp_ref: '',
    remark: createDefaultKamRemark(),
  }
  kamList.value.push(newEntry)
  activeIndex.value = kamList.value.length - 1
  debouncedSave()
}

async function deleteKam(index: number) {
  const entry = kamList.value[index]
  if (!entry) return
  try {
    await ElMessageBox.confirm(
      `确定删除 KAM「${entry.title || entry.item_id}」？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  kamList.value.splice(index, 1)
  if (activeIndex.value !== null) {
    if (activeIndex.value >= kamList.value.length)
      activeIndex.value = kamList.value.length > 0 ? kamList.value.length - 1 : null
  }
  await saveAll()
}

// ─── Save ───
async function saveAll() {
  if (!props.projectId || !props.wpId) return
  saving.value = true
  saveStatus.value = 'saving'
  try {
    const items = kamList.value.map((k) => ({
      item_id: k.item_id,
      conclusion: k.title || null,
      remark: JSON.stringify(k.remark),
      wp_ref: k.wp_ref || null,
    }))
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    saveStatus.value = 'saved'
    emit('save')
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch (err: any) {
    saveStatus.value = 'error'
    if (err?.message !== 'canceled' && err?.code !== 'ERR_CANCELED')
      ElMessage.warning('保存失败，请重试')
  } finally { saving.value = false }
}

function debouncedSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; saveAll() }, 1500)
}

function flushPendingSave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    saveAll()
  }
}

// ─── Field Handlers ───
function onTitleChange() { debouncedSave() }
function onWpRefChange() { debouncedSave() }
function onRemarkFieldChange() { debouncedSave() }
function onWordingChange(val: KamWordingReviewStatus) {
  if (activeKam.value) { activeKam.value.remark.wording_review = val; debouncedSave() }
}
function onGovernanceChange(val: boolean) {
  if (activeKam.value) { activeKam.value.remark.governance_confirmed = val; debouncedSave() }
}

// ─── Status Helpers ───
function getWordingLabel(status: KamWordingReviewStatus): string {
  return status === 'done' ? '已完成' : status === 'na' ? '不适用' : '待审核'
}
function getWordingType(status: KamWordingReviewStatus) {
  return status === 'done' ? 'success' : status === 'na' ? 'info' : 'warning'
}

// ─── Push to Report ───
async function pushToReport() {
  if (!props.projectId || !props.wpId) return
  if (kamList.value.length === 0) {
    ElMessage.warning('暂无 KAM 条目可推送')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将把当前所有 KAM 数据推送至审计报告的「关键审计事项段」，已有内容将被覆盖。',
      '推送至审计报告',
      { type: 'warning', confirmButtonText: '确认推送', cancelButtonText: '取消' },
    )
  } catch { return }
  // Flush any pending save first
  flushPendingSave()
  pushing.value = true
  try {
    const result = await api.post('/api/a17/kam/push-to-report', {
      project_id: props.projectId,
      wp_id: props.wpId,
    }) as { success: boolean; pushed_count: number; message: string }
    if (result.success) {
      ElMessage.success(result.message)
    } else {
      ElMessage.warning(result.message)
    }
  } catch (err: any) {
    ElMessage.error('推送失败: ' + (err?.message || '未知错误'))
  } finally { pushing.value = false }
}

// ─── AI Assist ───
async function checkAiEnabled() {
  try {
    const resp = await api.get('/api/feature-flags') as any
    const flags = resp?.flags || resp || {}
    aiEnabled.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch { aiEnabled.value = false }
}

async function handleAiGenerate() {
  if (!activeKam.value) return
  aiDraft.value = ''
  aiError.value = ''
  aiDialogVisible.value = true
  aiLoading.value = true
  try {
    const result = await api.post(`/api/a17/kam/${activeKam.value.item_id}/ai-generate`, {
      project_id: props.projectId,
      kam_title: activeKam.value.title || '',
      user_hint: '',
      wp_refs: activeKam.value.wp_ref || '',
    }) as { draft?: string; error?: string }
    if (result?.error) { aiError.value = result.error }
    else if (result?.draft) { aiDraft.value = result.draft }
    else { aiError.value = '未获取到生成内容' }
  } catch (err: any) { aiError.value = err?.message || 'AI 服务请求失败' }
  finally { aiLoading.value = false }
}

function adoptAiDraft() {
  if (!aiDraft.value || !activeKam.value) return
  // Parse the draft and fill into the 3 elements
  activeKam.value.remark.situation = aiDraft.value
  aiDialogVisible.value = false
  ElMessage.success('已采纳 AI 建议稿（请按需编辑三要素各段）')
  debouncedSave()
}

// ─── Lifecycle ───
onMounted(() => { loadKamEntries(); checkAiEnabled() })
onBeforeUnmount(() => { flushPendingSave() })
watch(() => [props.projectId, props.wpId], () => {
  if (props.projectId && props.wpId) loadKamEntries()
})
</script>

<template>
  <div class="gt-kam-workpaper" v-loading="loading">
    <!-- Header -->
    <div class="gt-kam-workpaper__header">
      <div class="gt-kam-workpaper__header-left">
        <span class="gt-kam-workpaper__title">关键审计事项 (KAM)</span>
        <el-tag type="primary" effect="dark" size="small" round>{{ kamCount }}</el-tag>
      </div>
      <div class="gt-kam-workpaper__header-right">
        <span class="gt-kam-workpaper__save-status">
          <span v-if="saveStatus === 'saving'" class="save-status--saving">保存中...</span>
          <span v-else-if="saveStatus === 'saved'" class="save-status--saved">✓ 已保存</span>
          <span v-else-if="saveStatus === 'error'" class="save-status--error">保存失败</span>
        </span>
        <el-button size="small" :loading="pushing" :disabled="kamList.length === 0"
          @click="pushToReport">推送至审计报告</el-button>
        <el-button type="primary" size="small" @click="addKam">+ 新增 KAM</el-button>
      </div>
    </div>

    <!-- KAM Card List -->
    <div class="gt-kam-workpaper__body">
      <div v-if="kamList.length === 0" class="gt-kam-workpaper__empty">
        暂无关键审计事项，点击「新增 KAM」开始
      </div>
      <div v-for="(kam, idx) in kamList" :key="kam.item_id"
        class="gt-kam-card" :class="{ 'is-active': activeIndex === idx }"
        @click="activeIndex = idx">
        <!-- Card header (always visible) -->
        <div class="gt-kam-card__header">
          <div class="gt-kam-card__meta">
            <span class="gt-kam-card__seq">{{ idx + 1 }}</span>
            <span class="gt-kam-card__title-text">{{ kam.title || '未命名 KAM' }}</span>
          </div>
          <div class="gt-kam-card__badges">
            <el-tag :type="getWordingType(kam.remark.wording_review)" size="small" effect="plain">
              {{ getWordingLabel(kam.remark.wording_review) }}
            </el-tag>
            <el-tag v-if="kam.remark.governance_confirmed" type="success" size="small" effect="plain">
              治理层已确认
            </el-tag>
            <el-button type="danger" size="small" text @click.stop="deleteKam(idx)">删除</el-button>
          </div>
        </div>

        <!-- Detail panel (expanded when active) -->
        <div v-if="activeIndex === idx" class="gt-kam-card__detail" @click.stop>
          <!-- 基本信息 -->
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">KAM 标题/风险领域</div>
            <el-input v-model="kam.title" placeholder="如：收入确认" size="small"
              @input="onTitleChange" />
          </div>
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">引用底稿索引</div>
            <el-input v-model="kam.wp_ref" placeholder="如：D4,B50" size="small"
              @input="onWpRefChange" />
          </div>

          <!-- 3 要素描述 -->
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">情况描述</div>
            <el-input v-model="kam.remark.situation" type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }" placeholder="描述该关键审计事项的情况..."
              @input="onRemarkFieldChange" />
          </div>
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">确定为 KAM 的原因</div>
            <el-input v-model="kam.remark.reason" type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明确定为关键审计事项的原因..."
              @input="onRemarkFieldChange" />
          </div>
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">审计应对</div>
            <el-input v-model="kam.remark.response" type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }" placeholder="描述审计应对措施..."
              @input="onRemarkFieldChange" />
          </div>
          <div class="gt-kam-card__section">
            <div class="gt-kam-card__section-title">引用底稿说明</div>
            <el-input v-model="kam.remark.refs" type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }" placeholder="如：详见 D4-1 收入测试底稿"
              @input="onRemarkFieldChange" />
          </div>

          <!-- AI 生成描述 -->
          <div v-if="aiEnabled" class="gt-kam-card__section">
            <el-button size="small" type="success" :loading="aiLoading"
              @click="handleAiGenerate">AI 生成描述</el-button>
          </div>

          <!-- 措辞审核 -->
          <div class="gt-kam-card__section gt-kam-card__section--inline">
            <div class="gt-kam-card__section-title">措辞审核</div>
            <el-radio-group :model-value="kam.remark.wording_review"
              @update:model-value="onWordingChange($event as KamWordingReviewStatus)" size="small">
              <el-radio-button value="pending">待审核</el-radio-button>
              <el-radio-button value="done">已完成</el-radio-button>
              <el-radio-button value="na">不适用</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 治理层确认 -->
          <div class="gt-kam-card__section gt-kam-card__section--inline">
            <div class="gt-kam-card__section-title">治理层确认</div>
            <el-switch :model-value="kam.remark.governance_confirmed"
              @update:model-value="onGovernanceChange($event as boolean)"
              active-text="已确认" inactive-text="未确认" />
          </div>
        </div>
      </div>
    </div>
    <!-- AI 预览弹窗 -->
    <el-dialog v-model="aiDialogVisible" title="AI 生成描述预览" width="600px" :close-on-click-modal="false">
      <div v-if="aiLoading" style="display:flex;align-items:center;gap:8px;padding:16px;color:var(--gt-color-text-secondary)">
        <span>正在生成建议稿...</span>
      </div>
      <div v-else-if="aiError" style="padding:12px;color:var(--gt-color-danger);font-size:13px">{{ aiError }}</div>
      <el-input v-else v-model="aiDraft" type="textarea" readonly :autosize="{ minRows: 6, maxRows: 16 }" />
      <template #footer>
        <el-button @click="aiDialogVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!aiDraft || aiLoading" @click="adoptAiDraft">采纳</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-kam-workpaper { display: flex; flex-direction: column; height: 100%; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md); overflow: hidden; }

/* ─── Header ─── */
.gt-kam-workpaper__header { display: flex; align-items: center; justify-content: space-between; padding: var(--gt-space-4) var(--gt-space-5); border-bottom: 1px solid var(--gt-color-border-light); }
.gt-kam-workpaper__header-left { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-kam-workpaper__header-right { display: flex; align-items: center; gap: var(--gt-space-3); }
.gt-kam-workpaper__title { font-size: var(--gt-font-size-lg); font-weight: 600; color: var(--gt-color-text); }
.gt-kam-workpaper__save-status { font-size: var(--gt-font-size-xs); }
.save-status--saving { color: var(--gt-color-text-tertiary); }
.save-status--saved { color: var(--gt-color-success); }
.save-status--error { color: var(--gt-color-danger); }

/* ─── Body ─── */
.gt-kam-workpaper__body { flex: 1; overflow-y: auto; padding: var(--gt-space-4) var(--gt-space-5); display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-kam-workpaper__empty { display: flex; align-items: center; justify-content: center; height: 160px; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm); }

/* ─── KAM Card ─── */
.gt-kam-card { border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md); transition: border-color var(--gt-transition-fast), box-shadow var(--gt-transition-fast); cursor: pointer; }
.gt-kam-card:hover { border-color: var(--gt-color-primary-light); }
.gt-kam-card.is-active { border-color: var(--gt-color-primary); box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.08); cursor: default; }

.gt-kam-card__header { display: flex; align-items: center; justify-content: space-between; padding: var(--gt-space-3) var(--gt-space-4); }
.gt-kam-card__meta { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-kam-card__seq { width: 22px; height: 22px; border-radius: 50%; background: var(--gt-color-primary); color: #fff; font-size: var(--gt-font-size-xs); font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.gt-kam-card__title-text { font-size: var(--gt-font-size-base); font-weight: 500; color: var(--gt-color-text); }
.gt-kam-card__badges { display: flex; align-items: center; gap: var(--gt-space-2); }

/* ─── Detail Panel ─── */
.gt-kam-card__detail { padding: 0 var(--gt-space-4) var(--gt-space-4); border-top: 1px solid var(--gt-color-border-light); }
.gt-kam-card__section { margin-top: var(--gt-space-3); }
.gt-kam-card__section--inline { display: flex; align-items: center; gap: var(--gt-space-3); }
.gt-kam-card__section-title { font-size: var(--gt-font-size-sm); font-weight: 500; color: var(--gt-color-text-secondary); margin-bottom: var(--gt-space-1); }
.gt-kam-card__section--inline .gt-kam-card__section-title { margin-bottom: 0; min-width: 80px; }

/* ─── GT Purple tokens override for el-tag[type=primary] ─── */
.gt-kam-workpaper :deep(.el-tag--primary) { --el-tag-bg-color: var(--gt-color-primary-bg); --el-tag-border-color: var(--gt-color-primary-light); --el-tag-text-color: var(--gt-color-primary); }
.gt-kam-workpaper :deep(.el-tag--primary.is-dark) { --el-tag-bg-color: var(--gt-color-primary); --el-tag-border-color: var(--gt-color-primary); --el-tag-text-color: #fff; }
</style>
