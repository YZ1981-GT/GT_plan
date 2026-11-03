<!--
  MyTemplatesDialog.vue — 查询模板选择（弹窗与页面版共用；advanced-query-linkage-closure 任务 33，R9.3~R9.5，design §4.2）

  列出本人可见的模板（本人、公开、指定项目共享）：每行「载入」emit `load(config, tpl)`（宿主经 queryTemplateRestore 还原
  数据源、条件、列、排序、每页行数）；`allowRun` 时另有「执行」emit `run(tpl)`（宿主按当前项目经服务端模板执行端点执行，
  重新鉴权、可翻页）；作者可删除，删除进回收站（R9.5）。
  改造前三处缺陷（AQ-16 / AQ-25）：默认导入 api 并读 `resp.data?.templates`（apiProxy 已解包 ⇒ 列表恒空）、
  `<script setup>` 里 export 函数、删除确认写「此操作不可恢复」；且零挂载。
  列表缓存走 queryTemplateCache（按登录用户隔离）：打开先显示缓存，同时向服务端重新取（回收站恢复后再打开即能读回）。
-->
<template>
  <el-dialog v-model="visible" title="📚 查询模板" width="760px" append-to-body destroy-on-close @open="loadTemplates">
    <div v-if="loading && !templates.length && !presets.length" class="gt-mtd-empty" data-testid="mtd-loading">加载中…</div>
    <div v-else class="gt-mtd-list" data-testid="mtd-list">
      <section class="gt-mtd-section" data-testid="mtd-system-presets">
        <div class="gt-mtd-section-title">系统预置 <el-tag size="small" type="info" effect="plain">只读</el-tag></div>
        <el-alert v-if="presetLoadError" type="error" :closable="false" show-icon :title="presetLoadError"
          data-testid="mtd-preset-error" />
        <div v-else-if="!presets.length" class="gt-mtd-empty" data-testid="mtd-preset-empty">暂无系统预置</div>
        <div v-for="preset in presets" v-else :key="preset.id" class="gt-mtd-item" data-testid="mtd-preset-item">
          <div class="gt-mtd-info">
            <div class="gt-mtd-name">{{ preset.name }}</div>
            <div class="gt-mtd-meta">
              <el-tag size="small" effect="plain" round type="info">{{ preset.category || '系统预置' }}</el-tag>
              <span class="gt-mtd-source">{{ sourceLabel(preset) }}</span>
            </div>
            <div v-if="preset.description" class="gt-mtd-desc">{{ preset.description }}</div>
          </div>
          <div class="gt-mtd-actions">
            <el-tooltip :disabled="!resolveBlockedReason" :content="resolveBlockedReason" placement="top">
              <span>
                <el-button size="small" type="primary" :disabled="!!resolveBlockedReason || !!resolvingKey"
                  :loading="resolvingKey === `preset-load:${preset.id}`" :aria-label="`载入系统预置 ${preset.name}`"
                  data-testid="mtd-preset-load" @click="onPresetAction(preset, 'load')">载入</el-button>
              </span>
            </el-tooltip>
            <el-tooltip :disabled="!resolveBlockedReason" :content="resolveBlockedReason" placement="top">
              <span>
                <el-button size="small" :disabled="!!resolveBlockedReason || !!resolvingKey"
                  :loading="resolvingKey === `preset-save:${preset.id}`" :aria-label="`另存系统预置 ${preset.name}`"
                  data-testid="mtd-preset-save-as" @click="onPresetAction(preset, 'save-as')">另存为我的模板</el-button>
              </span>
            </el-tooltip>
          </div>
        </div>
      </section>

      <section class="gt-mtd-section" data-testid="mtd-user-templates">
        <div class="gt-mtd-section-title">我的模板</div>
        <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" data-testid="mtd-error" />
        <div v-else-if="!templates.length" class="gt-mtd-empty" data-testid="mtd-empty">
          暂无可用的查询模板，可在查询界面点击「💾 保存」创建
        </div>
        <div v-for="tpl in templates" v-else :key="tpl.id" class="gt-mtd-item" data-testid="mtd-item">
          <div class="gt-mtd-info">
            <div class="gt-mtd-name">{{ tpl.name }}</div>
            <div class="gt-mtd-meta">
              <el-tag size="small" effect="plain" round :type="normalizeTemplateScope(tpl.scope) === 'private' ? 'info' : 'warning'">
                {{ templateScopeLabel(tpl.scope) }}
              </el-tag>
              <span class="gt-mtd-source">{{ sourceLabel(tpl) }}</span>
              <span v-if="tpl.config?.cell_range" class="gt-mtd-range">{{ tpl.config.cell_range }}</span>
              <span class="gt-mtd-date">{{ updatedText(tpl) }}</span>
            </div>
            <div v-if="tpl.description" class="gt-mtd-desc">{{ tpl.description }}</div>
          </div>
          <div class="gt-mtd-actions">
            <el-tooltip :disabled="!userLoadBlockedReason(tpl)" :content="userLoadBlockedReason(tpl)" placement="top">
              <span>
                <el-button size="small" type="primary" :disabled="!!userLoadBlockedReason(tpl) || !!resolvingKey"
                  :loading="resolvingKey === `template-load:${tpl.id}`" :aria-label="`载入模板 ${tpl.name}`"
                  data-testid="mtd-load" @click="onLoad(tpl)">载入</el-button>
              </span>
            </el-tooltip>
            <el-tooltip v-if="allowRun" :disabled="!runBlockedReason" :content="runBlockedReason" placement="top">
              <span>
                <el-button size="small" :disabled="!!runBlockedReason" :aria-label="`执行模板 ${tpl.name}`" data-testid="mtd-run"
                  @click="onRun(tpl)">执行</el-button>
              </span>
            </el-tooltip>
            <el-button v-if="tpl.is_owner" size="small" type="danger" plain :icon="Delete" :aria-label="`删除模板 ${tpl.name}`"
              data-testid="mtd-delete" @click="onDelete(tpl)" />
          </div>
        </div>
      </section>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { customQuery as P_cq } from '@/services/apiPaths'
import { isKnownYear } from '@/components/custom-query/queryPayloads'
import { useAuthStore } from '@/stores/auth'
import { fmtDateTime, parseServerTime } from '@/utils/formatters'
import { describeQueryError, queryErrorToast } from './queryErrorText'
import {
  TEMPLATE_PRESET_CACHE_KEY, invalidateTemplateCache, readTemplateCache, writeTemplateCache,
} from './queryTemplateCache'
import { normalizeTemplateScope, templateScopeLabel } from './queryTemplateScope'
import { templateSourceOf, type QueryTemplateItem } from './queryTemplateRestore'

interface SystemPresetItem extends QueryTemplateItem {
  category?: string
  params?: string[]
  read_only: true
}

interface ResolvedParam {
  key?: string
  label?: string
  value?: unknown
  basis?: string | null
  missing_reason?: string | null
}

interface ResolvedTemplate {
  config: Record<string, unknown>
  params?: ResolvedParam[]
  notes?: string[]
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 当前项目与年度用于解析系统预置及含 `$param` 的用户模板。 */
  projectId?: string
  year?: number | null
  /** 显示「执行」（弹窗：按当前项目经服务端模板执行端点执行） */
  allowRun?: boolean
  /** 「执行」不可用的原因（如未选项目）；空串 = 可用 */
  runBlockedReason?: string
}>(), { projectId: '', year: null, allowRun: false, runBlockedReason: '' })

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  load: [config: Record<string, unknown>, tpl: QueryTemplateItem, notices?: string[]]
  'save-as': [config: Record<string, unknown>, tpl: QueryTemplateItem, notices: string[]]
  run: [tpl: QueryTemplateItem]
}>()

const visible = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })
const templates = ref<QueryTemplateItem[]>([])
const presets = ref<SystemPresetItem[]>([])
const loading = ref(false)
const loadError = ref('')
const presetLoadError = ref('')
const resolvingKey = ref('')
const authStore = useAuthStore()
const owner = () => String(authStore.userId || '')

/** 系统预置目录项补齐共用模板类型需要的只读字段。 */
function normalizePreset(raw: unknown): SystemPresetItem | null {
  if (!raw || typeof raw !== 'object') return null
  const item = raw as Record<string, unknown>
  const id = String(item.id ?? '').trim()
  const name = String(item.name ?? '').trim()
  const dataSource = String(item.data_source ?? '').trim()
  if (!id || !name || !dataSource) return null
  return {
    id, name, data_source: dataSource, config: null, scope: 'system', is_owner: false, read_only: true,
    description: typeof item.description === 'string' ? item.description : null,
    category: typeof item.category === 'string' ? item.category : undefined,
    params: Array.isArray(item.params) ? item.params.filter((v): v is string => typeof v === 'string') : [],
  }
}

/** 打开即取：用户模板与系统预置分键缓存，并分别刷新，任一失败不遮住另一分区。 */
async function loadTemplates() {
  loadError.value = ''
  presetLoadError.value = ''
  templates.value = readTemplateCache<QueryTemplateItem>({ owner: owner() }) ?? []
  presets.value = readTemplateCache<SystemPresetItem>({ owner: owner(), key: TEMPLATE_PRESET_CACHE_KEY }) ?? []
  loading.value = true
  const [templateResult, presetResult] = await Promise.allSettled([
    api.get(P_cq.templates, { _silent: true } as any) as Promise<{ templates?: QueryTemplateItem[] } | null>,
    api.get(P_cq.templatePresets, { _silent: true } as any) as Promise<{ presets?: unknown[] } | null>,
  ])
  if (templateResult.status === 'fulfilled') {
    const list = Array.isArray(templateResult.value?.templates) ? templateResult.value!.templates! : []
    templates.value = list
    writeTemplateCache(list, { owner: owner() })
  } else if (!templates.value.length) {
    loadError.value = queryErrorToast('加载查询模板', describeQueryError(templateResult.reason))
  }
  if (presetResult.status === 'fulfilled') {
    const list = (Array.isArray(presetResult.value?.presets) ? presetResult.value!.presets! : [])
      .map(normalizePreset).filter((item): item is SystemPresetItem => item !== null)
    presets.value = list
    writeTemplateCache(list, { owner: owner(), key: TEMPLATE_PRESET_CACHE_KEY })
  } else if (!presets.value.length) {
    presetLoadError.value = queryErrorToast('加载系统预置', describeQueryError(presetResult.reason))
  }
  loading.value = false
}

function sourceLabel(tpl: QueryTemplateItem): string {
  return templateSourceOf(tpl) || '（未设置数据源）'
}

function updatedText(tpl: QueryTemplateItem): string {
  const ts = tpl.updated_at || tpl.created_at
  return ts ? fmtDateTime(parseServerTime(ts)) : '—'
}

/** resolve 必须有明确项目和年度，避免把预置参数套到错误上下文。 */
const resolveBlockedReason = computed(() => {
  if (!props.projectId) return '请先选择项目'
  if (!isKnownYear(props.year)) return '请先选择审计年度'
  return ''
})

function containsParam(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsParam)
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  if (typeof record.$param === 'string' && record.$param) return true
  return Object.values(record).some(containsParam)
}

function userLoadBlockedReason(tpl: QueryTemplateItem): string {
  return containsParam(tpl.config) ? resolveBlockedReason.value : ''
}

function resolvedNotices(data: ResolvedTemplate): string[] {
  const params = Array.isArray(data.params) ? data.params : []
  const paramLines = params.map((param) => {
    if (param.missing_reason) return String(param.missing_reason)
    if (!param.basis) return ''
    if (param.key === 'materiality_performance') return `当前阈值：${param.basis}`
    if (param.key === 'cutoff_start' || param.key === 'cutoff_end') return `截止窗口：${param.basis}`
    return `${param.label || '参数'}：${param.basis}`
  }).filter(Boolean)
  const notes = Array.isArray(data.notes) ? data.notes.filter((note): note is string => typeof note === 'string' && !!note) : []
  return [...paramLines, ...notes]
}

async function resolveItem(
  tpl: QueryTemplateItem, kind: 'preset' | 'template', actionKey: string,
): Promise<{ config: Record<string, unknown>; notices: string[] } | null> {
  if (resolveBlockedReason.value) {
    ElMessage.warning(resolveBlockedReason.value)
    return null
  }
  resolvingKey.value = actionKey
  try {
    const path = kind === 'preset' ? P_cq.templatePresetResolve(tpl.id) : P_cq.templateResolve(tpl.id)
    const data = await api.get<ResolvedTemplate>(path, {
      params: { project_id: props.projectId, year: props.year }, _silent: true,
    } as any)
    if (!data?.config || typeof data.config !== 'object' || Array.isArray(data.config)) {
      ElMessage.warning('模板解析结果无效，请稍后重试')
      return null
    }
    return { config: data.config, notices: resolvedNotices(data) }
  } catch (e: unknown) {
    ElMessage.warning(queryErrorToast('解析查询模板', describeQueryError(e)))
    return null
  } finally {
    resolvingKey.value = ''
  }
}

async function onLoad(tpl: QueryTemplateItem) {
  if (!templateSourceOf(tpl)) {
    ElMessage.warning('模板没有数据源，无法载入')
    return
  }
  if (containsParam(tpl.config)) {
    const resolved = await resolveItem(tpl, 'template', `template-load:${tpl.id}`)
    if (!resolved) return
    emit('load', resolved.config, tpl, resolved.notices)
  } else {
    emit('load', tpl.config ?? {}, tpl)
  }
  visible.value = false
}

async function onPresetAction(preset: SystemPresetItem, action: 'load' | 'save-as') {
  const actionKey = action === 'load' ? `preset-load:${preset.id}` : `preset-save:${preset.id}`
  const resolved = await resolveItem(preset, 'preset', actionKey)
  if (!resolved) return
  if (action === 'load') emit('load', resolved.config, preset, resolved.notices)
  else emit('save-as', resolved.config, preset, resolved.notices)
  visible.value = false
}

function onRun(tpl: QueryTemplateItem) {
  if (props.runBlockedReason || !templateSourceOf(tpl)) return
  emit('run', tpl)
  visible.value = false
}

async function onDelete(tpl: QueryTemplateItem) {
  try {
    await ElMessageBox.confirm(`确认删除模板「${tpl.name}」？删除后可在回收站恢复。`, '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch {
    return
  }
  try {
    await api.delete(P_cq.templateDetail(tpl.id), { _silent: true } as any)
    templates.value = templates.value.filter((t) => t.id !== tpl.id)
    invalidateTemplateCache()
    ElMessage.success(`已删除模板「${tpl.name}」，可在回收站恢复`)
  } catch (e: unknown) {
    ElMessage.warning(queryErrorToast('删除模板', describeQueryError(e)))
  }
}

defineExpose({ loadTemplates })
</script>

<style scoped>
.gt-mtd-empty { text-align: center; padding: 32px; color: var(--el-text-color-secondary); }
.gt-mtd-list { max-height: 520px; overflow-y: auto; }
.gt-mtd-section + .gt-mtd-section { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.gt-mtd-section-title { display: flex; align-items: center; gap: 8px; padding: 0 12px 6px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-mtd-item { display: flex; align-items: center; justify-content: space-between; padding: 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.gt-mtd-item:last-child { border-bottom: none; }
.gt-mtd-item:hover { background: var(--el-fill-color-light); }
.gt-mtd-info { flex: 1; min-width: 0; }
.gt-mtd-name { font-weight: 500; font-size: var(--gt-font-size-sm); color: var(--el-text-color-primary); }
.gt-mtd-meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--el-text-color-secondary); }
.gt-mtd-source { background: var(--el-color-primary-light-9); padding: 0 6px; border-radius: 3px; }
.gt-mtd-range { background: var(--el-color-success-light-9); padding: 0 6px; border-radius: 3px; }
.gt-mtd-desc { margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--el-text-color-regular); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gt-mtd-actions { display: flex; gap: 4px; margin-left: 12px; }
</style>
