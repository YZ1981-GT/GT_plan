<template>
  <div class="gt-login-page">
    <!-- 左侧品牌区 -->
    <div class="gt-login-brand">
      <div class="brand-content gt-fade-in">
        <img src="/gt-logo.png" alt="Grant Thornton 致同" class="brand-logo" />
        <h1 class="brand-title">致同审计作业平台</h1>
        <p class="brand-desc">面向会计师事务所的审计全流程作业系统</p>
      </div>
      <!-- 装饰圆 -->
      <div class="brand-circle brand-circle--1"></div>
      <div class="brand-circle brand-circle--2"></div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="gt-login-form-wrap">
      <div class="gt-login-card gt-scale-in">
        <h2 class="login-title">登录</h2>
        <p class="login-subtitle">请输入您的账号信息</p>

        <el-form ref="formRef" :model="form" :rules="rules" label-width="0" @submit.prevent="handleLogin">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password :prefix-icon="Lock" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" native-type="submit" style="width: 100%; height: 44px; font-size: 15px">
              登录
            </el-button>
          </el-form-item>
          <el-form-item>
            <div class="login-footer">
              <span>还没有账号？</span>
              <el-link type="primary" @click="$router.push('/register')">去注册</el-link>
            </div>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    // R7-S1-04: 优先 redirect query，否则按角色跳转到对应首页
    const ROLE_HOME: Record<string, string> = {
      auditor: '/my/dashboard',
      manager: '/dashboard/manager',
      partner: '/dashboard/partner',
      qc: '/qc/inspections',
      eqcr: '/eqcr/workbench',
      admin: '/',
    }
    const redirect = route.query.redirect as string | undefined
    const target = redirect || ROLE_HOME[authStore.user?.role ?? ''] || '/'
    router.replace(target)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message ?? '登录失败')
  } finally { loading.value = false }
}
</script>

<style scoped>
.gt-login-page {
  display: flex;
  min-height: 100vh;
}

/* ── 左侧品牌 ── */
.gt-login-brand {
  flex: 1;
  background: var(--gt-gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  /* 网格纹理 */
  background-image:
    var(--gt-gradient-primary),
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 100% 100%, 30px 30px, 30px 30px;
}
.gt-login-brand::before {
  content: '';
  position: absolute;
  top: -30%; right: -15%;
  width: 50%; height: 160%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.08) 0%, transparent 70%);
  pointer-events: none;
  animation: loginGlow 10s ease-in-out infinite;
}
@keyframes loginGlow {
  0%, 100% { opacity: 0.5; transform: translate(0, 0); }
  50% { opacity: 1; transform: translate(-30px, 20px); }
}
.gt-login-brand::after {
  content: '';
  position: absolute;
  bottom: -20%; left: -10%;
  width: 40%; height: 140%;
  background: radial-gradient(ellipse, rgba(0,148,179,0.12) 0%, transparent 70%);
  pointer-events: none;
}

.brand-content {
  text-align: center;
  z-index: 1;
  color: #fff;
}

.brand-logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  filter: brightness(0) invert(1);
  margin-bottom: var(--gt-space-5);
}

.brand-title {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 2px;
  margin-bottom: var(--gt-space-2);
  text-shadow: 0 2px 12px rgba(0,0,0,0.15);
}

.brand-desc {
  font-size: 15px;
  opacity: 0.75;
}

.brand-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.04);
}

.brand-circle--1 {
  width: 400px;
  height: 400px;
  top: -100px;
  right: -100px;
  animation: floatCircle 8s ease-in-out infinite;
}

.brand-circle--2 {
  width: 300px;
  height: 300px;
  bottom: -80px;
  left: -60px;
  animation: floatCircle 10s ease-in-out infinite reverse;
}

@keyframes floatCircle {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(15px, -15px); }
}

/* ── 右侧表单 ── */
.gt-login-form-wrap {
  width: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-bg-white);
  padding: var(--gt-space-8);
  position: relative;
}
.gt-login-form-wrap::before {
  content: '';
  position: absolute;
  top: 60px; right: 40px;
  width: 120px; height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(75, 45, 119, 0.03) 0%, transparent 70%);
  pointer-events: none;
}
.gt-login-form-wrap::after {
  content: '';
  position: absolute;
  bottom: 80px; left: 30px;
  width: 80px; height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 148, 179, 0.03) 0%, transparent 70%);
  pointer-events: none;
}

.gt-login-card {
  width: 100%;
  max-width: 360px;
}

.login-title {
  font-size: var(--gt-font-size-2xl);
  font-weight: 700;
  background: var(--gt-gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: var(--gt-space-1);
}

.login-subtitle {
  font-size: var(--gt-font-size-base);
  color: var(--gt-color-text-secondary);
  margin-bottom: var(--gt-space-6);
}

.login-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
</style>
