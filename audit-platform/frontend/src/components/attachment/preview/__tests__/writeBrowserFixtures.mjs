/**
 * Write Task 19 browser fixtures (zip/eml/dxf/dwg).
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { generateFixture } from '../archive/archiveFixtures.ts'

const __dirname = dirname(fileURLToPath(import.meta.url))
const dir = resolve(
  'D:/GT_plan/.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion/browser_fixtures',
)
mkdirSync(dir, { recursive: true })

const { bytes: zipBytes, sha256: zipSha } = generateFixture('zip_utf8_ok')
writeFileSync(resolve(dir, 'sample.zip'), Buffer.from(zipBytes))

const eml = Buffer.from(
  [
    'From: a@example.com',
    'To: b@example.com',
    'Subject: e2e-preview',
    'MIME-Version: 1.0',
    'Content-Type: text/html; charset=utf-8',
    '',
    '<html><body><img src="https://evil.example/x.png" srcset="https://evil.example/y.png"><p>hi</p></body></html>',
    '',
  ].join('\r\n'),
)
writeFileSync(resolve(dir, 'sample.eml'), eml)

const dxf = Buffer.from(
  '0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0\n20\n0\n11\n10\n21\n10\n0\nENDSEC\n0\nEOF\n',
)
writeFileSync(resolve(dir, 'sample.dxf'), dxf)

const dwg = Buffer.from([0x41, 0x43, 0x31, 0x30, 0x31, 0x00])
writeFileSync(resolve(dir, 'sample.dwg'), dwg)

const digests = {
  zip: zipSha,
  eml: createHash('sha256').update(eml).digest('hex'),
  dxf: createHash('sha256').update(dxf).digest('hex'),
  dwg: createHash('sha256').update(dwg).digest('hex'),
}
writeFileSync(resolve(dir, 'digests.json'), JSON.stringify(digests, null, 2))
console.log('wrote', dir, digests)
