/**
 * Fail-closed compatibility gate for G-C0 wire payloads.
 *
 * Mirrors `validate_contract_version()` in
 * `backend/app/services/guidance_gc0_contract.py`. The two implementations
 * MUST produce the same decision for the same payload — this is enforced
 * by the vitest suite next to this file (see `index.spec.ts`).
 *
 * Acceptance rules (design.md §1.7):
 * - missing `contractVersion` → BLOCKED (identity required)
 * - non-string / malformed    → BLOCKED (identity invalid)
 * - unknown major             → BLOCKED (fail-closed)
 * - known major + unsupported minor
 *     → DEGRADED for consumer, BLOCKED for producer
 * - any required minor > negotiated minor → REJECTED (missing capability)
 * - otherwise ACCEPT with the negotiated minor
 */

export type CompatibilityOutcome = 'ACCEPT' | 'BLOCKED' | 'REJECTED' | 'DEGRADED';

export interface CompatibilityReason {
  code: string;
  detail: string;
  field?: string | null;
}

export interface CompatibilityDecision {
  outcome: CompatibilityOutcome;
  reasons: CompatibilityReason[];
  negotiatedVersion: string | null;
}

const SUPPORTED_MAJOR = new Set<string>(['1']);
const SUPPORTED_MINOR_MAX = 0;

function parseVersion(raw: unknown): [string, string] | null {
  if (typeof raw !== 'string') return null;
  const parts = raw.split('.');
  if (parts.length !== 2) return null;
  if (!/^\d+$/.test(parts[0]) || !/^\d+$/.test(parts[1])) return null;
  return [parts[0], parts[1]];
}

function blocked(code: string, detail: string, field?: string): CompatibilityDecision {
  return {
    outcome: 'BLOCKED',
    reasons: [{ code, detail, field: field ?? null }],
    negotiatedVersion: null,
  };
}

export function validateContractVersion(
  payload: unknown,
  opts: { consumerRole?: 'consumer' | 'producer'; requiredMinors?: number[] } = {},
): CompatibilityDecision {
  const consumerRole = opts.consumerRole ?? 'consumer';
  const requiredMinors = opts.requiredMinors ?? [];

  if (typeof payload !== 'object' || payload === null) {
    return blocked(
      'identity-not-object',
      'payload is not a JSON object',
    );
  }

  const raw = (payload as Record<string, unknown>).contractVersion;
  if (raw === undefined || raw === null) {
    return blocked(
      'identity-missing',
      'contractVersion is missing',
      'contractVersion',
    );
  }

  const parsed = parseVersion(raw);
  if (!parsed) {
    return blocked(
      'identity-malformed',
      `contractVersion '${String(raw)}' is not '<major>.<minor>'`,
      'contractVersion',
    );
  }

  const [major, minor] = parsed;
  if (!SUPPORTED_MAJOR.has(major)) {
    return blocked(
      'unknown-major',
      `producer major '${major}' not supported (bundle supports ${Array.from(
        SUPPORTED_MAJOR,
      ).join(', ')})`,
      'contractVersion',
    );
  }

  const minorInt = Number.parseInt(minor, 10);
  if (Number.isNaN(minorInt)) {
    return blocked(
      'identity-malformed',
      `minor '${minor}' is not an integer`,
      'contractVersion',
    );
  }

  if (minorInt > SUPPORTED_MINOR_MAX) {
    const outcome: CompatibilityOutcome = consumerRole === 'consumer' ? 'DEGRADED' : 'BLOCKED';
    return {
      outcome,
      reasons: [
        {
          code: 'unsupported-minor',
          detail: `minor ${minorInt} > ${SUPPORTED_MINOR_MAX} supported by this bundle`,
          field: 'contractVersion',
        },
      ],
      negotiatedVersion: `${major}.${SUPPORTED_MINOR_MAX}`,
    };
  }

  if (requiredMinors.some((r) => r > minorInt)) {
    return {
      outcome: 'REJECTED',
      reasons: [
        {
          code: 'missing-capability',
          detail: `producer minor ${minorInt} does not cover required minor ${Math.max(
            ...requiredMinors,
          )}`,
          field: 'contractVersion',
        },
      ],
      negotiatedVersion: null,
    };
  }

  return {
    outcome: 'ACCEPT',
    reasons: [],
    negotiatedVersion: `${major}.${minorInt}`,
  };
}
