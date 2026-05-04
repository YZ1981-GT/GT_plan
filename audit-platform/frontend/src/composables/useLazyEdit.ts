/**
 * 按需渲染编辑控件 composable
 *
 * 解决大表格（200+行）编辑模式卡顿问题：
 * - 只有当前聚焦的单元格渲染 el-input/el-input-number
 * - 其他单元格显示纯文本（点击后切换为编辑控件）
 * - 失焦后自动切回纯文本
 *
 * 用法：
 *   const { isEditing, startEdit, stopEdit, editingKey } = useLazyEdit()
 *
 *   // 模板中：
 *   <td @click="startEdit(ri, ci)">
 *     <el-input v-if="isEditing(ri, ci)" v-model="row[ci]" @blur="stopEdit" autofocus />
 *     <span v-else>{{ row[ci] }}</span>
 *   </td>
 */
import { ref } from 'vue'

export function useLazyEdit() {
  /** 当前正在编辑的单元格 key（格式：`row_col`） */
  const editingKey = ref('')

  /** 判断某单元格是否正在编辑 */
  function isEditing(rowIdx: number, colIdx: number): boolean {
    return editingKey.value === `${rowIdx}_${colIdx}`
  }

  /** 开始编辑某单元格 */
  function startEdit(rowIdx: number, colIdx: number) {
    editingKey.value = `${rowIdx}_${colIdx}`
  }

  /** 停止编辑（失焦时调用） */
  function stopEdit() {
    editingKey.value = ''
  }

  /** 判断某行是否有正在编辑的单元格 */
  function isRowEditing(rowIdx: number): boolean {
    return editingKey.value.startsWith(`${rowIdx}_`)
  }

  return {
    editingKey,
    isEditing,
    startEdit,
    stopEdit,
    isRowEditing,
  }
}
