/**
 * 表格交互插件（spec excel-style-table-editing ADR-1 / design §10）
 *
 * - 全局 mixin：每个 ElTable 实例挂载时接上内核、卸载时拆掉（不包装 ElTable，模板 ref 仍是原实例）；
 * - 待写盘：切换在线编辑前先提交表格里正在编辑的格；
 * - 样式：选区 / 编辑态 / 显示文本。
 */
import { effectScope, type App } from 'vue'
import { registerPendingFlusher } from '@/components/workpaper/sync/pendingWrites'
import { commitAllGridEdits, markGridInstalled } from './GridKernel'
import { kernelForElTable } from './gridRegistry'
import '@/styles/gt-grid.css'

interface MixinThis {
  $options?: { name?: string }
  $?: Parameters<typeof kernelForElTable>[0]
  $el?: unknown
}

export const gridTableMixin = {
  mounted(this: MixinThis) {
    if (this.$options?.name !== 'ElTable' || !this.$) return
    if (this.$el instanceof HTMLElement) kernelForElTable(this.$).attach(this.$el)
  },
  beforeUnmount(this: MixinThis) {
    if (this.$options?.name !== 'ElTable' || !this.$) return
    kernelForElTable(this.$).detach()
  },
}

let flusherScope: ReturnType<typeof effectScope> | null = null

export const gridPlugin = {
  install(app: App): void {
    app.mixin(gridTableMixin)
    markGridInstalled()
    if (!flusherScope) {
      flusherScope = effectScope(true)
      flusherScope.run(() => registerPendingFlusher(() => commitAllGridEdits()))
    }
  },
}

export default gridPlugin
