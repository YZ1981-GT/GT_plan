<template>
  <el-dialog
    v-model="visible"
    title="一键导入附注"
    width="700px"
    :close-on-click-modal="false"
  >
    <!-- Step 1: Upload -->
    <div v-if="step === 'upload'">
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        accept=".xlsx"
        :limit="1"
        :on-change="handleFileChange"
      >
        <el-icon style="font-size: 48px; color: #909399"><i class="el-icon-upload" /></el-icon>
        <div>将 xlsx 文件拖到此处，或<em>点击上传</em></div>
        <template #tip>
          <div style="color: #909399; font-size: 12px">
            仅支持由系统导出的 .xlsx 附注离线编辑包
          </div>
        </template>
      </el-upload>
    </div>

    <!-- Step 2: Diff Preview -->
    <div v-else-if="step === 'preview'">
      <el-alert
        v-if="templateWarning"
        :title="templateWarning"
        type="warning"
        show-icon
        style="margin-bottom: 12px"
      />

      <div style="margin-bottom: 12px; color: #606266">
        匹配结果：{{ matchSummary.matched }} 章节匹配 /
        {{ matchSummary.import_only }} 仅导入包有 /
        {{ matchSummary.system_only }} 仅系统有 /
        {{ matchSummary.total_cell_diffs }} 处字段差异
      </div>

      <el-table :data="diffList" max-height="350" border size="small">
        <el-table-column prop="section_title" label="章节" width="200" />
        <el-table-column prop="match_status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.match_status)" size="small">
              {{ statusLabel(row.match_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="diff_count" label="差异数" width="80" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-select
              v-if="row.match_status === 'matched'"
              v-model="decisions[row.section_id]"
              size="small"
              style="width: 150px"
            >
              <el-option label="覆盖（导入版）" value="overwrite" />
              <el-option label="保留（本地版）" value="keep" />
              <el-option label="选择性合并" value="merge" />
              <el-option label="丢弃" value="discard" />
            </el-select>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- Cell-level diff detail (expandable per section) -->
      <el-collapse v-if="expandedDiffs.length" style="margin-top: 12px">
        <el-collapse-item
          v-for="section in expandedDiffs"
          :key="section.section_id"
          :title="`${section.section_title} (${section.diff_count} 处差异)`"
        >
          <el-table :data="section.diffs" size="small" border max-height="200">
            <el-table-column prop="cell" label="单元格" width="80" />
            <el-table-column label="类型" width="70">
              <template #default="{ row }">
                <el-tag
                  :type="row.type === 'add' ? 'success' : row.type === 'remove' ? 'danger' : 'warning'"
                  size="small"
                >{{ row.type === 'add' ? '新增' : row.type === 'remove' ? '删除' : '修改' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="local" label="本地值" />
            <el-table-column prop="imported" label="导入值" />
            <el-table-column v-if="decisions[section.section_id] === 'merge'" label="导入?" width="70">
              <template #default="{ row }">
                <el-checkbox
                  :model-value="isCellSelected(section.section_id, row.cell)"
                  @change="(v: any) => toggleCellSelection(section.section_id, row.cell, !!v)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- Step 3: Importing -->
    <div v-else-if="step === 'importing'">
      <el-progress :percentage="importProgress" :status="importProgress === 100 ? 'success' : undefined" />
      <p style="text-align: center; margin-top: 12px">正在导入...</p>
    </div>

    <!-- Step 4: Done -->
    <div v-else-if="step === 'done'">
      <el-result icon="success" title="导入完成">
        <template #sub-title>
          {{ importResult.sections_imported }} 章节导入 /
          {{ importResult.sections_kept }} 处保留 /
          {{ importResult.conflicts }} 处冲突
        </template>
      </el-result>
    </div>

    <template #footer>
      <el-button v-if="step !== 'importing'" @click="visible = false">
        {{ step === 'done' ? '关闭' : '取消' }}
      </el-button>
      <el-button
        v-if="step === 'upload'"
        type="primary"
        :disabled="!selectedFile"
        :loading="validating"
        @click="handleValidate"
      >
        校验并预览
      </el-button>
      <el-button
        v-if="step === 'preview'"
        type="primary"
        :loading="importing"
        @click="handleImport"
      >
        确认导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean]; 'imported': [] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

type Step = 'upload' | 'preview' | 'importing' | 'done'
const step = ref<Step>('upload')
const selectedFile = ref<File | null>(null)
const validating = ref(false)
const importing = ref(false)
const importProgress = ref(0)

const templateWarning = ref('')
const matchSummary = ref({ matched: 0, import_only: 0, system_only: 0, total_cell_diffs: 0 })
const diffList = ref<any[]>([])
const decisions = ref<Record<string, string>>({})
const importResult = ref({ sections_imported: 0, sections_kept: 0, conflicts: 0 })
const mergeCells = ref<Record<string, string[]>>({})

// Cell-level diff expansion
const expandedDiffs = computed(() =>
  diffList.value.filter(d => d.match_status === 'matched' && d.diff_count > 0)
)

function isCellSelected(sectionId: string, cellKey: string): boolean {
  return (mergeCells.value[sectionId] || []).includes(cellKey)
}

function toggleCellSelection(sectionId: string, cellKey: string, selected: boolean) {
  if (!mergeCells.value[sectionId]) mergeCells.value[sectionId] = []
  if (selected) {
    mergeCells.value[sectionId].push(cellKey)
  } else {
    mergeCells.value[sectionId] = mergeCells.value[sectionId].filter(k => k !== cellKey)
  }
}

function handleFileChange(file: any) {
  selectedFile.value = file?.raw || null
}

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'primary' | 'danger' {
  if (status === 'matched') return 'primary'
  if (status === 'import_only') return 'warning'
  return 'info'
}

function statusLabel(status: string) {
  if (status === 'matched') return '匹配'
  if (status === 'import_only') return '仅导入'
  return '仅系统'
}

async function handleValidate() {
  if (!selectedFile.value) return
  validating.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const resp: any = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/offline-import/preview`,
      formData,
    )

    if (!resp.validation?.valid) {
      ElMessage.error(resp.validation?.errors?.join('; ') || '文件校验失败')
      return
    }

    templateWarning.value = resp.template_check?.warning || ''
    matchSummary.value = resp.match_summary
    diffList.value = resp.diffs || []

    // Default decisions: overwrite for matched sections with diffs
    decisions.value = {}
    for (const d of diffList.value) {
      if (d.match_status === 'matched') {
        decisions.value[d.section_id] = d.diff_count > 0 ? 'overwrite' : 'keep'
      }
    }

    step.value = 'preview'
  } catch (e: any) {
    ElMessage.error(e?.message || '校验失败')
  } finally {
    validating.value = false
  }
}

async function handleImport() {
  importing.value = true
  step.value = 'importing'
  importProgress.value = 0

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value!)
    formData.append('decisions', JSON.stringify(decisions.value))
    formData.append('merge_cells', JSON.stringify(mergeCells.value))

    // Use SSE for progress tracking
    importProgress.value = 10
    const progressInterval = setInterval(() => {
      if (importProgress.value < 90) {
        importProgress.value += 5
      }
    }, 300)

    const resp: any = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/offline-import/execute`,
      formData,
    )

    clearInterval(progressInterval)
    importProgress.value = 100
    importResult.value = resp
    step.value = 'done'
    emit('imported')
    ElMessage.success(
      `导入完成：${resp.sections_imported} 章节导入 / ${resp.sections_kept} 处保留 / ${resp.conflicts} 处冲突`
    )
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
    step.value = 'preview'
  } finally {
    importing.value = false
  }
}
</script>
