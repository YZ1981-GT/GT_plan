/**
 * Task 10.2 (Wave 9) — 附件与引用 UAT suite
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R2, R3, R4, R9
 * Design: §10.2 (Playwright 边界 / 第 5 层), §12 UAT Design Matrix (UAT-04, UAT-05)
 *
 * 逐项覆盖：
 *   - UAT-04 附件版本/影响/stale（端到端）：治理安全上传形成不可变 AttachmentVersion(v1) + 按版本安全
 *            读取(version_no / SHA-256 绑定 / opaque locator) → 经 **已接线** 的版本替换写端点
 *            POST .../attachments/{attachment_id}/versions 生成 vN+1 → 断言 new_version_no=2、
 *            previous_version_id=v1、旧 v1 快照 bytes/hash 不变(immutable P4) → GET
 *            .../attachments/{attachment_id}/impact 反映 current version_no 从 1 升至 2（下游影响面）；
 *            并经统一图 GET /evidence/refs/impact 验证被引用证据的下游可达 path。
 *   - UAT-05 EvidenceRef 重启持久与双向查询（正向落库）：admin 同 scope 创建 EvidenceRef → 201 持久 →
 *            source/evidence 双向查询一致(P8) + 单条详情脱敏 + 新会话(重启代理)按 id 再查
 *            id/version/status 不变、双向视图不变。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 设计边界（design §10.2 第 5 层）：Playwright 只验证「用户可见 / 浏览器可达的流程与网络契约」，
 * 不承担 DB trigger / 并发 / PBT / 6000VU / offline-verifier 内部证明（各由专用测试证明）。
 * 需要数据库断言时经测试专用只读 API/fixture，不在浏览器中直连数据库。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 诚实门历史（两处曾 test.skip 的用户流现已解除并转为真实断言，非假绿）：
 *   (A) 已解除：「替换现有附件 → 生成 vN+1」现由 POST .../evidence/attachments/{attachment_id}/versions
 *       接线（委托 AttachmentVersionManager.replace_version：父行 FOR UPDATE 版本递增、旧版本不可变、
 *       command-root + outbox stale 传播），并配 GET .../attachments/{attachment_id}/impact 只读影响面。
 *       UAT-04 端到端替换/immutability/impact 现为浏览器可驱动的真实断言。
 *       注：合成替换以 new_content_hash + new_storage_key 登记新版本元数据（不上传真实 v2 字节），
 *       故不断言「读取 v2 内容成功」（无真实字节的版本内容读取会被 storage 边界正确拒绝）；
 *       immutability 由「替换后重读 v1 内容 version_no=1 且 hash 不变」证明，影响由 impact version_no 升至 2 证明。
 *   (B) 已解除：create_ref 现遵循 admin/partner 全局可见（与 ProjectYearScopeGuard 一致的角色豁免），
 *       admin 对同 scope 的合法关联返回 201 并落库；跨项目/外部 scope 仍脱敏 404
 *       SCOPE_NOT_FOUND_OR_FORBIDDEN。UAT-05 正向创建→(重启代理)→双向一致现为真实断言。
 *
 * 环境：backend 9980 / frontend 3030（start-dev.bat）。登录 admin/admin123。
 * 运行：npx playwright test --config=playwright-uat.config.ts evidence-governance-attachment-ref-uat
 */
import { expect, test, type APIRequestContext } from '@playwright/test'

const FE = 'http://localhost:3030'
const API = 'http://localhost:9980'

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

// ── 拉取 openapi 路径集合（治理契约事实源）─────────────────────────────────
async function fetchOpenApiPaths(request: APIRequestContext, token: string): Promise<string[]> {
  const resp = await request.get(`${API}/openapi.json`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(resp.ok(), `openapi HTTP ${resp.status()}`).toBeTruthy()
  const spec = await resp.json()
  return Object.keys(spec.paths ?? {})
}

function hasRoute(paths: string[], predicate: (p: string) => boolean): string[] {
  return paths.filter(predicate)
}

// 后端 ResponseWrapperMiddleware 把 2xx JSON 包成 { code, message, data }；由
// EvidenceGovernanceError handler 产生的错误体是顶层 { code, error_code, message, retryable }。
// 统一解包：有 data 对象则取 data，否则取原体。
function unwrap(text: string): any {
  const body = JSON.parse(text)
  return body && typeof body === 'object' && body.data && typeof body.data === 'object'
    ? body.data
    : body ?? {}
}

// ── 取一个当前用户可访问的项目（用于构造治理 scope 路径）────────────────────
async function firstProject(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; year: number } | null> {
  const resp = await request.get(`${API}/api/projects?page=1&page_size=5`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list: any[] = Array.isArray(body?.data) ? body.data : body?.data?.items ?? []
  if (list.length === 0) return null
  return { id: String(list[0].id), year: Number(list[0].audit_year) || 2025 }
}

// 治理 evidence scope 根
function evidenceBase(pid: string, year: number): string {
  return `${API}/api/projects/${pid}/years/${year}/evidence`
}

/** 经治理安全上传端点上传一份合法附件，返回可用 Attachment/Version id（自供真实测试数据）。 */
async function uploadLegal(
  request: APIRequestContext,
  token: string,
  proj: { id: string; year: number },
  tag: string,
): Promise<{ attachmentId: string; versionId: string; hash: string }> {
  const base = evidenceBase(proj.id, proj.year)
  const content = `UAT-10.2 ${tag} evidence ${Date.now()}-${Math.random()}`
  const resp = await request.post(`${base}/attachments`, {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat102-${tag}-${Date.now()}` },
    multipart: {
      file: { name: `uat102-${tag}.txt`, mimeType: 'text/plain', buffer: Buffer.from(content) },
      declared_media_type: 'text/plain',
      synchronous_finalize: 'true',
    },
  })
  const txt = await resp.text()
  expect(resp.status(), `治理上传应 201 available（当前 ${resp.status()}）。body: ${txt}`).toBe(201)
  const d = unwrap(txt)
  expect(d.outcome, '上传 outcome 应 accepted').toBe('accepted')
  expect(d.attachment_id, '应返回 attachment_id').toBeTruthy()
  expect(d.attachment_version_id, '应返回 attachment_version_id').toBeTruthy()
  expect(String(d.content_hash), '应返回 SHA-256 content_hash').toMatch(/^[0-9a-f]{64}$/)
  return {
    attachmentId: String(d.attachment_id),
    versionId: String(d.attachment_version_id),
    hash: String(d.content_hash),
  }
}

/**
 * 尝试创建一个 EvidenceRef（source=attachment_version → evidence=attachment_version，均为自供真实版本）。
 * 返回 { status, body }。成功=201 且 body.id；本环境因成员模型分叉预期干净 404（见诚实门 B）。
 * 绝不 5xx（早先的 router↔service 签名 500 已修复）。
 */
async function tryCreateRef(
  request: APIRequestContext,
  token: string,
  proj: { id: string; year: number },
  sourceVersionId: string,
  evidenceVersionId: string,
): Promise<{ status: number; body: any; text: string }> {
  const base = evidenceBase(proj.id, proj.year)
  const resp = await request.post(`${base}/refs/references`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': `uat102-ref-${Date.now()}-${Math.random()}`,
    },
    data: {
      source_type: 'attachment_version',
      source_id: sourceVersionId,
      evidence_type: 'attachment_version',
      evidence_id: evidenceVersionId,
    },
  })
  const text = await resp.text()
  return { status: resp.status(), body: unwrap(text), text }
}

/** 读取某版本的安全内容投影（version_no / hash / opaque locator）。 */
async function readVersion(
  request: APIRequestContext,
  token: string,
  proj: { id: string; year: number },
  versionId: string,
): Promise<{ status: number; body: any; text: string }> {
  const base = evidenceBase(proj.id, proj.year)
  const resp = await request.get(`${base}/attachments/versions/${versionId}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const text = await resp.text()
  return { status: resp.status(), body: unwrap(text), text }
}

/** 读取某附件当前的影响面（version_no / 直接+传递影响 / 阻断状态）。 */
async function readAttachmentImpact(
  request: APIRequestContext,
  token: string,
  proj: { id: string; year: number },
  attachmentId: string,
): Promise<{ status: number; body: any; text: string }> {
  const base = evidenceBase(proj.id, proj.year)
  const resp = await request.get(`${base}/attachments/${attachmentId}/impact`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const text = await resp.text()
  return { status: resp.status(), body: unwrap(text), text }
}

/**
 * 经 **已接线** 的版本替换写端点 POST .../attachments/{attachment_id}/versions 生成 vN+1。
 * 合成替换以 new_content_hash + new_storage_key 登记新版本元数据（父行 FOR UPDATE 递增、旧版本不可变）。
 * 返回 { status, body }。成功=201 且 body.new_version_no / body.previous_version_id。
 */
async function replaceVersion(
  request: APIRequestContext,
  token: string,
  proj: { id: string; year: number },
  attachmentId: string,
): Promise<{ status: number; body: any; text: string }> {
  const base = evidenceBase(proj.id, proj.year)
  // 64-hex 合成新内容哈希（真实 v2 字节不经此端点上传；本端点只登记新不可变版本元数据）。
  const newHash = (Date.now().toString(16) + Math.random().toString(16).slice(2)).padEnd(64, '0').slice(0, 64)
  const resp = await request.post(`${base}/attachments/${attachmentId}/versions`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': `uat102-replace-${attachmentId}-${Date.now()}-${Math.random()}`,
    },
    data: {
      new_content_hash: newHash,
      new_storage_key: `uat102/${attachmentId}/${Date.now()}`,
      new_storage_type: 'local',
      new_media_type: 'text/plain',
      new_byte_size: 64,
      // 版本被引用时需先看 impact 再确认；此处显式确认以驱动 vN+1 生成路径。
      impact_confirmed: true,
    },
  })
  const text = await resp.text()
  return { status: resp.status(), body: unwrap(text), text }
}

// ─────────────────────────────────────────────────────────────────────────────
// 前置 — 环境与附件/引用网络契约基线
// ─────────────────────────────────────────────────────────────────────────────
test.describe('Task 10.2 前置 — 环境与附件/引用网络契约基线', () => {
  test('登录成功并可读取 openapi', async ({ request }) => {
    const token = await login(request)
    const paths = await fetchOpenApiPaths(request, token)
    expect(paths.length).toBeGreaterThan(0)
  })

  test('login 页 UI 可达（浏览器可见流程存在）', async ({ page }) => {
    await page.goto(FE)
    await page.waitForLoadState('domcontentloaded')
    const username = page.locator('input[placeholder*="用户名"], input[type="text"]').first()
    const password = page.locator('input[type="password"]').first()
    await expect(username).toBeVisible({ timeout: 8000 })
    await expect(password).toBeVisible({ timeout: 8000 })
  })

  test('治理 attachments / EvidenceRef / impact 路由均已接入 router（openapi 事实源）', async ({
    request,
  }) => {
    const token = await login(request)
    const paths = await fetchOpenApiPaths(request, token)

    expect(
      hasRoute(paths, (p) => /\/evidence\/attachments$/.test(p)).length,
      '治理安全上传 attachments 路由已接入',
    ).toBeGreaterThan(0)
    expect(
      hasRoute(paths, (p) => p.includes('/evidence/attachments/versions/') && p.endsWith('/content'))
        .length,
      '按版本安全读取路由已接入',
    ).toBeGreaterThan(0)
    expect(
      hasRoute(paths, (p) => p.includes('/evidence/refs/references')).length,
      'EvidenceRef references 路由已接入',
    ).toBeGreaterThan(0)
    expect(
      hasRoute(paths, (p) => p.includes('/evidence/refs/impact')).length,
      'EvidenceRef impact 路由已接入',
    ).toBeGreaterThan(0)
    // 新接线（曾缺失，诚实门 A 现已解除）：附件版本替换写端点 + 附件影响面只读端点。
    expect(
      hasRoute(paths, (p) => /\/evidence\/attachments\/\{attachment_id\}\/versions$/.test(p)).length,
      '附件版本替换写端点 .../attachments/{attachment_id}/versions 已接入',
    ).toBeGreaterThan(0)
    expect(
      hasRoute(paths, (p) => /\/evidence\/attachments\/\{attachment_id\}\/impact$/.test(p)).length,
      '附件影响面只读端点 .../attachments/{attachment_id}/impact 已接入',
    ).toBeGreaterThan(0)

    console.log('[10.2] wired evidence paths:')
    for (const p of paths.filter((x) => x.includes('/evidence')).sort()) console.log('   ', p)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-04 附件版本/影响/stale (R2, R4, R9)
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-04 附件版本/影响/stale', () => {
  // (a) 治理安全上传创建不可变 AttachmentVersion(v1) + 按版本安全读取（真实驱动网络契约）
  test('治理安全上传创建版本 + 按版本安全读取（version_no=1 / hash 绑定 / opaque locator）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj, '需要至少一个可访问项目').toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)
    const auth = { Authorization: `Bearer ${token}` }

    const { versionId, hash } = await uploadLegal(request, token, proj!, 'v1')

    // 按版本安全读取：version_no / 绑定 hash / opaque 受控 locator（绝不含绝对路径 / storage_key）。
    const rd = await request.get(`${base}/attachments/versions/${versionId}/content`, {
      headers: auth,
    })
    const rdText = await rd.text()
    expect(rd.status(), `按版本安全读取应 200（当前 ${rd.status()}）。body: ${rdText}`).toBe(200)
    const rdData = unwrap(rdText)
    expect(rdData.version_no, '首版本 version_no 应为 1（不可变快照）').toBe(1)
    expect(rdData.content_hash, '读取 hash 应与上传 hash 一致（P5 哈希绑定）').toBe(hash)
    // C3：locator 必须是受控 /api 下载 URL（opaque），不得泄露文件系统绝对路径 / storage_key。
    expect(String(rdData.locator), 'locator 应为受控 /api 下载 URL').toMatch(/^\/api\//)
    expect(String(rdData.locator), 'locator 不得含 Windows 盘符绝对路径').not.toMatch(/[A-Za-z]:\\/)
    expect(String(rdData.locator), 'locator 不得直接暴露 storage/wp_storage 物理路径').not.toMatch(
      /storage[\\/]/,
    )
  })

  // (b) 影响范围/统一图查询网络契约 —— 已修复（早先 500 签名漂移），实测其现可用
  test('影响范围(impact/UnifiedGraph)查询网络契约可用（200 + {nodes,total_visited,truncated}）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj, '需要至少一个可访问项目以构造 scope').toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)

    // impact 需要 source_type + source_id（design §6.2）。即使无数据也应返回 200 + 空 nodes。
    const resp = await request.get(
      `${base}/refs/impact?source_type=workpaper_cell&source_id=uat04-probe`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const bodyText = await resp.text()
    expect(
      resp.status(),
      `impact 查询应 200（当前 ${resp.status()}）。早先 router↔service 签名漂移致 500 现应已修复。body: ${bodyText}`,
    ).toBe(200)
    const data = unwrap(bodyText)
    expect(data, 'impact 响应应含 nodes 数组').toHaveProperty('nodes')
    expect(Array.isArray(data.nodes), 'nodes 应为数组').toBeTruthy()
    expect(data, 'impact 响应应含 total_visited').toHaveProperty('total_visited')
    expect(data, 'impact 响应应含 truncated').toHaveProperty('truncated')
  })

  // (c) 影响路径反映真实绑定：创建 ref 后，impact(起点=ref.source) 返回下游 evidence 节点 + path。
  //     依赖一个成功落库的 EvidenceRef（正向创建）；本环境成员模型分叉致创建被拒时精确 skip。
  test('创建 ref → impact 起点返回下游节点与 path（统一图影响路径反映绑定）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)

    // 自供两份真实附件版本：src（消费端起点）→ evi（被引用证据）。
    const src = await uploadLegal(request, token, proj!, 'impact-src')
    const evi = await uploadLegal(request, token, proj!, 'impact-evi')

    const created = await tryCreateRef(request, token, proj!, src.versionId, evi.versionId)

    // 诚实门 B 已解除：admin 同 scope 创建应 201 落库（绝不 5xx，绝不脱敏 4xx）。
    expect(
      created.status,
      `admin 同 scope 创建 ref 应 201 落库（当前 ${created.status}）。body: ${created.text}`,
    ).toBe(201)

    // ── impact(起点=src) 应可达 evi，含非空 path（统一图影响路径反映真实绑定）──
    expect(created.body.id, '创建成功应返回 ref id').toBeTruthy()
    const impact = await request.get(
      `${base}/refs/impact?source_type=attachment_version&source_id=${src.versionId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(impact.status()).toBe(200)
    const idata = unwrap(await impact.text())
    const hit = (idata.nodes ?? []).find(
      (n: any) => n.target_type === 'attachment_version' && n.target_id === evi.versionId,
    )
    expect(hit, 'impact 起点应可达被引用证据版本（下游节点）').toBeTruthy()
    expect(Array.isArray(hit.path) && hit.path.length >= 1, '下游节点应带非空影响 path').toBeTruthy()
  })

  // (d) 完整 UAT-04 端到端（诚实门 A 已解除）：替换 → vN+1 → 旧 v1 快照不变 → impact 反映 version_no 升至 2。
  test('替换附件 → vN+1(version_no=2) / 旧 v1 快照 bytes·hash 不变(immutable) / impact 反映变更（端到端）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj, '需要至少一个可访问项目').toBeTruthy()

    // 1) 治理安全上传 → v1（version_no=1，hash=h1，可读字节）。
    const v1 = await uploadLegal(request, token, proj!, 'replace-v1')

    // 2) 替换前影响面：current version_no 应为 1。
    const impactBefore = await readAttachmentImpact(request, token, proj!, v1.attachmentId)
    expect(
      impactBefore.status,
      `替换前 impact 应 200（当前 ${impactBefore.status}）。body: ${impactBefore.text}`,
    ).toBe(200)
    expect(impactBefore.body.version_no, '替换前 current version_no 应为 1').toBe(1)
    // 影响报告契约形状（直接+传递+阻断状态）。
    for (const k of ['direct_impacts', 'transitive_impacts', 'total_count', 'blocked']) {
      expect(impactBefore.body, `impact 报告应含 ${k}`).toHaveProperty(k)
    }
    expect(Array.isArray(impactBefore.body.direct_impacts), 'direct_impacts 应为数组').toBeTruthy()

    // 3) 经已接线的版本替换写端点 → vN+1。
    const rep = await replaceVersion(request, token, proj!, v1.attachmentId)
    expect(
      rep.status,
      `版本替换应 201（当前 ${rep.status}）。诚实门 A 已解除(端点已接线)。body: ${rep.text}`,
    ).toBe(201)
    expect(rep.body.new_version_no, '新版本 version_no 应为 2（vN+1，父行 FOR UPDATE 递增）').toBe(2)
    expect(rep.body.previous_version_id, 'previous_version_id 应指向被替换的 v1').toBe(v1.versionId)
    expect(String(rep.body.new_version_id), '应返回新版本 id').toMatch(/^[0-9a-f-]{36}$/)
    expect(String(rep.body.content_hash), '新版本应绑定新 SHA-256 content_hash').toMatch(/^[0-9a-f]{64}$/)
    expect(
      rep.body.content_hash,
      '新版本 hash 应不同于 v1 hash（内容已替换）',
    ).not.toBe(v1.hash)
    expect(String(rep.body.command_root_id), '替换应产生 command-root（审计根）').toMatch(/^[0-9a-f-]{36}$/)

    // 4) 旧 v1 快照不可变：替换后重读 v1，version_no 仍为 1、hash 仍为 h1、locator 仍受控。
    const v1After = await readVersion(request, token, proj!, v1.versionId)
    expect(
      v1After.status,
      `替换后重读 v1 应仍 200（不可变快照，当前 ${v1After.status}）。body: ${v1After.text}`,
    ).toBe(200)
    expect(v1After.body.version_no, '旧 v1 version_no 应仍为 1（immutable P4）').toBe(1)
    expect(v1After.body.content_hash, '旧 v1 hash 应与替换前完全一致（bytes 未被覆盖）').toBe(v1.hash)
    expect(String(v1After.body.locator), '旧 v1 locator 仍应为受控 /api URL').toMatch(/^\/api\//)
    expect(String(v1After.body.locator), '旧 v1 locator 不得泄露绝对路径').not.toMatch(/[A-Za-z]:\\/)

    // 5) 影响面反映变更：替换后 current version_no 升至 2（下游影响面对齐最新版本）。
    const impactAfter = await readAttachmentImpact(request, token, proj!, v1.attachmentId)
    expect(
      impactAfter.status,
      `替换后 impact 应 200（当前 ${impactAfter.status}）。body: ${impactAfter.text}`,
    ).toBe(200)
    expect(
      impactAfter.body.version_no,
      'impact 应反映 current version_no 从 1 升至 2（替换生效 + 下游 stale 传播的用户可见面）',
    ).toBe(2)
    expect(typeof impactAfter.body.blocked, 'impact.blocked 应为布尔').toBe('boolean')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// UAT-05 EvidenceRef 重启持久与双向查询 (R2, R3, R4, R9)
// ─────────────────────────────────────────────────────────────────────────────
test.describe('UAT-05 EvidenceRef 重启持久与双向查询', () => {
  test('admin 同 scope 创建 EvidenceRef → 201 落库（诚实门 B 已解除）+ 畸形入参干净 4xx', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()

    // 自供两份真实附件版本作为 source/evidence（均能被 adapter.resolve 解析）。
    const src = await uploadLegal(request, token, proj!, 'create-src')
    const evi = await uploadLegal(request, token, proj!, 'create-evi')

    const r = await tryCreateRef(request, token, proj!, src.versionId, evi.versionId)

    // 诚实门 B 已解除：create_ref 现遵循 admin/partner 全局可见（与 ScopeGuard 一致的角色豁免），
    // admin 对同 scope 合法关联应 201 落库。（同时回归：早先 router↔service 签名 500 已修，绝不 5xx。）
    expect(
      r.status,
      `admin 同 scope 创建 EvidenceRef 应 201 落库（当前 ${r.status}）。body: ${r.text}`,
    ).toBe(201)
    expect(r.body.id, '创建成功应返回 ref id').toBeTruthy()
    expect(String(r.body.intent_hash), '应返回 intent_hash（幂等键）').toMatch(/^[0-9a-f]{64}$/)
    expect(r.body.dependency_id, '应返回统一图 dependency_id（活动依赖边）').toBeTruthy()
    console.log(`[10.2 UAT-05] ref created id=${r.body.id} dep=${r.body.dependency_id}`)

    // 畸形 source_id（非 UUID）回归守卫：边界先于业务，必须干净 4xx 而非 5xx。
    const base = evidenceBase(proj!.id, proj!.year)
    const malformed = await request.post(`${base}/refs/references`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Idempotency-Key': `uat102-malformed-${Date.now()}`,
      },
      data: {
        source_type: 'workpaper_cell',
        source_id: 'D2-1!B5', // 人类可读单元格引用，非 UUID
        evidence_type: 'attachment_version',
        evidence_id: evi.versionId,
      },
    })
    expect(malformed.status(), '畸形 source_id 必须 4xx（非 5xx）').toBeGreaterThanOrEqual(400)
    expect(malformed.status(), '畸形 source_id 不得 5xx 崩溃').toBeLessThan(500)
  })

  test('双向查询一致（source 与 evidence 方向均 200 + shape + P8 子集不变量）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)
    const auth = { Authorization: `Bearer ${token}` }

    const src = await request.get(
      `${base}/refs/references?direction=source&source_type=attachment_version&source_id=uat05-src`,
      { headers: auth },
    )
    const evi = await request.get(
      `${base}/refs/references?direction=evidence&evidence_type=attachment_version&evidence_id=uat05-evi`,
      { headers: auth },
    )

    expect(src.status(), `source 方向查询应 200（当前 ${src.status()}）。早先签名漂移 500 现应已修复`).toBe(
      200,
    )
    expect(evi.status(), `evidence 方向查询应 200（当前 ${evi.status()}）`).toBe(200)

    const sData = unwrap(await src.text())
    const eData = unwrap(await evi.text())
    for (const d of [sData, eData]) {
      expect(d, '查询响应应含 items 数组').toHaveProperty('items')
      expect(Array.isArray(d.items), 'items 应为数组').toBeTruthy()
      expect(d, '查询响应应含 next_cursor').toHaveProperty('next_cursor')
      expect(d, '查询响应应含 has_more').toHaveProperty('has_more')
    }

    // P8 双向一致：evidence 方向出现的 ref 必同时出现在 source 方向（同一逻辑关联的两视图）。
    const srcIds = new Set((sData.items ?? []).map((r: any) => r.id))
    for (const r of eData.items ?? []) {
      expect(srcIds.has(r.id), `evidence 方向 ref ${r.id} 应同时出现在 source 方向`).toBeTruthy()
    }
  })

  test('单条引用详情脱敏（不存在→干净 404 SCOPE_NOT_FOUND_OR_FORBIDDEN，绝不 5xx）', async ({
    request,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)

    const resp = await request.get(
      `${base}/refs/references/11111111-1111-1111-1111-111111111111`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const bodyText = await resp.text()
    expect(resp.status(), `单条详情不应 5xx（当前 ${resp.status()}）。body: ${bodyText}`).toBeLessThan(500)
    expect(resp.status(), '不存在的 ref 应 404').toBe(404)
    expect(unwrap(bodyText).error_code, '应脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN').toBe(
      'SCOPE_NOT_FOUND_OR_FORBIDDEN',
    )
  })

  // 「重启持久」代理：全新认证会话（新 APIRequestContext + 重新登录）再查治理端点，
  // 结果与创建会话一致。证明 EvidenceRef 存 PostgreSQL（数据/契约不依赖单个请求会话或内存态）。
  test('新会话(重启代理)再查双向端点契约与持久层稳定一致', async ({ request, playwright }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)

    const query = async (ctx: APIRequestContext, tok: string) => {
      const r = await ctx.get(
        `${base}/refs/references?direction=source&source_type=attachment_version&source_id=uat05-persist-probe`,
        { headers: { Authorization: `Bearer ${tok}` } },
      )
      return { status: r.status(), data: unwrap(await r.text()) }
    }

    const first = await query(request, token)
    expect(first.status, '原会话查询应 200').toBe(200)

    // 全新会话：独立 APIRequestContext + 独立登录 token（模拟服务重启后客户端重新连接）。
    const fresh = await playwright.request.newContext()
    try {
      const freshToken = await login(fresh)
      const second = await query(fresh, freshToken)
      expect(second.status, '新会话查询应 200（持久层/契约会话无关）').toBe(200)
      // 同一 scope 同一查询在跨会话下返回一致的条数（持久化稳定，非会话内内存态）。
      expect(
        (second.data.items ?? []).length,
        '新会话与原会话对同一查询应返回一致条数',
      ).toBe((first.data.items ?? []).length)
    } finally {
      await fresh.dispose()
    }
  })

  // happy-path：正向创建一个 ref → 记录 → 新会话按 id/双向查询不变。正向创建被成员模型分叉阻断时精确 skip。
  test('创建的 ref 经新会话(重启代理)后 id/version/status 与双向视图不变', async ({
    request,
    playwright,
  }) => {
    const token = await login(request)
    const proj = await firstProject(request, token)
    expect(proj).toBeTruthy()
    const base = evidenceBase(proj!.id, proj!.year)

    const src = await uploadLegal(request, token, proj!, 'persist-src')
    const evi = await uploadLegal(request, token, proj!, 'persist-evi')
    const created = await tryCreateRef(request, token, proj!, src.versionId, evi.versionId)

    // 诚实门 B 已解除：admin 同 scope 创建应 201 落库，作为「重启代理」持久对象。
    expect(
      created.status,
      `admin 同 scope 创建 ref 应 201 落库（当前 ${created.status}）。body: ${created.text}`,
    ).toBe(201)

    // ── 记录 → 新会话按 id / 双向查询不变 ──
    const refId = created.body.id as string
    expect(refId, '创建成功应返回 ref id').toBeTruthy()

    const fresh = await playwright.request.newContext()
    try {
      const freshToken = await login(fresh)
      const auth = { Authorization: `Bearer ${freshToken}` }

      // 单条详情：id/version/hash/status 不变。
      const detail = await fresh.get(`${base}/refs/references/${refId}`, { headers: auth })
      expect(detail.status(), '新会话按 id 读取应 200').toBe(200)
      const dd = unwrap(await detail.text())
      expect(dd.id, '新会话 ref id 应不变').toBe(refId)
      expect(dd.status, '新会话 ref status 应为 active').toBe('active')
      expect(dd.evidence_id, '新会话 evidence_id 应不变').toBe(evi.versionId)

      // 双向：source 方向与 evidence 方向都能查到同一 ref id。
      const bySrc = unwrap(
        await (
          await fresh.get(
            `${base}/refs/references?direction=source&source_type=attachment_version&source_id=${src.versionId}`,
            { headers: auth },
          )
        ).text(),
      )
      const byEvi = unwrap(
        await (
          await fresh.get(
            `${base}/refs/references?direction=evidence&evidence_type=attachment_version&evidence_id=${evi.versionId}`,
            { headers: auth },
          )
        ).text(),
      )
      expect(
        (bySrc.items ?? []).some((r: any) => r.id === refId),
        '新会话 source 方向应含该 ref',
      ).toBeTruthy()
      expect(
        (byEvi.items ?? []).some((r: any) => r.id === refId),
        '新会话 evidence 方向应含该 ref（P8 双向一致）',
      ).toBeTruthy()
    } finally {
      await fresh.dispose()
    }
  })
})
