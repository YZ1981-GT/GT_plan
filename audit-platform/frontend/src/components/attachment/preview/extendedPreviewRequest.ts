import http from '@/utils/http'
import { logger } from '@/utils/logger'
import type { PreviewFamily } from './attachmentPreviewFormats'
import type { PreviewResourceScope } from './previewResourceScope'

export type ExtendedLoadState =
  | 'loading'
  | 'ready'
  | 'forbidden'
  | 'not_found'
  | 'load_failed'
  | 'wiring_error'
  | 'limit_reached'
  | 'cancelled'
  | 'stale'

export interface ExtendedFetchOk {
  status: 'ready'
  bytes: ArrayBuffer
  contentType: string | null
  generation: number
}

export interface ExtendedFetchErr {
  status: Exclude<ExtendedLoadState, 'loading' | 'ready'>
  generation: number
  message?: string
}

export type ExtendedFetchResult = ExtendedFetchOk | ExtendedFetchErr

function headerValue(headers: any, name: string): string | null {
  if (!headers) return null
  const value =
    headers[name] ||
    headers[name.toLowerCase()] ||
    headers[name.toUpperCase()] ||
    (typeof headers.get === 'function' ? headers.get(name) : null)
  return value == null ? null : String(value)
}

function normalizeContentType(value: string | null | undefined): string | null {
  return value ? value.split(';')[0].trim().toLowerCase() : null
}

function isJsonContentType(value: string | null | undefined): boolean {
  const mime = normalizeContentType(value)
  return mime === 'application/json' || Boolean(mime?.endsWith('+json'))
}

export async function fetchExtendedBytes(opts: {
  attachmentId: string
  downloadUrl: string
  family: PreviewFamily
  signal: AbortSignal
  generation: number
  isCurrent: (g: number) => boolean
  scope: PreviewResourceScope
  maxBytes?: number
}): Promise<ExtendedFetchResult> {
  const { attachmentId, downloadUrl, family, signal, generation, isCurrent, maxBytes } = opts

  if (downloadUrl.includes('/preview') && !downloadUrl.includes('/download')) {
    logger.error('attachment_preview_download_url_required', { attachmentId, family })
    return { status: 'wiring_error', generation, message: 'download_url_required' }
  }

  try {
    const response = await http.get(downloadUrl, {
      responseType: 'blob',
      _silent: true,
      _dedupe: false,
      signal,
    } as any)

    if (!isCurrent(generation)) return { status: 'stale', generation }

    const blob = response.data as Blob
    const headerType = normalizeContentType(headerValue(response.headers, 'content-type'))
    const blobType = normalizeContentType(blob?.type)
    const contentType = headerType || blobType
    if (isJsonContentType(headerType) || isJsonContentType(blobType)) {
      logger.error('attachment_preview_json_blob_trap', {
        attachmentId,
        family,
        contentType,
        requestId: headerValue(response.headers, 'x-request-id'),
      })
      return { status: 'wiring_error', generation, message: 'json_blob_trap' }
    }

    if (
      maxBytes !== undefined &&
      Number.isFinite(maxBytes) &&
      typeof blob?.size === 'number' &&
      blob.size > maxBytes
    ) {
      return { status: 'limit_reached', generation, message: 'input_byte_limit' }
    }
    if (!blob || typeof blob.arrayBuffer !== 'function') {
      return { status: 'load_failed', generation, message: 'invalid_blob_response' }
    }

    const bytes = await blob.arrayBuffer()
    if (!isCurrent(generation)) return { status: 'stale', generation }
    if (maxBytes !== undefined && Number.isFinite(maxBytes) && bytes.byteLength > maxBytes) {
      return { status: 'limit_reached', generation, message: 'input_byte_limit' }
    }
    return { status: 'ready', bytes, contentType, generation }
  } catch (error: any) {
    if (!isCurrent(generation)) return { status: 'stale', generation }
    if (signal.aborted || error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') {
      return { status: 'cancelled', generation }
    }
    const status = error?.response?.status
    if (status === 403) return { status: 'forbidden', generation }
    if (status === 404) return { status: 'not_found', generation }
    // 401 remains owned by the global authentication chain.
    return { status: 'load_failed', generation, message: error?.message }
  }
}
