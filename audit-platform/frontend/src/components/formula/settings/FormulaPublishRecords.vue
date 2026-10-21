<!--
  发布记录 + 全局候选审核（spec formula-global-settings-sync，R4.5 / R13.7 / R14.3）。
  发布记录：变更内容、发布人、时间、各分类计数。候选（非管理员「设为全局」、模板「提交为全局候选」、自定义预设）：
  管理员先看影响预览、做决策后通过（即发布），或填写原因驳回。
-->
<template>
  <div class="gt-fpr" data-testid="formula-publish-records">
    <div class="gt-fpr-bar">
      <el-select v-model="status" size="small" style="width: 140px" @change="load">
        <el-option value="" label="全部状态" />
        <el-option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key" :label="label" />
      </el-select>
      <el-select v-model="domain" size="small" clearable placeholder="全部公式域" style="width: 180px" @change="load">
        <el-option v-for="d in domains" :key="d.key" :value="d.key" :label="d.label" />
      </el-select>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table v-loading="loading" :data="items" size="small" border max-height="calc(100vh - 320px)" row-key="id"
      empty-text="暂无记录">
      <el-table-column label="时间" width="150">
        <template #default="{ row }">{{ fmtTime(row.published_at) }}</template>
      </el-table-column>
      <el-table-column label="公式域" width="140">
        <template #default="{ row }">{{ domainLabel(row.domain) }}</template>
      </el-table-column>
      <el-table-column label="作用范围" width="120">
        <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
      </el-table-column>
      <el-table-column label="来源" width="120">
        <template #default="{ row }">{{ SOURCE_LABELS[row.source] || row.source }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTag(row.status)">{{ STATUS_LABELS[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="变更" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ changeSummary(row) }}</template>
      </el-table-column>
      <el-table-column label="影响" min-width="160">
        <template #default="{ row }">{{ impactSummary(row) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="说明" min-width="140" show-overflow-tooltip />
      <el-table-column v-if="isAdmin" label="审核" width="130" fixed="right">
        <template #default="{ row }">
          <template v-if="isPendingRecord(row)">
            <el-button link type="primary" size="small" :data-testid="`fpr-review-${row.id}`" @click="onReview(row)">预览并通过</el-button>
            <el-button link type="danger" size="small" @click="onReject(row)">驳回</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <FormulaPublishPreviewDialog v-model="previewVisible" :preview="preview" :loading="previewLoading"
      title="审核全局候选：发布前影响预览" submit-text="通过并发布" :hint="previewHint" :submit="onApprove" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import FormulaPublishPreviewDialog from './FormulaPublishPreviewDialog.vue'
import {
  formulaErrorText, formulaSettingsApi, isPendingRecord, scopeLabel,
  type Decisions, type FormulaDomainInfo, type PublishRecord, type SyncPreview,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaPublishRecords' })

const props = withDefaults(defineProps<{ domains: FormulaDomainInfo[]; isAdmin?: boolean }>(), { isAdmin: false })
const emit = defineEmits<{ published: [] }>()

const STATUS_LABELS: Record<string, string> = { published: '已发布', pending: '待审核', rejected: '已驳回' }
const SOURCE_LABELS: Record<string, string> = {
  global_edit: '全局设置', direct_edit: '直接修改报表配置', promote: '项目设为全局', master_sync: '主模板同步',
  template_promote: '模板设为全局', candidate: '候选审核通过', apply_to_projects: '应用到指定项目',
}

const items = ref<PublishRecord[]>([])
const loading = ref(false)
const status = ref('')
const domain = ref('')
const preview = ref<SyncPreview | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
const reviewing = ref<PublishRecord | null>(null)

const previewHint = computed(() => {
  const stale = (preview.value?.global_changed_since_submit as string[] | undefined) || []
  return stale.length ? `提交后全局又改过 ${stale.length} 处：通过后以候选内容为准覆盖当前全局，请核对。` : ''
})

function domainLabel(key: string): string {
  if (key === 'template') return '公式模板（多域）'
  if (key === 'preset') return '自定义公式预设'
  return props.domains.find((d) => d.key === key)?.label || key
}
function statusTag(s: string): 'success' | 'warning' | 'info' {
  return ({ published: 'success', pending: 'warning' } as Record<string, 'success' | 'warning'>)[s] || 'info'
}
function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', { hour12: false })
}
function changeSummary(r: PublishRecord): string {
  const cs = r.change_set || []
  const head = cs.slice(0, 3).map((c) => c.label || c.slot_key).join('、')
  return cs.length > 3 ? `${head} 等 ${cs.length} 处` : (head || '—')
}
function impactSummary(r: PublishRecord): string {
  const s = r.summary || {}
  if (s.affected_project_count == null) return '—'
  const parts = [`${s.affected_project_count} 个项目`]
  if (s.conflict_count) parts.push(`冲突 ${s.conflict_count}`)
  if (s.pending_total) parts.push(`待确认 ${s.pending_total}`)
  return parts.join('，')
}

async function load() {
  loading.value = true
  try {
    items.value = (await formulaSettingsApi.publishes({
      status: status.value || undefined, domain: domain.value || undefined, limit: 100,
    }))?.items || []
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载发布记录失败'))
  } finally {
    loading.value = false
  }
}

async function onReview(row: PublishRecord) {
  reviewing.value = row
  preview.value = null
  previewVisible.value = true
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.candidatePreview(row.id)
  } catch (e: any) {
    previewVisible.value = false
    ElMessage.error(formulaErrorText(e, '加载候选预览失败'))
  } finally {
    previewLoading.value = false
  }
}

async function onApprove(payload: { decisions: Decisions; note: string }): Promise<boolean> {
  const row = reviewing.value
  if (!row) return false
  try {
    await formulaSettingsApi.reviewCandidate(row.id, { approve: true, decisions: payload.decisions, note: payload.note || undefined })
    ElMessage.success('候选已通过并发布')
    emit('published')
    await load()
    return true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '审核失败'))
    return false
  }
}

async function onReject(row: PublishRecord) {
  let note = ''
  try {
    const res = await ElMessageBox.prompt('请填写驳回原因（提交人可在发布记录里看到）', '驳回全局候选', {
      confirmButtonText: '驳回', cancelButtonText: '取消', inputPlaceholder: '驳回原因',
    })
    note = String((res as any)?.value || '').trim()
  } catch { return }
  try {
    await formulaSettingsApi.reviewCandidate(row.id, { approve: false, note: note || undefined })
    ElMessage.success('已驳回')
    await load()
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '驳回失败'))
  }
}

onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.gt-fpr-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
</style>
