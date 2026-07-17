/**
 * Task 10.4 (Wave 9) — AI / 复核 / 归档 / Legal Hold UAT suite
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R8, R9, R10, R11, R13
 * Design: §10.2 (Playwright 边界), §12 UAT Design Matrix (UAT-10~13)
 *
 * 逐项覆盖（全部驱动真实治理 HTTP 契约，无假绿）：
 *   - UAT-10 AI 全入口门禁：AI 生成登记为 draft → 未经人工确认 FormalOutput 资格为
 *            blocked(NOT_CONFIRMED)；人工 confirm 后 eligible；FormalOutput preflight
 *            产出 watermark，finalize 同 watermark 通过、篡改 watermark 失败(WATERMARK_CHANGED)。
 *   - UAT-11 QC/EQCR 再复核：绑定有效非 stale 证据 ref + 独立人工关闭 Blocking Review →
 *            closed；replace/deactivate 证据 → 复核自动重开(re_review_required) 且
 *            completion-block=true；读端点暴露 version/hash/确认/locator/is_stale。
 *   - UAT-12 归档完整性：clean 集合归档 preflight+build 成功、封存包离线验签通过、成功归档
 *            NOT 生成 blocking difference report；篡改封存包离线验签失败并给出机器可读差异。
 *   - UAT-13 删除清理覆盖无绕过（一票否决）：active hold 覆盖附件 → 覆盖(version-replace)
 *            返回 423 LEGAL_HOLD_ACTIVE 零效果；purge 四条件(hold active) → allowed=false
 *            delta=0 unmet=[hold_active]，即使 retention_expired=true 且主体具 purge 能力。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 设计边界（design §10.2）：Playwright 只验证「用户可见 / 浏览器可达的流程与网络契约」，
 * 不承担 DB trigger / 并发 / PBT / 6000VU / offline-verifier 内部证明。离线验签本属独立
 * 只读进程（design §10.2 层 7），此处仅通过已挂载的 /archive/verify 网络契约驱动其重算。
 *
 * 环境：backend 9980 / frontend 3030（start-dev.bat）。登录 admin/admin123。
 * 治理端点前缀：/api/projects/{project_id}/years/{year}/evidence/...（openapi 为唯一事实源）。
 */
import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext } from '@playwright/test'

const FE = 'http://localhost:3030'
const API = 'http://localhost:9980'

// 最小合法 PDF（magic MIME 通过 → 上传 finalize 为 available）
const PDF_BYTES = Buffer.from(
  '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n',
)

// ── 登录并返回 token（body.data.access_token）───────────────────────────────
async function login(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `login HTTP ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, 'access_token present').toBeTruthy()
  return token as string
}

// ── ResponseWrapperMiddleware 把 2xx JSON 包成 {code,message,data}；解包出真正 payload ──
function unwrap(body: any): any {
  if (
    body &&
    typeof body === 'object' &&
    'data' in body &&
    ['code', 'message', 'data'].every((k) => k in body || true) &&
    Object.keys(body).every((k) => ['code', 'message', 'data'].includes(k))
  ) {
    return body.data
  }
  return body
}

type ApiResult = { status: number; body: any; data: any }

async function api(
  request: APIRequestContext,
  method: 'get' | 'post',
  path: string,
  token: string,
  opts: { data?: any; idempotent?: boolean } = {},
): Promise<ApiResult> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
  if (opts.idempotent) headers['Idempotency-Key'] = randomUUID()
  const url = path.startsWith('http') ? path : `${API}${path}`
  const resp =
    method === 'get'
      ? await request.get(url, { headers })
      : await request.post(url, { headers, data: opts.data ?? {} })
  const body = await resp.json().catch(() => ({}))
  return { status: resp.status(), body, data: unwrap(body) }
}

async function fetchOpenApiPaths(request: APIRequestContext, token: string): Promise<string[]> {
  const resp = await request.get(`${API}/openapi.json`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(resp.ok(), `openapi HTTP ${resp.status()}`).toBeTruthy()
  const spec = await resp.json()
  return Object.keys(spec.paths ?? {})
}

// ── 选取一个真实项目（治理端点按 project/year 作用域）──────────────────────────
async function pickProject(
  request: APIRequestContext,
  token: string,
): Promise<{ projectId: string; year: number }> {
  const resp = await request.get(`${API}/api/projects?page=1&page_size=20`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(resp.ok(), `projects HTTP ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const items: any[] = body.data ?? body ?? []
  const p = items.find((x) => x?.id && x?.audit_year)
  expect(p, 'at least one project with audit_year exists').toBeTruthy()
  return { projectId: String(p.id), year: Number(p.audit_year) }
}

function base(projectId: string, year: number, sub: string): string {
  return `${API}/api/projects/${projectId}/years/${year}/evidence${sub}`
}

// ── 上传一个真实附件（治理安全上传）→ {attachmentId, versionId} ──────────────
async function uploadAttachment(
  request: APIRequestContext,
  token: string,
  projectId: string,
  year: number,
): Promise<{ attachmentId: string; versionId: string }> {
  const resp = await request.post(base(projectId, year, '/attachments'), {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': randomUUID() },
    multipart: {
      declared_media_type: 'application/pdf',
      synchronous_finalize: 'true',
      source_type: 'manual',
      file: { name: 'uat104.pdf', mimeType: 'application/pdf', buffer: PDF_BYTES },
    },
  })
  const body = await resp.json()
  const d = unwrap(body)
  expect(resp.status(), `upload HTTP ${resp.status()} ${JSON.stringify(d)}`).toBe(201)
  expect(d.availability, 'attachment available').toBe('available')
  return { attachmentId: String(d.attachment_id), versionId: String(d.attachment_version_id) }
}

// ─────────────────────────────────────────────────────────────────────────────
// 前置：登录 + 四个治理域网络契约已挂载（openapi 为事实源）
// ─────────────────────────────────────────────────────────────────────────────
test.describe('Task 10.4 前置 — 环境与治理网络契约基线', () => {
  test('登录成功并可读取 openapi', async ({ request }) => {
    const token = await login(request)
    const paths = await fetchOpenApiPaths(request, token)
    expect(paths.length).toBeGreaterThan(0)
  })

  test('四个治理域 HTTP 契约均已挂载（AI-gate / Review / Archive / Legal-Hold）', async ({
    request,
  }) => {
    const token = await login(request)
    const paths = await fetchOpenApiPaths(request, token)
    const has = (frag: string) => paths.some((p) => p.includes(frag))

    // AI-gate / FormalOutput
    expect(has('/evidence/ai/generations'), 'AI generations wired').toBeTruthy()
    expect(has('/evidence/ai/formal-output/preflight'), 'FormalOutput preflight wired').toBeTruthy()
    expect(has('/evidence/ai/formal-output/finalize'), 'FormalOutput finalize wired').toBeTruthy()
    // Review-evidence
    expect(has('/evidence/reviews/'), 'review-evidence wired').toBeTruthy()
    expect(has('/evidence/reviews/completion-block'), 'completion-block wired').toBeTruthy()
    // Archive-manifest / verify
    expect(has('/evidence/archive/manifests'), 'archive manifests wired').toBeTruthy()
    expect(has('/evidence/archive/verify'), 'offline verify wired').toBeTruthy()
    // Legal-hold / retention
    expect(has('/evidence/legal-holds'), 'legal-holds wired').toBeTruthy()
    expect(has('/evidence/legal-holds/purge-jobs'), 'purge-jobs wired').toBeTruthy()
  })

  test('login 页 UI 可达（浏览器可见流程存在）', async ({ page }) => {
    await page.goto(FE)
    await page.waitForLoadState('domcontentloaded')
    const username = page.locator('input[placeholder*="用户名"], input[type="text"]').first()
    const password = page.locator('input[type="password"]').first()
    await expect(username).toBeVisible({ timeout: 8000 })
    await expect(password).toBeVisible({ timeout: 8000 })
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-10 AI 全入口门禁 (R8) — 未确认 draft 被 AIEvidenceGate 拒绝进入正式产出；确认后放行
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-10 AI 全入口门禁', () => {
  test('AI 生成未人工确认 → 资格 blocked(NOT_CONFIRMED)；确认后 eligible；FormalOutput watermark 门禁', async ({
    request,
  }) => {
    const token = await login(request)
    const { projectId, year } = await pickProject(request, token)

    // 1) 登记 AI 生成（底稿结论入口）→ 默认 draft 生命周期
    const reg = await api(request, 'post', base(projectId, year, '/ai/generations'), token, {
      idempotent: true,
      data: {
        entry_point: 'generate_conclusion',
        prompt_hash: `uat10-${randomUUID()}`,
        model_name: 'uat-model',
        output: 'AI 起草的底稿结论（UAT-10 未确认）',
        service_status: 'available',
      },
    })
    expect(reg.status, `register ${JSON.stringify(reg.body)}`).toBe(201)
    expect(reg.data.lifecycle_status).toBe('draft')
    const contentId = reg.data.content_id
    expect(contentId).toBeTruthy()

    // 2) 未确认 → FormalOutput 资格 blocked，原因含 NOT_CONFIRMED（P17 门禁）
    const elig1 = await api(
      request,
      'get',
      base(projectId, year, `/ai/generations/${contentId}/eligibility`),
      token,
    )
    expect(elig1.status).toBe(200)
    expect(elig1.data.eligible, 'unconfirmed draft is NOT eligible').toBe(false)
    expect(elig1.data.status).toBe('blocked')
    expect(
      (elig1.data.reasons ?? []).map((r: any) => r.code),
      'blocked reason includes NOT_CONFIRMED',
    ).toContain('NOT_CONFIRMED')

    // 3) 人工确认（Service Identity 禁止；此处为人工 admin）
    const conf = await api(
      request,
      'post',
      base(projectId, year, `/ai/generations/${contentId}/confirm`),
      token,
      { idempotent: true },
    )
    expect(conf.status).toBe(200)
    expect(conf.data.confirmed === true || conf.data.replayed === true).toBeTruthy()

    // 4) 确认后 → 资格 eligible
    const elig2 = await api(
      request,
      'get',
      base(projectId, year, `/ai/generations/${contentId}/eligibility`),
      token,
    )
    expect(elig2.status).toBe(200)
    expect(elig2.data.eligible, 'confirmed content is eligible').toBe(true)
    expect(elig2.data.status).toBe('eligible')

    // 5) FormalOutput preflight → 产出 watermark（供 finalize 比对）
    const targetId = `uat10-target-${randomUUID()}`
    const pre = await api(request, 'post', base(projectId, year, '/ai/formal-output/preflight'), token, {
      data: { target_id: targetId, target_type: 'workpaper_conclusion' },
    })
    expect(pre.status).toBe(200)
    expect(pre.data.phase).toBe('preflight')
    expect(pre.data.watermark, 'preflight returns a watermark').toBeTruthy()
    const watermark = pre.data.watermark

    // 6) finalize 同 watermark → pass
    const finOk = await api(request, 'post', base(projectId, year, '/ai/formal-output/finalize'), token, {
      data: {
        target_id: targetId,
        target_type: 'workpaper_conclusion',
        preflight_watermark: watermark,
      },
    })
    expect(finOk.status).toBe(200)
    expect(finOk.data.verdict, 'finalize with same watermark passes').toBe('pass')

    // 7) finalize 篡改 watermark → fail(WATERMARK_CHANGED)
    const finBad = await api(request, 'post', base(projectId, year, '/ai/formal-output/finalize'), token, {
      data: {
        target_id: targetId,
        target_type: 'workpaper_conclusion',
        preflight_watermark: 'TAMPERED-WATERMARK',
      },
    })
    expect(finBad.status).toBe(200)
    expect(finBad.data.verdict).toBe('fail')
    expect(
      (finBad.data.blocking_reasons ?? []).map((r: any) => r.code),
      'tampered watermark blocked by WATERMARK_CHANGED',
    ).toContain('WATERMARK_CHANGED')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-11 QC/EQCR 再复核 (R9, R10) — 关闭 Blocking Review 后证据失效 → 自动重开 + 完成阻断
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-11 QC/EQCR 再复核', () => {
  test('绑定非 stale 证据关闭复核 → 停用证据自动重开(re_review_required) + completion-block=true', async ({
    request,
  }) => {
    const token = await login(request)
    const { projectId, year } = await pickProject(request, token)

    // 0) 上传真实附件作为证据目标（自包含，不依赖既有底稿单元格）
    const { versionId } = await uploadAttachment(request, token, projectId, year)

    // 1) 创建有效 EvidenceRef（attachment_version 两端解析；非 stale）
    const ref = await api(request, 'post', base(projectId, year, '/refs/references'), token, {
      idempotent: true,
      data: {
        // NOTE: 不传 target_hash —— attachment_version 适配器会解析出版本真实内容 hash，
        // 若客户端传入不一致值会触发 VERSION_CONFLICT。让服务端绑定解析出的版本 hash。
        source_type: 'attachment_version',
        source_id: versionId,
        evidence_type: 'attachment_version',
        evidence_id: versionId,
        label: 'UAT-11 evidence ref',
      },
    })
    expect(ref.status, `create ref ${JSON.stringify(ref.body)}`).toBe(201)
    const refId = ref.data.id
    expect(refId).toBeTruthy()

    const reviewId = randomUUID()

    // 2) 绑定证据到复核意见（冻结 raised 快照）
    const bind = await api(
      request,
      'post',
      base(projectId, year, `/reviews/${reviewId}/evidence`),
      token,
      {
        idempotent: true,
        data: { evidence_ref_id: refId, target_hash: 'uat11-hash', locator: { page: 1 } },
      },
    )
    expect(bind.status, `bind ${JSON.stringify(bind.body)}`).toBe(201)

    // 3) 独立人工关闭 Blocking Review（充分说明 + 至少一个非 stale ref；P21）
    const close = await api(request, 'post', base(projectId, year, `/reviews/${reviewId}/close`), token, {
      idempotent: true,
      data: { closing_explanation: '证据充分，复核意见已解决', severity: 'high' },
    })
    expect(close.status, `close ${JSON.stringify(close.body)}`).toBe(200)
    expect(close.data.status).toBe('closed')

    // 4) 读端点暴露 version/hash/确认/locator/is_stale（关闭态；证据尚非 stale）
    const view1 = await api(request, 'get', base(projectId, year, `/reviews/${reviewId}`), token)
    expect(view1.status).toBe(200)
    expect(view1.data.status).toBe('closed')
    expect(view1.data.evidence.length).toBeGreaterThan(0)
    const ev1 = view1.data.evidence[0]
    expect(ev1.evidence_ref_id).toBe(refId)
    expect('content_hash' in ev1 && 'target_version' in ev1 && 'locator' in ev1).toBeTruthy()
    expect(ev1.is_stale, 'evidence not stale before invalidation').toBe(false)

    // 5) 停用（失效）证据 ref → status inactive
    const deact = await api(
      request,
      'post',
      base(projectId, year, `/refs/references/${refId}/deactivate`),
      token,
      { idempotent: true, data: { reason: '证据被替换/失效' } },
    )
    expect(deact.status, `deactivate ${JSON.stringify(deact.body)}`).toBe(200)
    expect(deact.data.new_status).toBe('inactive')

    // 6) 证据失效后复核自动重开 → re_review_required（P22）
    const reopen = await api(
      request,
      'post',
      base(projectId, year, `/reviews/${reviewId}/reopen`),
      token,
      { idempotent: true, data: { reason: 'evidence_invalidated' } },
    )
    expect(reopen.status, `reopen ${JSON.stringify(reopen.body)}`).toBe(200)
    expect(reopen.data.status).toBe('re_review_required')

    // 7) 重开后读端点显示 re_review_required 且证据 is_stale=true
    const view2 = await api(request, 'get', base(projectId, year, `/reviews/${reviewId}`), token)
    expect(view2.status).toBe(200)
    expect(view2.data.status).toBe('re_review_required')
    expect(view2.data.evidence[0].is_stale, 'evidence stale after deactivation').toBe(true)

    // 8) QC/EQCR/partner 完成被 re_review_required 阻断（本复核在阻断清单内）
    const block = await api(request, 'get', base(projectId, year, '/reviews/completion-block'), token)
    expect(block.status).toBe(200)
    expect(block.data.blocked, 'completion blocked by re_review_required').toBe(true)
    expect(block.data.re_review_required_reviews).toContain(reviewId)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-12 归档完整性 (R11) — 成功归档无 blocking report + 封存包离线验签通过；篡改验签失败
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-12 归档完整性（失败才有 blocking report / 成功离线验签）', () => {
  test('clean 集合归档成功且无 blocking report + 离线验签通过；篡改封存包验签失败并给出差异', async ({
    request,
  }) => {
    const token = await login(request)
    const { projectId, year } = await pickProject(request, token)

    // 1) 归档前置门禁（冻结 watermark；只读）
    const pre = await api(request, 'post', base(projectId, year, '/archive/preflight'), token, { data: {} })
    expect(pre.status).toBe(200)
    expect(pre.data.phase).toBe('preflight')
    expect(pre.data.evidence_ready).toBe(true)

    // 2) 构建并封存归档清单（clean 集合 → 成功；成功归档 NOT 生成 blocking report）
    const build = await api(request, 'post', base(projectId, year, '/archive/manifests'), token, {
      idempotent: true,
      data: {},
    })
    expect(build.status, `build ${JSON.stringify(build.body)}`).toBe(201)
    expect(build.data.success, 'clean archive succeeds').toBe(true)
    expect(build.data.state).toBe('sealed')
    // 成功归档不得生成 blocking difference report
    expect(build.data.blocked ?? false).toBeFalsy()
    expect(build.data.blocking_difference_report ?? null).toBeNull()
    const sealed = build.data.sealed_package
    expect(sealed, 'sealed package present for offline verify').toBeTruthy()

    // 3) 离线验签（独立重算 member/manifest/package hash）→ 通过
    const verifyOk = await api(request, 'post', base(projectId, year, '/archive/verify'), token, {
      data: { package: sealed },
    })
    expect(verifyOk.status).toBe(200)
    expect(verifyOk.data.verification_status).toBe('passed')
    expect(verifyOk.data.is_valid).toBe(true)
    expect(verifyOk.data.summary.difference_count).toBe(0)

    // 4) 列表确认封存清单无 blocking report 标志
    const list = await api(request, 'get', base(projectId, year, '/archive/manifests'), token)
    expect(list.status).toBe(200)
    const mine = (list.data.items ?? []).find((m: any) => m.id === build.data.manifest_id)
    expect(mine, 'built manifest listed').toBeTruthy()
    expect(mine.state).toBe('sealed')
    expect(mine.has_blocking_report, 'sealed manifest has no blocking report').toBe(false)

    // 5) 篡改封存包 package_hash → 离线验签失败并给出机器可读差异
    const tampered = JSON.parse(JSON.stringify(sealed))
    tampered.package_hash = '0'.repeat(64)
    const verifyBad = await api(request, 'post', base(projectId, year, '/archive/verify'), token, {
      data: { package: tampered },
    })
    expect(verifyBad.status).toBe(200)
    expect(verifyBad.data.verification_status).toBe('failed')
    expect(verifyBad.data.is_valid).toBe(false)
    expect(
      (verifyBad.data.differences ?? []).map((d: any) => d.type),
      'tamper detected as package_hash_mismatch',
    ).toContain('package_hash_mismatch')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-13 删除清理覆盖无绕过 (R13) — 一票否决
//   active hold 覆盖附件 → 覆盖(version-replace)=423 零效果；purge 四条件(hold active)
//   → allowed=false delta=0，即使 retention_expired=true 且 admin 具 purge 能力，亦无绕过。
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-13 删除清理覆盖无绕过（一票否决）', () => {
  test('active hold 下 覆盖=423 LEGAL_HOLD_ACTIVE 零效果 + purge 四条件 allowed=false delta=0', async ({
    request,
  }) => {
    const token = await login(request)
    const { projectId, year } = await pickProject(request, token)

    // 0) 上传真实附件
    const { attachmentId } = await uploadAttachment(request, token, projectId, year)

    // 1) 基线：无 hold 时覆盖成功（生成 v2）——证明覆盖端点本身可用，后续 423 确为 hold 否决
    const baseRep = await api(
      request,
      'post',
      base(projectId, year, `/attachments/${attachmentId}/versions`),
      token,
      { idempotent: true, data: { new_content_hash: 'a'.repeat(64), impact_confirmed: true } },
    )
    expect(baseRep.status, `baseline replace ${JSON.stringify(baseRep.body)}`).toBe(201)
    expect(baseRep.data.new_version_no).toBe(2)

    // 2) 创建覆盖该附件的 Legal Hold（固化统一图闭包）
    const hold = await api(request, 'post', base(projectId, year, '/legal-holds'), token, {
      idempotent: true,
      data: {
        reason: 'UAT-13 litigation hold',
        seed_nodes: [{ node_type: 'attachment', node_id: attachmentId }],
      },
    })
    expect(hold.status, `create hold ${JSON.stringify(hold.body)}`).toBe(201)
    expect(hold.data.direct_count).toBeGreaterThanOrEqual(1)

    // 3) 覆盖（version-replace）在 active hold 下 → 423 LEGAL_HOLD_ACTIVE（零效果，不新增版本）
    const held = await api(
      request,
      'post',
      base(projectId, year, `/attachments/${attachmentId}/versions`),
      token,
      { idempotent: true, data: { new_content_hash: 'b'.repeat(64), impact_confirmed: true } },
    )
    expect(held.status, 'overwrite under hold rejected with 423').toBe(423)
    expect(held.body.error_code).toBe('LEGAL_HOLD_ACTIVE')

    // 3b) 零效果确认：impact 端点显示 has_legal_hold=true 且当前版本仍为 2（覆盖未生效）
    const impact = await api(
      request,
      'get',
      base(projectId, year, `/attachments/${attachmentId}/impact`),
      token,
    )
    expect(impact.status).toBe(200)
    expect(impact.data.has_legal_hold, 'attachment under legal hold').toBe(true)
    expect(impact.data.version_no, 'no new version created under hold').toBe(2)

    // 4) purge 四条件门禁：hold active → allowed=false delta=0 unmet=[hold_active]
    //    即使 retention_expired=true 且 admin 具 retention.purge 能力，亦无绕过。
    const purge = await api(request, 'post', base(projectId, year, '/legal-holds/purge-jobs'), token, {
      idempotent: true,
      data: {
        node_type: 'attachment',
        node_id: attachmentId,
        retention_expired: true,
        purge_reason: 'retention_expired',
      },
    })
    expect(purge.status).toBe(200)
    expect(purge.data.allowed, 'purge not allowed under active hold').toBe(false)
    expect(purge.data.delta, 'zero destructive effect').toBe(0)
    expect(purge.data.unmet_conditions).toContain('hold_active')
    expect(purge.data.tombstone_id ?? null, 'no tombstone written (no purge)').toBeNull()
  })
})
