/**
 * Wave 9 · OCR & RAG UAT suite — task 10.3
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R5, R6, R7, R9
 * Design: §6.2 端点 (OCR row), §10.2 (Playwright 只验证用户可见/浏览器可达的 UAT 流程与
 *          网络契约；DB trigger/并发/lease/6000VU 不由 Playwright 证明), §12 UAT matrix
 *
 * §12 UAT matrix（本套件覆盖）：
 *   UAT-06 OCR running 时刷新/重启 → 同一 Job/attempt/transition/lease 恢复且不重复消费
 *   UAT-07 OCR corrected/rejected/冲突写回 → required 均 decided；rejected 不映射；成功全写/失败全回滚
 *   UAT-08 七角色+ServiceIdentity 轮换重试 → capability 真源；越权零效果（一票否决）
 *   UAT-09 打开 citation 并替换来源 → 精确版本/page/region；旧 citation invalid/stale
 *
 * 已接线端点契约（start-dev.bat 后端 9980，router_registry/system.py §135）：
 *   POST /api/projects/{pid}/years/{yr}/evidence/attachments                    — 安全上传（自供 OCR/引用源）
 *   POST /api/projects/{pid}/years/{yr}/evidence/refs/references                — 创建 EvidenceRef（R3）
 *   POST /api/projects/{pid}/years/{yr}/evidence/refs/references/{rid}/deactivate — 停用 EvidenceRef（替换来源）
 *   POST /api/projects/{pid}/years/{yr}/evidence/citations                      — 注册 CitationSnapshot（本任务新接线，R7）
 *   GET  /api/projects/{pid}/years/{yr}/evidence/citations                      — 列出引用快照
 *   GET  /api/projects/{pid}/years/{yr}/evidence/citations/{cid}/locate         — 打开/定位引用（打开时重鉴权，R7.3）
 *   POST /api/projects/{pid}/years/{yr}/evidence/ocr/jobs                        — 提交 OCR Job（ocr.start）
 *   GET  /api/projects/{pid}/years/{yr}/evidence/ocr/jobs/{jid}                  — 查询 Job
 *   POST /api/projects/{pid}/years/{yr}/evidence/ocr/jobs/{jid}/retry           — 重试（ocr.retry）
 *   GET  /api/projects/{pid}/years/{yr}/evidence/ocr/jobs/{jid}/timeline        — 状态迁移时间线
 *   GET  /api/projects/{pid}/years/{yr}/evidence/ocr/jobs/{jid}/results/{rid}   — OCR 结果
 *   PUT  .../results/{rid}/confirmations                                        — 字段确认
 *   POST .../results/{rid}/writeback                                            — 原子写回
 *   GET  .../results/{rid}/mapping                                              — 写回映射预览
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 诚实性声明（禁止假绿）:
 * 本 suite 分两层。
 *  (A) 可达性/前置条件表征 —— 断言当前环境中**已核实为真**的客观事实（会 PASS）。
 *  (B) UAT-06/07/08/09 验收流程 —— 编码每条 UAT 的**真实验收判据**并真实驱动已接线端点：
 *      · UAT-06 完整驱动（自供附件 → 提交 Job → 幂等复用 → 新会话重查持久 → 时间线可查、不重复消费）。
 *      · UAT-09 完整驱动（上传源 → 创建 EvidenceRef → 注册 CitationSnapshot → 打开定位到精确
 *        版本/page/region 且打开时重鉴权 → 停用来源 EvidenceRef → 旧 citation 变 invalid/stale）。
 *      · UAT-07 驱动可达的网络契约（映射/确认/写回端点受治理、绝不 500）；其**原子写回正向流程**
 *        因无浏览器可达的 OCR worker/结果播种入口而 BLOCKED（其权威证明落 PBT P12/P13/P14 +
 *        PG integration，§10.2 明确 DB 事务/原子性不由 Playwright 承担）。
 *      · UAT-08 驱动可达的**零副作用**判据（对非 failed Job 重试 → 干净 409、Job 与时间线零变化）；
 *        其**越权角色否决**（一票否决）因平台无运行期用户创建/项目成员（project_users）写入 API、
 *        且 project_users 全表为空（无法造出通过 scope 却缺 ocr.retry 的非 admin 项目成员），
 *        又将 denied/not-found 脱敏合并为 404 → 在网络层不可正向区分 → BLOCKED（权威证明落
 *        PBT P10 + side-effect，§10.2 明确不由 Playwright 承担）。
 *  BLOCKED 一律 test.skip(true, <精确根因>)，绝不伪造 PASS。端点/夹具一旦补齐，去掉 skip 即成永久可执行编码。
 * ─────────────────────────────────────────────────────────────────────────────
 */
import { test, expect, request as pwRequest } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:9980'
const FAKE_UUID = '11111111-1111-1111-1111-111111111111'
const FAKE_RESULT = '00000000-0000-0000-0000-0000000000aa'

interface ProjectScope {
  id: string
  year: number
}

/** ResponseWrapperMiddleware 只包装 2xx JSON 为 {code,message,data}；治理错误体是顶层
 *  {code,error_code,message,...}。统一解包：有 data 对象则取 data，否则取原体。 */
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

/** 取当前用户可访问的第一个项目 scope（OCR 治理 scope 授权用）。 */
async function firstProject(
  request: APIRequestContext,
  token: string,
): Promise<ProjectScope | null> {
  const resp = await request.get(`${BACKEND}/api/projects?page=1&page_size=20`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const items: any[] = Array.isArray(body?.data) ? body.data : body?.data?.items ?? []
  const first = items.find((p) => p?.id)
  if (!first) return null
  return { id: String(first.id), year: Number(first.audit_year) || 2025 }
}

/** 经安全上传端点上传一份合法附件，返回可用附件版本 id + content_hash（自供 OCR 源）。 */
async function uploadLegal(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
): Promise<{ attachmentId: string; versionId: string; contentHash: string }> {
  const resp = await request.post(
    `${BACKEND}/api/projects/${proj.id}/years/${proj.year}/evidence/attachments`,
    {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat10_3-legal-${Date.now()}-${Math.random()}` },
      multipart: {
        file: {
          name: 'ocr-source.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('legal evidence content for ocr uat 10.3'),
        },
        declared_media_type: 'text/plain',
      },
    },
  )
  expect(resp.status(), '合法上传应 201 available').toBe(201)
  const data = unwrap(await resp.json())
  expect(data.attachment_id, '合法上传应返回可用 attachment_id').toBeTruthy()
  expect(data.attachment_version_id, '合法上传应返回可用 attachment_version_id').toBeTruthy()
  expect(data.content_hash, '合法上传应返回 content_hash（OCR Job 绑定）').toBeTruthy()
  return {
    attachmentId: String(data.attachment_id),
    versionId: String(data.attachment_version_id),
    contentHash: String(data.content_hash),
  }
}

function ocrBase(proj: ProjectScope): string {
  return `${BACKEND}/api/projects/${proj.id}/years/${proj.year}/evidence/ocr`
}

/** 提交 OCR Job（自供源）。返回 {jobId, state, created, commandRootId, raw}. */
async function submitJob(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
  src: { attachmentId: string; versionId: string; contentHash: string },
  idempotencyKey: string,
): Promise<{ status: number; jobId: string | null; state: string | null; created: boolean | null; replayed: boolean | null; raw: any }> {
  const resp = await request.post(`${ocrBase(proj)}/jobs`, {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': idempotencyKey },
    data: {
      attachment_id: src.attachmentId,
      attachment_version_id: src.versionId,
      content_hash: src.contentHash,
    },
  })
  const data = unwrap(await resp.json())
  return {
    status: resp.status(),
    jobId: data?.job?.id ?? null,
    state: data?.job?.state ?? null,
    created: data?.created ?? null,
    replayed: data?.replayed ?? null,
    raw: data,
  }
}

function evidenceBase(proj: ProjectScope): string {
  return `${BACKEND}/api/projects/${proj.id}/years/${proj.year}/evidence`
}

/** 创建绑定到该附件版本（作为 evidence 侧）的活动 EvidenceRef。
 *  不传 attachment_version_id（绕过元数据门禁，evidence_id 已标识版本）；不传 context
 *  （evidence_refs.context 为 JSONB，裸字符串会 500——本任务外的既有 bug，此处规避）。 */
async function createRef(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
  src: { versionId: string; contentHash: string },
): Promise<string> {
  const resp = await request.post(`${evidenceBase(proj)}/refs/references`, {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat09-ref-${Date.now()}-${Math.random()}` },
    data: {
      source_type: 'attachment_version',
      source_id: src.versionId,
      evidence_type: 'attachment_version',
      evidence_id: src.versionId,
      target_version: 1,
      target_hash: src.contentHash,
      label: 'uat09-citation',
    },
  })
  expect(resp.status(), '创建 EvidenceRef 应 201').toBe(201)
  const data = unwrap(await resp.json())
  expect(data.id, 'EvidenceRef 应返回 id').toBeTruthy()
  return String(data.id)
}

/** 从活动 EvidenceRef 注册一个 CitationSnapshot（治理层过滤链不放宽）。 */
async function createCitation(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
  refId: string,
  page: number,
  region: Record<string, number>,
): Promise<{ status: number; citationId: string | null; raw: any }> {
  const resp = await request.post(`${evidenceBase(proj)}/citations`, {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat09-cite-${Date.now()}-${Math.random()}` },
    data: {
      evidence_ref_id: refId,
      page,
      region,
      excerpt_text: '关键金额 1,234.00',
      index_version: 'idx-v1',
      locator_version: 'loc-v1',
    },
  })
  const data = unwrap(await resp.json())
  return { status: resp.status(), citationId: data?.citation_id ?? null, raw: data }
}

async function locateCitation(
  request: APIRequestContext,
  token: string,
  proj: ProjectScope,
  citationId: string,
): Promise<any> {
  const resp = await request.get(`${evidenceBase(proj)}/citations/${citationId}/locate`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(resp.status(), 'locate 应 200（状态在读取时派生，不抛错）').toBe(200)
  return unwrap(await resp.json())
}

test.describe('证据治理 UAT — OCR & RAG 套件 (R5/R6/R7/R9)', () => {
  test.beforeAll(async ({ request }) => {
    if (!(await healthy(request))) {
      test.skip(true, `后端 ${BACKEND} 不健康，跳过 OCR & RAG UAT`)
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // (A) 可达性 / 前置条件表征 —— 已验证事实（PASS）
  // ═══════════════════════════════════════════════════════════════════════════

  test('A1 · 浏览器登录 + 应用外壳可达（admin/admin123）', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page, '登录后应离开 /login').not.toHaveURL(/\/login/, { timeout: 15000 })
    const sessTok = await page.evaluate(() => sessionStorage.getItem('token'))
    expect(sessTok, 'UI 登录后 sessionStorage.token 应存在').toBeTruthy()
  })

  test('A2 · OCR 治理路由已注册（未认证 → 401，非 404）', async ({ request }) => {
    const res = await request.get(
      `${BACKEND}/api/projects/${FAKE_UUID}/years/2025/evidence/ocr/jobs/${FAKE_UUID}`,
    )
    expect(res.status(), 'OCR 治理路由应已注册（401 而非 404）').toBe(401)
  })

  test('A3 · OCR 治理契约返回脱敏编码结果（404 SCOPE_NOT_FOUND + error_code 信封）', async ({
    request,
  }) => {
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const res = await request.get(`${ocrBase(proj!)}/jobs/${FAKE_UUID}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.status(), 'OCR 治理契约应返回脱敏 404（非 500）').toBe(404)
    const body = unwrap(await res.json())
    // 设计 §7.2 / R4.2：不存在与无权访问共用同一脱敏 error_code。
    expect(body.error_code, '响应应携带稳定 error_code=SCOPE_NOT_FOUND_OR_FORBIDDEN').toBe(
      'SCOPE_NOT_FOUND_OR_FORBIDDEN',
    )
  })

  test('A4 · 安全上传端点已接线（可自供受治理 OCR 源：201 + content_hash + version）', async ({
    request,
  }) => {
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const src = await uploadLegal(request, token, proj!)
    expect(src.attachmentId, '自供源应有 attachment_id').toBeTruthy()
    expect(src.versionId, '自供源应有 attachment_version_id').toBeTruthy()
    expect(src.contentHash, '自供源应有 content_hash').toMatch(/^[0-9a-f]{64}$/)
  })

  test('A5 · citation 治理 HTTP 契约已接线（list/locate/validate 可达，受 scope 治理）', async ({
    request,
  }) => {
    // 早先该端点缺失（全 404）；治理 citation_router 现已挂载（openapi 事实源）。
    // 更新为对「现实已接线契约」的真实正向断言（对齐 A2/A3 对 OCR 的接线断言范式）。
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const cbase = `${BACKEND}/api/projects/${proj!.id}/years/${proj!.year}/evidence/citations`

    // list：只读，返回 200 + items 数组（受 scope 授权）。
    const list = await request.get(cbase, { headers: { Authorization: `Bearer ${token}` } })
    expect(list.status(), 'citation list 应 200（已接线）').toBe(200)
    const listData = unwrap(await list.json())
    expect(Array.isArray(listData.items), 'citation list 应含 items 数组').toBeTruthy()

    // locate（不存在的有效 UUID）：打开时重鉴权，来源不可读 → 优雅返回 status=invalid（不抛错、不泄露）。
    const loc = await request.get(`${cbase}/${FAKE_UUID}/locate`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(loc.status(), 'citation locate 应 200（优雅返回 stale/invalid 状态而非抛错）').toBe(200)
    const locData = unwrap(await loc.json())
    expect(locData.status, '不存在 citation locate 状态应为 invalid').toBe('invalid')
    expect(locData.reason, 'locate 原因应为 citation_not_found（脱敏、不泄露存在性以外信息）').toBe(
      'citation_not_found',
    )
    expect(locData.readable, '不可读来源 readable=false').toBe(false)

    // 遗留别名 citation-snapshots 仍不存在（未接线）→ 404。
    const alias = await request.get(
      `${BACKEND}/api/projects/${proj!.id}/years/${proj!.year}/evidence/citation-snapshots`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(alias.status(), '遗留别名 citation-snapshots 未接线 → 404').toBe(404)
  })

  test('A6 · 无浏览器可达的 OCR 识别/结果播种入口（映射/确认/写回受治理但无 500）', async ({
    request,
  }) => {
    // 提交仅创建 queued Job（不运行识别、不产 OCRResult）；识别由 worker 完成，无 HTTP 触发口。
    // 故对"无结果"的映射/确认/写回，端点必须返回受治理编码（404/422），绝不 500。
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const src = await uploadLegal(request, token, proj!)
    const submit = await submitJob(request, token, proj!, src, `uat10_3-a6-${Date.now()}`)
    expect(submit.status, '提交应 201').toBe(201)
    expect(submit.state, '新 Job 初态应为 queued').toBe('queued')
    const jid = submit.jobId!

    // 映射（无结果）→ 404 受治理
    const mapping = await request.get(`${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/mapping`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(mapping.status(), '无结果映射应 404 受治理（非 500）').toBe(404)

    // 确认（无结果）→ 404 受治理
    const confirm = await request.put(
      `${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/confirmations`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { field_name: 'amount', decision: 'corrected', confirmed_value: '100' },
      },
    )
    expect(confirm.status(), '无结果确认应 404 受治理（非 500）').toBe(404)

    // 写回缺 Idempotency-Key → 422（写命令强制幂等键）
    const wbNoKey = await request.post(
      `${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/writeback`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { target_type: 'workpaper_cell', target_id: 'D2-1!B5' },
      },
    )
    expect(wbNoKey.status(), '写回缺 Idempotency-Key 应 422').toBe(422)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // (B) UAT-06/07/08/09 验收流程 —— 逐项
  // ═══════════════════════════════════════════════════════════════════════════

  // ── UAT-06 · Job 重启恢复（完整驱动，PASS）─────────────────────────────────
  test('UAT-06 · Job 重启恢复：同一 Job/transition 恢复、幂等复用、不重复消费', async ({
    request,
  }) => {
    test.info().annotations.push({
      type: 'UAT-06 验收判据',
      description:
        'OCR running/queued 时刷新/重启后：复用同一 OCRJob（幂等键命中 + 相同载荷编排复用）、' +
        'transition 恢复可查、不重复消费。真实进程重启不可行 → 以新会话重查证明持久化。',
    })
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目，无法执行 UAT-06')

    // 1) 自供受治理 OCR 源并提交 Job（初态 queued，attempt_count=0）。
    const src = await uploadLegal(request, token, proj!)
    const idem = `uat06-${Date.now()}`
    const first = await submitJob(request, token, proj!, src, idem)
    expect(first.status, '首次提交应 201').toBe(201)
    expect(first.jobId, '首次提交应返回 Job id').toBeTruthy()
    expect(first.state, '新 Job 初态应为 queued').toBe('queued')
    expect(first.created, '首次提交应 created=true').toBe(true)
    const jobId = first.jobId!

    // 2) 相同 Idempotency-Key 重提交 → facade 幂等重放（replayed=true），不新建 Job。
    const replaySame = await submitJob(request, token, proj!, src, idem)
    expect(replaySame.status, '相同幂等键重提交应 201').toBe(201)
    expect(replaySame.replayed, '相同 Idempotency-Key 应 facade 幂等重放').toBe(true)

    // 3) 不同 Idempotency-Key、相同载荷 → 编排层 R5.4 复用同一活动 Job（created=false，同 id）。
    const reuse = await submitJob(request, token, proj!, src, `${idem}-diff`)
    expect(reuse.status, '相同载荷重提交应 201').toBe(201)
    expect(reuse.created, '相同载荷（不同幂等键）应编排层复用（created=false）').toBe(false)
    expect(reuse.jobId, '编排层复用应返回同一 Job id（不重复消费）').toBe(jobId)

    // 4) 查询 Job：状态持久、attempt_count 未因重复提交而增加（提交不消费/不 lease）。
    const jobRes = await request.get(`${ocrBase(proj!)}/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(jobRes.status(), 'Job 查询应 200').toBe(200)
    const job = unwrap(await jobRes.json())
    expect(job.id, 'Job id 持久').toBe(jobId)
    expect(job.state, 'Job 状态持久为 queued').toBe('queued')
    expect(job.attempt_count, '重复提交不得推进 attempt_count（不重复消费）').toBe(0)

    // 5) 时间线：初始 transition(None→queued) 已持久，actor/时刻可查。
    const tlRes = await request.get(`${ocrBase(proj!)}/jobs/${jobId}/timeline`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(tlRes.status(), '时间线查询应 200').toBe(200)
    const tl = unwrap(await tlRes.json())
    expect(Array.isArray(tl.transitions), '时间线应为数组').toBeTruthy()
    expect(tl.transitions.length, '至少有一条 queued transition').toBeGreaterThanOrEqual(1)
    const queuedT = tl.transitions.find((t: any) => t.to_state === 'queued')
    expect(queuedT, '应存在到 queued 的 transition').toBeTruthy()
    expect(queuedT.at, 'transition 应携带发生时刻（可恢复时间线）').toBeTruthy()
    expect(queuedT.actor_type, 'transition 应记录 actor 类型').toBeTruthy()
    const transitionCountBefore = tl.transitions.length

    // 6) 新会话（模拟刷新/重启后重新登录）重查 → Job 与 transition 持久一致、不重复消费。
    const fresh = await pwRequest.newContext()
    try {
      const freshToken = await loginToken(fresh)
      const freshJob = await fresh.get(`${ocrBase(proj!)}/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${freshToken}` },
      })
      expect(freshJob.status(), '新会话 Job 查询应 200（持久）').toBe(200)
      const fj = unwrap(await freshJob.json())
      expect(fj.id, '新会话应查到同一 Job id').toBe(jobId)
      expect(fj.state, '新会话 Job 状态一致').toBe('queued')
      expect(fj.attempt_count, '新会话 attempt_count 一致（未重复消费）').toBe(0)

      const freshTl = await fresh.get(`${ocrBase(proj!)}/jobs/${jobId}/timeline`, {
        headers: { Authorization: `Bearer ${freshToken}` },
      })
      expect(freshTl.status(), '新会话时间线查询应 200').toBe(200)
      const ftl = unwrap(await freshTl.json())
      expect(ftl.transitions.length, '新会话 transition 数一致（持久、不重复）').toBe(
        transitionCountBefore,
      )
    } finally {
      await fresh.dispose()
    }
  })

  // ── UAT-07 · 人工确认 / 原子写回 ────────────────────────────────────────────
  test('UAT-07(契约) · 确认/写回/映射端点受治理且绝不 500（可达网络契约）', async ({
    request,
  }) => {
    test.info().annotations.push({
      type: 'UAT-07 可达契约',
      description:
        '对已提交但尚无 OCRResult 的 Job，映射/确认/写回端点必须受 scope+capability 治理并返回' +
        '稳定编码（404/422），绝不 500 崩溃。这证明端点已正确接线、错误脱敏、幂等键强制。',
    })
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const src = await uploadLegal(request, token, proj!)
    const submit = await submitJob(request, token, proj!, src, `uat07-${Date.now()}`)
    expect(submit.status, '提交应 201').toBe(201)
    const jid = submit.jobId!

    // 映射预览（无结果）→ 404 受治理编码，非 500。
    const mapping = await request.get(`${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/mapping`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(mapping.status(), '映射应 404 受治理（非 500）').toBe(404)
    expect(unwrap(await mapping.json()).error_code).toBe('SCOPE_NOT_FOUND_OR_FORBIDDEN')

    // 字段确认（无结果）→ 404 受治理，非 500。
    const confirm = await request.put(
      `${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/confirmations`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { field_name: 'amount', decision: 'rejected' },
      },
    )
    expect(confirm.status(), '确认应 404 受治理（非 500）').toBe(404)
    expect(unwrap(await confirm.json()).error_code).toBe('SCOPE_NOT_FOUND_OR_FORBIDDEN')

    // 写回：缺 Idempotency-Key → 422；带 key（无结果）→ 404 受治理，均非 500。
    const wbNoKey = await request.post(
      `${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/writeback`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: { target_type: 'workpaper_cell', target_id: 'D2-1!B5' },
      },
    )
    expect(wbNoKey.status(), '写回缺幂等键应 422').toBe(422)

    const wbWithKey = await request.post(
      `${ocrBase(proj!)}/jobs/${jid}/results/${FAKE_RESULT}/writeback`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat07-wb-${Date.now()}` },
        data: { target_type: 'workpaper_cell', target_id: 'D2-1!B5' },
      },
    )
    expect(wbWithKey.status(), '写回（无结果）应 404 受治理（非 500）').toBe(404)
    expect(unwrap(await wbWithKey.json()).error_code).toBe('SCOPE_NOT_FOUND_OR_FORBIDDEN')
  })

  test('UAT-07(正向) · 人工确认 → 原子写回（required 均 decided / rejected 不映射 / 全写或全回滚）', async () => {
    test.info().annotations.push({
      type: 'UAT-07 验收判据',
      description:
        '低置信字段 corrected→confirm→原子写回；rejected 永不进入 mapping；所有 required 必须先 decided；' +
        '目标版本冲突 → 无部分更新（成功全写/失败全回滚）。',
    })
    test.skip(
      true,
      'BLOCKED（非一票否决）：原子写回正向流程需要一条带 OCRResult 的 Job，但 OCR 识别由 worker 调用 ' +
        'UnifiedOCRService 完成，POST /jobs 只创建 queued Job（不运行识别、不产 OCRResult），' +
        '且无任何 HTTP 端点触发 worker 或播种 OCRResult → 浏览器/网络层无法进行 accept/correct/reject 与写回。' +
        ' 此外写回原子性/rejected 不映射/目标版本冲突全回滚属 §10.2 排除的 DB 事务范畴，' +
        '权威证明落 PBT P12(未确认不可写回)/P13(写回原子性)/P14(写回幂等) + PG integration + 只读 fixture API。' +
        ' 端点本身已接线且对无结果 Job 返回受治理编码（见 UAT-07(契约)）。' +
        ' 解除条件：提供浏览器可达的 OCR 识别触发/结果播种入口或测试专用只读 fixture API。',
    )
  })

  // ── UAT-08 · 重试权限否决（一票否决）─────────────────────────────────────────
  test('UAT-08(零副作用) · 对非 failed Job 重试 → 干净 409 且 Job/时间线零变化', async ({
    request,
  }) => {
    test.info().annotations.push({
      type: 'UAT-08 相邻可达判据',
      description:
        '重试路径受治理：对非 failed（queued）Job 重试被状态机守卫以干净 409 INVALID_STATE_TRANSITION 否决，' +
        '且对 Job 与其时间线零副作用；对不存在 Job 重试 → 脱敏 404。',
    })
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目')
    const src = await uploadLegal(request, token, proj!)
    const submit = await submitJob(request, token, proj!, src, `uat08-${Date.now()}`)
    expect(submit.status, '提交应 201').toBe(201)
    const jid = submit.jobId!

    // 基线：时间线 transition 数。
    const tl0 = unwrap(
      await (await request.get(`${ocrBase(proj!)}/jobs/${jid}/timeline`, {
        headers: { Authorization: `Bearer ${token}` },
      })).json(),
    )
    const before = tl0.transitions.length

    // admin（有 ocr.retry 能力）对 queued（非 failed）Job 重试 → 状态机守卫 409，零副作用。
    const retry = await request.post(`${ocrBase(proj!)}/jobs/${jid}/retry`, {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat08-retry-${Date.now()}` },
    })
    expect(retry.status(), '对 queued Job 重试应 409（状态机守卫，非 500）').toBe(409)
    expect(unwrap(await retry.json()).error_code, '应为 INVALID_STATE_TRANSITION').toBe(
      'INVALID_STATE_TRANSITION',
    )

    // 零副作用：Job 仍 queued、时间线 transition 数不变。
    const jobAfter = unwrap(
      await (await request.get(`${ocrBase(proj!)}/jobs/${jid}`, {
        headers: { Authorization: `Bearer ${token}` },
      })).json(),
    )
    expect(jobAfter.state, '被否决的重试不得改变 Job 状态').toBe('queued')
    const tl1 = unwrap(
      await (await request.get(`${ocrBase(proj!)}/jobs/${jid}/timeline`, {
        headers: { Authorization: `Bearer ${token}` },
      })).json(),
    )
    expect(tl1.transitions.length, '被否决的重试不得追加 Job transition（零副作用）').toBe(before)

    // 不存在 Job 重试 → 脱敏 404。
    const retryMissing = await request.post(`${ocrBase(proj!)}/jobs/${FAKE_UUID}/retry`, {
      headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat08-missing-${Date.now()}` },
    })
    expect(retryMissing.status(), '不存在 Job 重试应 404').toBe(404)
    expect(unwrap(await retryMissing.json()).error_code).toBe('SCOPE_NOT_FOUND_OR_FORBIDDEN')
  })

  test('UAT-08(权限否决) · 越权角色重试被否决且零效果【一票否决】', async () => {
    test.info().annotations.push({
      type: 'UAT-08 验收判据',
      description:
        '无 ocr.retry 权限的角色（readonly/qc/eqcr/auditor）重试被明确否决且零副作用；' +
        '有权限角色（manager/partner/admin）按幂等重试 failed Job；ServiceIdentity 不能人工确认；capability 为唯一真源。',
    })
    test.skip(
      true,
      'BLOCKED【一票否决】：越权角色重试否决无法在网络层正向证明——' +
        '(1) 仅有 admin 凭据；readonly/qc/eqcr/auditor 未分配到项目且无已知口令 → 无法以越权角色驱动；' +
        '(2) 设计 §7.2/R4.2 将 capability-denied 与 not-found 刻意脱敏合并为 SCOPE_NOT_FOUND_OR_FORBIDDEN(404) → ' +
        'HTTP 层无法区分"越权否决"与"不存在"；' +
        '(3) 无 failed 状态的种子 Job（识别失败由 worker 产生，无 HTTP 触发口）供有权限角色正向重试对照。' +
        ' 权威证明落 PBT P10(重试授权/越权零副作用) + side-effect 只读断言，§10.2 明确不由 Playwright 承担。' +
        ' 相邻的"零副作用"判据已由 UAT-08(零副作用) 真实验证（对非 failed Job 重试干净 409 且零变化）。' +
        ' 解除条件：多角色测试账号 + 已播种 failed Job + 只读 side-effect fixture API。',
    )
  })

  // ── UAT-09 · 精确引用 / 失效（完整驱动，PASS）──────────────────────────────
  test('UAT-09 · 打开 citation 精确定位 / 停用来源致失效（完整正向流程）', async ({
    request,
  }) => {
    test.info().annotations.push({
      type: 'UAT-09 验收判据',
      description:
        '注册 CitationSnapshot → 打开定位到精确 attachment 版本/page/region（打开时重鉴权，readable/' +
        'version_valid/hash_valid 全真）→ 停用来源 EvidenceRef（替换来源）→ 同一 citation 转为 ' +
        'invalid/stale（reason=evidence_ref_deactivated，且不再暴露可定位 page/region）。',
    })
    const token = await loginToken(request)
    const proj = await firstProject(request, token)
    test.skip(!proj, '无可用项目，无法执行 UAT-09')

    // 1) 自供受治理来源（上传合法附件）+ 创建绑定其版本的活动 EvidenceRef。
    const src = await uploadLegal(request, token, proj!)
    const refId = await createRef(request, token, proj!, {
      versionId: src.versionId,
      contentHash: src.contentHash,
    })

    // 2) 从该活动 EvidenceRef 注册 CitationSnapshot（治理过滤链：同 scope ∩ 可读 ∩ active ref ∩
    //    版本/hash 有效 ∩ page/region 可定位；不放宽 P15/P16）。
    const region = { x: 12, y: 20, w: 100, h: 40 }
    const created = await createCitation(request, token, proj!, refId, 3, region)
    expect(created.status, 'citation 注册应 201').toBe(201)
    expect(created.citationId, 'citation 应返回 id').toBeTruthy()
    expect(created.raw.status, '新 citation 应 active').toBe('active')
    expect(created.raw.page, 'citation 应保留精确 page').toBe(3)
    expect(created.raw.region, 'citation 应保留精确 region').toEqual(region)
    expect(created.raw.target_hash, 'citation 应绑定来源 content_hash').toBe(src.contentHash)
    const citationId = created.citationId!

    // 3) 打开 citation：打开时重鉴权 → active + 精确版本/page/region（R7.3 / P15）。
    const active = await locateCitation(request, token, proj!, citationId)
    expect(active.status, '打开有效 citation → active').toBe('active')
    expect(active.readable, '来源可读 readable=true').toBe(true)
    expect(active.version_valid, '版本仍匹配 version_valid=true').toBe(true)
    expect(active.hash_valid, 'hash 仍匹配 hash_valid=true').toBe(true)
    expect(active.source_available, '来源存在 source_available=true').toBe(true)
    expect(active.page, '定位到精确 page').toBe(3)
    expect(active.region, '定位到精确 region').toEqual(region)

    // 4) 停用来源 EvidenceRef（等同「替换/失效来源」）。
    const deact = await request.post(
      `${evidenceBase(proj!)}/refs/references/${refId}/deactivate`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': `uat09-deact-${Date.now()}` },
        data: { reason: 'UAT-09 来源替换/失效' },
      },
    )
    expect(deact.status(), '停用 EvidenceRef 应 200').toBe(200)

    // 5) 再次打开同一 citation：来源失效 → invalid/stale（R7.2/R7.3 / R9）。
    const invalid = await locateCitation(request, token, proj!, citationId)
    expect(invalid.status, '来源停用后 citation → invalid').toBe('invalid')
    expect(invalid.reason, '失效原因应为 evidence_ref_deactivated').toBe('evidence_ref_deactivated')
    expect(invalid.source_available, '来源不再可用 source_available=false').toBe(false)
    // 失效 citation 不再暴露可定位 page/region（必须重新核验，R7.3）。
    expect(invalid.page, '失效 citation 不再暴露 page').toBeNull()
    expect(invalid.region, '失效 citation 不再暴露 region').toBeNull()

    // 6) list 现至少包含该 citation（持久、可查）。
    const list = await request.get(`${evidenceBase(proj!)}/citations`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(list.status(), 'citation list 应 200').toBe(200)
    const items: any[] = unwrap(await list.json()).items ?? []
    expect(items.some((c) => String(c.id) === citationId), 'list 应含刚注册的 citation').toBeTruthy()
  })
})
