<template>
  <el-card class="gt-user-settings" shadow="never">
    <template #header>
      <span class="gt-card-title">用户偏好设置</span>
    </template>
    <el-form label-width="120px" size="default">
      <el-form-item label="界面语言">
        <LanguageSwitcher :user-id="userId" />
      </el-form-item>
      <el-form-item label="默认会计准则">
        <StandardSelector v-model="defaultStandard" @change="onStandardChange" style="width: 300px" />
      </el-form-item>
      <el-form-item label="默认审计类型">
        <AuditTypeSelector v-model="defaultAuditType" @change="onAuditTypeChange" style="width: 300px" />
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import LanguageSwitcher from './LanguageSwitcher.vue'
import StandardSelector from './StandardSelector.vue'
import AuditTypeSelector from './AuditTypeSelector.vue'

defineProps<{ userId?: string }>()

const defaultStandard = ref(localStorage.getItem('gt-default-standard') || '')
const defaultAuditType = ref(localStorage.getItem('gt-default-audit-type') || '')

function onStandardChange(id: string) {
  localStorage.setItem('gt-default-standard', id)
  ElMessage.success('默认会计准则已更新')
}

function onAuditTypeChange(type: string) {
  localStorage.setItem('gt-default-audit-type', type)
  ElMessage.success('默认审计类型已更新')
}

onMounted(() => {})
</script>

<style scoped>
.gt-user-settings { max-width: 600px; }
.gt-card-title { font-weight: 600; font-size: var(--gt-font-size-lg); }
</style>
