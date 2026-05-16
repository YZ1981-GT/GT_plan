<template>
  <div class="eqcr-memo-editor">
    <div class="eqcr-memo-editor__header">
      <h4>EQCR 独立复核备忘录</h4>
      <div class="eqcr-memo-editor__actions">
        <el-tag v-if="memoStatus" :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
        <!-- R7-S3-04 Task 22：版本历史下拉 -->
        <el-select
          v-if="historyVersions.length > 0"
          v-model="viewingVersion"
          size="small"
          style="width: 140px"
          placeholder="当前版本"
          clearable
          @change="onVersionChange"
        >
          <el-option :value="0" label="当前版本" />
          <el-option
            v-for="h in historyVersions"
            :key="h.version"
            :value="h.version"
            :label="`v${h.version} (${h.saved_at?.slice(0, 10) || '?'})`"
          />
        </el-select>
        <el-button size="small" @click="onGenerate" :loading="generating" round>
          {{ memo ? '重新生成' : '生成备忘录' }}
        </el-button>
        <el-button size="small" @click="onSave" :loading="saving" :disabled="!memo || memoStatus === 'finalized'" round>
          保存
        </el-button>
        <el-button
          size="small"
          type="primary"
          @click="onFinalize"
          :loading="finalizing"
          :disabled="!memo || memoStatus === 'finalized'"
          v-permission="'eqcr:approve'"
          round
        >
          定稿
        </el-button>
        <!-- R8-S2-05：导出 Word -->
        <el-button
          size="small"
          @click="onExportWord"
          :loading="exportingWord"
          :disabled="!memo"
          round
        >
          📄 导出 Word
        </el-button>
      </div>
    </div>

    <el-empty v-if="!memo && !loading" description="备忘录尚未生成，请点击「生成备忘录」">
    </el-empty>

    <div v-if="loading" v-loading="true" style="min-height: 200px"></div>

    <!-- 章节编辑 -->
    <div v-if="memo" class="eqcr-memo-editor__sections">
      <div
        v-for="section in sectionOrder"
        :key="section"
        class="eqcr-memo-section"
      >
        <div class="eqcr-memo-section__title">{{ section }}</div>
        <el-input
          v-model="editableSections[section]"
          type="textarea"
          :rows="4"
          :disabled="memoStatus === 'finalized'"
          :placeholder="`${section}内容...`"
        />
      </div>
    </div>

    <!-- 定稿确认 -->
    <el-dialog v-model="showFinalizeConfirm" title="确认定稿" width="400px" append-to-body>
      <p>定稿后备忘录将不可修改，PDF 版本将在归档包导出时自动生成。确认定稿？</p>
      <template #footer>
        <el-button @click="showFinalizeConfirm = false">取消</el-button>
        <el-button type="primary" @click="doFinalize" :loading="finalizing">确认定稿</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/services/apiProxy'
import { eqcr as P_eqcr } from '@/services/apiPaths'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const finalizing = ref(false)
const exportingWord = ref(false)
const showFinalizeConfirm = ref(false)

const memo = ref<any>(null)
const sectionOrder = ref<string[]>([])
const editableSections = reactive<Record<string, string>>({})

// R7-S3-04 Task 22：版本历史
const historyVersions = ref<Array<{ version: number; saved_at: string; sections_snapshot: Record<string, string> }>>([])
const viewingVersion = ref<number>(0)

function onVersionChange(ver: number) {
  if (ver === 0 || !ver) {
    // 回到当前版本
    if (memo.value?.sections) {
      Object.assign(editableSections, memo.value.sections)
    }
    return
  }
  const hist = historyVersions.value.find(h => h.version === ver)
  if (hist?.sections_snapshot) {
    Object.assign(editableSections, hist.sections_snapshot)
  }
}
const memoStatus = ref<string>('')

const statusLabel = computed(() => {
  if (memoStatus.value === 'finalized') return '已定稿'
  if (memoStatus.value === 'draft') return '草稿'
  return ''
})

const statusTagType = computed(() => {
  if (memoStatus.value === 'finalized') return 'success'
  return 'info'
})

async function loadMemo() {
  loading.value = true
  try {
    const data = await api.get(P_eqcr.memoPreview(props.projectId))
    memo.value = data
    memoStatus.value = data.status || 'draft'
    // 填充可编辑内容
    const sections = data.sections || {}
    for (const [key, val] of Object.entries(sections)) {
      editableSections[key] = val as string
    }
    // 使用默认章节顺序
    sectionOrder.value = Object.keys(sections)
    // R10 Spec C / F8：版本历史走专用端点（最多 5 版，基于 wizard_state.history）
    try {
      const versionsData = await api.get<{ versions: typeof historyVersions.value }>(
        P_eqcr.memoVersions(props.projectId),
      )
      historyVersions.value = versionsData?.versions || data.history || []
    } catch {
      // 端点失败时降级为 preview 响应里的 history
      historyVersions.value = data.history || []
    }
    viewingVersion.value = 0
  } catch (e: any) {
    if (e?.response?.status === 404) {
      memo.value = null
    } else {
      ElMessage.error('加载备忘录失败')
    }
  } finally {
    loading.value = false
  }
}

async function onGenerate() {
  generating.value = true
  try {
    const data = await api.post(P_eqcr.memoGenerate(props.projectId))
    memo.value = data
    memoStatus.value = data.status || 'draft'
    sectionOrder.value = data.section_order || Object.keys(data.sections || {})
    const sections = data.sections || {}
    for (const [key, val] of Object.entries(sections)) {
      editableSections[key] = val as string
    }
    ElMessage.success('备忘录生成完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await api.put(P_eqcr.memoSave(props.projectId), {
      sections: { ...editableSections },
    })
    ElMessage.success('备忘录已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onFinalize() {
  // R10 Spec C / F6：定稿二次确认（用 confirmDangerous 加强文案）
  try {
    const { confirmDangerous } = await import('@/utils/confirm')
    await confirmDangerous(
      '⚠ 定稿后备忘录将不可修改，将自动通知签字合伙人，PDF 版本将在归档包导出时自动生成。\n\n是否继续定稿？',
      'EQCR 备忘录定稿',
    )
  } catch {
    return
  }
  await doFinalize()
}

async function doFinalize() {
  finalizing.value = true
  try {
    await api.post(P_eqcr.memoFinalize(props.projectId))
    memoStatus.value = 'finalized'
    showFinalizeConfirm.value = false
    ElMessage.success('备忘录已定稿，PDF 将在归档时自动生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '定稿失败')
  } finally {
    finalizing.value = false
  }
}

// R8-S2-05：导出 Word
async function onExportWord() {
  if (!props.projectId) return
  exportingWord.value = true
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.get(P_eqcr.memoExport(props.projectId, 'docx'), {
      responseType: 'blob',
    })
    const blob = new Blob([resp.data], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // 文件名由后端 Content-Disposition 提供
    const cd = resp.headers?.['content-disposition'] || ''
    const match = cd.match(/filename="?([^";]+)"?/)
    a.download = match?.[1] ? decodeURIComponent(match[1]) : 'EQCR备忘录.docx'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导出失败')
  } finally {
    exportingWord.value = false
  }
}

onMounted(loadMemo)
</script>

<style scoped>
.eqcr-memo-editor__header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
}
.eqcr-memo-editor__header h4 { margin: 0; font-weight: 600; }
.eqcr-memo-editor__actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.eqcr-memo-editor__sections { display: flex; flex-direction: column; gap: 16px; }
.eqcr-memo-section__title {
  font-size: var(--gt-font-size-sm); font-weight: 600; margin-bottom: 6px;
  color: var(--gt-color-primary, #4b2d77);
  padding-left: 8px;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
</style>
