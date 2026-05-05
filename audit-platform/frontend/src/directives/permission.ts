import type { Directive, DirectiveBinding } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ROLE_PERMISSIONS } from '@/composables/usePermission'

/**
 * v-permission 指令 — 按钮级权限控制
 *
 * 用法：
 *   v-permission="'adjustment:delete'"       — 单权限
 *   v-permission="['project:edit', 'admin']"  — 任一匹配即显示
 *
 * 无权限时设置 display:none 隐藏元素
 *
 * 修复 P1.1：不再在指令里调用 usePermission()（每次调用都创建新的 computed，造成内存泄漏）。
 * 改为直接访问 authStore.user?.role，并使用导出的 ROLE_PERMISSIONS 常量做权限判断。
 */
function checkPermissionDirect(el: HTMLElement, binding: DirectiveBinding) {
  const authStore = useAuthStore()
  const role = authStore.user?.role ?? ''
  const value = binding.value

  let hasPermission = false
  if (!role) {
    hasPermission = false
  } else if (role === 'admin') {
    // admin 拥有所有权限，但 'admin' 权限字符串仅 admin 角色通过
    hasPermission = true
  } else if (Array.isArray(value)) {
    // 任一权限匹配即显示；'admin' 权限字符串非 admin 角色不通过
    hasPermission = value.some(
      (p) => p !== 'admin' && (ROLE_PERMISSIONS[role]?.includes(p) ?? false),
    )
  } else if (typeof value === 'string') {
    if (value === 'admin') {
      hasPermission = false // 非 admin 角色不通过
    } else {
      hasPermission = ROLE_PERMISSIONS[role]?.includes(value) ?? false
    }
  }

  // 恢复显示（处理权限动态变化的场景）
  el.style.display = hasPermission ? '' : 'none'
}

export const vPermission: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    checkPermissionDirect(el, binding)
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    checkPermissionDirect(el, binding)
  },
}
