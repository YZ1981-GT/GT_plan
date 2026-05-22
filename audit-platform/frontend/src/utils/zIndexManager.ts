/**
 * 弹窗 z-index 管理 (UI-3)
 *
 * 使用 Element Plus 内置的 useZIndex 管理弹窗层级，
 * 确保嵌套弹窗（如底稿编辑器→折旧计算→确认删除）z-index 不冲突。
 *
 * 使用方式：
 *   import { getNextZIndex } from '@/utils/zIndexManager'
 *
 *   // 在嵌套弹窗中使用：
 *   <el-dialog :z-index="getNextZIndex()" append-to-body>
 *     ...
 *   </el-dialog>
 *
 * 说明：
 *   Element Plus 默认会自动管理 el-dialog 的 z-index，但在多层嵌套
 *   或动态创建弹窗的场景下，手动指定 z-index 可确保后打开的弹窗
 *   始终在上层。每次调用 getNextZIndex() 都会返回一个递增的值。
 */
import { useZIndex } from 'element-plus'

const { nextZIndex } = useZIndex()

/**
 * 获取下一个可用的 z-index 值
 * 每次调用返回递增值，确保后打开的弹窗始终在上层
 */
export function getNextZIndex(): number {
  return nextZIndex()
}
