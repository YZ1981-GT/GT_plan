<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="400px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
    @close="handleCancel"
  >
    <div class="password-confirm-content">
      <p class="hint-text">请输入您的登录密码以确认此操作</p>

      <el-form :model="formModel" :rules="formRules" @submit.prevent="handleSubmit">
        <el-form-item :error="errorMessage" prop="password">
          <el-input
            ref="passwordInputRef"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            show-password
            :disabled="locked"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
      </el-form>

      <!-- 锁定状态提示 -->
      <div v-if="locked" class="locked-state">
        <el-alert
          type="error"
          :closable="false"
          show-icon
        >
          <template #title>
            账户已锁定，请 {{ lockRemainingText }} 后重试
          </template>
        </el-alert>
      </div>

      <!-- 剩余尝试次数 -->
      <div v-else-if="attemptsRemaining !== null && attemptsRemaining < 5" class="attempts-warning">
        <el-text type="warning" size="small">
          剩余尝试次数：{{ attemptsRemaining }}
        </el-text>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!password || locked"
        @click="handleSubmit"
      >
        确认
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import type { FormRules } from 'element-plus'
import http from '@/utils/http'
import { rules } from '@/utils/formRules'

const props = withDefaults(defineProps<{
  visible: boolean
  title?: string
}>(), {
  title: '安全验证',
})

const emit = defineEmits<{
  (e: 'confirmed', token: string): void
  (e: 'cancelled'): void
  (e: 'update:visible', val: boolean): void
}>()

const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const attemptsRemaining = ref<number | null>(null)
const locked = ref(false)
const lockRemainingText = ref('')
const passwordInputRef = ref<any>(null)

// 表单校验规则（el-form-must-have-rules ESLint 卡点）
const formModel = computed(() => ({ password: password.value }))
const formRules: FormRules = {
  password: [rules.required('密码')],
}

// 打开时聚焦密码输入框
watch(() => props.visible, (val) => {
  if (val) {
    password.value = ''
    errorMessage.value = ''
    attemptsRemaining.value = null
    locked.value = false
    nextTick(() => {
      passwordInputRef.value?.focus()
    })
  }
})

async function handleSubmit() {
  if (!password.value || locked.value || submitting.value) return

  submitting.value = true
  errorMessage.value = ''

  try {
    const resp = await http.post('/api/auth/verify-password', {
      password: password.value,
    })

    const token = resp.data.confirmation_token
    emit('confirmed', token)
    emit('update:visible', false)
  } catch (err: any) {
    const status = err?.response?.status
    const data = err?.response?.data

    if (status === 423) {
      // 账户锁定
      locked.value = true
      const lockedUntil = data?.detail?.locked_until || data?.locked_until
      if (lockedUntil) {
        const until = new Date(lockedUntil)
        const diff = Math.max(0, Math.ceil((until.getTime() - Date.now()) / 60000))
        lockRemainingText.value = `${diff} 分钟`
      } else {
        lockRemainingText.value = '30 分钟'
      }
      errorMessage.value = ''
    } else if (status === 401) {
      // 密码错误
      const detail = data?.detail
      if (typeof detail === 'object') {
        attemptsRemaining.value = detail.attempts_remaining ?? null
        errorMessage.value = `密码错误${attemptsRemaining.value !== null ? `，剩余 ${attemptsRemaining.value} 次尝试` : ''}`
      } else {
        errorMessage.value = '密码错误'
      }
      password.value = ''
    } else {
      errorMessage.value = '验证失败，请稍后重试'
    }
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  emit('cancelled')
  emit('update:visible', false)
}

function handleVisibleChange(val: boolean) {
  emit('update:visible', val)
}
</script>

<style scoped>
.password-confirm-content {
  padding: 0 4px;
}

.hint-text {
  margin: 0 0 16px;
  color: #606266;
  font-size: 14px;
}

.locked-state {
  margin-top: 12px;
}

.attempts-warning {
  margin-top: 8px;
}
</style>
