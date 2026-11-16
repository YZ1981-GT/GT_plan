/**
 * 自定义模板 publication 管理（list / commit-visibility / instantiate）。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20
 *
 * 后端已就绪的三个端点：
 *   GET  /api/custom-template-ingestion/publications
 *   POST /api/custom-template-ingestion/publications/commit-visibility
 *   POST /api/custom-template-ingestion/publications/instantiate
 *
 * 🔴 本 composable 只做「展示 + 触发」，不伪造状态：
 *   - `runtimeDiscoverable` 一律取服务端返回值，前端不按 state 自己推；
 *   - instantiate 成功后必须真拿到 `workbookInstanceId` 才算成功，
 *     服务端返回 `instantiated: false` 时按失败处理（而不是当成功）。
 */
import { computed, ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

const BASE = '/api/custom-template-ingestion'

export interface TemplatePublication {
  publicationKey: string
  candidateId: string
  state: string
  artifactDigest: string
  authorityRef: string
  reason: string | null
  runtimeDiscoverable: boolean
  createdAt: string
  updatedAt: string
}

export interface CommitVisibilityResult {
  publicationKey: string
  visibilityState: string
  state: string
  runtimeDiscoverable: boolean
  requiredConsumers?: string[]
  idempotent: boolean
}

export interface InstantiateEntry {
  entryId: string
  sheetUid: string
  wpCode: string
  componentType: string
  projectionMode: string
}

export interface InstantiateResult {
  publicationKey: string
  workbookInstanceId: string
  projectId: string
  pinned: boolean
  instantiated: boolean
  sheetCount: number
  entries: InstantiateEntry[]
  contextFingerprint?: string
  workbookGeneration?: number
}

export interface SheetMappingInput {
  sheetUid: string
  wpCode: string
  componentType: string
  projectionMode: string
  sheetCode?: string | null
  manifestVersion?: string | null
}

/** 后端必需 consumer（与 finalize_saga.REQUIRED_FINALIZE_CONSUMERS 逐值一致）。 */
export const REQUIRED_FINALIZE_CONSUMERS = [
  'guidance',
  'renderer',
  'public_shell',
  'entry_namespace',
] as const

export const PUBLICATION_STATE_LABELS: Record<string, string> = {
  PENDING_VISIBILITY: '待确认可见性',
  ACTIVE: '已发布（可实例化）',
  WITHDRAWN: '已撤回',
  SECURITY_REVOKED: '安全撤销',
  FAILED: '已失败',
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return fallback
}

export function useTemplatePublications() {
  const publications: Ref<TemplatePublication[]> = ref([])
  const loading = ref(false)
  const lastError = ref<string | null>(null)

  const pending = computed(() =>
    publications.value.filter((p) => p.state === 'PENDING_VISIBILITY'),
  )
  const active = computed(() =>
    publications.value.filter((p) => p.state === 'ACTIVE'),
  )

  async function load(state?: string): Promise<void> {
    loading.value = true
    lastError.value = null
    try {
      const response = await api.get<{ publications: TemplatePublication[] }>(
        `${BASE}/publications`,
        { params: state ? { state } : undefined, _silent: true },
      )
      publications.value = response?.publications ?? []
    } catch (error) {
      lastError.value = apiErrorMessage(error, '加载 publication 列表失败')
      publications.value = []
    } finally {
      loading.value = false
    }
  }

  /** 提交 ACK 并推进可见性。只有四个 consumer 全 ACCEPTED 才会 ACTIVE。 */
  async function commitVisibility(
    publicationKey: string,
    acks: { consumer: string; verdict: 'ACCEPTED' | 'REJECTED'; reasonCodes?: string[] }[],
  ): Promise<CommitVisibilityResult | null> {
    lastError.value = null
    try {
      const response = await api.post<CommitVisibilityResult>(
        `${BASE}/publications/commit-visibility`,
        {
          publicationKey,
          acks: acks.map((a) => ({
            consumer: a.consumer,
            consumerVersion: '1.0.0',
            verdict: a.verdict,
            reasonCodes: a.reasonCodes ?? [],
          })),
        },
        { _silent: true },
      )
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '推进可见性失败')
      return null
    }
  }

  /** 一键把四个 consumer 全标 ACCEPTED（仅用于演示 / 内部验收，真实场景应逐个收集）。 */
  async function acceptAllConsumers(publicationKey: string): Promise<CommitVisibilityResult | null> {
    return commitVisibility(
      publicationKey,
      REQUIRED_FINALIZE_CONSUMERS.map((c) => ({ consumer: c, verdict: 'ACCEPTED' as const })),
    )
  }

  /** 实例化：需要调用方给出 sheet 映射（服务端按 preflight 报告校验白名单）。 */
  async function instantiate(
    publicationKey: string,
    workingPaperId: string,
    sheets: SheetMappingInput[],
  ): Promise<InstantiateResult | null> {
    lastError.value = null
    if (!sheets.length) {
      lastError.value = '至少需要一个 sheet 映射'
      return null
    }
    try {
      const response = await api.post<InstantiateResult>(
        `${BASE}/publications/instantiate`,
        { publicationKey, workingPaperId, sheets },
        { _silent: true },
      )
      // 🔴 服务端说没真实例化就不是成功 —— 不能把 pinned 当完成。
      if (!response?.instantiated || !response?.workbookInstanceId) {
        lastError.value = response?.instantiated === false
          ? '服务端未完成实例化（pinned 不等于已建册）'
          : '实例化回执缺少 workbookInstanceId'
        return null
      }
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '实例化失败')
      return null
    }
  }

  return {
    publications,
    pending,
    active,
    loading,
    lastError,
    load,
    commitVisibility,
    acceptAllConsumers,
    instantiate,
  }
}
