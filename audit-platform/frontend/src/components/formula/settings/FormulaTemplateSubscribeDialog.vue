<!--
  订阅 / 退订公式模板（spec formula-global-settings-sync，design §16.6，R13.3 / R13.5 / R13.10）。
  订阅：选域 → 选模板 → 预览（直接生效 / 已一致 / 冲突）→ 冲突逐条「采用模板 / 保留本项目」→ 订阅（只写本项目层）。
  退订：「保留模板公式为本项目适配」或「回到全局」；回到全局时与全局不同的公式位逐条确认。
  每个域最多订阅一个模板；订阅、退订需本项目编辑权限。
-->
<template>
  <el-dialog v-model="visible" title="公式模板订阅" width="760px" append-to-body destroy-on-close
    data-testid="formula-template-subscribe">
    <div class="gt-ftsub-row">
      <span class="gt-ftsub-label">公式域</span>
      <el-select v-model="domain" style="width: 220px" data-testid="ftsub-domain">
        <el-option v-for="d in domainOptions" :key="d.key" :value="d.key" :label="d.label" />
      </el-select>
    </div>

    <div v-loading="loading">
      <template v-if="current">
        <el-alert type="success" :closable="false" show-icon class="gt-ftsub-gap"
          :title="`本项目已订阅「${current.template_name}」v${current.template_version}`"
          :description="current.behind ? `模板已更新到 v${current.current_version}${current.pinned ? '（本项目暂缓采用，处理完待确认后自动跟上）' : ''}` : '已是最新版本'" />
        <div class="gt-ftsub-row">
          <span class="gt-ftsub-label">退订方式</span>
          <el-radio-group v-model="unsubscribeMode">
            <el-radio value="keep">保留模板公式为本项目适配</el-radio>
            <el-radio value="global">回到全局</el-radio>
          </el-radio-group>
        </div>
        <div class="gt-ftsub-actions">
          <el-button type="danger" plain :loading="previewLoading" data-testid="ftsub-unsubscribe" @click="onUnsubscribePreview">
            退订
          </el-button>
        </div>
      </template>
      <template v-else>
        <el-table :data="templates" size="small" border max-height="360" empty-text="没有可订阅的模板（看不到的模板说明未共享给你）">
          <el-table-column prop="name" label="模板" min-width="200" show-overflow-tooltip />
          <el-table-column prop="share_scope_label" label="共享范围" width="90" />
          <el-table-column label="适用范围" width="140">
            <template #default="{ row }">{{ scopeLabel(row.applicable_scope) }}</template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="70" align="center" />
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" :loading="previewLoading && pickedId === row.id"
                :data-testid="`ftsub-pick-${row.id}`" @click="onSubscribePreview(row)">订阅</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
  <FormulaPublishPreviewDialog v-model="previewVisible" :preview="preview" :title="previewTitle" :submit="onSubmit"
    :hint="previewHint" :submit-text="mode === 'subscribe' ? '确认订阅' : '确认退订'" :conflict-options="conflictOptions"
    default-conflict="adopt" :allow-defer="false" :show-note="false" :show-project="false"
    :new-label="mode === 'subscribe' ? '模板定义' : '全局定义'" local-label="本项目当前" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import FormulaPublishPreviewDialog from './FormulaPublishPreviewDialog.vue'
import {
  formulaErrorText, formulaSettingsApi, scopeLabel,
  type ConflictChoice, type Decisions, type FormulaDomainInfo, type FormulaTemplateInfo,
  type SyncPreview, type TemplateSubscription,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaTemplateSubscribeDialog' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: string
  defaultDomain?: string
}>(), { defaultDomain: 'report' })

const emit = defineEmits<{ 'update:modelValue': [value: boolean]; changed: [domain: string] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const domain = ref(props.defaultDomain)
const domainOptions = ref<FormulaDomainInfo[]>([])
const subscriptions = ref<TemplateSubscription[]>([])
const templates = ref<FormulaTemplateInfo[]>([])
const loading = ref(false)
const unsubscribeMode = ref<'keep' | 'global'>('keep')
const mode = ref<'subscribe' | 'unsubscribe'>('subscribe')
const pickedId = ref('')
const preview = ref<SyncPreview | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)

const current = computed(() => subscriptions.value.find((s) => s.domain === domain.value) || null)
const previewTitle = computed(() => {
  if (mode.value === 'subscribe') return '订阅预览'
  return unsubscribeMode.value === 'keep' ? '退订预览：保留为本项目适配' : '退订预览：回到全局'
})
const previewHint = computed(() => {
  if (mode.value === 'subscribe') return '模板公式写入本项目；冲突（本项目改过且与模板不同）请逐条选择。之后模板更新会提醒本项目确认。'
  if (unsubscribeMode.value === 'keep') {
    return `将保留 ${preview.value?.kept ?? 0} 处模板公式为本项目适配；之后全局更新正常同步，与本项目不同时会提醒确认。`
  }
  return '与全局不同的公式位逐条确认：回到全局，或保留本项目的写法。'
})
const conflictOptions = computed<ReadonlyArray<{ value: ConflictChoice; label: string }>>(() => mode.value === 'subscribe'
  ? [{ value: 'adopt', label: '采用模板' }, { value: 'keep', label: '保留本项目' }]
  : [{ value: 'adopt', label: '回到全局' }, { value: 'keep', label: '保留本项目' }])

async function loadAll() {
  if (!props.projectId) return
  loading.value = true
  try {
    const [subs, list] = await Promise.all([
      formulaSettingsApi.subscriptions(props.projectId),
      formulaSettingsApi.templates({ domain: domain.value }),
    ])
    subscriptions.value = subs?.items || []
    templates.value = list?.items || []
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载公式模板失败'))
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, async (open) => {
  if (!open) return
  domain.value = props.defaultDomain
  unsubscribeMode.value = 'keep'
  // 域清单与模板清单并行取（loadAll 同步进入加载态）：原先等域清单回来才开始加载，期间列表空着、
  // 露出「没有可订阅的模板」（R5 走查：公式管理中心还在加载时打开订阅，几秒内都是这句）
  const domainsReq = formulaSettingsApi.domains()
    .then((data) => { domainOptions.value = (data?.domains || []).filter((d) => d.wired) })
    .catch(() => { /* 域清单拿不到时只显示当前域 */ })
  await Promise.all([domainsReq, loadAll()])
}, { immediate: true })

watch(domain, () => { if (props.modelValue) void loadAll() })

async function onSubscribePreview(tpl: FormulaTemplateInfo) {
  mode.value = 'subscribe'
  pickedId.value = tpl.id
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.subscribePreview(props.projectId, { template_id: tpl.id, domain: domain.value })
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '订阅预览失败'))
  } finally {
    previewLoading.value = false
  }
}

async function onUnsubscribePreview() {
  mode.value = 'unsubscribe'
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.unsubscribePreview(props.projectId, {
      domain: domain.value, mode: unsubscribeMode.value,
    })
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '退订预览失败'))
  } finally {
    previewLoading.value = false
  }
}

async function onSubmit(payload: { decisions: Decisions }): Promise<boolean> {
  try {
    if (mode.value === 'subscribe') {
      await formulaSettingsApi.subscribe(props.projectId, {
        template_id: pickedId.value, domain: domain.value, decisions: payload.decisions,
      })
      ElMessage.success('已订阅：模板公式已写入本项目，选「保留本项目」的公式不变')
    } else {
      await formulaSettingsApi.unsubscribe(props.projectId, {
        domain: domain.value, mode: unsubscribeMode.value, decisions: payload.decisions,
      })
      ElMessage.success(unsubscribeMode.value === 'keep' ? '已退订，模板公式保留为本项目适配' : '已退订，公式回到全局')
    }
    emit('changed', domain.value)
    await loadAll()
    return true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, mode.value === 'subscribe' ? '订阅失败' : '退订失败'))
    return false
  }
}
</script>

<style scoped>
.gt-ftsub-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.gt-ftsub-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); width: 64px; }
.gt-ftsub-gap { margin-bottom: 10px; }
.gt-ftsub-actions { display: flex; justify-content: flex-end; }
</style>
