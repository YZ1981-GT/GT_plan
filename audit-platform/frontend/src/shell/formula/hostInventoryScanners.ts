/**
 * Source-level scanners for formula Task 2 red baseline.
 * Grep hits feed the *duplicate inventory*; they do NOT flip outlet support.
 */

import { readFileSync } from 'node:fs'
import { join, relative } from 'node:path'

import type { DuplicateCapabilityFinding } from './workpaperHostInventory'
import { isDomainOwnedRelativePath } from './domainExclusions'

const FE_SRC = join(__dirname, '../..')

function walkVueFiles(dir: string, out: string[] = []): string[] {
  // Lazy require to keep module load light when only inventory is imported.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { readdirSync, statSync } = require('node:fs') as typeof import('node:fs')
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist' || name.startsWith('.')) continue
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) walkVueFiles(full, out)
    else if (name.endsWith('.vue') || name.endsWith('.ts')) out.push(full)
  }
  return out
}

function toRel(full: string): string {
  return relative(FE_SRC, full).replace(/\\/g, '/')
}

/** Parse GtWpToolbar template for named slots vs CSS class. */
export function inspectGtWpToolbarOutlets(toolbarSource: string): {
  hasRightCssClass: boolean
  namedSlots: string[]
  hasPageCapabilitiesPrimarySlot: boolean
  hasPageCapabilitiesCompatibilitySlot: boolean
} {
  const hasRightCssClass = /class=["'][^"']*gt-wp-toolbar__right/.test(toolbarSource)
  const namedSlots = [...toolbarSource.matchAll(/<slot\s+name=["']([^"']+)["']/g)].map(
    (m) => m[1],
  )
  return {
    hasRightCssClass,
    namedSlots,
    hasPageCapabilitiesPrimarySlot: namedSlots.includes('page-capabilities-primary'),
    hasPageCapabilitiesCompatibilitySlot: namedSlots.includes(
      'page-capabilities-compatibility',
    ),
  }
}

export function loadGtWpToolbarSource(): string {
  return readFileSync(
    join(FE_SRC, 'components/workpaper/GtWpToolbar.vue'),
    'utf8',
  )
}

/**
 * Enumerate duplicate AI / review / rail / formula entry sites on workpaper-route
 * sources. Domain-owned paths are skipped (exclusion evidence lives elsewhere).
 */
export function scanDuplicateCapabilityFindings(
  roots: string[] = [join(FE_SRC, 'components/workpaper'), join(FE_SRC, 'layouts'), join(FE_SRC, 'views')],
): DuplicateCapabilityFinding[] {
  const findings: DuplicateCapabilityFinding[] = []
  const patterns: Array<{ kind: DuplicateCapabilityFinding['kind']; re: RegExp; detail: string }> = [
    {
      kind: 'ai-assist',
      // Real DSH carrier only — not dead "AI 助手" sidebars.
      re: /<DshPanel\b|showDshPanel\s*=/,
      detail: 'AI assist / DSH panel entry',
    },
    {
      kind: 'ai-review-panel',
      // Canonical toolbar entry; AiReviewPanel is panel body; A171 is chapter review (not AI taxonomy).
      re: /GtWpAiReviewToolbar|AIContentReviewPanel/,
      detail: 'AI review panel mount',
    },
    {
      kind: 'human-review',
      re: /WorkpaperReviewPanel|<GtWpReviewRail\b/,
      detail: 'human / workpaper review panel',
    },
    {
      kind: 'guidance-rail',
      re: /<WpGuidancePanel\b|<GuidanceTabContent\b/,
      detail: 'guidance rail / panel',
    },
    {
      kind: 'bare-ai',
      re: /\bopenAiAssist\s*\(|ai-assist-fab/i,
      detail: 'bare AI entry',
    },
    {
      kind: 'fixed-offset-rail',
      // Only capability-rail carriers; sheet overlays with position:fixed are not rails.
      re: /position:\s*fixed[\s\S]{0,200}(wp-capability-shell|gt-wp-review-rail|guidance-rail)/i,
      detail: 'fixed-offset rail candidate',
    },
    {
      kind: 'formula-entry',
      // Real FormulaManagerDialog openers only — not "四表取数（公式管理）" labels.
      re: /showFormulaManager\s*=|open-formula-manager|FormulaManagerDialog/,
      detail: 'formula manager entry',
    },
  ]

  for (const root of roots) {
    let files: string[] = []
    try {
      files = walkVueFiles(root)
    } catch {
      continue
    }
    for (const file of files) {
      const rel = toRel(file)
      if (isDomainOwnedRelativePath(rel)) continue
      // Production surface only — tests are not capability carriers.
      if (rel.includes('/__tests__/') || rel.includes('\\__tests__\\') || /\/__tests__\//.test(rel)) {
        continue
      }
      if (rel.includes('__tests__')) continue
      // Confine uniqueness to workpaper route surfaces.
      if (rel.startsWith('views/') && !/Workpaper|workpaper-editor|ThreeColumn/i.test(rel)) {
        if (!rel.includes('layouts')) {
          if (!/Workpaper/i.test(rel)) continue
        }
      }
      const text = readFileSync(file, 'utf8')
      for (const p of patterns) {
        if (p.re.test(text)) {
          findings.push({
            kind: p.kind,
            relativePath: rel,
            detail: p.detail,
          })
        }
      }
    }
  }

  // Deduplicate by kind+path
  const seen = new Set<string>()
  return findings.filter((f) => {
    const k = `${f.kind}|${f.relativePath}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}
