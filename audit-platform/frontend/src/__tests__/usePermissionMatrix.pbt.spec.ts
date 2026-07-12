/**
 * Property-Based Test: P10 · 权限判定与共享定义一致（覆盖 5 角色）
 * Feature: platform-global-hardening, Property 10
 *
 * **Validates: Requirements 7.1, 7.6**
 *
 * For any (role ∈ 5角色, action, resource, context) combination,
 * `can()` returns a deterministic boolean consistent with the shared
 * definition table (PERMISSION_TABLE + special rules).
 *
 * fast-check `{ numRuns: 100 }`
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  can,
  isReadonly,
  getAllowedActions,
  whyCannotDo,
  ALL_ROLES,
  ALL_ACTIONS,
  ALL_RESOURCES,
  type Role,
  type Action,
  type Resource,
  type PermissionContext,
} from '@/permissions/permission-matrix'

// ─── Arbitraries ────────────────────────────────────────────────────────────

const arbRole = fc.constantFrom(...ALL_ROLES)
const arbAction = fc.constantFrom(...ALL_ACTIONS)
const arbResource = fc.constantFrom(...ALL_RESOURCES)
const arbContext: fc.Arbitrary<PermissionContext | undefined> = fc.oneof(
  fc.constant(undefined),
  fc.record({
    isLocked: fc.oneof(fc.constant(undefined), fc.boolean()),
    reviewStatus: fc.oneof(fc.constant(undefined), fc.constantFrom('approved', 'pending', 'draft')),
  }),
)

// ─── Expected permission table (ground truth mirror) ─────────────────────────
// This is the reference table duplicated here for property verification.
// If the source PERMISSION_TABLE changes, this test will catch inconsistencies.

const EXPECTED_TABLE: Record<Role, Record<Resource, Set<Action>>> = {
  assistant: {
    workpaper: new Set(['edit', 'view', 'export', 'import']),
    adjustment: new Set(['edit', 'view', 'export', 'import']),
    report: new Set(['view', 'export']),
    note: new Set(['edit', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
  manager: {
    workpaper: new Set(['edit', 'review', 'view', 'export', 'import']),
    adjustment: new Set(['edit', 'review', 'approve', 'view', 'export', 'import']),
    report: new Set(['edit', 'review', 'view', 'export']),
    note: new Set(['edit', 'review', 'view', 'export']),
    template: new Set(['edit', 'view']),
    project_settings: new Set(['edit', 'view']),
  },
  partner: {
    workpaper: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'import', 'refresh']),
    adjustment: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'import']),
    report: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'refresh']),
    note: new Set(['edit', 'review', 'approve', 'delete', 'view', 'export', 'refresh']),
    template: new Set(['edit', 'delete', 'view']),
    project_settings: new Set(['edit', 'delete', 'view']),
  },
  qc_partner: {
    workpaper: new Set(['review', 'view', 'export']),
    adjustment: new Set(['review', 'view', 'export']),
    report: new Set(['review', 'view', 'export']),
    note: new Set(['review', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
  eqcr: {
    workpaper: new Set(['review', 'view', 'export']),
    adjustment: new Set(['review', 'view', 'export']),
    report: new Set(['review', 'view', 'export']),
    note: new Set(['review', 'view', 'export']),
    template: new Set(['view']),
    project_settings: new Set(['view']),
  },
}

/**
 * Compute expected result applying special rules on top of the base table.
 * Special rules:
 * 1. view is always allowed (information transparency)
 * 2. reviewStatus === 'approved' + action === 'edit' → deny all roles
 * 3. isLocked + resource === 'workpaper' + action === 'edit' → only partner allowed
 */
function expectedCan(
  role: Role,
  action: Action,
  resource: Resource,
  context?: PermissionContext,
): boolean {
  // Rule 1: view always allowed
  if (action === 'view') return true

  // Rule 2: approved review blocks edit for everyone
  if (context?.reviewStatus === 'approved' && action === 'edit') {
    return false
  }

  // Rule 3: locked workpaper edit → only partner
  if (context?.isLocked && resource === 'workpaper' && action === 'edit') {
    return role === 'partner'
  }

  // Base table lookup
  const rolePerms = EXPECTED_TABLE[role]
  if (!rolePerms) return false
  const resourcePerms = rolePerms[resource]
  if (!resourcePerms) return false
  return resourcePerms.has(action)
}

// ─── Property Tests ─────────────────────────────────────────────────────────

describe('Property 10: 权限判定与共享定义一致（覆盖 5 角色）', () => {
  it('can(role, action, resource, context) returns deterministic boolean consistent with shared definition table', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbAction,
        arbResource,
        arbContext,
        (role, action, resource, context) => {
          const actual = can(role, action, resource, context)
          const expected = expectedCan(role, action, resource, context)

          // Must be a boolean (deterministic)
          expect(typeof actual).toBe('boolean')
          // Must match the expected permission table + special rules
          expect(actual).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('isReadonly(role, resource, context) === !can(role, "edit", resource, context)', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbResource,
        arbContext,
        (role, resource, context) => {
          const readonly = isReadonly(role, resource, context)
          const canEdit = can(role, 'edit', resource, context)
          expect(readonly).toBe(!canEdit)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('getAllowedActions returns exactly the actions where can() is true', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbResource,
        arbContext,
        (role, resource, context) => {
          const allowed = getAllowedActions(role, resource, context)
          const allowedSet = new Set(allowed)

          for (const action of ALL_ACTIONS) {
            const canDoIt = can(role, action, resource, context)
            expect(allowedSet.has(action)).toBe(canDoIt)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('whyCannotDo returns null iff can() is true; non-null string otherwise', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbAction,
        arbResource,
        arbContext,
        (role, action, resource, context) => {
          const allowed = can(role, action, resource, context)
          const reason = whyCannotDo(role, action, resource, context)

          if (allowed) {
            expect(reason).toBeNull()
          } else {
            expect(reason).not.toBeNull()
            expect(typeof reason).toBe('string')
            expect(reason!.length).toBeGreaterThan(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('view action is always allowed for any role and resource', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbResource,
        arbContext,
        (role, resource, context) => {
          expect(can(role, 'view', resource, context)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('locked workpaper edit is only allowed for partner role', () => {
    fc.assert(
      fc.property(
        arbRole,
        (role) => {
          const lockedCtx: PermissionContext = { isLocked: true }
          const result = can(role, 'edit', 'workpaper', lockedCtx)
          if (role === 'partner') {
            expect(result).toBe(true)
          } else {
            expect(result).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('approved review status blocks edit for all roles and resources', () => {
    fc.assert(
      fc.property(
        arbRole,
        arbResource,
        (role, resource) => {
          const approvedCtx: PermissionContext = { reviewStatus: 'approved' }
          expect(can(role, 'edit', resource, approvedCtx)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})
