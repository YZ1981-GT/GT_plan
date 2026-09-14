/**
 * E2E / UAT — 证据治理「安全接收」套件（Task 10.1, Wave 9）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R1, R3, R4, R12
 * Design: §5.1 流式上传与安全读取, §6.2 端点, §7.2 稳定失败类别,
 *         §10.2 测试分层与 Playwright 边界（第 5 层）, §12 UAT-01～03 Design Matrix
 *
 * 本套件按设计 §10.2 只验证「用户可见、浏览器/网络可达」的边界与网络契约，
 * 且现在真实驱动已接线的治理 HTTP 端点（不再只探测可达性 / 占位 id）：
 *
 *   - UAT-01 附件安全接收（R1/R12）：经安全上传端点上传 legal / MIME-mismatch /
 *            empty / 未认证；每次上传先形成 UploadAttempt（outcome != pending），
 *            仅合法文件形成可用 Attachment/Version；非法上传无可用记录、无可访问恶意内容。
 *   - UAT-02 越界读取阻断（R1/R12/R15，一票否决）：越界 / 跨项目 / 不存在的读取在
 *            读取字节前被拒绝，返回脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN，不泄露路径或存在性；
 *            同 scope 合法读取只返回 opaque locator（绝不返回绝对路径）。
 *   - UAT-03 跨项目关联阻断（R3/R4，一票否决）：把项目 A 的附件版本关联到项目 B 的底稿被拒绝，
 *            返回干净的 4xx（非 500、非 201），关联数不变，且不暴露 B 的信息。
 *
 * 端点契约（已接线，start-dev.bat 后端 9980）：
 *   POST /api/projects/{pid}/years/{yr}/evidence/attachments                     — 安全上传
 *   GET  /api/projects/{pid}/years/{yr}/evidence/attachments/{aid}/content       — 安全读取（by attachment）
 *   GET  /api/projects/{pid}/years/{yr}/evidence/attachments/versions/{vid}/content — 安全读取（by version）
 *   POST /api/projects/{pid}/years/{yr}/evidence/refs/references                 — 创建 EvidenceRef
 *   GET  /api/projects/{pid}/years/{yr}/evidence/refs/references                 — 双向查询 EvidenceRef
 *
 * 本层不替代 PG 约束/并发/trigger、PBT、offline verifier 或 6000 VU（各由专用测试证明）。
 *
 * ⚠ 诚实性声明（禁止假绿）：断言按 requirements/design 的**目标契约**编写。
 * 若端点未接线（404）、崩溃（500）或行为不符合契约，断言会如实失败以暴露真实缺口。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

// 后端直连（与 start-dev.bat 的 9980 一致）；UI 走 baseURL(3030)。
const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:9980'

interface ProjectScope {
  id: string
  year: number
}

/** ResponseWrapperMiddleware 只包装 2xx JSON 为 {code,message,data}；
 *  由 EvidenceGovernanceError handler 产生的错误体是顶层 {code,error_code,message,...}，
 *  由端点直接 return 的非 2xx 体（如 415/422 的 attempt 结果）也是顶层未包装。
 *  统一解包：有 data 对象则取 data，否则取原体。 */
function unwrap(body: any): any {
  if (body && typeof body === 'object' && body.data && typeof body.data === 'object') {
    return body.data
  }
  return body ?? {}
}

async function healthy(request: APIRequestContext): Promise<boolean> {
  try {
    const r = await request.get(`${BACKEND}/api/health`, { timeout: 5000 })
    return r.status() === 200
  } catch {
    return false
  }
}

async function loginToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${BACKEND}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), '登录应成功').toBeTruthy()
  const body = await resp.json()
  const token = body?.data?.access_token ?? body?.access_token
  expect(token, 'access_token 应存在').toBeTruthy()
  return token as string
}

/** 取两个当前用户可访问的、彼此不同的项目 scope（用于跨项目/跨 scope 否决）。 */
async function twoProjects(
  request: APIRequestContext,
  token: string,
): Promise<[ProjectScope, ProjectScope] | null> {
  const resp = await request.get(`${BACKEND}/api/projects?page=1&page_size=20`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const items: any[] = Array.isArray(body?.data) ? body.data : body?.data?.items ?? []
  const scopes: ProjectScope[] = items
    .filter((p) => p?.id)
    .map((p) => ({ id: String(p.id), year: Number(p.audit_year) || 2025 }))
  // 去重到两个不同的项目 id。
  const uniq: ProjectScope[] = []
  for (const s of scopes) {
    if (!uniq.some((u) => u.id === s.id)) uniq.push(s)
    if (uniq.length === 2) break
  }
  if (uniq.length < 2) return null
  return [uniq[0], uniq[1]]
}

/** 经安全上传端点上传一份合法附件，返回可用 Attachment/Version id（自供测试数据）。 */
async function uploadLegal(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
): Promise<{ attachmentId: string; versionId: string }> {
  const resp = await request.post(
    `${BACKEND}/api/projects/${proj.id}/years/${proj.year}/evidence/attachments`,
    {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat01-legal-${Date.now()}` },
      multipart: {
        file: { name: 'legal.txt', mimeType: 'text/plain', buffer: Buffer.from('legal evidence content') },
        declared_media_type: 'text/plain',
      },
    },
  )
  expect(resp.status(), '合法上传应 201').toBe(201)
  const data = unwrap(await resp.json())
  expect(data.attachment_id, '合法上传应返回可用 attachment_id').toBeTruthy()
  expect(data.attachment_version_id, '合法上传应返回可用 attachment_version_id').toBeTruthy()
  return { attachmentId: String(data.attachment_id), versionId: String(data.attachment_version_id) }
}

test.describe('证据治理 UAT — 安全接收套件 (R1/R3/R4/R12)', () => {
  test.beforeAll(async ({ request }) => {
    if (!(await healthy(request))) {
      test.skip(true, `后端 ${BACKEND} 不健康，跳过安全接收 UAT`)
    }
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 前置：浏览器可达 + 真实 UI 登录（design §10.2 用户可见流程）
  // ───────────────────────────────────────────────────────────────────────────
  test('前置：UI 登录可达并建立会话', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible()
    const token = await page.evaluate(() => sessionStorage.getItem('token'))
    expect(token, '登录后浏览器会话应持有 token').toBeTruthy()
  })

  // ───────────────────────────────────────────────────────────────────────────
  // UAT-01 附件安全接收（R1/R12）
  //   每次上传先建最小 UploadAttempt（内容验证之前）→ 流式验证；仅合法 available；
  //   非法（MIME 不符 / 空 / 未认证）无可用 Attachment/Version 且无可访问恶意内容。
  // ───────────────────────────────────────────────────────────────────────────
  test('UAT-01 附件安全接收：每次上传先形成 UploadAttempt，仅合法文件形成可用记录', async ({
    request,
  }) => {
    const token = await loginToken(request)
    const projects = await twoProjects(request, token)
    test.skip(!projects, '无可用项目，无法执行 UAT-01')
    const [projA] = projects!
    const uploadUrl = `${BACKEND}/api/projects/${projA.id}/years/${projA.year}/evidence/attachments`

    // (1) 合法文件 → 201 available，形成可用 Attachment/Version（accepted attempt）。
    const legal = await request.post(uploadUrl, {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat01-legal-${Date.now()}` },
      multipart: {
        file: { name: 'legal.txt', mimeType: 'text/plain', buffer: Buffer.from('legal evidence content') },
        declared_media_type: 'text/plain',
      },
    })
    expect(legal.status(), '合法上传应 201 available').toBe(201)
    const legalData = unwrap(await legal.json())
    expect(legalData.attempt_id, '合法上传必须先形成 UploadAttempt').toBeTruthy()
    expect(legalData.outcome, '合法上传 outcome 应为 accepted（非 pending）').toBe('accepted')
    expect(legalData.is_available, '合法上传应可用').toBeTruthy()
    expect(legalData.attachment_id, '合法上传应有可用 Attachment').toBeTruthy()
    expect(legalData.attachment_version_id, '合法上传应有可用 Version').toBeTruthy()

    // (2) MIME 不符（声明 pdf，字节为 PNG）→ 415 rejected，无可用记录，无可访问恶意内容。
    const pngBytes = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(32)])
    const mismatch = await request.post(uploadUrl, {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat01-mismatch-${Date.now()}` },
      multipart: {
        file: { name: 'evil.pdf', mimeType: 'application/pdf', buffer: pngBytes },
        declared_media_type: 'application/pdf',
      },
    })
    expect(mismatch.status(), 'MIME 不符应 415（稳定失败类别 §7.2）').toBe(415)
    const mismatchData = unwrap(await mismatch.json())
    expect(mismatchData.attempt_id, 'MIME 不符也必须先形成 UploadAttempt').toBeTruthy()
    expect(
      ['rejected', 'quarantined', 'failed'],
      'MIME 不符的 attempt 必须收敛为失败终态（非 pending）',
    ).toContain(mismatchData.outcome)
    // 无可用记录：不得暴露可用 Attachment/Version（无可访问恶意内容）。
    expect(mismatchData.attachment_id ?? null, 'MIME 不符不得创建可用 Attachment').toBeNull()
    expect(mismatchData.availability ?? null, 'MIME 不符不得进入 available').toBeNull()

    // (3) 空文件 → 422 rejected，无可用记录。
    const empty = await request.post(uploadUrl, {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat01-empty-${Date.now()}` },
      multipart: {
        file: { name: 'empty.txt', mimeType: 'text/plain', buffer: Buffer.alloc(0) },
        declared_media_type: 'text/plain',
      },
    })
    expect(empty.status(), '空文件应 4xx 拒绝（非 5xx）').toBeGreaterThanOrEqual(400)
    expect(empty.status(), '空文件不得 5xx 崩溃').toBeLessThan(500)
    const emptyData = unwrap(await empty.json())
    expect(
      ['rejected', 'quarantined', 'failed'],
      '空文件的 attempt 必须收敛为失败终态',
    ).toContain(emptyData.outcome)
    expect(emptyData.availability ?? null, '空文件不得进入 available').toBeNull()

    // (4) 未认证上传（无 actor）→ 401/403，不得形成可用记录（actor 完备性 R1/P3）。
    const noAuth = await request.post(uploadUrl, {
      multipart: {
        file: { name: 'legal.txt', mimeType: 'text/plain', buffer: Buffer.from('x') },
        declared_media_type: 'text/plain',
      },
    })
    expect([401, 403], '未认证上传必须被拒绝').toContain(noAuth.status())
  })

  // ───────────────────────────────────────────────────────────────────────────
  // UAT-02 越界读取阻断（一票否决）
  //   scope/权限/边界先于字节 I/O；跨项目 / 不存在 / 越界统一脱敏拒绝；
  //   同 scope 合法读取只返回 opaque locator，绝不返回绝对路径。
  // ───────────────────────────────────────────────────────────────────────────
  test('UAT-02 越界读取阻断：读取字节前拒绝且不泄露路径或文件存在性【一票否决】', async ({
    request,
  }) => {
    const token = await loginToken(request)
    const projects = await twoProjects(request, token)
    test.skip(!projects, '无可用项目，无法执行 UAT-02')
    const [projA, projB] = projects!

    // 自供真实数据：在项目 A 上传一份合法附件。
    const { attachmentId, versionId } = await uploadLegal(request, token, projA)

    // (a) 同 scope 合法读取 → 200，且只返回 opaque locator（绝不含绝对路径 / storage_key）。
    const okRead = await request.get(
      `${BACKEND}/api/projects/${projA.id}/years/${projA.year}/evidence/attachments/${attachmentId}/content`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(okRead.status(), '同 scope 合法读取应 200').toBe(200)
    const okBody = await okRead.text()
    const okData = unwrap(JSON.parse(okBody))
    expect(okData.locator, '成功读取应返回受控下载 URL（opaque locator）').toContain('/api/attachments/')
    expect(okBody, '成功读取不得泄露绝对路径（盘符）').not.toMatch(/[A-Za-z]:\\/)
    expect(okBody.toLowerCase(), '成功读取不得泄露文件系统 storage 路径').not.toContain('storage/')

    // (a2) by-version 安全读取路径同样可达（边界先于字节 I/O）。
    const okVer = await request.get(
      `${BACKEND}/api/projects/${projA.id}/years/${projA.year}/evidence/attachments/versions/${versionId}/content`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(okVer.status(), 'by-version 同 scope 读取应 200').toBe(200)

    // (b) 跨 scope 读取：从项目 B 的 scope 读取属于项目 A 的附件 → 边界先于字节，脱敏拒绝。
    const crossRead = await request.get(
      `${BACKEND}/api/projects/${projB.id}/years/${projB.year}/evidence/attachments/${attachmentId}/content`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const crossText = await crossRead.text()
    expect(crossRead.status(), '跨 scope 读取不得 200（不得越界读到 A 的内容）').not.toBe(200)
    expect(crossRead.status(), '跨 scope 读取必须干净 4xx（非 5xx 崩溃）').toBeGreaterThanOrEqual(400)
    expect(crossRead.status(), '跨 scope 读取不得 5xx').toBeLessThan(500)
    expect(unwrap(JSON.parse(crossText)).error_code, '跨 scope 读取应脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN').toBe(
      'SCOPE_NOT_FOUND_OR_FORBIDDEN',
    )
    expect(crossText, '跨 scope 拒绝不得泄露绝对路径').not.toMatch(/[A-Za-z]:\\/)
    expect(crossText.toLowerCase(), '跨 scope 拒绝不得泄露 storage 路径').not.toContain('storage/')

    // (c) 不存在的 id（越界代理）→ 404 脱敏，不泄露存在性。
    const missing = await request.get(
      `${BACKEND}/api/projects/${projA.id}/years/${projA.year}/evidence/attachments/00000000-0000-0000-0000-0000000000ff/content`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(missing.status(), '不存在读取应 404').toBe(404)
    expect(unwrap(await missing.json()).error_code).toBe('SCOPE_NOT_FOUND_OR_FORBIDDEN')

    // (d) 路径遍历 / 畸形 id（非 UUID）→ 脱敏拒绝，不得 5xx，不泄露路径。
    const traversal = await request.get(
      `${BACKEND}/api/projects/${projA.id}/years/${projA.year}/evidence/attachments/${encodeURIComponent(
        '../../etc/passwd',
      )}/content`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(traversal.status(), '路径遍历/畸形 id 必须 4xx（非 5xx）').toBeGreaterThanOrEqual(400)
    expect(traversal.status(), '路径遍历/畸形 id 不得 5xx').toBeLessThan(500)
    expect((await traversal.text()).toLowerCase(), '遍历拒绝不得泄露 storage 路径').not.toContain('storage/')
  })

  // ───────────────────────────────────────────────────────────────────────────
  // UAT-03 跨项目关联阻断（一票否决）
  //   把项目 A 的附件版本关联到项目 B 的底稿单元格 → 干净 4xx（非 500、非 201）；
  //   关联数不变；不暴露 B 的信息。
  // ───────────────────────────────────────────────────────────────────────────
  test('UAT-03 跨项目关联阻断：关联数不变且响应不暴露 B 信息【一票否决】', async ({
    request,
  }) => {
    const token = await loginToken(request)
    const projects = await twoProjects(request, token)
    test.skip(!projects, '需要至少两个项目执行跨项目关联否决')
    const [projA, projB] = projects!

    // 自供真实数据：项目 A 的真实附件版本（合法上传）。
    const { versionId: foreignVersionId } = await uploadLegal(request, token, projA)

    const refsBase = `${BACKEND}/api/projects/${projB.id}/years/${projB.year}/evidence/refs/references`

    // 关联数（before）：项目 B scope 内、以该外部版本为证据的关联数（应为 0）。
    const listBefore = await request.get(
      `${refsBase}?direction=evidence&evidence_type=attachment_version&evidence_id=${foreignVersionId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(listBefore.status(), '双向查询应可达').toBe(200)
    const countBefore = (unwrap(await listBefore.json()).items ?? []).length

    // 尝试：在项目 B 的 scope 下，把「底稿单元格」关联到属于项目 A 的附件版本。
    const sourceCellUuid = '00000000-0000-0000-0000-0000000000cc' // 项目 B 的底稿单元格（合法 UUID 形态）
    const resp = await request.post(refsBase, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Idempotency-Key': `uat03-${Date.now()}`,
      },
      data: {
        source_type: 'workpaper_cell',
        source_id: sourceCellUuid,
        evidence_type: 'attachment_version',
        evidence_id: foreignVersionId,
      },
    })
    const status = resp.status()
    const bodyText = await resp.text()

    // (1) 不得创建关联：不得 201 Created。
    expect(status, `跨项目关联必须被拒绝，不得创建（收到 ${status}）`).not.toBe(201)
    // (2) 必须是干净的拒绝：4xx（403/404/409/422），而非 500 崩溃。
    expect(
      status >= 400 && status < 500,
      `跨项目关联必须以干净 4xx 否决返回（design §7.2 SCOPE_NOT_FOUND_OR_FORBIDDEN），实际 ${status}。` +
        `500 表示端点缺陷而非设计否决。\nbody: ${bodyText}`,
    ).toBeTruthy()
    expect(unwrap(JSON.parse(bodyText)).error_code, '跨项目关联应脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN').toBe(
      'SCOPE_NOT_FOUND_OR_FORBIDDEN',
    )
    // (3) 不得泄露项目 B 的信息 / 文件系统路径。
    expect(bodyText, '否决响应不得包含项目 B 的 UUID').not.toContain(projB.id)
    expect(bodyText.toLowerCase(), '否决响应不得泄露文件系统路径').not.toContain('storage/')

    // (4) 畸形 source_id（非 UUID）同样必须干净 4xx（回归守卫：边界先于业务，绝不 5xx）。
    const malformed = await request.post(refsBase, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Idempotency-Key': `uat03-malformed-${Date.now()}`,
      },
      data: {
        source_type: 'workpaper_cell',
        source_id: 'D2-1!B5', // 人类可读单元格引用，非 UUID
        evidence_type: 'attachment_version',
        evidence_id: foreignVersionId,
      },
    })
    expect(malformed.status(), '畸形 source_id 必须 4xx（非 5xx）').toBeGreaterThanOrEqual(400)
    expect(malformed.status(), '畸形 source_id 不得 5xx 崩溃').toBeLessThan(500)

    // (5) 关联数不变：项目 B scope 内以该外部版本为证据的关联数仍为 before。
    const listAfter = await request.get(
      `${refsBase}?direction=evidence&evidence_type=attachment_version&evidence_id=${foreignVersionId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const countAfter = (unwrap(await listAfter.json()).items ?? []).length
    expect(countAfter, '跨项目关联被否决后，关联数必须不变').toBe(countBefore)
  })
})
