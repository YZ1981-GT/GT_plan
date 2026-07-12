/**
 * useWorkpaperScaffold — 底稿骨架 composable（一次性 provide 全部全局能力）
 *
 * 在 `<script setup>` 中调用即完成全部 provide，适用于：
 * 1. GtWorkpaperShell.vue 内部（Shell 共享此实现）
 * 2. 存量主入口（已有复杂根结构，不便套壳组件模板）
 *
 * 注入清单（Req 2.1）：
 * - displayPrefs → DisplayPrefs_Key
 * - agingConfig → AgingConfig_Key
 * - 版本链工具栏 → provide('versionToolbar', ...)
 * - 复核 provide → useWorkpaperReviewProvide
 * - AI provide → provide('generateAiText', ...)
 * - jumpToSection / reload → useWorkpaperEntryInjections
 *
 * DEV 环境校验（Req 2.6）：缺失 wpCode/wpId/projectId/year 时 console.error，生产不 throw。
 *
 * 返回 { displayPrefs, agingConfig, versionToolbar, fontStyle } 供模板绑定。
 *
 * Requirements: 2.1, 2.6
 */
import { provide, computed, toRef, type Ref, type ComputedRef } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key, type DisplayPrefsContract } from './displayPrefsKey'
import { useAgingConfig, type UseAgingConfigReturn } from '@/composables/useAgingConfig'
import { useWorkpaperVersionToolbar } from './useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './useWorkpaperEntryInjections'
import http from '@/utils/http'

// ─── AgingConfig InjectionKey ─────────────────────────────────────────────────

import type { InjectionKey } from 'vue'

export const AgingConfig_Key: InjectionKey<UseAgingConfigReturn> = Symbol('agingConfig')

// ─── Options 接口 ─────────────────────────────────────────────────────────────

export interface UseWorkpaperScaffoldOptions {
  wpCode: string | Ref<string>
  wpId: string | Ref<string>
  projectId: string | Ref<string>
  year?: number | Ref<number | undefined>
  agingSubject?: string
  readonly?: boolean | Ref<boolean>
  onJumpToSection?: (sheetLabel: string) => void
  reloadFn?: () => Promise<void> | void
}

// ─── 返回类型 ─────────────────────────────────────────────────────────────────

export interface UseWorkpaperScaffoldReturn {
  displayPrefs: DisplayPrefsContract
  agingConfig: UseAgingConfigReturn
  versionToolbar: ReturnType<typeof useWorkpaperVersionToolbar>
  fontStyle: ComputedRef<Record<string, string>>
}

// ─── 主实现 ───────────────────────────────────────────────────────────────────

export function useWorkpaperScaffold(opts: UseWorkpaperScaffoldOptions): UseWorkpaperScaffoldReturn {
  // ── 规范化 Ref ──────────────────────────────────────────────────────────────
  const wpCodeRef = toRef(opts, 'wpCode') as Ref<string>
  const wpIdRef = toRef(opts, 'wpId') as Ref<string>
  const projectIdRef = toRef(opts, 'projectId') as Ref<string>
  const yearRef = toRef(opts, 'year') as Ref<number | undefined>

  // ── DEV 环境校验（Req 2.6）──────────────────────────────────────────────────
  if (import.meta.env.DEV) {
    const missing: string[] = []
    if (!wpCodeRef.value) missing.push('wpCode')
    if (!wpIdRef.value) missing.push('wpId')
    if (!projectIdRef.value) missing.push('projectId')
    if (yearRef.value === undefined || yearRef.value === null) missing.push('year')
    if (missing.length > 0) {
      console.error(`[GtWorkpaperShell] 缺少必要上下文：${missing.join(', ')}`)
    }
  }

  // ── 1. DisplayPrefs ─────────────────────────────────────────────────────────
  const displayPrefs = useDisplayPrefsStore()
  provide(DisplayPrefs_Key, displayPrefs)

  // ── 2. AgingConfig ──────────────────────────────────────────────────────────
  const agingConfig = useAgingConfig(projectIdRef, opts.agingSubject)
  provide(AgingConfig_Key, agingConfig)

  // ── 3. 版本链工具栏 ────────────────────────────────────────────────────────
  const versionToolbar = useWorkpaperVersionToolbar({
    wpId: wpIdRef,
    projectId: projectIdRef,
  })
  provide('versionToolbar', versionToolbar)

  // ── 4. 复核 provide ────────────────────────────────────────────────────────
  useWorkpaperReviewProvide({
    wpId: wpIdRef,
    projectId: projectIdRef,
  })

  // ── 5. AI provide ──────────────────────────────────────────────────────────
  async function generateAiText(
    section: string,
    context: string,
    existingContent: string,
  ): Promise<string> {
    const id = wpIdRef.value
    if (!id) return ''
    try {
      const res = await http.post(
        `/api/workpapers/${id}/ai/generate-text`,
        {
          section,
          prompt: `请基于 ${wpCodeRef.value} 底稿的以下情况，生成专业、简洁的审计说明/结论：${context}`,
          context,
          existingContent: existingContent || '',
        },
        { _silent: true } as any,
      )
      return (
        res.data?.data?.content ||
        res.data?.content ||
        res.data?.data?.text ||
        res.data?.text ||
        ''
      )
    } catch (err) {
      console.warn(`[GtWorkpaperShell] generateAiText failed:`, err)
      return ''
    }
  }
  provide('generateAiText', generateAiText)

  // ── 6. jumpToSection / reload ──────────────────────────────────────────────
  useWorkpaperEntryInjections({
    onJumpToSection: opts.onJumpToSection ?? (() => {}),
    reloadFn: opts.reloadFn ?? (() => Promise.resolve()),
  })

  // ── fontStyle（供模板 :style 绑定 --wp-font-size） ─────────────────────────
  const fontStyle = computed<Record<string, string>>(() => ({
    '--wp-font-size': displayPrefs.fontConfig?.tableFont ?? '13px',
  }))

  return {
    displayPrefs,
    agingConfig,
    versionToolbar,
    fontStyle,
  }
}

export default useWorkpaperScaffold
