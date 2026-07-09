/**
 * useS34CrossRef.ts — S34 Bundle 跨底稿引用导航逻辑
 *
 * 职责：
 * 1. isS34InternalRef(value) — 判断引用是否指向 S34 内部底稿（S34-x 或 S34-x-n）
 * 2. getS34TabFromRef(ref) — 提取父 Tab ID（如 S34-16-1 → S34-16）
 * 3. handleS34ChipClick — 路由内部 ref 到 Tab 切换，外部 ref 到全局导航
 *
 * 纯函数导出供 PBT 测试；composable 通过 provide/inject 供 GtAProgramConsole 消费。
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/
 * Task: 8.1
 * Requirements: 6.1, 6.2, 6.3
 */

import { type Ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'
import type { TabDef } from './S34_TAB_CONFIG'

// ─── Pure Functions（可独立测试）───

/**
 * 判断是否为 S34 内部引用
 * 匹配模式：S34-{数字} 或 S34-{数字}-{数字}
 *
 * 例如：
 *   S34-16    → true（Tab 级引用）
 *   S34-16-1  → true（子 sheet 引用）
 *   S34-2-2   → true
 *   D4-24     → false（外部底稿）
 *   B23-1     → false
 *   S34       → false（父底稿本身）
 */
export function isS34InternalRef(value: string): boolean {
  return /^S34-\d+(-\d+)?$/.test(value)
}

/**
 * 从引用中提取父 Tab ID
 * S34-16-1 → S34-16（Tab 级 ID）
 * S34-16   → S34-16（已是 Tab 级）
 * S34-2-2  → S34-2
 *
 * 如果不匹配 S34 模式，返回原字符串。
 */
export function getS34TabFromRef(ref: string): string {
  const match = ref.match(/^(S34-\d+)/)
  return match ? match[1] : ref
}

// ─── Composable ───

export interface UseS34CrossRefOptions {
  /** 可见 Tab 列表 */
  visibleTabs: Ref<TabDef[]>
  /** 当前活动 Tab */
  activeTab: Ref<string>
  /** 项目 ID */
  projectId: Ref<string>
}

/**
 * S34 跨底稿引用导航 composable
 *
 * 返回 handleChipClick 函数，供 GtS34Bundle 绑定到
 * GtAProgramConsole 的 @jump-to-workpaper 事件。
 *
 * 分流逻辑：
 * - 内部 S34-x 引用 → 切换到对应 Tab（如果可见）
 * - 外部引用 → 通过 wp-index-resolve API 跳转到全局底稿
 */
export function useS34CrossRef(options: UseS34CrossRefOptions) {
  const { visibleTabs, activeTab, projectId } = options
  const router = useRouter()
  const route = useRoute()

  /**
   * 处理 chip 点击（来自 GtAProgramConsole @jump-to-workpaper）
   *
   * @param wpCode 目标底稿编码（如 'S34-16-1', 'D4-24', 'B23-1'）
   */
  async function handleChipClick(wpCode: string) {
    if (!wpCode) return

    if (isS34InternalRef(wpCode)) {
      // ─── 内部跳转：切换到对应 Tab ───
      const tabId = getS34TabFromRef(wpCode)
      if (visibleTabs.value.some(t => t.id === tabId)) {
        activeTab.value = tabId
      }
      // 如果 Tab 不可见（底稿不存在），忽略（Req 6.4 灰态由 GtIndexChip 处理）
    } else {
      // ─── 外部跳转：全局底稿导航 ───
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
    isS34InternalRef,
    getS34TabFromRef,
  }
}
