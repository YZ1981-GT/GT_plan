/// <reference lib="webworker" />
import { parseEmailBytes } from './emailParser'

export type EmailWorkerRequest = {
  requestId: string
  bytes: ArrayBuffer
  hintExt?: string
}

self.onmessage = async (ev: MessageEvent<EmailWorkerRequest>) => {
  const { requestId, bytes, hintExt } = ev.data || ({} as EmailWorkerRequest)
  try {
    const result = await parseEmailBytes(bytes, hintExt)
    // inline parts 用 transfer 回传
    const transfer: Transferable[] = []
    if (result.status === 'ok') {
      for (const p of result.email.inlineParts) transfer.push(p.bytes)
    }
    ;(self as DedicatedWorkerGlobalScope).postMessage({ requestId, ok: true, result }, transfer)
  } catch (e) {
    ;(self as DedicatedWorkerGlobalScope).postMessage({
      requestId,
      ok: false,
      error: e instanceof Error ? e.message : 'parse_failed',
    })
  }
}

export {}
