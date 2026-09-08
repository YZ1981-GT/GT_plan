/**
 * PAC Task 21+ isolated typecheck probe — full-repo vue-tsc OOMs at 8GB+.
 *
 * Surface: renderConfig wire, one router domain (auth), registry types,
 * pacNetworkGate. The 11 domain + 6 entry arrays are NOT type-checked here:
 * their `() => import('*.vue')` targets make vue-tsc resolve 200+ SFC graphs
 * and OOM even at 6GB. The two split faces' structural equivalence is fully
 * covered at runtime by Vitest `routeDomainProjection.spec.ts` +
 * `registrySplitEquivalence.pbt.spec.ts`, and their pure-type shape by
 * `pacDomainEntryTypes.spec.ts` (type-level asserts, no SFC resolution).
 */
import type { RouteRecordRaw } from 'vue-router'
import type { RenderConfigWire, RenderDecisionWire } from '../types/renderConfig'
import { RENDER_CONFIG_FIELD_STATUS } from '../types/renderConfig'
import { authRoutes } from '../router/domains/auth'
import type { HtmlRendererEntry } from '../components/workpaper/registry/types'
import {
  isAmbientFailedResponse,
  partitionConsoleErrors,
} from './_helpers/pacNetworkGate'

const routes: RouteRecordRaw[] = [...authRoutes]
const status = RENDER_CONFIG_FIELD_STATUS
const wire: RenderConfigWire | undefined = undefined
const trace: RenderDecisionWire[] = []
const entry: Pick<HtmlRendererEntry, 'componentType'> = { componentType: 'h-static-doc' }

// decision_trace must stay active once a FE consumer exists (WpDecisionTracePanel).
const _assertActive: typeof status.decision_trace = 'active'

const ambient = isAmbientFailedResponse({
  status: 404,
  url: 'https://documentserver.example/web-apps/apps/api/documents/api.js',
})
const parts = partitionConsoleErrors(['Failed to load resource: 500'])

void routes
void status
void wire
void trace
void entry
void _assertActive
void ambient
void parts

export {}
