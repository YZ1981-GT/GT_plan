/**
 * useConsolSubjectSource — Property 24 (part 1): Consolidation Name Source Fidelity + Fallback
 *
 * **Validates: Requirements 19.1, 19.5, 19.7**
 *
 * ACNR consumer wiring, task 28.5 — P24 fidelity/fallback for the consolidation
 * subject-name source. The existing `useConsolSubjectSource.spec.ts` covers concrete
 * examples; this file adds the fast-check property that must hold for **any** random
 * TB registry name set:
 *
 *   - Fidelity: every produced subjectTree leaf name ∈ (hardcoded names ∪ registry names).
 *   - Canonical adoption: a leaf whose (normalized) name is confirmed by the TB registry
 *     adopts the registry's canonical label byte-for-byte (真源, Req 19.1).
 *   - Fallback identity: an empty/unavailable TB registry → subjectTree === HARDCODED_SUBJECT_TREE
 *     (same object identity, no blank picker, Req 19.5).
 *   - Leaf-count invariant: the mapping is 1:1 — it never drops or adds leaves (Req 19.7).
 *   - Contract: every leaf has value === label and no internal placeholder code.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useAddressRegistry } from '@/stores/addressRegistry'
import {
  useConsolSubjectSource,
  HARDCODED_SUBJECT_TREE,
  type SubjectTreeNode,
} from '../composables/useConsolSubjectSource'

// ─── helpers ────────────────────────────────────────────────────────────────

/** Collect leaf nodes (non-disabled, no children) in document order. */
function collectLeaves(nodes: SubjectTreeNode[]): SubjectTreeNode[] {
  const out: SubjectTreeNode[] = []
  for (const n of nodes) {
    if (n.children && n.children.length > 0) out.push(...collectLeaves(n.children))
    else if (!n.disabled) out.push(n)
  }
  return out
}

/** Build a minimal TB-domain address entry keyed by `label`. */
function makeTbEntry(label: string) {
  return {
    uri: `tb://${label}`,
    domain: 'tb',
    source: 'tb',
    path: '',
    cell: '',
    label,
    formula_ref: '',
    jump_route: '',
  }
}

const HARDCODED_LEAVES = collectLeaves(HARDCODED_SUBJECT_TREE)
const HARDCODED_LEAF_NAMES: string[] = HARDCODED_LEAVES.map((l) => l.value)
const HARDCODED_LEAF_NAME_SET = new Set(HARDCODED_LEAF_NAMES)

// ─── Property 24 (fidelity + fallback) ────────────────────────────────────────

describe('useConsolSubjectSource — P24 fidelity + fallback (property)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('empty registry → subjectTree identity (HARDCODED_SUBJECT_TREE) for any noise (Req 19.5)', () => {
    fc.assert(
      fc.property(
        // random non-TB-domain noise must never flip the source to registry-backed
        fc.array(
          fc.record({
            label: fc.string({ minLength: 0, maxLength: 8 }),
            domain: fc.constantFrom('report', 'note', 'wp', 'aux', ''),
          }),
          { maxLength: 12 },
        ),
        (noise) => {
          setActivePinia(createPinia())
          const store = useAddressRegistry()
          store.addresses = noise.map((n) => ({ ...makeTbEntry(n.label), domain: n.domain })) as any

          const { subjectTree, isRegistryBacked } = useConsolSubjectSource()
          // No TB-domain entries with labels → not registry backed → identity fallback
          expect(isRegistryBacked.value).toBe(false)
          expect(subjectTree.value).toBe(HARDCODED_SUBJECT_TREE)
        },
      ),
      { numRuns: 40 },
    )
  })

  it('any TB registry subset → fidelity, canonical adoption, leaf-count invariant (Req 19.1/19.7)', () => {
    fc.assert(
      fc.property(
        // random subset of real subject names to "confirm" via TB registry
        fc.subarray(HARDCODED_LEAF_NAMES),
        // whether the registry stores a padded canonical variant (whitespace differs from hardcoded)
        fc.boolean(),
        // random extra TB names that do NOT correspond to any subject leaf
        fc.array(
          fc.array(fc.constantFrom('额', '外', '科', '目', 'X', 'Y', 'Z'), { minLength: 1, maxLength: 5 }).map((a) => a.join('')),
          { maxLength: 6 },
        ),
        (selected, padded, extras) => {
          setActivePinia(createPinia())
          const store = useAddressRegistry()

          // canonical label the registry advertises for each selected subject name
          const canonicalFor = (name: string) => (padded ? ` ${name} ` : name)
          const selectedSet = new Set(selected)

          const tbEntries = [
            ...selected.map((name) => makeTbEntry(canonicalFor(name))),
            ...extras.map((name) => makeTbEntry(name)),
          ]
          store.addresses = tbEntries as any

          const { subjectTree, registrySubjectNames } = useConsolSubjectSource()
          const registryNameSet = new Set<string>(registrySubjectNames.value)

          const producedLeaves = collectLeaves(subjectTree.value)

          // (a) leaf-count invariant — never drops/adds leaves
          expect(producedLeaves.length).toBe(HARDCODED_LEAVES.length)

          for (let i = 0; i < producedLeaves.length; i++) {
            const leaf = producedLeaves[i]
            const original = HARDCODED_LEAF_NAMES[i]

            // (b) contract: value === label, no internal placeholder code
            expect(leaf.value).toBe(leaf.label)
            expect(leaf.value.startsWith('_')).toBe(false)

            if (selectedSet.has(original)) {
              // (c) canonical adoption: confirmed leaf takes the registry's canonical label
              expect(leaf.value).toBe(canonicalFor(original))
              // and that canonical name is present in the registry name set
              expect(registryNameSet.has(leaf.value.trim())).toBe(true)
            } else {
              // (d) unconfirmed leaf falls back to the hardcoded literal (绝不丢叶子)
              expect(leaf.value).toBe(original)
            }

            // (e) fidelity: every produced leaf name ⊆ (hardcoded ∪ registry)
            expect(
              HARDCODED_LEAF_NAME_SET.has(leaf.value) || registryNameSet.has(leaf.value.trim()),
            ).toBe(true)
          }
        },
      ),
      { numRuns: 60 },
    )
  })
})
