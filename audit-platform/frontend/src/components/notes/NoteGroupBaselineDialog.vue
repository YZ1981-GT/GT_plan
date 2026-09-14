<template>
  <!-- C.3.6: 集团基线对话框 + 版本对比 + diff -->
  <el-dialog
    v-model="visible"
    title="集团附注模板基线"
    width="800px"
    :close-on-click-modal="false"
  >
    <!-- 使用说明 -->
    <el-alert type="info" :closable="true" show-icon style="margin-bottom: 16px;">
      <template #title>
        <span style="font-weight: 600;">使用说明</span>
      </template>
      <template #default>
        <div style="font-size: 12px; line-height: 1.8; color: var(--gt-color-text-secondary);">
          <p style="margin: 0;">集团基线用于统一管理同集团下各子企业的附注模板结构。</p>
          <ul style="margin: 4px 0 0; padding-left: 16px;">
            <li><b>应用基线</b>：从已有基线导入章节结构到当前项目，本地已修改的章节不会被覆盖</li>
            <li><b>保存为基线</b>：将当前项目的附注章节结构保存为基线，供其他子企业项目引用</li>
            <li><b>版本对比</b>：对比两个基线版本之间的章节差异（新增/删除/修改）</li>
          </ul>
        </div>
      </template>
    </el-alert>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 应用基线 -->
      <el-tab-pane label="应用基线" name="apply">
        <el-form label-width="100px">
          <el-form-item label="选择基线">
            <el-select v-model="selectedBaselineId" placeholder="选择要应用的基线" style="width: 100%" @change="onBaselineSelect">
              <el-option
                v-for="b in baselines"
                :key="b.id"
                :label="`${b.name} ${b.version}`"
                :value="b.id"
              >
                <span>{{ b.name }}</span>
                <el-tag size="small" type="info" style="margin-left: 8px">{{ b.version }}</el-tag>
                <el-tag size="small" :type="b.template_type === 'soe' ? 'primary' : 'warning'" style="margin-left: 4px">
                  {{ b.template_type === 'soe' ? '国企' : '上市' }}
                </el-tag>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item v-if="diffPreview" label="影响预览">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="新增章节">{{ diffPreview.added }}</el-descriptions-item>
              <el-descriptions-item label="修改章节">{{ diffPreview.modified }}</el-descriptions-item>
              <el-descriptions-item label="本地保留">{{ diffPreview.local_override }}</el-descriptions-item>
              <el-descriptions-item label="无变化">{{ diffPreview.unchanged }}</el-descriptions-item>
            </el-descriptions>
          </el-form-item>
        </el-form>

        <div style="margin-top: 12px; text-align: right">
          <el-button :loading="applying" type="primary" :disabled="!selectedBaselineId" @click="handleApply">
            应用基线
          </el-button>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 保存为基线 -->
      <el-tab-pane label="保存为基线" name="save">
        <el-form label-width="100px">
          <el-form-item label="基线名称" required>
            <el-input v-model="saveForm.name" placeholder="例如: 集团2025年基线" />
          </el-form-item>
          <el-form-item label="模板类型">
            <el-radio-group v-model="saveForm.template_type">
              <el-radio value="soe">国企版</el-radio>
              <el-radio value="listed">上市版</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div style="margin-top: 12px; text-align: right">
          <el-button :loading="saving" type="primary" :disabled="!saveForm.name" @click="handleSave">
            保存为基线
          </el-button>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 版本对比 -->
      <el-tab-pane label="版本对比" name="diff">
        <el-form label-width="100px">
          <el-form-item label="版本 A">
            <el-select v-model="diffA" placeholder="选择版本 A" style="width: 100%">
              <el-option v-for="b in baselines" :key="b.id" :label="`${b.name} ${b.version}`" :value="b.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="版本 B">
            <el-select v-model="diffB" placeholder="选择版本 B" style="width: 100%">
              <el-option v-for="b in baselines" :key="b.id" :label="`${b.name} ${b.version}`" :value="b.id" />
            </el-select>
          </el-form-item>
          <el-button :loading="diffing" :disabled="!diffA || !diffB || diffA === diffB" @click="computeDiff">
            对比
          </el-button>
        </el-form>

        <el-table v-if="diffData.length" :data="diffData" border size="small" max-height="300" style="margin-top: 12px">
          <el-table-column prop="section_id" label="章节 ID" width="180" />
          <el-table-column prop="section_title" label="标题" />
          <el-table-column label="变更" width="100">
            <template #default="{ row }">
              <el-tag :type="row.change_type === 'added' ? 'success' : row.change_type === 'removed' ? 'danger' : 'warning'" size="small">
                {{ row.change_type === 'added' ? '新增' : row.change_type === 'removed' ? '删除' : '修改' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean]; 'applied': [] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeTab = ref('apply')
const baselines = ref<any[]>([])
const selectedBaselineId = ref('')
const diffPreview = ref<any>(null)
const applying = ref(false)
const saving = ref(false)
const diffing = ref(false)

const saveForm = ref({ name: '', template_type: 'soe' })
const diffA = ref('')
const diffB = ref('')
const diffData = ref<any[]>([])

watch(visible, (v) => {
  if (v) loadBaselines()
})

async function loadBaselines() {
  try {
    const resp: any = await api.get('/api/group-note-baselines', { _silent: true } as any)
    baselines.value = resp || []
  } catch {
    baselines.value = []
  }
}

async function onBaselineSelect(baselineId: string) {
  if (!baselineId) {
    diffPreview.value = null
    return
  }
  try {
    const resp: any = await api.get(
      `/api/group-note-baselines/${baselineId}/preview-diff`,
      { params: { project_id: props.projectId, year: props.year } }
    )
    diffPreview.value = resp
  } catch {
    diffPreview.value = null
  }
}

async function handleApply() {
  try {
    await ElMessageBox.confirm('确定要应用此基线？本地修改将保留，但其他章节会被基线覆盖', '确认应用', { type: 'warning' })
  } catch {
    return
  }
  applying.value = true
  try {
    await api.post(
      `/api/projects/${props.projectId}/apply-group-baseline`,
      { baseline_id: selectedBaselineId.value, year: props.year }
    )
    ElMessage.success('基线应用完成')
    emit('applied')
    visible.value = false
  } catch (e: any) {
    handleApiError(e, '应用')
  } finally {
    applying.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await api.post('/api/group-note-baselines', {
      name: saveForm.value.name,
      project_id: props.projectId,
      year: props.year,
      template_type: saveForm.value.template_type,
    })
    ElMessage.success('基线保存成功')
    saveForm.value = { name: '', template_type: 'soe' }
    loadBaselines()
  } catch (e: any) {
    handleApiError(e, '保存')
  } finally {
    saving.value = false
  }
}

async function computeDiff() {
  diffing.value = true
  try {
    const resp: any = await api.get(
      `/api/group-note-baselines/diff`,
      { params: { baseline_a: diffA.value, baseline_b: diffB.value } }
    )
    diffData.value = resp?.diffs || []
  } catch (e: any) {
    handleApiError(e, '对比')
  } finally {
    diffing.value = false
  }
}
</script>
