import type { Directive, DirectiveBinding } from 'vue'
import { usePermission } from '@/composables/usePermission'

/**
 * v-permission 指令 — 按钮级权限控制
 *
 * 用法：
 *   v-permission="'adjustment:delete'"       — 单权限
 *   v-permission="['project:edit', 'admin']"  — 任一匹配即显示
 *
 * 无权限时设置 display:none 隐藏元素
 */
function checkPermission(el: HTMLElement, binding: DirectiveBinding) {
  const { can, canAny } = usePermission()
  const value = binding.value

  let hasPermission = false
  if (Array.isArray(value)) {
    hasPermission = canAny(...value)
  } else if (typeof value === 'string') {
    hasPermission = can(value)
  }

  if (!hasPermission) {
    el.style.display = 'none'
  } else {
    // 恢复显示（处理权限动态变化的场景）
    el.style.display = ''
  }
}

export const vPermission: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    checkPermission(el, binding)
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    checkPermission(el, binding)
  },
}
