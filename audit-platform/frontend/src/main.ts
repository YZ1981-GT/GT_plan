import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
// Element Plus 样式：按需导入由 unplugin-vue-components 自动处理，
// 但仍需全局引入 base 样式（CSS 变量、字体等）
import 'element-plus/dist/index.css'

// dayjs 全局中文
dayjs.locale('zh-cn')
// Element Plus 暗色主题 CSS 变量（配合 html.dark class 自动生效）
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'nprogress/nprogress.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'
import { initWebVitals } from './utils/monitor'
import { queryClient } from './utils/queryClient'
import { vPermission } from './directives/permission'
import { registerServiceWorker } from './composables/useOfflineCache'
import vTabWheel from './directives/vTabWheel'
import { installCrossWpEventBridge } from './utils/crossWpEventBridge'
import { clearOnUpgrade } from './utils/aiChatCacheCleanup'
import { gridPlugin } from './components/grid/plugin'
import http from './utils/http'
import { installPushKeptNotice } from './utils/disclosureSyncPushNotice'
import { startSessionHandoff } from './utils/crossWindowAuth'
import { advanceRequestIdentityEpoch } from './services/requestIdentityEpoch'
import { claimClientInstanceId } from './utils/clientInstance'

// 跨底稿事件传输桥（P0）：统一 window CustomEvent ⇄ mitt eventBus，
// 归一 substantive:adjudicated / disclosure:note-text-updated payload。
// 必须在任何组件挂载前安装，确保所有生产者/消费者互通。
installCrossWpEventBridge()

// 底稿披露同步：公式推送写过的格保持试算表审定数时提示一次（spec note-pull-followup-closure R3）
installPushKeptNotice(http)

// Task 10: 首次升级时清理遗留 AI 聊天敏感缓存（doc_ai_chat_*）
clearOnUpgrade()

// 多窗口：认领本标签页的窗口编号（「复制标签页」沿用了原标签页的编号时换新号，编辑锁才能区分两个窗口）
// spec: workpaper-multi-window-lock-gaps R1；取锁前 useEditingLock 会等认领结果，这里不阻塞挂载
void claimClientInstanceId()

const app = createApp(App)

app.use(createPinia())
app.use(VueQueryPlugin, { queryClient })

// 多窗口：新窗口启动时若 sessionStorage 无 token，通过 BroadcastChannel 向已有窗口请求会话
// spec: multi-window-ledger-workbench Phase 2 Task 12
// 场景：用户手动在地址栏输入独立查账 URL，浏览器新建标签页没有 opener 复制的 sessionStorage
// 🔴 必须在 app.use(router) 之前发起：路由守卫判「未登录」前等它结束（原先并行，首个导航先被送去登录页）
startSessionHandoff(async (session) => {
  // 新窗口取得的是另一逻辑会话的起点，先作废本页可能已有的匿名/旧订阅者。
  advanceRequestIdentityEpoch()
  sessionStorage.setItem('token', session.token)
  sessionStorage.setItem('refreshToken', session.refreshToken)
  if (session.user) sessionStorage.setItem('user', JSON.stringify(session.user))
  // Pinia store 在 app.use(createPinia()) 后可用，手动同步
  const { useAuthStore } = await import('./stores/auth')
  const authStore = useAuthStore()
  authStore.token = session.token
  authStore.refreshToken = session.refreshToken
  authStore.user = session.user
})

app.use(router)
// 表格按 Excel 方式选中 / 编辑（spec excel-style-table-editing）
app.use(gridPlugin)

// 注册全局指令
app.directive('permission', vPermission)
app.directive('tab-wheel', vTabWheel)

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

// 离线缓存 Service Worker 注册（Phase 8 Task 5.2）
registerServiceWorker()

app.mount('#app')