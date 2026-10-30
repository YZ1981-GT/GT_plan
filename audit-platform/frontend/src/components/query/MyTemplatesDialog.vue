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
  <el-dialog v-model="visible" title="📚 查询模板" width="720px" append-to-body destroy-on-close @open="loadTemplates">
    <div v-if="loading && !templates.length" class="gt-mtd-empty" data-testid="mtd-loading">加载中…</div>
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="loadError" data-testid="mtd-error" />
    <div v-else-if="!templates.length" class="gt-mtd-empty" data-testid="mtd-empty">
      暂无可用的查询模板，可在查询界面点击「💾 保存」创建
    </div>
    <div v-else class="gt-mtd-list" data-testid="mtd-list">
      <div v-for="tpl in templates" :key="tpl.id" class="gt-mtd-item" data-testid="mtd-item">
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
          <el-button size="small" type="primary" :aria-label="`载入模板 ${tpl.name}`" data-testid="mtd-load" @click="onLoad(tpl)">
            载入
          </el-button>
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
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { customQuery as P_cq } from '@/services/apiPaths'
import { useAuthStore } from '@/stores/auth'
import { fmtDateTime, parseServerTime } from '@/utils/formatters'
import { describeQueryError, queryErrorToast } from './queryErrorText'
import { invalidateTemplateCache, readTemplateCache, writeTemplateCache } from './queryTemplateCache'
import { normalizeTemplateScope, templateScopeLabel } from './queryTemplateScope'
import { templateSourceOf, type QueryTemplateItem } from './queryTemplateRestore'

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 显示「执行」（弹窗：按当前项目经服务端模板执行端点执行） */
  allowRun?: boolean
  /** 「执行」不可用的原因（如未选项目）；空串 = 可用 */
  runBlockedReason?: string
}>(), { allowRun: false, runBlockedReason: '' })

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  load: [config: Record<string, unknown>, tpl: QueryTemplateItem]
  run: [tpl: QueryTemplateItem]
}>()

const visible = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })
const templates = ref<QueryTemplateItem[]>([])
const loading = ref(false)
const loadError = ref('')
const authStore = useAuthStore()
const owner = () => String(authStore.userId || '')

/** 打开即取：先显示本人的缓存（5 分钟内），同时向服务端重新取并刷新缓存 */
async function loadTemplates() {
  loadError.value = ''
  templates.value = readTemplateCache<QueryTemplateItem>({ owner: owner() }) ?? []
  loading.value = true
  try {
    const data = await api.get(P_cq.templates, { _silent: true } as any) as { templates?: QueryTemplateItem[] } | null
    const list = Array.isArray(data?.templates) ? data!.templates! : []
    templates.value = list
    writeTemplateCache(list, { owner: owner() })
  } catch (e: unknown) {
    if (!templates.value.length) loadError.value = queryErrorToast('加载查询模板', describeQueryError(e))
  } finally {
    loading.value = false
  }
}

function sourceLabel(tpl: QueryTemplateItem): string {
  return templateSourceOf(tpl) || '（未设置数据源）'
}

function updatedText(tpl: QueryTemplateItem): string {
  const ts = tpl.updated_at || tpl.created_at
  return ts ? fmtDateTime(parseServerTime(ts)) : '—'
}

function onLoad(tpl: QueryTemplateItem) {
  if (!templateSourceOf(tpl)) {
    ElMessage.warning('模板没有数据源，无法载入')
    return
  }
  emit('load', tpl.config ?? {}, tpl)
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
.gt-mtd-list { max-height: 420px; overflow-y: auto; }
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
