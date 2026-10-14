<script setup lang="ts">
/**
 * NoteContentTemplateSaveDialog — 把本项目全套附注正文保存为内容模板（Task 47，AC-7.1~7.7）
 *
 * 第二轮复盘 R-22：首版菜单只弹「功能开发中」，Task 47 却标了完成。
 * 流程：名称 / 说明 / 归属 → 服务端预检（质量摘要 + digest；集团归属此时即校验发布权限）→ 集团发布二次确认
 * → 携 digest 保存。预检后改了表单或来源变化（409）都要重新预检；内容未变化 ⇒ 复用已有版本。
 * 客户端只发 {year, name, description, owner_scope, snapshot_digest}：正文与来源信息全部由服务端生成。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  useNoteContentTemplate, type OwnerScope, type SaveTemplateResult, type SnapshotPreviewResult,
} from '@/composables/useNoteContentTemplate'
import { REPORT_SCOPE_LABELS, TEMPLATE_TYPE_LABELS } from './noteTextBatchLabels'

const props = defineProps<{ visible: boolean; projectId: string; year: number }>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; 'saved': [result: SaveTemplateResult] }>()

const tmpl = useNoteContentTemplate({ projectId: computed(() => props.projectId) })
const form = reactive({ name: '', description: '', ownerScope: 'personal' as OwnerScope })
const formRef = ref<FormInstance>()
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请填写模板名称', trigger: 'blur' }],
  ownerScope: [{ required: true, message: '请选择模板归属', trigger: 'change' }],
}
const preview = ref<SnapshotPreviewResult | null>(null)
const result = ref<SaveTemplateResult | null>(null)

const input = computed(() => ({ year: props.year, name: form.name, description: form.description || null,
  ownerScope: form.ownerScope }))
const quality = computed(() => preview.value?.quality_summary ?? {})
const QUALITY_ITEMS: Array<[string, string]> = [
  ['with_content', '有内容'], ['empty', '空白'], ['placeholder', '占位文本'], ['draft', '草稿'], ['stale', '待刷新'],
  ['entity_specific', '企业特有'], ['account_explanation', '报表科目解释'], ['high_risk', '高风险'],
]

// 预检后再改表单 ⇒ 预检结果作废（集团归属要重新校验发布权限）
watch(() => [form.name, form.description, form.ownerScope], () => { preview.value = null; result.value = null })

async function onPreview() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  preview.value = await tmpl.previewSnapshot(input.value)
}

async function onSave() {
  const checked = preview.value
  if (!checked) return
  if (form.ownerScope === 'group') {
    try {
      await ElMessageBox.confirm(
        `将发布为集团模板「${form.name.trim()}」，集团「${checked.group_root_project_name ?? ''}」下所有项目均可查看和引用。确认发布？`,
        '发布集团模板', { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
  }
  const saved = await tmpl.saveTemplate(input.value, checked.snapshot_digest)
  if (!saved) {
    if (tmpl.lastError.value?.code === 'STALE_SNAPSHOT') preview.value = null
    return
  }
  result.value = saved
  ElMessage.success(saved.reused ? `内容未变化，沿用已有版本 v${saved.version_no}` : `已保存为 v${saved.version_no}`)
  emit('saved', saved)
}

function close() {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog :model-value="visible" title="💾 保存为内容模板" width="620px" append-to-body destroy-on-close
    @update:model-value="(v: boolean) => emit('update:visible', v)">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="88px" @submit.prevent>
      <el-form-item label="模板名称" prop="name">
        <el-input v-model="form.name" maxlength="200" show-word-limit placeholder="同名再次保存会生成新版本" />
      </el-form-item>
      <el-form-item label="说明" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="2000" />
      </el-form-item>
      <el-form-item label="归属" prop="ownerScope">
        <el-radio-group v-model="form.ownerScope">
          <el-radio value="personal">个人模板（仅本人可见）</el-radio>
          <el-radio value="group">集团模板（同集团项目可见，需集团经理或合伙人发布）</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <div class="gt-nts-note">模板保存本项目全部附注章节的正文（叙述性与报表科目解释），不含表格数据；保存后的版本不可修改。</div>
    <div v-if="preview" class="gt-nts-preview">
      <div>来源：{{ preview.source_project_name }} {{ preview.source_year }} 年 ·
        {{ TEMPLATE_TYPE_LABELS[preview.template_type] ?? preview.template_type }} ·
        {{ REPORT_SCOPE_LABELS[preview.report_scope] ?? preview.report_scope }} · 共 {{ preview.section_count }} 章</div>
      <div v-if="preview.group_root_project_name">发布范围：集团「{{ preview.group_root_project_name }}」</div>
      <div class="gt-nts-quality">
        <el-tag v-for="[key, label] in QUALITY_ITEMS" :key="key" size="small" :type="key === 'high_risk' ? 'danger' : 'info'">
          {{ label }} {{ quality[key] ?? 0 }}
        </el-tag>
      </div>
    </div>
    <el-alert v-if="result" type="success" :closable="false" show-icon
      :title="result.reused ? `内容未变化，已沿用版本 v${result.version_no}` : `已保存为版本 v${result.version_no}`" />
    <template #footer>
      <el-button @click="close">{{ result ? '关闭' : '取消' }}</el-button>
      <el-button :loading="tmpl.loading.value" @click="onPreview">🔍 预检</el-button>
      <el-button type="primary" :loading="tmpl.saveLoading.value" :disabled="!preview || !!result" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.gt-nts-note { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 12px; }
.gt-nts-preview { font-size: 13px; padding: 10px 12px; border-radius: 4px; background: var(--el-fill-color-lighter); margin-bottom: 12px; }
.gt-nts-quality { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
</style>
