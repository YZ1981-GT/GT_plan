<!--
  保存为公式模板（spec formula-global-settings-sync，design §16.6，R13.1 / R13.2）。
  来源：本项目当前有效定义（默认只取本项目自己的公式 = 适配过 / 来自订阅模板；可选全部有效公式）或全局设置副本。
  共享范围：个人 / 项目组 / 集团（归属当前项目，需本项目编辑权限）/ 事务所（仅管理员）。可见性由服务端判定。
-->
<template>
  <el-dialog v-model="visible" title="保存为公式模板" width="600px" append-to-body destroy-on-close
    data-testid="formula-template-save">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
      <el-form-item label="模板名称" prop="name">
        <el-input v-model="form.name" maxlength="200" placeholder="如：国企单体报表公式（本所口径）" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="2000" />
      </el-form-item>
      <el-form-item label="来源" prop="source">
        <el-radio-group v-model="form.source">
          <el-radio v-if="projectId" value="project">本项目当前公式</el-radio>
          <el-radio value="global">全局设置副本</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.source === 'project'" label="公式范围">
        <el-radio-group v-model="form.slotMode">
          <el-radio value="own">只取本项目改过的（含订阅模板来的）</el-radio>
          <el-radio value="all">本项目全部有效公式</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="公式域" prop="domains">
        <el-checkbox-group v-model="form.domains">
          <el-checkbox v-for="d in domainOptions" :key="d.key" :value="d.key">{{ d.label }}</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="适用范围" prop="applicable_scope">
        <el-select v-model="form.applicable_scope" style="width: 100%">
          <el-option v-for="o in APPLICABLE_SCOPE_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="共享范围" prop="share_scope">
        <el-radio-group v-model="form.share_scope">
          <el-radio v-for="o in shareOptions" :key="o.value" :value="o.value"
            :disabled="['team', 'group'].includes(o.value) && !canEditProject">{{ o.label }}</el-radio>
        </el-radio-group>
        <div class="gt-fts-hint">{{ shareHint }}</div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" data-testid="fts-submit" @click="onSave">保存模板</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  APPLICABLE_SCOPE_OPTIONS, SHARE_SCOPE_OPTIONS, formulaErrorText, formulaSettingsApi,
  type FormulaDomainInfo, type ShareScope, type TemplateDetail,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaTemplateSaveDialog' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 来源 / 所属项目（无项目上下文时只能从全局设置保存，共享范围不含项目组 / 集团） */
  projectId?: string
  defaultDomain?: string
  /** 默认适用范围（如 `soe_standalone`） */
  defaultScope?: string
  /** 当前来源 / 所属项目是否有 edit 权限；只读用户不能创建项目组 / 集团模板。 */
  canEditProject?: boolean
}>(), { projectId: '', defaultDomain: 'report', defaultScope: '', canEditProject: false })

const emit = defineEmits<{ 'update:modelValue': [value: boolean]; saved: [template: TemplateDetail] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()
const saving = ref(false)
const isAdmin = ref(false)
const domainOptions = ref<FormulaDomainInfo[]>([])
const form = reactive({
  name: '', description: '', source: 'project' as 'project' | 'global', slotMode: 'own' as 'own' | 'all',
  domains: [] as string[], applicable_scope: '', share_scope: 'personal' as ShareScope,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  domains: [{ type: 'array', required: true, min: 1, message: '至少选择一个公式域', trigger: 'change' }],
  applicable_scope: [{
    validator: (_r, value, cb) => (form.source === 'global' && !value
      ? cb(new Error('从全局设置保存须选择适用范围')) : cb()),
    trigger: 'change',
  }],
}

const shareOptions = computed(() => SHARE_SCOPE_OPTIONS.filter((o) =>
  (o.value !== 'firm' || isAdmin.value) && ((o.value !== 'team' && o.value !== 'group') || !!props.projectId)))
const shareHint = computed(() => {
  if (props.projectId && !props.canEditProject) return '当前账号只有只读权限，项目组 / 集团模板需要本项目编辑权限'
  return SHARE_SCOPE_OPTIONS.find((o) => o.value === form.share_scope)?.hint || ''
})

watch(() => props.modelValue, async (open) => {
  if (!open) return
  Object.assign(form, {
    name: '', description: '', source: props.projectId ? 'project' : 'global', slotMode: 'own',
    domains: [props.defaultDomain], applicable_scope: props.defaultScope, share_scope: 'personal',
  })
  try {
    const data = await formulaSettingsApi.domains()
    domainOptions.value = (data?.domains || []).filter((d) => d.wired)
    isAdmin.value = !!data?.is_admin
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载公式域失败'))
  }
}, { immediate: true })

/** 「全部有效公式」= 显式列出公式位；「只取本项目改过的」= 不传，由服务端只取本项目自己的定义。 */
async function slotKeysFor(): Promise<Record<string, string[]> | undefined> {
  if (form.source !== 'project' || form.slotMode !== 'all' || !props.projectId) return undefined
  const out: Record<string, string[]> = {}
  for (const d of form.domains) {
    const eff = await formulaSettingsApi.effective(props.projectId, d)
    out[d] = (eff?.slots || []).filter((s) => s.definition && !s.disabled).map((s) => s.slot_key)
  }
  return out
}

async function onSave() {
  if (saving.value || !(await formRef.value?.validate().catch(() => false))) return
  saving.value = true
  try {
    const slotKeys = await slotKeysFor()
    const tpl = await formulaSettingsApi.createTemplate({
      name: form.name.trim(), description: form.description.trim() || null, share_scope: form.share_scope,
      owner_project_id: ['team', 'group'].includes(form.share_scope) ? props.projectId : null,
      applicable_scope: form.applicable_scope, source: form.source,
      source_project_id: form.source === 'project' ? props.projectId : null,
      domains: form.domains, slot_keys: slotKeys,
    })
    const n = Object.values(tpl?.definitions || {}).reduce((acc, list) => acc + list.length, 0)
    ElMessage.success(`模板「${tpl?.name || form.name}」已保存（${n} 条公式）`)
    emit('saved', tpl)
    visible.value = false
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '保存模板失败'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.gt-fts-hint { width: 100%; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
