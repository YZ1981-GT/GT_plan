/// <reference lib="webworker" />
import { parseDxfBytes } from './dxfModel'

self.onmessage = (ev: MessageEvent<{ requestId: string; bytes: ArrayBuffer }>) => {
  const { requestId, bytes } = ev.data || { requestId: '', bytes: new ArrayBuffer(0) }
  try {
    const result = parseDxfBytes(bytes)
    ;(self as DedicatedWorkerGlobalScope).postMessage({ requestId, ok: true, result })
  } catch (e) {
    ;(self as DedicatedWorkerGlobalScope).postMessage({
      requestId,
      ok: false,
      error: e instanceof Error ? e.message : 'parse_failed',
    })
  }
}

export {}
