<script setup lang="ts">
/**
 * GtReviewChecklist — A21~A25 角色复核检查表
 * 配置驱动：definitions JSON + checklist_responses 持久化
 *
 * RBAC + Sequential Gate + Sign-Lock + Unresolved Count 消费
 * guard 数据从 render-config html_data.guard 注入
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useProjectRole } from '@/composables/useProjectRole'

interface ReviewItem {
  seq: number
  content: string
  item_id: string
  auto_na?: boolean
  auto_na_reason?: string | null
}

interface ReviewTemplate {
  wp_code: string
  role_label: string
  audit_type_label: string
  items: ReviewItem[]
}

interface GuardData {
  readonly?: boolean
  locked?: boolean
  signed_by?: string | null
  signed_at?: string | null
  gate_reason?: string | null
  unresolved_count?: number
  rbac_denied?: boolean
}

interface HtmlData {
  template?: ReviewTemplate | null
  responses?: Record<string, { conclusion: string; remark: string; wp_ref?: string }>
  guard?: GuardData
}

const props = defineProps<{
  projectId: string
  wpId: string
  wpCode?: string
  htmlData?: HtmlData
  readonly?: boolean
  sheetName?: string
  schema?: any
  year?: number
}>()
const emit = defineEmits<{ (e: 'save'): void; (e: 'pass'): void; (e: 'reject'): void }>()

const effectiveWpCode = computed(() => (props.wpCode || '').toUpperCase())
const projectIdRef = computed(() => props.projectId)

// ─── Guard 数据消费 (Task 7.1) ──────────────────────────────────────────
const guard = computed<GuardData>(() => props.htmlData?.guard ?? {})
const isReadonly = computed(() => props.readonly || guard.value.readonly === true)
const isLocked = computed(() => guard.value.locked === true)
const gateReason = computed(() => guard.value.gate_reason || '')
const unresolvedCount = computed(() => guard.value.unresolved_count ?? 0)
const signedBy = computed(() => guard.value.signed_by || '')
const signedAt = computed(() => guard.value.signed_at || '')

const { projectRole } = useProjectRole(projectIdRef)
const isSigningPartner = computed(() => projectRole.value === 'signing_partner')

// 格式化签字时间为本地日期时间 (Task 7.2)
const formattedSignedAt = computed(() => {
  if (!signedAt.value) return ''
  try {
    return new Date(signedAt.value).toLocaleString('zh-CN')
  } catch {
    return signedAt.value
  }
})

const template = ref<ReviewTemplate | null>(null)
const context = ref<Record<string, unknown>>({})
const responses = ref<Record<string, { conclusion: string; remark: string }>>({})
const recordText = ref('')
const signStatus = ref<'pass' | 'reject' | ''>('')
const loading = ref(false)
const saving = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const applicableInfo = ref<{ applicable: boolean; mandatory: boolean; reason?: string } | null>(null)
const hints = ref<{ item_pattern: string; suggested: string; reason: string }[]>([])
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── 解锁对话框状态 (Task 7.4) ─────────────────────────────────────────
const unlockDialogVisible = ref(false)
const unlockReason = ref('')
const unlockLoading = ref(false)

const applicableItems = computed(() =>
  (template.value?.items || []).filter(i => !i.auto_na),
)

const completedCount = computed(() =>
  applicableItems.value.filter(i => {
    const c = responses.value[i.item_id]?.conclusion
    return c === 'Y' || c === 'NA'
  }).length,
)

const progressPct = computed(() => {
  const total = applicableItems.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const allItemsDone = computed(() =>
  applicableItems.value.length > 0 &&
  applicableItems.value.every(i => {
    const c = responses.value[i.item_id]?.conclusion
    return c === 'Y' || c === 'NA'
  }),
)

// 签字按钮禁用逻辑 (Task 7.3)
const signButtonDisabled = computed(() =>
  !allItemsDone.value || signStatus.value === 'pass' || unresolvedCount.value > 0 || isReadonly.value,
)
const signButtonTooltip = computed(() => {
  if (unresolvedCount.value > 0) return '尚有未清复核意见'
  if (!allItemsDone.value) return '请先完成所有适用检查项'
  return ''
})

const categoryLabel = computed(() => {
  const bc = String(context.value.business_category || '')
  return bc ? `${bc[0]}类` : ''
})

async function loadDefinition() {
  if (!effectiveWpCode.value) return
  loading.value = true
  try {
    const res = await api.get(
      `/api/projects/${props.projectId}/a21/review-definitions`,
      { params: { wp_code: effectiveWpCode.value } },
    )
    const data = res?.data ?? res
    template.value = data?.template ?? null
    context.value = data?.context ?? {}
  } catch (e) {
    console.error('[A21] load definition failed:', e)
    ElMessage.error('加载复核模板失败')
  } finally {
    loading.value = false
  }
}

async function loadResponses() {
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: { item_id: string; conclusion: string; remark: string }[] =
      Array.isArray(res) ? res : (res?.data ?? [])
    const map: Record<string, { conclusion: string; remark: string }> = {}
    for (const row of list) {
      map[row.item_id] = { conclusion: row.conclusion || '', remark: row.remark || '' }
    }
    responses.value = map
    const recKey = `${effectiveWpCode.value}-record`
    recordText.value = map[recKey]?.remark || ''
    const signKey = `${effectiveWpCode.value}-sign`
    signStatus.value = (map[signKey]?.conclusion as 'pass' | 'reject' | '') || ''
  } catch (e) {
    console.warn('[A21] load responses failed:', e)
  }
}

async function loadApplicableBadge() {
  try {
    const res = await api.get(
      `/api/projects/${props.projectId}/a21/applicable-review-templates`,
    )
    const list = Array.isArray(res) ? res : (res?.data ?? [])
    const hit = list.find((t: any) => t.wp_code === effectiveWpCode.value)
    if (hit) {
      applicableInfo.value = {
        applicable: !!hit.applicable,
        mandatory: !!hit.mandatory,
        reason: hit.reason,
      }
    }
  } catch { /* non-critical */ }
}

async function loadHints() {
  try {
    const res = await api.get(
      `/api/projects/${props.projectId}/a21/prefill-suggestions`,
      { params: { wp_code: effectiveWpCode.value } },
    )
    const data = res?.data ?? res
    hints.value = data?.hints || []
  } catch { /* non-critical */ }
}

function setItemConclusion(itemId: string, conclusion: 'Y' | 'N' | 'NA') {
  if (isReadonly.value) return
  responses.value[itemId] = {
    conclusion,
    remark: responses.value[itemId]?.remark || '',
  }
  debouncedSave()
}

function debouncedSave() {
  if (isReadonly.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doSave(), 1500)
}

async function doSave() {
  if (!template.value || isReadonly.value) return
  saving.value = true
  saveStatus.value = 'saving'
  try {
    const items: { item_id: string; conclusion: string; remark: string }[] = []
    for (const item of template.value.items) {
      const r = responses.value[item.item_id]
      if (!r?.conclusion && !r?.remark) continue
      items.push({
        item_id: item.item_id,
        conclusion: r?.conclusion || '',
        remark: r?.remark || '',
      })
    }
    if (recordText.value.trim()) {
      items.push({
        item_id: `${effectiveWpCode.value}-record`,
        conclusion: 'done',
        remark: recordText.value,
      })
    }
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    saveStatus.value = 'saved'
    emit('save')
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch {
    saveStatus.value = 'error'
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSign(action: 'pass' | 'reject') {
  if (action === 'pass' && !allItemsDone.value) {
    ElMessage.warning('请先完成所有适用检查项')
    return
  }
  if (action === 'pass' && unresolvedCount.value > 0) {
    ElMessage.warning(`尚有 ${unresolvedCount.value} 项复核意见未清零，无法签字`)
    return
  }
  let comment = ''
  if (action === 'reject') {
    try {
      const { value } = await ElMessageBox.prompt('请输入退回原因', '退回复核', { type: 'warning' })
      comment = value || ''
    } catch { return }
  }
  try {
    await api.post(`/api/workpapers/${props.wpId}/review-sign`, {
      project_id: props.projectId,
      wp_code: effectiveWpCode.value,
      action,
      comment,
    })
    signStatus.value = action
    ElMessage.success(action === 'pass' ? '复核通过' : '已退回')
    if (action === 'pass') emit('pass')
    else emit('reject')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '签字失败'
    ElMessage.error(detail)
  }
}

// ─── 解锁操作 (Task 7.4) ────────────────────────────────────────────────
function openUnlockDialog() {
  unlockReason.value = ''
  unlockDialogVisible.value = true
}

async function confirmUnlock() {
  if (!unlockReason.value.trim()) {
    ElMessage.warning('解锁必须填写原因')
    return
  }
  unlockLoading.value = true
  try {
    await api.post(`/api/workpapers/${props.wpId}/review-unlock`, {
      project_id: props.projectId,
      wp_code: effectiveWpCode.value,
      reason: unlockReason.value.trim(),
    })
    ElMessage.success('已解锁，复核表恢复可编辑')
    unlockDialogVisible.value = false
    // 刷新数据恢复可编辑状态
    await loadResponses()
    // 通知父组件刷新 render-config
    emit('save')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '解锁失败'
    ElMessage.error(detail)
  } finally {
    unlockLoading.value = false
  }
}

async function handleExport() {
  try {
    const url = `/api/workpapers/${props.wpId}/export-review-xlsx?project_id=${props.projectId}&wp_code=${effectiveWpCode.value}`
    await api.download(url, `${effectiveWpCode.value}.xlsx`)
  } catch {
    ElMessage.error('导出失败')
  }
}

function itemRemark(itemId: string): string {
  return responses.value[itemId]?.remark || ''
}

function setItemRemark(itemId: string, remark: string) {
  if (isReadonly.value) return
  if (!responses.value[itemId]) {
    responses.value[itemId] = { conclusion: '', remark }
  } else {
    responses.value[itemId].remark = remark
  }
  debouncedSave()
}

function applyHint(h: { item_pattern: string; suggested: string; reason: string }) {
  if (isReadonly.value) return
  const item = template.value?.items.find(i => i.item_id.endsWith(h.item_pattern))
  if (item && !item.auto_na) {
    setItemConclusion(item.item_id, h.suggested as 'Y' | 'N' | 'NA')
    ElMessage.success('已应用建议')
  }
}

watch(recordText, () => { if (!isReadonly.value) debouncedSave() })
watch(() => props.wpId, () => { loadResponses(); loadDefinition() })

onMounted(async () => {
  await loadDefinition()
  await loadResponses()
  loadApplicableBadge()
  loadHints()
})

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<template>
  <div v-loading="loading" class="gt-review-checklist">
    <!-- Task 7.1: gate_reason 警告提示 -->
    <el-alert
      v-if="gateReason"
      type="warning"
      :closable="false"
      show-icon
      class="gt-review-checklist__gate-alert"
    >
      {{ gateReason }}
    </el-alert>

    <!-- Task 7.2: 锁定状态 Banner -->
    <el-alert
      v-if="isLocked"
      type="info"
      :closable="false"
      show-icon
      class="gt-review-checklist__lock-alert"
    >
      <template #default>
        <span>已由 {{ signedBy }} 于 {{ formattedSignedAt }} 签字锁定</span>
        <!-- Task 7.4: 解锁按钮（合伙人专属） -->
        <el-button
          v-if="isSigningPartner"
          size="small"
          type="warning"
          plain
          style="margin-left: 12px"
          @click="openUnlockDialog"
        >
          解锁
        </el-button>
      </template>
    </el-alert>

    <div v-if="!applicableInfo?.applicable && applicableInfo !== null" class="na-banner">
      本模板对当前项目不适用{{ applicableInfo.reason ? `：${applicableInfo.reason}` : '' }}
    </div>

    <div class="header-bar">
      <div class="meta">
        <span class="role">{{ template?.role_label || '角色复核' }}</span>
        <el-tag size="small">{{ template?.audit_type_label }}</el-tag>
        <el-tag v-if="categoryLabel" size="small" type="info">{{ categoryLabel }}</el-tag>
        <el-tag v-if="applicableInfo?.mandatory" size="small" type="danger">必做</el-tag>
        <el-tag v-if="isReadonly && !isLocked" size="small" type="info">只读</el-tag>
      </div>
      <div class="header-actions">
        <span v-if="saveStatus === 'saving'" class="save-hint">保存中…</span>
        <span v-else-if="saveStatus === 'saved'" class="save-hint saved">已保存</span>
        <el-button size="small" @click="handleExport">导出 xlsx</el-button>
      </div>
    </div>

    <div class="progress-row">
      <span>进度 {{ completedCount }}/{{ applicableItems.length }}</span>
      <el-progress :percentage="progressPct" :stroke-width="8" style="flex:1; max-width: 240px;" />
    </div>

    <div v-if="hints.length && !isReadonly" class="hints-row">
      <span class="hints-label">预填建议：</span>
      <el-button
        v-for="(h, idx) in hints"
        :key="idx"
        size="small"
        link
        type="primary"
        @click="applyHint(h)"
      >
        {{ h.reason }}
      </el-button>
    </div>

    <el-scrollbar max-height="420px" class="items-scroll">
      <div
        v-for="item in template?.items"
        :key="item.item_id"
        class="check-item"
        :class="{ 'is-auto-na': item.auto_na }"
      >
        <div class="item-content">
          <span class="seq">{{ item.seq }}.</span>
          {{ item.content }}
          <el-tag v-if="item.auto_na" size="small" type="info" class="na-tag">
            N/A — {{ item.auto_na_reason || '不适用' }}
          </el-tag>
        </div>
        <div v-if="!item.auto_na" class="item-actions">
          <!-- Task 7.1: readonly 时禁用 radio -->
          <el-radio-group
            :model-value="responses[item.item_id]?.conclusion"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => setItemConclusion(item.item_id, v as 'Y'|'N'|'NA')"
          >
            <el-radio-button value="Y">是</el-radio-button>
            <el-radio-button value="N">否</el-radio-button>
            <el-radio-button value="NA">N/A</el-radio-button>
          </el-radio-group>
          <!-- Task 7.1: readonly 时禁用 input -->
          <el-input
            :model-value="itemRemark(item.item_id)"
            placeholder="备注"
            size="small"
            class="remark-input"
            :disabled="isReadonly"
            @update:model-value="(v: string) => setItemRemark(item.item_id, v)"
          />
        </div>
      </div>
    </el-scrollbar>

    <div class="record-section">
      <div class="section-title">复核记录</div>
      <!-- Task 7.1: readonly 时禁用 textarea -->
      <el-input
        v-model="recordText"
        type="textarea"
        :rows="4"
        placeholder="填写复核记录…"
        :disabled="isReadonly"
      />
    </div>

    <div class="sign-section">
      <el-tag v-if="signStatus === 'pass'" type="success">已通过</el-tag>
      <el-tag v-else-if="signStatus === 'reject'" type="warning">已退回</el-tag>

      <!-- Task 7.3: 未清意见 Badge -->
      <el-badge
        v-if="unresolvedCount > 0"
        :value="unresolvedCount"
        type="danger"
        class="unresolved-badge"
      >
        <el-tooltip :content="signButtonTooltip" :disabled="!signButtonTooltip" placement="top">
          <el-button type="success" :disabled="signButtonDisabled" @click="handleSign('pass')">
            通过
          </el-button>
        </el-tooltip>
      </el-badge>
      <el-tooltip v-else :content="signButtonTooltip" :disabled="!signButtonTooltip" placement="top">
        <el-button type="success" :disabled="signButtonDisabled" @click="handleSign('pass')">
          通过
        </el-button>
      </el-tooltip>

      <el-button type="warning" :disabled="isReadonly" @click="handleSign('reject')">退回</el-button>
    </div>

    <!-- Task 7.4: 解锁原因对话框 -->
    <el-dialog
      v-model="unlockDialogVisible"
      title="解锁复核表"
      width="450px"
      :close-on-click-modal="false"
    >
      <p style="margin-bottom: 12px; color: #666">
        解锁后该复核表将恢复可编辑状态，签字记录将被移除。
      </p>
      <el-input
        v-model="unlockReason"
        type="textarea"
        :rows="3"
        placeholder="请输入解锁原因（必填）"
        maxlength="500"
        show-word-limit
      />
      <template #footer>
        <el-button @click="unlockDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="unlockLoading"
          :disabled="!unlockReason.trim()"
          @click="confirmUnlock"
        >
          确认解锁
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-review-checklist {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-review-checklist__gate-alert {
  margin-bottom: 4px;
}
.gt-review-checklist__lock-alert {
  margin-bottom: 4px;
}
.na-banner {
  padding: 8px 12px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
  color: var(--el-text-color-secondary);
  font-size: var(--gt-font-size-sm);
}
.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.role { font-weight: 600; font-size: var(--gt-font-size-md); }
.header-actions { display: flex; align-items: center; gap: 8px; }
.save-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.save-hint.saved { color: var(--el-color-success); }
.progress-row { display: flex; align-items: center; gap: 12px; font-size: var(--gt-font-size-sm); }
.hints-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; font-size: 12px; }
.hints-label { color: var(--el-text-color-secondary); }
.check-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.check-item.is-auto-na { opacity: 0.55; }
.item-content { margin-bottom: 6px; line-height: 1.5; font-size: var(--gt-font-size-sm); }
.seq { font-weight: 600; margin-right: 4px; }
.na-tag { margin-left: 8px; }
.item-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.remark-input { width: 200px; }
.record-section .section-title { font-weight: 600; margin-bottom: 6px; font-size: var(--gt-font-size-sm); }
.sign-section { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }
.unresolved-badge { margin-right: 4px; }
</style>
