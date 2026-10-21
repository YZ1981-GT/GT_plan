<!--
  保存后选择应用范围（spec formula-global-settings-sync，design §11，R7）：
  仅本项目（默认）/ 设为全局并应用到全部项目（仅管理员）/ 提交为全局候选（非管理员，审核后发布）/ 应用到指定项目。
  除「仅本项目」外都先预览影响（R3），有冲突逐条确认后再执行；同一次操作带固定请求号，重复提交不重复生效（R11.3）。
-->
<template>
  <el-dialog v-model="visible" title="应用范围" width="560px" append-to-body destroy-on-close
    data-testid="formula-apply-scope">
    <p class="gt-fas-lead">已保存 {{ slotKeys.length }} 处公式到本项目。是否同时应用到其他地方？</p>
    <el-radio-group v-model="target" class="gt-fas-options">
      <el-radio value="project">仅本项目</el-radio>
      <el-radio v-if="canEditGlobal" value="global">设为全局，并应用到全部项目</el-radio>
      <el-radio v-else value="candidate">提交为全局候选（管理员审核后发布到全部项目）</el-radio>
      <el-radio value="projects">应用到指定项目</el-radio>
    </el-radio-group>
    <div v-if="target === 'projects'" class="gt-fas-projects">
      <el-select v-model="projectIds" multiple filterable collapse-tags collapse-tags-tooltip :loading="targetsLoading"
        placeholder="选择项目（只列出你有编辑权限、未归档的项目）" style="width: 100%" data-testid="fas-projects">
        <el-option v-for="t in targets" :key="t.project_id" :value="t.project_id"
          :label="t.same_scope ? t.name : `${t.name}（准则不同）`" />
      </el-select>
      <div class="gt-fas-muted">准则不同的项目按其自身有效定义比较；公式位不存在时会作为该项目独有公式写入。</div>
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ target === 'project' ? '完成' : '取消' }}</el-button>
      <el-button v-if="target !== 'project'" type="primary" :loading="previewLoading"
        :disabled="target === 'projects' && !projectIds.length" data-testid="fas-next" @click="onPreview">
        下一步：预览影响
      </el-button>
    </template>
  </el-dialog>
  <FormulaPublishPreviewDialog v-model="previewVisible" :preview="preview" :loading="previewLoading" :title="previewTitle"
    :submit="onSubmit" :submit-text="submitText" :allow-defer="target === 'global'"
    :readonly-decisions="target === 'candidate'" :conflict-options="conflictOptions" :show-note="target !== 'projects'"
    new-label="本项目定义" local-label="目标项目当前" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import FormulaPublishPreviewDialog from './FormulaPublishPreviewDialog.vue'
import {
  formulaErrorText, formulaSettingsApi, newRequestId,
  type ApplyTarget, type ApplyTargetKind, type ConflictChoice, type Decisions, type SyncPreview,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaApplyScopeDialog' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: string
  domain: string
  slotKeys: string[]
  /** 当前用户是否 admin（有效定义接口的 can_edit_global） */
  canEditGlobal?: boolean
}>(), { canEditGlobal: false })

const emit = defineEmits<{ 'update:modelValue': [value: boolean]; done: [target: ApplyTargetKind] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const target = ref<'project' | ApplyTargetKind>('project')
const projectIds = ref<string[]>([])
const targets = ref<ApplyTarget[]>([])
const targetsLoading = ref(false)
const preview = ref<SyncPreview | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
let requestId = ''

watch(() => props.modelValue, (open) => {
  if (!open) return
  target.value = 'project'
  projectIds.value = []
  preview.value = null
  requestId = ''
})

watch(target, async (t) => {
  if (t !== 'projects' || targets.value.length || !props.projectId) return
  targetsLoading.value = true
  try {
    targets.value = (await formulaSettingsApi.applyTargets(props.projectId, props.domain))?.items || []
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载可选项目失败'))
  } finally {
    targetsLoading.value = false
  }
})

const previewTitle = computed(() => ({
  global: '设为全局：发布前影响预览', candidate: '提交全局候选：影响预览', projects: '应用到指定项目：影响预览',
} as Record<string, string>)[target.value] || '影响预览')
const submitText = computed(() => ({ global: '确认发布', candidate: '提交候选', projects: '确认应用' } as Record<string, string>)[target.value] || '确认')
const conflictOptions = computed<ReadonlyArray<{ value: ConflictChoice; label: string }>>(() => target.value === 'projects'
  ? [{ value: 'adopt', label: '采用本项目定义' }, { value: 'keep', label: '保留目标项目' }, { value: 'ask', label: '交目标项目确认' }]
  : [{ value: 'adopt', label: '采用新全局' }, { value: 'keep', label: '保留项目' }, { value: 'ask', label: '交项目确认' }])

async function onPreview() {
  const t = target.value
  if (t === 'project') { visible.value = false; return }
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.applyPreview(props.projectId, props.domain, {
      target: t, slot_keys: props.slotKeys, project_ids: t === 'projects' ? projectIds.value : [],
    })
    requestId = newRequestId()
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '预览影响失败'))
  } finally {
    previewLoading.value = false
  }
}

async function onSubmit(payload: { decisions: Decisions; note: string }): Promise<boolean> {
  const t = target.value
  if (t === 'project') return true
  try {
    const result = await formulaSettingsApi.apply(props.projectId, props.domain, {
      target: t, slot_keys: props.slotKeys, project_ids: t === 'projects' ? projectIds.value : [],
      decisions: payload.decisions, request_id: requestId || newRequestId(), note: payload.note || undefined,
    })
    if (t === 'candidate') ElMessage.success('已提交为全局候选，管理员审核通过后发布到全部项目')
    else if (t === 'global') ElMessage.success(`已设为全局并发布，${result?.changed_project_count ?? 0} 个项目的有效公式随之更新`)
    else ElMessage.success(`已应用到 ${projectIds.value.length} 个项目`)
    visible.value = false
    emit('done', t)
    return true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '应用失败'))
    return false
  }
}
</script>

<style scoped>
.gt-fas-lead { margin: 0 0 10px; font-size: var(--gt-font-size-sm); }
.gt-fas-options { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.gt-fas-projects { margin-top: 10px; }
.gt-fas-muted { margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
