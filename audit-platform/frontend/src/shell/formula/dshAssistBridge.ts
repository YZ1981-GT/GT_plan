/**
 * DSH assist bridge — AI assist opens PlatformAiChatPanel / DshPanel only.
 */

import type { InjectionKey, Ref } from 'vue'

export interface DshAssistBridge {
  isOpen: Ref<boolean>
  open: () => void
  close: (options: { preserveDraft: boolean }) => void
}

export const DSH_ASSIST_BRIDGE_KEY: InjectionKey<DshAssistBridge> = Symbol('dshAssistBridge')

export const WORKPAPER_SHELL_ACTIVE_KEY: InjectionKey<Ref<boolean>> = Symbol(
  'workpaperCapabilityShellActive',
)
