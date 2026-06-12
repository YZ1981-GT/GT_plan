<template>
  <el-dialog
    v-model="visible"
    title="模板复制"
    width="560px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form label-position="top">
      <!-- 复制模式选择 -->
      <el-form-item label="复制模式">
        <el-radio-group v-model="copyMode">
          <el-radio value="single">复制单份底稿</el-radio>
          <el-radio value="cycle">复制整个审计循环</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 单底稿模式 -->
      <template v-if="copyMode === 'single'">
        <el-form-item label="源底稿 ID" required>
          <el-input
            v-model="sourceWpId"
            placeholder="输入源底稿 UUID"
            clearable
          />
        </el-form-item>
      </template>

      <!-- 批量循环模式 -->
      <template v-else>
        <el-form-item label="源项目 ID" required>
          <el-input
            v-model="sourceProjectId"
            placeholder="输入源项目 UUID"
            clearable
          />
        </el-form-item>
        <el-form-item label="审计循环" required>
          <el-select v-model="auditCycle" placeholder="选择审计循环" style="width: 100%">
            <el-option
              v-for="cycle in auditCycles"
              :key="cycle.code"
              :label="`${cycle.code} - ${cycle.name}`"
              :value="cycle.code"
            />
          </el-select>
        </el-form-item>
      </template>

      <!-- 覆盖选项 -->
      <el-form-item>
        <el-checkbox v-model="overwrite">
          覆盖目标已有同编码底稿
        </el-checkbox>
      </el-form-item>

      <!-- 冲突提示 -->
      <el-alert
        v-if="!overwrite"
        type="info"
        :closable="false"
        show-icon
      >
        目标项目已存在同 wp_code 的底稿将被跳过。勾选"覆盖"可强制替换。
      </el-alert>
    </el-form>

    <!-- 结果展示 -->
    <div v-if="copyResults.length > 0" class="wp-template-copy__results">
      <el-divider>复制结果</el-divider>
      <el-table :data="copyResults" size="small" border>
        <el-table-column prop="source_wp_code" label="源底稿编码" width="140" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" />
      </el-table>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ copyResults.length > 0 ? '关闭' : '取消' }}</el-button>
      <el-button
        v-if="copyResults.length === 0"
        type="primary"
        :loading="loading"
        :disabled="!canSubmit"
        @click="handleCopy"
      >
        开始复制
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * WpTemplateCopyDialog — 模板复制弹窗
 *
 * 选择源底稿/源项目+循环，显示目标冲突提示（同 wp_code 已存在）。
 *
 * Requirements: 7.1, 7.4, 7.5
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useWpExportImport } from '@/composables/useWpExportImport'
import type { CopyResult } from '@/composables/useWpExportImport'

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'copied', results: CopyResult[]): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const { templateCopy, loading } = useWpExportImport()

const copyMode = ref<'single' | 'cycle'>('single')
const sourceWpId = ref('')
const sourceProjectId = ref('')
const auditCycle = ref('')
const overwrite = ref(false)
const copyResults = ref<CopyResult[]>([])

const auditCycles = [
  { code: 'A', name: '报表/调整' },
  { code: 'B', name: '控制了解' },
  { code: 'C', name: '控制测试' },
  { code: 'D', name: '销售收入' },
  { code: 'E', name: '货币资金' },
  { code: 'F', name: '采购存货' },
  { code: 'G', name: '投资' },
  { code: 'H', name: '固定资产' },
  { code: 'I', name: '无形资产' },
  { code: 'J', name: '职工薪酬' },
  { code: 'K', name: '管理' },
  { code: 'L', name: '筹资' },
  { code: 'M', name: '股东权益' },
  { code: 'N', name: '税费' },
  { code: 'S', name: '专项' },
]

const canSubmit = computed(() => {
  if (copyMode.value === 'single') return !!sourceWpId.value.trim()
  return !!sourceProjectId.value.trim() && !!auditCycle.value
})

function statusTagType(status: string) {
  switch (status) {
    case 'copied': return 'success'
    case 'overwritten': return 'warning'
    case 'skipped': return 'info'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

function statusLabel(status: string) {
  switch (status) {
    case 'copied': return '已复制'
    case 'overwritten': return '已覆盖'
    case 'skipped': return '已跳过'
    case 'failed': return '失败'
    default: return status
  }
}

async function handleCopy() {
  try {
    const params: Record<string, any> = { overwrite: overwrite.value }
    if (copyMode.value === 'single') {
      params.source_wp_id = sourceWpId.value.trim()
    } else {
      params.source_project_id = sourceProjectId.value.trim()
      params.audit_cycle = auditCycle.value
    }

    const result = await templateCopy(props.projectId, params)
    const results = Array.isArray(result) ? result : [result]
    copyResults.value = results
    emit('copied', results)
    ElMessage.success('模板复制完成')
  } catch (err: any) {
    ElMessage.error(err?.message || '模板复制失败')
  }
}

function handleClose() {
  copyMode.value = 'single'
  sourceWpId.value = ''
  sourceProjectId.value = ''
  auditCycle.value = ''
  overwrite.value = false
  copyResults.value = []
  visible.value = false
}
</script>

<style scoped>
.wp-template-copy__results {
  margin-top: 16px;
}
</style>
