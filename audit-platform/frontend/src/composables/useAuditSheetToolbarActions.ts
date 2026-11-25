/**
 * useAuditSheetToolbarActions — 审定表工具栏动作：公式 / 还原 / 发布到试算表
 *
 * 从 GtAuditSheet.vue 抽出（同 spec workpaper-frontend-large-component-split 的拆分方式；
 * 组件回升到 870 行超出 ≤800 守卫后按铁律抽 composable 而非抬上限）。
 *
 * 铁律：行为零变更；props 一律以 getter 传入保持响应式；emit 以回调传入，组件保持事件契约。
 * 🔴 发布门：二次确认（confirmDangerous）与 publish-to-tb 调用必须同文件
 *    （backend/scripts/check/check_tb_publish_confirm_gate.py 判据 A1）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'

export function useAuditSheetToolbarActions(options: {
  readonly: () => boolean
  wpId: () => string
  sheetName: () => string
  htmlData: () => unknown
  emitOpenFormula: (payload: { sheetName: string }) => void
  emitRestore: () => void
}) {
  /**
   * 公式按钮：emit open-formula 携带 sheetName 上下文。
   * 后续接 FormulaEditDialog（由父组件监听打开）。readonly 时不触发。
   */
  function onOpenFormula() {
    if (options.readonly()) return
    options.emitOpenFormula({ sheetName: options.sheetName() })
  }

  /**
   * 还原按钮：二次确认后 emit restore。
   * 本组件 props 驱动、无 render-config 取数能力，由父组件（useWpRenderer）
   * 重新从后端拉取模板默认行并经 htmlData 回流。readonly 时不触发。
   */
  async function onRestore() {
    if (options.readonly()) return
    try {
      await confirmDangerous('还原将丢弃当前编辑，恢复模板默认行，是否继续？', '还原确认')
    } catch {
      // 用户取消
      return
    }
    options.emitRestore()
    ElMessage.success('正在恢复模板默认行…')
  }

  // ─── 发布到试算表（P0-项3：显式确认 + 二次确认，中文）───
  const publishing = ref(false)

  /**
   * 发布审定数到试算表：区别于保存。普通保存不再自动回写 trial_balance，
   * 必须经本操作显式确认（后端再校验发布权限 + 幂等）。
   */
  async function onPublishToTb() {
    if (options.readonly() || publishing.value) return
    try {
      await confirmDangerous(
        '发布后将把本审定表各科目的审定数写入试算表（trial_balance），并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
      )
    } catch {
      return // 用户取消
    }
    publishing.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const resp: any = await api.post(
        `/api/workpapers/${options.wpId()}/audit-determination/publish-to-tb`,
        { sheet_name: options.sheetName(), html_data: options.htmlData() },
      )
      ElMessage.success(resp?.message || '已发布到试算表')
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 403) {
        ElMessage.error('无发布权限（需底稿编辑权）')
      } else if (status === 423) {
        ElMessage.error('项目已被合并锁定，无法发布')
      } else if (status === 400) {
        ElMessage.error(err?.response?.data?.detail || err?.response?.data?.message || '当前 sheet 无可发布的审定数')
      } else {
        ElMessage.error('发布失败，请稍后重试')
      }
    } finally {
      publishing.value = false
    }
  }

  return { onOpenFormula, onRestore, onPublishToTb, publishing }
}
