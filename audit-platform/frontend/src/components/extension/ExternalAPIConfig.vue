<template>
  <el-card shadow="never" class="gt-api-config">
    <template #header><span class="gt-card-title">外部API配置</span></template>
    <el-form ref="formRef" :model="form" label-width="100px" size="default">
      <el-form-item label="API端点">
        <el-input v-model="form.endpoint" placeholder="https://api.example.com/v1" />
      </el-form-item>
      <el-form-item label="超时时间">
        <el-input-number v-model="form.timeout" :min="1" :max="300" :step="5" />
        <span style="margin-left: 8px; color: var(--gt-color-text-secondary); font-size: 13px">秒</span>
      </el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="form.api_key" type="password" show-password placeholder="输入API密钥" />
      </el-form-item>
      <el-form-item label="请求头">
        <el-input v-model="form.headers" type="textarea" :rows="3" placeholder='{"Authorization": "Bearer xxx"}' />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="onSave" :loading="saving">保存</el-button>
        <el-button @click="testConnection" :loading="testing">测试连接</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const saving = ref(false)
const testing = ref(false)

const form = ref({
  endpoint: '',
  timeout: 30,
  api_key: '',
  headers: '',
})

function onSave() {
  saving.value = true
  setTimeout(() => {
    ElMessage.success('配置已保存')
    saving.value = false
  }, 500)
}

function testConnection() {
  testing.value = true
  setTimeout(() => {
    ElMessage.info('连接测试功能开发中')
    testing.value = false
  }, 1000)
}
</script>

<style scoped>
.gt-api-config { border-radius: var(--gt-radius-md); max-width: 600px; }
.gt-card-title { font-weight: 600; }
</style>
