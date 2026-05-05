import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
// Element Plus 样式：按需导入由 unplugin-vue-components 自动处理，
// 但仍需全局引入 base 样式（CSS 变量、字体等）
import 'element-plus/dist/index.css'
import 'nprogress/nprogress.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'
import { initWebVitals } from './utils/monitor'
import { queryClient } from './utils/queryClient'
import { vPermission } from './directives/permission'

const app = createApp(App)

app.use(createPinia())
app.use(VueQueryPlugin, { queryClient })
app.use(router)

// 注册全局指令
app.directive('permission', vPermission)

// 图标由 unplugin-vue-components 自动按需注册，无需全量注册（P1.3 修复）

// 全局错误处理 — 防止组件错误导致白屏
app.config.errorHandler = (err, _instance, info) => {
  console.error('[全局错误]', err, info)
  ElMessage.error('页面发生错误，请刷新重试')
}

// 未捕获的 Promise 错误
window.addEventListener('unhandledrejection', (event) => {
  console.error('[未捕获Promise]', event.reason)
  // 不弹窗（http.ts 拦截器已处理 API 错误），只记录
})

// 路由错误捕获
router.onError((error) => {
  console.error('[路由错误]', error)
  ElMessage.error('页面加载失败，请刷新重试')
})

// 性能监控
initWebVitals()

app.mount('#app')