<template>
  <el-dialog
    v-model="visible"
    title="编辑单元格"
    width="420px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="cell-writeback-form">
      <el-form label-width="80px" size="default">
        <el-form-item label="位置">
          <span class="cell-location">{{ sheetName }} / {{ cellRef }}</span>
        </el-form-item>
        <el-form-item label="当前值">
          <span class="cell-old-value">{{ oldValue ?? '(空)' }}</span>
        </el-form-item>
        <el-form-item label="新值">
          <el-input
            v-model="newValue"
            :placeholder="String(oldValue ?? '')"
            clearable
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
      </el-form>

      <!-- 冲突提示 -->
      <el-alert
        v-if="conflictInfo"
        type="warning"
        :closable="false"
        show-icon
        class="conflict-alert"
      >
        <template #title>
          数据冲突：{{ conflictInfo.latest_editor }} 于
          {{ formatTime(conflictInfo.latest_updated_at) }} 更新了此底稿
        </template>
        <template #default>
          请重新加载数据后再编辑。
        </template>
      </el-alert>

      <!-- 权限不足提示 -->
      <el-alert
        v-if="permissionError"
        type="error"
        :closable="false"
        show-icon
        class="permission-alert"
      >
        <template #title>{{ permissionError }}</template>
      </el-alert>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        v-if="conflictInfo"
        type="warning"
        @click="handleReload"
      >
        重新加载
      </el-button>
      <el-button
        v-else
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="handleSubmit"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  modelValue: boolean
  wpCode: string
  sheetName: string
  cellRef: string
  oldValue: any
  openedAt: string  // ISO 8601
  module?: 'workpaper' | 'report' | 'note' | 'adj' | 'tb'
}

const props = withDefaults(defineProps<Props>(), {
  module: 'workpaper',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'success': [payload: { cellRef: string; newValue: any; updatedAt: string }]
  'reload': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const newValue = ref('')
const submitting = ref(false)
const conflictInfo = ref<{ latest_updated_at: string; latest_editor: string } | null>(null)
const permissionError = ref<string | null>(null)

const canSubmit = computed(() => {
  return newValue.value !== '' && !permissionError.value && !conflictInfo.value
})

function formatTime(iso: string) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  conflictInfo.value = null
  permissionError.value = null

  try {
    const res = await request.post('/api/custom-query/cell-writeback', {
      wp_code: props.wpCode,
      sheet_name: props.sheetName,
      cell_ref: props.cellRef,
      new_value: newValue.value,
      module: props.module,
    }, {
      headers: {
        'X-File-Opened-At': props.openedAt,
      },
    })

    if (res.status === 409 || res.data?.conflict) {
      conflictInfo.value = {
        latest_updated_at: res.data.latest_updated_at,
        latest_editor: res.data.latest_editor,
      }
      return
    }

    ElMessage.success('保存成功')
    emit('success', {
      cellRef: props.cellRef,
      newValue: newValue.value,
      updatedAt: res.data.updated_at,
    })
    visible.value = false
  } catch (err: any) {
    if (err?.response?.status === 409) {
      const data = err.response.data
      conflictInfo.value = {
        latest_updated_at: data.latest_updated_at,
        latest_editor: data.latest_editor,
      }
    } else if (err?.response?.status === 403) {
      const data = err.response.data
      permissionError.value = data?.error === 'no_write_permission'
        ? '您没有此底稿的写入权限'
        : data?.error === 'non_workpaper_source'
          ? '非底稿数据源不支持编辑'
          : '权限不足'
    } else {
      handleApiError(err, '保存单元格')
    }
  } finally {
    submitting.value = false
  }
}

function handleReload() {
  emit('reload')
  handleClose()
}

function handleClose() {
  newValue.value = ''
  conflictInfo.value = null
  permissionError.value = null
  visible.value = false
}
</script>

<style scoped>
.cell-writeback-form {
  padding: 0 8px;
}
.cell-location {
  font-family: monospace;
  color: var(--el-text-color-secondary);
}
.cell-old-value {
  color: var(--el-text-color-regular);
}
.conflict-alert,
.permission-alert {
  margin-top: 12px;
}
</style>
