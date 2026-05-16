<template>
  <el-dialog append-to-body
    v-model="visible"
    title="登记函证结果"
    width="600px"
    @close="handleClose"
  >
    <el-form :model="form" label-width="130px">
      <el-form-item label="函证ID">
        <el-input :model-value="confirmationId" readonly />
      </el-form-item>
      <el-form-item label="函证状态" required>
        <el-select v-model="form.confirmation_status" placeholder="请选择状态" style="width: 100%">
          <el-option label="待发送" value="PENDING" />
          <el-option label="已发送" value="SENT" />
          <el-option label="已回函" value="RECEIVED" />
          <el-option label="异常" value="EXCEPTION" />
        </el-select>
      </el-form-item>
      <el-form-item label="确认金额">
        <el-input-number v-model="form.confirmed_amount" :min="0" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item label="差异金额">
        <el-input-number v-model="form.difference_amount" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item label="差异原因">
        <el-input v-model="form.difference_reason" type="textarea" :rows="3" placeholder="说明差异原因" />
      </el-form-item>
      <el-form-item label="替代程序">
        <el-input v-model="form.alternative_procedures" type="textarea" :rows="3" placeholder="执行的替代审计程序" />
      </el-form-item>
      <el-form-item label="附件上传">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="5"
          action="#"
        >
          <template #trigger>
            <el-button size="small" type="primary">选择文件</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">支持 PDF、Word、图片格式，最多5个文件</div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmationApi } from '@/services/collaborationApi'

const props = defineProps<{
  modelValue: boolean
  confirmationId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'saved'): void
}>()

const projectId = 'current-project-id'

const visible = ref(false)
const uploadRef = ref()

watch(
  () => props.modelValue,
  (val) => { visible.value = val },
)

watch(
  () => visible.value,
  (val) => { emit('update:modelValue', val) },
)

const form = ref({
  confirmation_status: 'PENDING',
  confirmed_amount: 0,
  difference_amount: 0,
  difference_reason: '',
  alternative_procedures: '',
})

function handleClose() {
  visible.value = false
}

async function handleSave() {
  try {
    await confirmationApi.recordResult(projectId, props.confirmationId, form.value)
    ElMessage.success('结果已保存')
    emit('saved')
    handleClose()
  } catch {
    ElMessage.error('保存失败')
  }
}
</script>

<style scoped>
.el-upload__tip {
  margin-top: 4px;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}
</style>
