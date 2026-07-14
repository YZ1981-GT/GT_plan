/**
 * useWorkpaperScaffold — 底稿运行时能力的一次性初始化入口。
 *
 * 若祖先已经提供 WorkpaperRuntimeContext，嵌套 Shell 直接复用该实例；
 * 独立渲染场景才初始化 displayPrefs / aging / version / review / AI 等能力。
 *
 * Requirements: 2.1, 2.4, 2.5
 */
import {
  computed,
  inject,
  isRef,
  provide,
  ref,
  watch,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key, type DisplayPrefsContract } from './displayPrefsKey'
import { useAgingConfig, type UseAgingConfigReturn } from '@/composables/useAgingConfig'
import { useWorkpaperVersionToolbar } from './useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './useWorkpaperEntryInjections'
import http from '@/utils/http'

export const AgingConfig_Key: InjectionKey<UseAgingConfigReturn> = Symbol('agingConfig')

export interface WorkpaperAiTextInput {
  section: string
  context?: Record<string, unknown> | string
  existingContent?: string
  prompt?: string
}

export interface GenerateWorkpaperAiText {
  (input: WorkpaperAiTextInput): Promise<string>
  (
    section: string,
    context?: Record<string, unknown> | string,
    existingContent?: string,
  ): Promise<string>
}

export interface UseWorkpaperScaffoldOptions {
  wpCode: string | Ref<string>
  wpId: string | Ref<string>
  projectId: string | Ref<string>
  year?: number | Ref<number | undefined>
  agingSubject?: string
  readonly?: boolean | Ref<boolean>
  onJumpToSection?: (sheetLabel: string) => void
  reloadFn?: () => Promise<void> | void
  /**
   * 可选的异步上下文就绪标记。Renderer 在 render-config 完成前传 false，
   * 避免把正常加载窗口误报为缺上下文；独立 Shell 不传时仍立即校验。
   */
  contextReady?: boolean | Ref<boolean>
}

export interface WorkpaperRuntimeContext {
  wpId: Ref<string>
  projectId: Ref<string>
  wpCode: Ref<string>
  year: Ref<number | undefined>
  displayPrefs: DisplayPrefsContract
  agingConfig: UseAgingConfigReturn
  version: ReturnType<typeof useWorkpaperVersionToolbar>
  review: ReturnType<typeof useWorkpaperReviewProvide>
  generateAiText: GenerateWorkpaperAiText
  jumpToSection: (sheetLabel: string) => void
  reload: () => Promise<void>
  /** 迁移期兼容既有 Shell 模板。 */
  versionToolbar: ReturnType<typeof useWorkpaperVersionToolbar>
  fontStyle: ComputedRef<Record<string, string>>
}

export type UseWorkpaperScaffoldReturn = WorkpaperRuntimeContext

export const WorkpaperRuntimeContextKey: InjectionKey<WorkpaperRuntimeContext> =
  Symbol('WorkpaperRuntimeContext')

function normalizeRef<T>(value: T | Ref<T>): Ref<T> {
  return isRef(value) ? value : ref(value) as Ref<T>
}

function stringifyContextValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

export function normalizeAiContext(
  context: WorkpaperAiTextInput['context'],
): Record<string, string> {
  if (typeof context === 'string') {
    return context ? { context } : {}
  }
  return Object.fromEntries(
    Object.entries(context ?? {}).map(([key, value]) => [key, stringifyContextValue(value)]),
  )
}

export function extractAiResponseText(payload: unknown): string {
  let current = payload
  for (let depth = 0; depth < 4; depth += 1) {
    if (!current || typeof current !== 'object') return ''
    const envelope = current as Record<string, unknown>
    if (typeof envelope.content === 'string') return envelope.content
    if (typeof envelope.text === 'string') return envelope.text
    current = envelope.data
  }
  return ''
}

export function useWorkpaperScaffold(opts: UseWorkpaperScaffoldOptions): UseWorkpaperScaffoldReturn {
  const ancestorRuntime = inject(WorkpaperRuntimeContextKey, null)
  if (ancestorRuntime) return ancestorRuntime

  const wpCodeRef = normalizeRef(opts.wpCode)
  const wpIdRef = normalizeRef(opts.wpId)
  const projectIdRef = normalizeRef(opts.projectId)
  const yearRef = normalizeRef<number | undefined>(opts.year)
  const contextReadyRef = normalizeRef(opts.contextReady ?? true)

  if (import.meta.env.DEV) {
    let lastMissingSignature = ''
    watch(
      [contextReadyRef, wpCodeRef, wpIdRef, projectIdRef, yearRef],
      ([ready]) => {
        if (!ready) return
        const missing: string[] = []
        if (!wpCodeRef.value) missing.push('wpCode')
        if (!wpIdRef.value) missing.push('wpId')
        if (!projectIdRef.value) missing.push('projectId')
        if (yearRef.value === undefined || yearRef.value === null) missing.push('year')
        const signature = missing.join(', ')
        if (signature && signature !== lastMissingSignature) {
          console.error(`[WorkpaperRuntime] 缺少必要上下文：${signature}`)
        }
        lastMissingSignature = signature
      },
      { immediate: true },
    )
  }

  const displayPrefs = useDisplayPrefsStore()
  provide(DisplayPrefs_Key, displayPrefs)

  const agingConfig = useAgingConfig(projectIdRef, opts.agingSubject)
  provide(AgingConfig_Key, agingConfig)

  const version = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
  provide('versionToolbar', version)

  const review = useWorkpaperReviewProvide({ wpId: wpIdRef, projectId: projectIdRef })

  const generateAiText: GenerateWorkpaperAiText = async (
    inputOrSection: WorkpaperAiTextInput | string,
    legacyContext: Record<string, unknown> | string = {},
    legacyExistingContent = '',
  ): Promise<string> => {
    const input: WorkpaperAiTextInput = typeof inputOrSection === 'string'
      ? {
          section: inputOrSection,
          context: legacyContext,
          existingContent: legacyExistingContent,
        }
      : inputOrSection
    if (!wpIdRef.value) return ''

    const context = normalizeAiContext(input.context)
    const contextSummary = Object.entries(context)
      .map(([key, value]) => `${key}=${value}`)
      .join('；')
    try {
      const response = await http.post(
        `/api/workpapers/${wpIdRef.value}/ai/generate-text`,
        {
          section: input.section,
          prompt: input.prompt
            ?? `请基于 ${wpCodeRef.value} 底稿的以下情况，生成专业、简洁的审计说明/结论：${contextSummary}`,
          context,
          existingContent: input.existingContent ?? '',
        },
        { _silent: true } as any,
      )
      return extractAiResponseText(response.data)
    } catch (error) {
      console.warn('[WorkpaperRuntime] generateAiText failed:', error)
      return ''
    }
  }
  provide('generateAiText', generateAiText)

  const jumpToSection = (sheetLabel: string): void => {
    opts.onJumpToSection?.(sheetLabel)
  }
  const reload = async (): Promise<void> => {
    await opts.reloadFn?.()
  }
  useWorkpaperEntryInjections({ onJumpToSection: jumpToSection, reloadFn: reload })

  const fontStyle = computed<Record<string, string>>(() => ({
    '--wp-font-size': displayPrefs.fontConfig?.tableFont ?? '13px',
  }))

  const runtime: WorkpaperRuntimeContext = {
    wpId: wpIdRef,
    projectId: projectIdRef,
    wpCode: wpCodeRef,
    year: yearRef,
    displayPrefs,
    agingConfig,
    version,
    review,
    generateAiText,
    jumpToSection,
    reload,
    versionToolbar: version,
    fontStyle,
  }
  provide(WorkpaperRuntimeContextKey, runtime)
  return runtime
}

export default useWorkpaperScaffold
