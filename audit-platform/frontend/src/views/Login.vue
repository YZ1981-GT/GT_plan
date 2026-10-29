<template>
  <div class="login-page">
    <!-- 左侧封面区（紫色渐变，占 68%） -->
    <div class="login-cover">
      <div class="login-cover__content gt-fade-in">
        <img src="/logo-citar.png" alt="致同" class="login-cover__logo" />
        <h1 class="login-cover__title">致同税务作业平台</h1>
        <p class="login-cover__desc">面向税务师事务所的税务全流程作业系统</p>
      </div>
      <!-- 装饰圆 -->
      <span class="login-cover__circle login-cover__circle--lg"></span>
      <span class="login-cover__circle login-cover__circle--md"></span>
      <span class="login-cover__circle login-cover__circle--sm"></span>
    </div>

    <!-- 右侧登录区（白底，占 32%） -->
    <div class="login-panel">
      <div class="login-panel__card gt-scale-in">
        <h2 class="login-panel__title">登录</h2>
        <p class="login-panel__subtitle">请输入您的账号信息</p>

        <el-form ref="formRef" :model="form" :rules="rules" label-width="0" @submit.prevent="handleLogin">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password :prefix-icon="Lock" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" native-type="submit" style="width: 100%; height: 44px; font-size: var(--gt-font-size-base)">
              登录
            </el-button>
          </el-form-item>
          <el-form-item>
            <div class="login-panel__footer">
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
    // 登录后统一进项目页。
    // 原先按角色分流到各自仪表盘（auditor→/my/dashboard、partner→/dashboard/partner 等），
    // 税审口径下项目列表是唯一入口，不再做角色分流。
    // redirect query 仍优先：从受保护页面被弹到登录页的用户，登录后应回到原页面而不是项目页。
    const redirect = route.query.redirect as string | undefined
    router.replace(redirect || '/projects')
  } catch (err: any) {
    ElMessage.warning(err?.response?.data?.message ?? '登录失败，请检查用户名和密码')
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
}

/* ── 左侧封面区（68%）── */
.login-cover {
  flex: 0 0 68%;
  max-width: 68%;
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
.login-cover::before {
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
.login-cover::after {
  content: '';
  position: absolute;
  bottom: -20%; left: -10%;
  width: 40%; height: 140%;
  background: radial-gradient(ellipse, rgba(0,148,179,0.12) 0%, transparent 70%);
  pointer-events: none;
}

.login-cover__content {
  text-align: center;
  z-index: 1;
  color: var(--gt-color-text-inverse);
  padding: 0 var(--gt-space-8);
}

.login-cover__logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  filter: brightness(0) invert(1);
  margin-bottom: var(--gt-space-5);
}

.login-cover__title {
  font-size: var(--gt-font-size-3xl);
  font-weight: 700;
  letter-spacing: 2px;
  margin-bottom: var(--gt-space-2);
  text-shadow: 0 2px 12px rgba(0,0,0,0.15);
}

.login-cover__desc {
  font-size: var(--gt-font-size-base);
  opacity: 0.75;
}

/* 装饰圆：三层错位漂浮 */
.login-cover__circle {
  position: absolute;
  display: block;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.04);
  pointer-events: none;
}

.login-cover__circle--lg {
  width: 420px;
  height: 420px;
  top: -110px;
  right: -90px;
  animation: loginCircleFloat 8s ease-in-out infinite;
}

.login-cover__circle--md {
  width: 300px;
  height: 300px;
  bottom: -80px;
  left: -60px;
  animation: loginCircleFloat 10s ease-in-out infinite reverse;
}

.login-cover__circle--sm {
  width: 160px;
  height: 160px;
  top: 18%;
  left: 12%;
  background: rgba(255, 255, 255, 0.03);
  animation: loginCircleFloat 13s ease-in-out infinite;
}

@keyframes loginCircleFloat {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(15px, -15px); }
}

/* ── 右侧登录区（32%）── */
.login-panel {
  flex: 1 1 32%;
  min-width: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-bg-white);
  padding: var(--gt-space-8);
  position: relative;
}
.login-panel::before {
  content: '';
  position: absolute;
  top: 60px; right: 40px;
  width: 120px; height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(75, 45, 119, 0.03) 0%, transparent 70%);
  pointer-events: none;
}
.login-panel::after {
  content: '';
  position: absolute;
  bottom: 80px; left: 30px;
  width: 80px; height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 148, 179, 0.03) 0%, transparent 70%);
  pointer-events: none;
}

.login-panel__card {
  width: 100%;
  max-width: 360px;
}

.login-panel__title {
  font-size: var(--gt-font-size-2xl);
  font-weight: 700;
  background: var(--gt-gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: var(--gt-space-1);
}

.login-panel__subtitle {
  font-size: var(--gt-font-size-base);
  color: var(--gt-color-text-secondary);
  margin-bottom: var(--gt-space-6);
}

.login-panel__footer {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}

/* 窄屏：封面区让位，只保留登录区 */
@media (max-width: 1024px) {
  .login-cover {
    display: none;
  }
  .login-panel {
    flex: 1 1 100%;
  }
}
</style>
