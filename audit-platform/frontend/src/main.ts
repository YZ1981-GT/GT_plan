import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// Register all Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 全局错误处理 — 防止组件错误导致白屏
app.config.errorHandler = (err, instance, info) => {
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

app.mount('#app')
