<template>
  <el-dialog
    v-model="visible"
    title="📤 导出填写模板"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="选择工作表">
        <el-checkbox-group v-model="form.sheetNames">
          <el-checkbox
            v-for="name in availableSheets"
            :key="name"
            :label="name"
            :value="name"
          >
            {{ name }}
          </el-checkbox>
        </el-checkbox-group>
        <el-button link type="primary" @click="selectAll" style="margin-top: 4px">
          全选
        </el-button>
      </el-form-item>

      <el-form-item label="加密选项">
        <el-switch v-model="form.enableEncrypt" />
        <span style="margin-left: 8px; color: #909399; font-size: 12px">
          启用 AES 加密保护文件
        </span>
      </el-form-item>

      <el-form-item v-if="form.enableEncrypt" label="加密密码">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          placeholder="请输入加密密码"
        />
      </el-form-item>

      <el-form-item label="截止日期">
        <el-date-picker
          v-model="form.deadline"
          type="date"
          placeholder="选择截止日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
        />
      </el-form-item>

      <el-form-item label="联系人">
        <el-input v-model="form.contactName" placeholder="姓名" style="margin-bottom: 4px" />
        <el-input v-model="form.contactEmail" placeholder="邮箱" style="margin-bottom: 4px" />
        <el-input v-model="form.contactPhone" placeholder="电话" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        :loading="exporting"
        :disabled="form.sheetNames.length === 0"
        @click="handleExport"
      >
        导出模板
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiProxy } from '@/services/apiProxy'

interface Props {
  modelValue: boolean
  wpId: string
  availableSheets: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = ref(props.modelValue)
const exporting = ref(false)

const form = reactive({
  sheetNames: [] as string[],
  enableEncrypt: false,
  password: '',
  deadline: '',
  contactName: '',
  contactEmail: '',
  contactPhone: '',
})

function selectAll() {
  form.sheetNames = [...props.availableSheets]
}

function handleClose() {
  emit('update:modelValue', false)
}

async function handleExport() {
  if (form.enableEncrypt && !form.password) {
    ElMessage.warning('请输入加密密码')
    return
  }

  exporting.value = true
  try {
    const payload: Record<string, unknown> = {
      sheet_names: form.sheetNames.length === props.availableSheets.length ? null : form.sheetNames,
      deadline: form.deadline,
      contact_name: form.contactName,
      contact_email: form.contactEmail,
      contact_phone: form.contactPhone,
    }
    if (form.enableEncrypt && form.password) {
      payload.password = form.password
    }

    const response = await apiProxy.post(
      `/api/workpapers/${props.wpId}/offline/export-template`,
      payload,
      { responseType: 'blob' }
    )

    // Download the file
    const blob = new Blob([response as unknown as BlobPart], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `wp_template_${props.wpId}.xlsx`
    a.click()
    URL.revokeObjectURL(url)

    ElMessage.success('模板导出成功')
    handleClose()
  } catch (e: unknown) {
    ElMessage.error('导出失败: ' + (e instanceof Error ? e.message : '未知错误'))
  } finally {
    exporting.value = false
  }
}

// Sync visible with modelValue
import { watch } from 'vue'
watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { if (!val) emit('update:modelValue', false) })
</script>
