<template>
  <!-- A.5.12: 准则切换器（国企版 ⇆ 上市版） -->
  <div class="note-template-switch">
    <el-radio-group
      v-model="currentType"
      size="small"
      @change="onTemplateChange"
    >
      <el-radio-button value="soe">国企版</el-radio-button>
      <el-radio-button value="listed">上市版</el-radio-button>
    </el-radio-group>

    <!-- A.5.13: 切换前确认弹窗 -->
    <el-dialog
      v-model="showPreview"
      title="准则切换预览"
      width="500px"
      :close-on-click-modal="false"
    >
      <div v-if="previewData" class="preview-content">
        <p>即将切换：{{ previewData.from }} → {{ previewData.to }}</p>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="共有章节">
            {{ previewData.common_sections }} 个 — 数据保留
          </el-descriptions-item>
          <el-descriptions-item label="将归档章节">
            {{ previewData.to_archive_sections }} 个 — 数据归档 30 天
          </el-descriptions-item>
          <el-descriptions-item label="将新增章节">
            {{ previewData.to_create_sections }} 个 — 创建空章节
          </el-descriptions-item>
          <el-descriptions-item label="格式调整章节">
            {{ previewData.format_changed_sections }} 个
          </el-descriptions-item>
          <el-descriptions-item label="用户编辑保留">
            {{ previewData.user_edits_preserved }} 处
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="previewData.warnings?.length"
          type="warning"
          :title="previewData.warnings.join('; ')"
          show-icon
          style="margin-top: 12px"
        />
      </div>
      <template #footer>
        <el-button @click="cancelSwitch">取消</el-button>
        <el-button type="primary" :loading="switching" @click="confirmSwitch">
          继续切换
        </el-button>
      </template>
    </el-dialog>

    <!-- A.5.14: 切换中进度 -->
    <el-dialog v-model="showProgress" title="切换中..." width="400px" :closable="false">
      <el-progress :percentage="switchProgress" />
      <p style="text-align: center; margin-top: 8px; color: #909399">正在切换准则版本...</p>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { useNoteTemplateConversion } from '@/composables/useNoteTemplateConversion'

interface Props {
  projectId: string
  year: number
  templateType: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:templateType': [val: string]
  'switched': []
}>()

const currentType = computed({
  get: () => props.templateType,
  set: (v) => emit('update:templateType', v),
})

const showPreview = ref(false)
const showProgress = ref(false)
const switching = ref(false)
const switchProgress = ref(0)
const previewData = ref<any>(null)
const pendingTarget = ref('')

async function onTemplateChange(val: string | number | boolean | undefined) {
  const newType = String(val ?? '')
  if (!newType || newType === props.templateType) return
  pendingTarget.value = newType
  // Revert UI immediately, wait for confirmation
  currentType.value = props.templateType

  try {
    const resp: any = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/template-conversion/preview`,
      { target_type: newType }
    )
    previewData.value = {
      ...resp,
      from: props.templateType === 'soe' ? '国企版' : '上市版',
      to: newType === 'soe' ? '国企版' : '上市版',
    }
    showPreview.value = true
  } catch (e: any) {
    handleApiError(e, '预览')
  }
}

function cancelSwitch() {
  showPreview.value = false
  pendingTarget.value = ''
}

async function confirmSwitch() {
  switching.value = true
  showPreview.value = false
  showProgress.value = true
  switchProgress.value = 30

  try {
    await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/template-conversion/execute`,
      { target_type: pendingTarget.value, confirmed: true }
    )
    switchProgress.value = 100

    setTimeout(() => {
      showProgress.value = false
      currentType.value = pendingTarget.value
      emit('switched')
      const preserved = previewData.value?.user_edits_preserved || 0
      ElMessage.success(`已切换为${pendingTarget.value === 'soe' ? '国企' : '上市'}版，保留 ${preserved} 处用户编辑`)
    }, 500)
  } catch (e: any) {
    showProgress.value = false
    handleApiError(e, '切换')
  } finally {
    switching.value = false
  }
}
</script>

<style scoped>
.note-template-switch {
  display: inline-flex;
  align-items: center;
}
.preview-content p {
  margin-bottom: 12px;
  font-weight: 500;
}
</style>
