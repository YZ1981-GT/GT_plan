import { ref, watch, type Ref } from 'vue'

/**
 * 重组件首次打开时才挂载；挂载过一次后保持挂载，保留组件内部状态。
 *
 * 适用于 ``defineAsyncComponent`` 弹窗：宿主可无条件声明弹窗，但在用户第一次打开前
 * 不下载分块、不执行弹窗初始化请求。Vue 作用域会在宿主卸载时自动停止 watcher。
 */
export function useMountOnFirstOpen(visible: Readonly<Ref<boolean>>): Readonly<Ref<boolean>> {
  const mounted = ref(Boolean(visible.value))
  watch(visible, (value) => {
    if (value) mounted.value = true
  })
  return mounted
}
