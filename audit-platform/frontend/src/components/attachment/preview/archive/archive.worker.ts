/// <reference lib="webworker" />
/**
 * archive.worker.ts — 不可信容器解析入口
 */
import { parseArchiveBytes } from './archiveContainer'

export type ArchiveWorkerRequest = {
  requestId: string
  bytes: ArrayBuffer
  hintExt?: string
}

export type ArchiveWorkerResponse = {
  requestId: string
  ok: boolean
  result?: ReturnType<typeof parseArchiveBytes>
  error?: string
}

self.onmessage = (ev: MessageEvent<ArchiveWorkerRequest>) => {
  const { requestId, bytes, hintExt } = ev.data || ({} as ArchiveWorkerRequest)
  try {
    const result = parseArchiveBytes(bytes, undefined, hintExt)
    const resp: ArchiveWorkerResponse = { requestId, ok: true, result }
    ;(self as DedicatedWorkerGlobalScope).postMessage(resp)
  } catch (e) {
    const resp: ArchiveWorkerResponse = {
      requestId,
      ok: false,
      error: e instanceof Error ? e.message : 'parse_failed',
    }
    ;(self as DedicatedWorkerGlobalScope).postMessage(resp)
  }
}

export {}
