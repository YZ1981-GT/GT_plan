/**
 * Isomorphic SHA-256 hex (Node + Vitest). Avoids static `node:crypto` imports
 * that Vite externalizes into the browser graph when inventory modules are pulled.
 */
export function sha256Hex(payload: string): string {
  // Vitest / Node path — dynamic require keeps Vite from rewriting this into client bundles
  // when the importer is only used from Node/gate scripts.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const nodeCrypto = require('crypto') as typeof import('crypto')
  return nodeCrypto.createHash('sha256').update(payload, 'utf8').digest('hex')
}
