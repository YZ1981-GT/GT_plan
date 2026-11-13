import http from '@/utils/http'
import {
  normalizeDisplayPreferences,
  toDisplayPreferencesPatchWire,
  type DisplayPreferencesPatch,
  type DisplayPreferencesState,
} from '@/utils/displayPreferencesNormalizer'

const DISPLAY_PREFERENCES_URL = '/api/users/me/display-preferences'

/** 服务器 revision 冲突的可恢复载荷。 */
export class DisplayPreferencesRevisionConflict extends Error {
  readonly current: DisplayPreferencesState

  constructor(current: DisplayPreferencesState) {
    super('显示偏好版本冲突')
    this.name = 'DisplayPreferencesRevisionConflict'
    this.current = current
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function conflictCurrent(error: unknown): DisplayPreferencesState | null {
  const response = (error as { response?: { status?: unknown; data?: unknown } })?.response
  if (response?.status !== 409 || !isRecord(response.data) || !('current' in response.data)) return null
  const current = normalizeDisplayPreferences(response.data.current)
  return current.revision >= 0 ? current : null
}

const backgroundRequest = (signal?: AbortSignal) => ({
  signal,
  _background: true,
  _dedupe: false,
  _silent: true,
} as any)

export async function getDisplayPreferences(signal?: AbortSignal): Promise<DisplayPreferencesState> {
  const response = await http.get(DISPLAY_PREFERENCES_URL, backgroundRequest(signal))
  return normalizeDisplayPreferences(response.data)
}

export async function patchDisplayPreferences(
  patch: DisplayPreferencesPatch,
  signal?: AbortSignal,
): Promise<DisplayPreferencesState> {
  try {
    const response = await http.patch(
      DISPLAY_PREFERENCES_URL,
      toDisplayPreferencesPatchWire(patch),
      backgroundRequest(signal),
    )
    return normalizeDisplayPreferences(response.data)
  } catch (error) {
    const current = conflictCurrent(error)
    if (current) throw new DisplayPreferencesRevisionConflict(current)
    throw error
  }
}

export { DISPLAY_PREFERENCES_URL }
