/**
 * useEditMode — 查看/编辑模式切换 composable
 *
 * 提供统一的编辑模式管理：
 * - isEditing：当前是否处于编辑模式
 * - isDirty：是否有未保存的变更
 * - enterEdit()：进入编辑模式
 * - exitEdit(force?)：退出编辑模式（有未保存变更时弹窗确认）
 * - markDirty()：标记有未保存变更
 * - clearDirty()：清除脏状态（保存后调用）
 * - 自动注册 onBeforeRouteLeave 守卫，离开页面时提示未保存变更
 *
 * 用法：
 *   const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()
 *
 * @module composables/useEditMode
 * @see R3.4
 */
import { ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'

export interface UseEditModeOptions {
  /** 初始编辑状态，默认 false */
  initialEditing?: boolean
  /** 是否注册路由离开守卫，默认 true；子组件调用时传 false 跳过，避免控制台警告 */
  guardRoute?: boolean
}

export function useEditMode(options?: UseEditModeOptions) {
  const isEditing = ref(options?.initialEditing ?? false)
  const isDirty = ref(false)

  /** 进入编辑模式 */
  function enterEdit() {
    isEditing.value = true
  }

  /**
   * 退出编辑模式
   * @param force 是否强制退出（跳过未保存确认），默认 false
   * @returns 是否成功退出
   */
  async function exitEdit(force = false): Promise<boolean> {
    if (!force && isDirty.value) {
      try {
        await ElMessageBox.confirm(
          '当前有未保存的修改，确定放弃吗？',
          '未保存提示',
          {
            confirmButtonText: '放弃修改',
            cancelButtonText: '继续编辑',
            type: 'warning',
          }
        )
      } catch {
        // 用户点击"继续编辑"
        return false
      }
    }
    isEditing.value = false
    isDirty.value = false
    return true
  }

  /** 标记有未保存变更 */
  function markDirty() {
    isDirty.value = true
  }

  /** 清除脏状态（保存成功后调用） */
  function clearDirty() {
    isDirty.value = false
  }

  // 路由离开守卫：有未保存变更时提示用户（子组件传 guardRoute: false 跳过）
  if (options?.guardRoute !== false) {
    onBeforeRouteLeave(async () => {
      if (isEditing.value && isDirty.value) {
        try {
          await ElMessageBox.confirm(
            '当前有未保存的修改，离开将丢失所有更改。确定离开吗？',
            '未保存提示',
            {
              confirmButtonText: '确定离开',
              cancelButtonText: '留在此页',
              type: 'warning',
            }
          )
          return true
        } catch {
          return false
        }
      }
      return true
    })
  }

  return {
    isEditing,
    isDirty,
    enterEdit,
    exitEdit,
    markDirty,
    clearDirty,
  }
}
