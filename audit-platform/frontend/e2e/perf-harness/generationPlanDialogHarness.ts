/**
 * 生成计划弹窗性能夹具入口（spec trim-generation-plan-followup-optimizations R6）。
 *
 * 由 Vite 开发服务按普通 HTML 页面提供（e2e/perf-harness/generation-plan-dialog.html，不进生产构建），
 * 只挂 GenerationPlanDialog；它调用的接口（模板集、生成计划）全部由 Playwright 路由应答，不连后端 / 数据库。
 */
import { createApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import GenerationPlanDialog from '@/components/workpaper/generation/GenerationPlanDialog.vue'

const open = ref(true)
const app = createApp({
  render: () => h(GenerationPlanDialog, {
    modelValue: open.value,
    'onUpdate:modelValue': (value: boolean) => { open.value = value },
    projectId: '00000000-0000-4000-8000-0000000000aa',
    year: 2025,
  }),
})
app.use(createPinia())
app.mount('#app')
;(window as unknown as { __harnessReady: boolean }).__harnessReady = true
