/**
 * useRegisterRelatedParty — 反向回流：各循环疑似关联方一键登记到 B19 关联方清单
 *
 * 场景：审计师在各循环关联方检查表（D2-6 / D6-5 / D7-6 / F1-6 / F4-6 / K1-11 等）
 * 识别出**管理层未披露**的疑似关联方时，一键登记到 related_party_registry
 * （B19 关联方清单 = 全平台各循环关联方核对的唯一真源），无需回到 B19 手工录入。
 *
 * 复用后端已存在的 eqcr CRUD：POST /api/eqcr/projects/{pid}/related-parties
 * 关系类型枚举对齐后端 VALID_RELATION_TYPES（见 b19Presets.RELATION_TYPE_OPTIONS）。
 *
 * 用法（任意循环组件）：
 *   const { registerSuspected } = useRegisterRelatedParty(projectId)
 *   await registerSuspected('XX贸易公司', { relationType: 'other', source: 'D2-6 关联方检查' })
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { RELATION_TYPE_OPTIONS } from './b19Presets'

export function useRegisterRelatedParty(projectId: string) {
  const rpBase = `/api/eqcr/projects/${projectId}/related-parties`

  /** 直接登记（已知名称与关系类型） */
  async function register(payload: {
    name: string
    relation_type?: string
    is_controlled_by_same_party?: boolean
    detail?: Record<string, string>
  }): Promise<boolean> {
    const name = (payload.name || '').trim()
    if (!name) {
      ElMessage.warning('关联方名称不能为空')
      return false
    }
    try {
      await api.post(rpBase, {
        name,
        relation_type: payload.relation_type || 'other',
        is_controlled_by_same_party: !!payload.is_controlled_by_same_party,
        detail: payload.detail || null,
      })
      ElMessage.success(`已登记「${name}」到 B19 关联方清单`)
      return true
    } catch (e: any) {
      // 409 唯一约束 = 已存在
      if (e?.response?.status === 409) {
        ElMessage.info(`「${name}」已在关联方清单中`)
        return false
      }
      // http 拦截器已提示其它错误
      return false
    }
  }

  /**
   * 交互式登记：弹窗让审计师确认名称、选择关系类型后登记。
   * @param defaultName 预填名称（如从明细行带入的交易对手）
   * @param source 来源标注（如 "D2-6 关联方检查"），写入 detail.source 便于追溯
   */
  async function registerSuspected(
    defaultName = '',
    opts: { source?: string; defaultRelationType?: string } = {},
  ): Promise<boolean> {
    let name = defaultName
    try {
      const r = await ElMessageBox.prompt('请确认要登记到 B19 关联方清单的名称：', '登记疑似关联方', {
        confirmButtonText: '登记',
        cancelButtonText: '取消',
        inputValue: defaultName,
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      name = (r.value || '').trim()
    } catch {
      return false // 用户取消
    }
    const detail = opts.source ? { source: opts.source } : undefined
    return register({ name, relation_type: opts.defaultRelationType || 'other', detail })
  }

  return { register, registerSuspected, RELATION_TYPE_OPTIONS }
}
