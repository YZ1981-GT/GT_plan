<!--
  QueryTemplateSaveDialog — 「保存为模板」对话框（advanced-query-linkage-closure 任务 28 / 29，AQ-39；R9.1，ADR-AQL-11）

  页面版与弹窗 💾 共用：三档可见范围「仅我可见 / 指定项目共享 / 公开」。可分享的项目取
  `GET /api/custom-query/template-share-targets`（与保存时逐项目的 edit 鉴权同一口径）；没有可分享的项目时分享两档置灰，
  只能存「仅我可见」。改造前页面版取 `GET /api/projects` 的 `can_edit`，该接口从不下发此字段 ⇒ 两档恒置灰（admin 亦然），
  弹窗 💾 固定存私有。保存失败显示后端中文原因；成功后模板列表缓存失效。
-->
<template>
  <el-dialog v-model="visible" title="保存查询模板" width="480px" append-to-body data-testid="cq-save-dialog">
    <el-form :model="form" :rules="rules" label-width="80px" size="small" @submit.prevent>
      <el-form-item label="名称" prop="name" required>
        <el-input v-model="form.name" placeholder="如 应收账款明细查询" maxlength="200" aria-label="模板名称" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" aria-label="模板说明" />
      </el-form-item>
      <el-form-item label="可见范围">
        <el-radio-group v-model="form.scope" aria-label="模板可见范围">
          <el-radio
            v-for="scope in SAVABLE_SCOPES"
            :key="scope"
            :value="scope"
            :disabled="scope !== 'private' && !canShareTemplates"
            :data-testid="`cq-save-scope-${scope}`"
          >{{ templateScopeLabel(scope) }}</el-radio>
        </el-radio-group>
        <div v-if="shareHint" class="gt-qtsd-hint" data-testid="cq-save-share-hint">{{ shareHint }}</div>
      </el-form-item>
      <el-form-item v-if="form.scope === 'project'" label="分享项目">
        <el-select
          v-model="form.shared_project_ids"
          multiple
          filterable
          placeholder="选择可编辑的项目"
          style="width: 100%"
          aria-label="分享到的项目"
        >
          <el-option v-for="p in shareOptions" :key="p.id" :label="p.label" :value="p.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="small" @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        size="small"
        :loading="saving"
        :disabled="!canSaveTemplate"
        data-testid="cq-save-confirm"
        @click="onConfirmSaveTemplate"
      >保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { customQuery as P_cq } from '@/services/apiPaths'
import { describeQueryError, queryErrorToast } from './queryErrorText'
import { invalidateTemplateCache } from './queryTemplateCache'
import {
  SAVABLE_SCOPES, SHARE_REQUIRED_SCOPES, normalizeTemplateScope, templateScopeLabel, type TemplateScope,
} from './queryTemplateScope'

interface SaveDialogProject { id: string; name?: string; code?: string }

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 模板的数据源键 */
  dataSource: string
  /** 要保存的查询配置（宿主按当前界面状态给出） */
  config: Record<string, unknown>
  /** 项目下拉（显示分享项目的名称；不在其中的分享目标按 id 显示） */
  projects?: SaveDialogProject[]
  defaultName?: string
  defaultDescription?: string
}>(), { projects: () => [], defaultName: '', defaultDescription: '' })

const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [template: unknown] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

const form = reactive({ name: '', description: '', scope: 'private' as TemplateScope, shared_project_ids: [] as string[] })
const rules = { name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }] }
const saving = ref(false)
/** 可分享到的项目 id（null = 还没取到 / 取失败） */
const shareTargets = ref<string[] | null>(null)
const shareTargetsFailed = ref(false)
let loadRound = 0

async function loadShareTargets() {
  const mine = ++loadRound
  shareTargets.value = null
  shareTargetsFailed.value = false
  try {
    const data = await api.get<{ project_ids?: unknown }>(P_cq.templateShareTargets, { _silent: true } as any)
    if (mine !== loadRound) return
    const ids = Array.isArray(data?.project_ids) ? data.project_ids.map(String) : null
    shareTargets.value = ids ?? []
    shareTargetsFailed.value = ids === null
  } catch {
    if (mine !== loadRound) return
    shareTargets.value = []
    shareTargetsFailed.value = true
  }
}

watch(visible, (open) => {
  if (!open) return
  form.name = props.defaultName
  form.description = props.defaultDescription
  form.scope = 'private'
  form.shared_project_ids = []
  void loadShareTargets()
}, { immediate: true })

const editableProjectIds = computed(() => new Set(shareTargets.value ?? []))
/** 有至少一个可分享的项目才开放分享两档（无则 fail-closed 只能存私有） */
const canShareTemplates = computed(() => editableProjectIds.value.size > 0)

const shareHint = computed(() => {
  if (canShareTemplates.value) return ''
  if (shareTargets.value === null) return '正在确认可分享的项目…'
  if (shareTargetsFailed.value) return `暂时无法确认可分享的项目，仅可保存为「${templateScopeLabel('private')}」`
  return `当前没有可编辑的项目，仅可保存为「${templateScopeLabel('private')}」`
})

const shareOptions = computed(() => {
  const byId = new Map(props.projects.map((p) => [String(p.id), p]))
  return [...editableProjectIds.value].map((id) => {
    const p = byId.get(id)
    return { id, label: p ? `${p.code ? `${p.code} ` : ''}${p.name || id}` : id }
  })
})

/** 提交用的分享目标：去重 + 只留可分享的项目（越权目标在提交前就被剔除） */
function resolveSharedProjectIds(): string[] {
  const seen = new Set<string>()
  return form.shared_project_ids.map(String).filter((id) => {
    if (seen.has(id) || !editableProjectIds.value.has(id)) return false
    seen.add(id)
    return true
  })
}

const canSaveTemplate = computed(() => {
  if (!form.name.trim()) return false
  const scope = normalizeTemplateScope(form.scope) as TemplateScope
  if (SHARE_REQUIRED_SCOPES.includes(scope) && !canShareTemplates.value) return false
  if (scope === 'project' && resolveSharedProjectIds().length === 0) return false
  return true
})

async function onConfirmSaveTemplate() {
  if (!canSaveTemplate.value) {
    ElMessage.warning(!form.name.trim() ? '请输入模板名称'
      : canShareTemplates.value ? '请选择至少一个可编辑的分享项目' : `当前没有可编辑的项目，仅可保存为「${templateScopeLabel('private')}」`)
    return
  }
  const scope = normalizeTemplateScope(form.scope) as TemplateScope
  saving.value = true
  try {
    const saved = await api.post(P_cq.templates, {
      name: form.name.trim(),
      description: form.description.trim() || null,
      data_source: props.dataSource,
      config: props.config,
      scope,
      shared_project_ids: scope === 'project' ? resolveSharedProjectIds() : [],
    }, { _silent: true } as any)
    invalidateTemplateCache()
    ElMessage.success(`模板「${form.name.trim()}」已保存`)
    emit('saved', saved)
    visible.value = false
  } catch (e) {
    ElMessage.warning(queryErrorToast('保存查询模板', describeQueryError(e)))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.gt-qtsd-hint { margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5; }
</style>
