/**
 * PAC Playwright / CI network console gate.
 *
 * Chrome console "Failed to load resource" often omits the URL, so the e2e
 * gate must pair console errors with `page.on('response')` failures and only
 * allow (1) ambient OnlyOffice/favicon noise and (2) explicitly named concurrent
 * WIP surfaces — never a blanket “any 4xx/5xx is OK”.
 */
export interface FailedResponse {
  status: number
  url: string
}

/** Ambient third-party / browser noise that PAC skeleton does not own. */
export const AMBIENT_FAILURE_URL_RE =
  /favicon\.ico|(?:^|\/\/)(?:[\w.-]*onlyoffice|documentserver)(?:[:/]|$)|\/web-apps\/|\/cache\/files\/|\/cool\/|WebSocket/i

/**
 * Concurrent WIP owned by `workpaper-guidance-content-closure`.
 * PAC mount e2e must not go green by ignoring first-party failures generally —
 * only this named path is exempt until that spec closes guidance HTTP.
 */
export const CONCURRENT_GUIDANCE_WIP_URL_RE =
  /\/api\/workpapers\/[^/?#]+\/guidance(?:\?|#|$)/i

export function isAmbientFailedResponse(hit: FailedResponse): boolean {
  if (hit.status < 400) return false
  return AMBIENT_FAILURE_URL_RE.test(hit.url)
}

export function isExemptFailedResponse(hit: FailedResponse): boolean {
  if (hit.status < 400) return false
  return isAmbientFailedResponse(hit) || CONCURRENT_GUIDANCE_WIP_URL_RE.test(hit.url)
}

/** pageerror / non-resource console lines that are known-harmless. */
export const HARMLESS_CONSOLE_RE = /ResizeObserver loop|favicon\.ico/i

export function partitionConsoleErrors(messages: readonly string[]): {
  pageErrors: string[]
  resourceErrors: string[]
  other: string[]
} {
  const pageErrors: string[] = []
  const resourceErrors: string[] = []
  const other: string[] = []
  for (const raw of messages) {
    const msg = String(raw)
    if (HARMLESS_CONSOLE_RE.test(msg)) continue
    if (/Failed to load resource/i.test(msg)) {
      resourceErrors.push(msg)
      continue
    }
    // Playwright pageerror strings are usually Error stacks / plain messages
    // without the "Failed to load resource" prefix.
    if (/^\s*(Error|TypeError|ReferenceError|SyntaxError)\b/.test(msg) || msg.includes('\n    at ')) {
      pageErrors.push(msg)
      continue
    }
    other.push(msg)
  }
  return { pageErrors, resourceErrors, other }
}

/**
 * Resource console noise is only tolerable when every failed response is exempt
 * (ambient or named concurrent WIP). First-party non-exempt failures stay RED.
 * Console resource errors with zero attributed responses stay RED.
 */
export function unexplainedResourceFailures(
  resourceConsoleCount: number,
  failedResponses: readonly FailedResponse[],
): FailedResponse[] {
  const unexplained = failedResponses.filter((hit) => !isExemptFailedResponse(hit))
  if (unexplained.length > 0) return unexplained
  if (resourceConsoleCount > 0 && failedResponses.length === 0) {
    return [{ status: 0, url: '<unattributed-resource-console-error>' }]
  }
  return []
}
