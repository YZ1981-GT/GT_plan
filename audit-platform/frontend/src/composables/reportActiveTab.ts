/**
 * 报表页（ReportView）当前所在页签 —— 模块级单例，给左侧项目菜单判断高亮用。
 *
 * 为什么不读 URL 的 `?tab=`：
 *   DefaultLayout 按 `fullPath` 给页面组件加 key，任何 query 变化都会整页重建、丢失页面状态，
 *   所以 ReportView 里**点页签不回写 URL**。URL 上的 tab 因此只代表「进入时」的页签，
 *   之后会和画面不一致 —— 拿它判断菜单高亮，就会出现「看的是报表分析、亮的是审定报表」。
 *
 * 写入方：仅 ReportView（挂载时与页签变化时写；卸载时清空）。
 * 读取方：ThreeColumnLayout 的 activeProjectSubNav。
 */
import { ref } from 'vue'

/** null = 报表页未挂载（此时菜单高亮回退到按路由判断） */
export const reportActiveTab = ref<string | null>(null)
