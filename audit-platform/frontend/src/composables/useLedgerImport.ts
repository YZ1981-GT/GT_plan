/**
 * Composable for ledger import v2 state management.
 * Manages the full import lifecycle: files → detect → mapping → progress → errors.
 * Includes sessionStorage cache (Task 66) and chunk upload persistence (Task 68).
 */
import { ref, computed } from 'vue'
import type {
  LedgerDetectionResult,
  SheetDetection,
  ConfirmedMapping,
  ImportError,
} from '@/components/ledger-import/LedgerImportDialog.vue'

export function useLedgerImport(projectId: string) {
  // ─── State ──────────────────────────────────────────────────────────────────

  const files = ref<File[]>([])
  const detectionResult = ref<LedgerDetectionResult | null>(null)
  const confirmedSheets = ref<SheetDetection[]>([])
  const confirmedMappings = ref<ConfirmedMapping[]>([])
  const jobId = ref('')
  const currentStep = ref(0)
  const errors = ref<ImportError[]>([])
  const isLoading = ref(false)

  // ─── Session Storage Cache (Task 66) ────────────────────────────────────────

  const cacheKey = `ledger_import_v2_${projectId}`

  function saveToSession() {
    if (detectionResult.value) {
      try {
        sessionStorage.setItem(cacheKey, JSON.stringify({
          detectionResult: detectionResult.value,
          confirmedSheets: confirmedSheets.value,
          currentStep: currentStep.value,
          jobId: jobId.value,
        }))
      } catch { /* quota exceeded — ignore */ }
    }
  }

  function restoreFromSession(): boolean {
    const cached = sessionStorage.getItem(cacheKey)
    if (!cached) return false
    try {
      const data = JSON.parse(cached)
      detectionResult.value = data.detectionResult ?? null
      confirmedSheets.value = data.confirmedSheets ?? []
      currentStep.value = data.currentStep ?? 0
      jobId.value = data.jobId ?? ''
      return true
    } catch {
      return false
    }
  }

  function clearSession() {
    sessionStorage.removeItem(cacheKey)
  }

  // ─── Chunk Upload State Persistence (Task 68) ───────────────────────────────

  function saveUploadState(uploadToken: string, uploadedChunks: number[]) {
    try {
      localStorage.setItem(`upload_chunks_${uploadToken}`, JSON.stringify(uploadedChunks))
    } catch { /* ignore */ }
  }

  function getUploadState(uploadToken: string): number[] {
    const data = localStorage.getItem(`upload_chunks_${uploadToken}`)
    if (!data) return []
    try {
      return JSON.parse(data)
    } catch {
      return []
    }
  }

  function clearUploadState(uploadToken: string) {
    localStorage.removeItem(`upload_chunks_${uploadToken}`)
  }

  // ─── Computed ───────────────────────────────────────────────────────────────

  const hasErrors = computed(() => errors.value.length > 0)
  const hasFatalErrors = computed(() => errors.value.some(e => e.severity === 'fatal'))
  const hasBlockingErrors = computed(() => errors.value.some(e => e.severity === 'blocking'))

  const detectedYear = computed(() => detectionResult.value?.detected_year ?? null)
  const yearConfidence = computed(() => detectionResult.value?.year_confidence ?? 0)

  // ─── Actions ────────────────────────────────────────────────────────────────

  function reset() {
    files.value = []
    detectionResult.value = null
    confirmedSheets.value = []
    confirmedMappings.value = []
    jobId.value = ''
    currentStep.value = 0
    errors.value = []
    isLoading.value = false
    clearSession()
  }

  return {
    // State
    files,
    detectionResult,
    confirmedSheets,
    confirmedMappings,
    jobId,
    currentStep,
    errors,
    isLoading,

    // Computed
    hasErrors,
    hasFatalErrors,
    hasBlockingErrors,
    detectedYear,
    yearConfidence,

    // Session cache (Task 66)
    saveToSession,
    restoreFromSession,
    clearSession,

    // Chunk upload persistence (Task 68)
    saveUploadState,
    getUploadState,
    clearUploadState,

    // Actions
    reset,
  }
}
