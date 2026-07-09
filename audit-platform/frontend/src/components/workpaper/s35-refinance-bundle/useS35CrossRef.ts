/**
 * useS35CrossRef.ts — S35 Bundle 跨底稿引用导航逻辑
 *
 * 职责：
 * 1. isS35InternalRef(value) — 判断引用是否指向 S35 内部底稿（S35-x 或 S35-x-1）
 * 2. getS35TabFromRef(ref) — 提取父 Tab ID（如 S35-1-1 → S35-1）
 * 3. handleChipClick — 路由内部 ref 到 Tab 切换，外部 ref 到全局导航
 *
 * 纯函数导出供 PBT 测试；composable 通过 provide/inject 供 GtAProgramConsole 消费。
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/
 * Task: 5.1
 * Requirements: 7.1, 7.2, 7.3, 7.4
 */

import { type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'
import type { TabDef } from '../composables/useS35BundleState'

// ─── Pure Functions（可独立测试）───

/**
 * 判断是否为 S35 内部引用
 * 匹配模式：S35-{数字} 或 S35-{数字}-{数字}
 *
 * 例如：
 *   S35-1    → true（Tab 级引用）
 *   S35-1-1  → true（子 sheet 引用）
 *   S35-3-1  → true
 *   D4-24    → false（外部底稿）
 *   S35      → false（父底稿本身）
 */
export function isS35InternalRef(value: string): boolean {
  return /^S35-\d+(-\d+)?$/.test(value)
}

/**
 * 从引用中提取父 Tab ID
 * S35-1-1 → S35-1（Tab 级 ID）
 * S35-1   → S35-1（已是 Tab 级）
 * S35-3-1 → S35-3
 *
 * 如果不匹配 S35 模式，返回原字符串。
 */
export function getS35TabFromRef(ref: string): string {
  const match = ref.match(/^(S35-\d+)/)
  return match ? match[1] : ref
}

// ─── Composable ───

export interface UseS35CrossRefOptions {
  /** 可见 Tab 列表 */
  visibleTabs: Ref<TabDef[]>
  /** 当前活动 Tab */
  activeTab: Ref<string>
  /** 项目 ID */
  projectId: Ref<string>
}

/**
 * S35 跨底稿引用导航 composable
 *
 * 返回 handleChipClick 函数，供 GtS35Bundle 绑定到
 * GtAProgramConsole 的 @jump-to-workpaper 事件。
 *
 * 分流逻辑（Req 7.2, 7.3）：
 * - 内部 S35-x 引用 → 切换到对应 Tab（如果可见）
 * - 外部引用 → 通过 wp-index-resolve API 跳转到全局底稿
 */
export function useS35CrossRef(options: UseS35CrossRefOptions) {
  const { visibleTabs, activeTab, projectId } = options
  const router = useRouter()

  /**
   * 处理 chip 点击（来自 GtAProgramConsole @jump-to-workpaper）
   *
   * @param wpCode 目标底稿编码（如 'S35-1-1', 'D4-24', 'B23-1'）
   */
  async function handleChipClick(wpCode: string) {
    if (!wpCode) return

    if (isS35InternalRef(wpCode)) {
      // ─── 内部跳转：切换到对应 Tab（Req 7.2）───
      const tabId = getS35TabFromRef(wpCode)
      if (visibleTabs.value.some(t => t.id === tabId)) {
        activeTab.value = tabId
      }
      // 如果 Tab 不可见（底稿不存在），忽略（Req 7.4 灰态由 GtIndexChip 处理）
    } else {
      // ─── 外部跳转：全局底稿导航（Req 7.3）───
      const pid = projectId.value
      if (!pid) return

      try {
        const res = await api.get<{ exists: boolean; wp_id?: string }>('/api/wp-index-resolve', {
          params: { ref: wpCode, project_id: pid },
        })
        if (res?.wp_id) {
          router.push({ path: `/projects/${pid}/workpapers/${res.wp_id}/edit` })
        } else if (res?.exists === false) {
          ElMessage.warning(`底稿 ${wpCode} 尚未生成`)
        } else {
          // wp_id 未返回但 exists，降级搜索
          router.push({ path: `/projects/${pid}/workpapers`, query: { search: wpCode } })
        }
      } catch {
        ElMessage.warning(`跳转 ${wpCode} 失败，请手动查找`)
      }
    }
  }

  return {
    handleChipClick,
    isS35InternalRef,
    getS35TabFromRef,
  }
}
