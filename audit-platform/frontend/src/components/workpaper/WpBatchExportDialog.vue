<template>
  <el-dialog
    v-model="visible"
    title="批量导出底稿"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form label-position="top">
      <el-form-item label="选择审计循环" required>
        <el-checkbox-group v-model="selectedCycles">
          <el-checkbox
            v-for="cycle in auditCycles"
            :key="cycle.code"
            :label="cycle.code"
            :value="cycle.code"
          >
            {{ cycle.code }} - {{ cycle.name }}
          </el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <el-form-item label="状态过滤（可选）">
        <el-select
          v-model="selectedStatuses"
          multiple
          clearable
          placeholder="不限（导出全部状态）"
          style="width: 100%"
        >
          <el-option label="草稿" value="draft" />
          <el-option label="复核中" value="in_review" />
          <el-option label="已批准" value="approved" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="selectedCycles.length === 0"
        @click="handleExport"
      >
        导出 ZIP
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * WpBatchExportDialog — 批量导出配置弹窗
 *
 * 选择审计循环（多选）+ 状态过滤，调用 batch-export-enhanced 端点下载 ZIP。
 *
 * Requirements: 2.1, 2.6
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useWpExportImport } from '@/composables/useWpExportImport'

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'exported'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const { batchExportEnhanced, loading } = useWpExportImport()

// 审计循环选项
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

const selectedCycles = ref<string[]>([])
const selectedStatuses = ref<string[]>([])

async function handleExport() {
  if (selectedCycles.value.length === 0) {
    ElMessage.warning('请至少选择一个审计循环')
    return
  }
  try {
    await batchExportEnhanced(
      props.projectId,
      selectedCycles.value,
      selectedStatuses.value.length > 0 ? selectedStatuses.value : undefined,
    )
    ElMessage.success('批量导出成功')
    emit('exported')
    handleClose()
  } catch (err: any) {
    ElMessage.error(err?.message || '批量导出失败')
  }
}

function handleClose() {
  visible.value = false
}
</script>
