<template>
  <div class="gt-ledger-standalone">
    <!-- 精简顶栏 -->
    <header class="gt-ledger-standalone__topbar">
      <div class="gt-ledger-standalone__left">
        <span class="gt-ledger-standalone__logo">📊</span>
        <span class="gt-ledger-standalone__title">查账工作台</span>
        <el-tag v-if="projectName" type="warning" effect="dark" size="small" style="margin-left: 8px">
          {{ projectName }}
        </el-tag>
      </div>
      <div class="gt-ledger-standalone__right">
        <el-button size="small" text style="color: rgba(255,255,255,0.85)" @click="goToMainWindow">
          ↗ 回到主窗口
        </el-button>
        <el-button size="small" text style="color: rgba(255,255,255,0.6)" @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </header>

    <!-- 主内容：复用查账组件 -->
    <main class="gt-ledger-standalone__main">
      <LedgerPenetration />
    </main>
  </div>
</template>

<script setup lang="ts">
/**
 * LedgerStandalonePage — 独立查账窗口壳页面
 *
 * 顶层路由 /ledger-workbench/:projectId，不嵌套 DefaultLayout。
 * 参考 AIChatView.vue 的 standalone 模式。
 *
 * spec: multi-window-ledger-workbench Phase 1 Task 1
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { api } from '@/services/apiProxy'
import LedgerPenetration from '@/views/LedgerPenetration.vue'

const route = useRoute()
const authStore = useAuthStore()
const projectStore = useProjectStore()

const projectId = computed(() => route.params.projectId as string)
const projectName = ref('')

onMounted(async () => {
  // 同步项目上下文
  projectStore.syncFromRoute(route as any)

  // 加载项目名称
  if (projectId.value) {
    try {
      const data = await api.get(`/api/projects/${projectId.value}`)
      projectName.value = data?.name || data?.client_name || ''
    } catch {
      projectName.value = ''
    }
  }
})

function goToMainWindow() {
  // 尝试聚焦 opener，如果不存在则打开新标签
  if (window.opener && !window.opener.closed) {
    window.opener.focus()
  } else {
    window.open(`/projects/${projectId.value}/ledger`, '_blank')
  }
}

function handleLogout() {
  authStore.logout()
  window.location.href = '/login'
}
</script>

<style scoped>
.gt-ledger-standalone {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
  background: var(--gt-color-bg, #f5f5f7);
}

.gt-ledger-standalone__topbar {
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  flex-shrink: 0;
  font-size: 14px;
}

.gt-ledger-standalone__left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.gt-ledger-standalone__logo {
  font-size: 18px;
}

.gt-ledger-standalone__title {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.gt-ledger-standalone__right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.gt-ledger-standalone__main {
  flex: 1;
  overflow: auto;
  min-height: 0;
}
</style>
