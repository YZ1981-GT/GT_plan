<template>
  <!-- 🔴 根元素不要再写 id="app"：`main.ts` 挂的就是 index.html 里的 `<div id="app">`，
       Vue 只替换挂载点的**内容**，所以这里再写一遍会在 DOM 里留下两个同 id 的元素
       （外层带 `data-v-app`、内层是本组件根）。重复 id 是非法 HTML，且会让按 `#app`
       取节点的工具拿到歧义结果 —— 2026-11-06 真实项目只读走查（spec
       trim-generation-plan-followup-optimizations R5.5）就因此在 Playwright strict mode
       上失败（`locator('#app') resolved to 2 elements`）。无任何 CSS / JS 依赖内层这个 id
       （现算全仓 `#app` 只有挂载、e2e 夹具自己的页面和这条走查）。
       守卫：`src/__tests__/appRootHasNoDuplicateId.spec.ts`。 -->
  <div>
    <!-- Element Plus 内置文案（空表格、分页、日期面板、下拉无匹配等）统一走中文语言包；
         未配置时默认英文（空表格显示「No Data」）。ElMessageBox 等命令式组件经全局配置同样生效。 -->
    <ElConfigProvider :locale="zhCn">
      <router-view />
    </ElConfigProvider>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAuthStore } from '@/stores/auth'
import { useDictStore } from '@/stores/dict'

const authStore = useAuthStore()
const dictStore = useDictStore()

// 页面刷新后自动恢复用户信息（token 从 localStorage 恢复，但 user 对象需要重新获取）
onMounted(async () => {
  if (authStore.isAuthenticated && !authStore.user) {
    try {
      await authStore.fetchUserProfile()
    } catch {
      // token 过期或无效，不阻断页面加载（路由守卫会处理跳转登录）
    }
  }

  // 加载枚举字典（sessionStorage 缓存）
  // 在 fetchUserProfile 之后检查认证状态，防止 token 失效后仍尝试加载字典
  // await 确保字典就绪后再渲染状态标签（避免首帧闪英文原始值）
  if (authStore.isAuthenticated) {
    await dictStore.load()
  }
})
</script>
