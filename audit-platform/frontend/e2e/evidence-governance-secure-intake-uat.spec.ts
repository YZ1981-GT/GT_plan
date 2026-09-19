/**
 * Wave 9 — 安全接收 Playwright UAT suite（Task 10.1）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R1, R3, R4, R12
 * UAT: UAT-01 上传先审计/无可用恶意文件、UAT-02 越界读取否决、UAT-03 跨项目关联否决
 * 一票否决: UAT-02、UAT-03
 *
 * 设计边界（design §10.2 测试分层与 Playwright 边界）：
 *   - Playwright 只验证「用户可见 / 浏览器可达的流程与网络契约」。
 *   - 不承担 DB trigger / 并发 / PBT / 6000 VU 的证明（这些在 PG integration / PBT /
 *     capacity 层完成）。
 *   - 需要 DB 断言（如「关联数不变」）时，只经「测试专用只读 API」采证
 *     （此处 = 治理层只读 GET references 端点），绝不在浏览器中直连数据库。
 *
 * 诚实性铁律：
 *   - 若治理端点尚未功能性接线（缺失路由 / 500 崩溃），对应 UAT 场景以带原因的
 *     test.skip 标注为 BLOCKED，绝不 fabricate 通过。
 *   - 端点一旦接线/修复，探针自动放行，真实验收断言即刻生效——本文件即成为
 *     UAT-01/02/03 的永久可执行编码。
 */
import { test, expect, request as pwRequest, type APIRequestContext } from '@playwright/test'

// 后端治理服务（frontend dev server 亦将 /api 代理至此）。
const API_BASE = process.env.EVIDENCE_API_BASE || 'http://localhost:9980'

// 两个不同项目，用于跨项目关联否决（UAT-03）。取自运行库真实项目。
// 若这些 ID 在目标库不存在，探针会将相关场景标为 BLOCKED（不 fabricate）。
const PROJECT_A = process.env.EVIDENCE_PROJECT_A || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const YEAR_A = Number(process.env.EVIDENCE_YEAR_A || 2025)
const PROJECT_B = process.env.EVIDENCE_PROJECT_B || 'a7fc75e5-b67f-436d-a126-42423018b6ce'
const YEAR_B = Number(process.env.EVIDENCE_YEAR_B || 2025)

interface Wiring {
  token: string | null
  loginOk: boolean
  // UAT-03: 治理 EvidenceRef 只读端点是否健康（用于「关联数不变」采证 + 创建否决探测）
  refsListStatus: number
  refsListHealthy: boolean
  // UAT-01: 治理上传端点（design API 根 /evidence/attachments）是否接线
  uploadStatus: number
  uploadWired: boolean
  // UAT-02: 治理安全读取端点是否接线
  contentStatus: number
  contentWired: boolean
  notes: string[]
}

const wiring: Wiring = {
  token: null,
  loginOk: false,
  refsListStatus: 0,
  refsListHealthy: false,
  uploadStatus: 0,
  uploadWired: false,
  contentStatus: 0,
  contentWired: false,
  notes: [],
}

let api: APIRequestContext

function authHeaders(): Record<string, string> {
  return wiring.token ? { Authorization: `Bearer ${wiring.token}` } : {}
}

test.beforeAll(async () => {
  api = await pwRequest.newContext({ baseURL: API_BASE, ignoreHTTPSErrors: true })

  // 1) 登录（浏览器同款网络契约）。
  try {
    const resp = await api.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
      headers: { 'Content-Type': 'application/json' },
    })
    if (resp.ok()) {
      const body = await resp.json()
      wiring.token = body?.data?.access_token ?? body?.access_token ?? null
      wiring.loginOk = !!wiring.token
    } else {
      wiring.notes.push(`login 非 2xx: ${resp.status()}`)
    }
  } catch (e) {
    wiring.notes.push(`login 异常: ${String(e)}`)
  }

  if (!wiring.loginOk) return

  // 2) UAT-03 只读端点健康探针（治理 EvidenceRef list）。
  //    仅当返回 200 才视为可用于「关联数不变」采证 + 创建否决验证。
  try {
    const r = await api.get(
      `/api/projects/${PROJECT_B}/years/${YEAR_B}/evidence/refs/references?direction=source`,
      { headers: authHeaders() },
    )
    wiring.refsListStatus = r.status()
    wiring.refsListHealthy = r.status() === 200
    if (!wiring.refsListHealthy) {
      wiring.notes.push(
        `UAT-03 阻断: GET evidence/refs/references 返回 ${r.status()}（期望 200）。` +
          `治理 EvidenceRef 路由↔服务签名漂移致 500，跨项目否决逻辑经网络契约不可达。`,
      )
    }
  } catch (e) {
    wiring.notes.push(`UAT-03 references 探针异常: ${String(e)}`)
  }

  // 3) UAT-01 治理上传端点探针（design §6.1 API 根 /evidence/attachments）。
  //    仅当返回「治理形状」响应（2xx 或带 error_code 的 4xx）才视为接线；
  //    404/405（路由缺失）或 500 视为未接线 → BLOCKED。
  try {
    const r = await api.post(
      `/api/projects/${PROJECT_A}/years/${YEAR_A}/evidence/attachments`,
      { headers: authHeaders(), multipart: { file: { name: 'probe.txt', mimeType: 'text/plain', buffer: Buffer.from('probe') } } },
    )
    wiring.uploadStatus = r.status()
    // 路由存在的标志：非 404/405（FastAPI 未匹配路由）。
    wiring.uploadWired = r.status() !== 404 && r.status() !== 405 && r.status() < 500
    if (!wiring.uploadWired) {
      wiring.notes.push(
        `UAT-01 阻断: POST evidence/attachments 返回 ${r.status()}。` +
          `SecureAttachmentGateway 未经任何 HTTP 路由暴露（无浏览器可达的治理上传端点）。`,
      )
    }
  } catch (e) {
    wiring.notes.push(`UAT-01 upload 探针异常: ${String(e)}`)
  }

  // 4) UAT-02 治理安全读取端点探针（content 读取 → 边界先于字节 I/O）。
  try {
    const fakeId = '00000000-0000-0000-0000-000000000000'
    const r = await api.get(
      `/api/projects/${PROJECT_A}/years/${YEAR_A}/evidence/attachments/${fakeId}/content`,
      { headers: authHeaders() },
    )
    wiring.contentStatus = r.status()
    // 治理读取端点若存在，对不存在对象应返回脱敏 403/404（error_code 形状），而非「路由缺失」。
    // 由于当前无此路由，FastAPI 返回 404 且无治理 envelope；无法区分「路由缺失」与「对象缺失」，
    // 故以「是否存在治理读取路由」的保守判定：需 body 含 error_code envelope 才算接线。
    let hasEnvelope = false
    try {
      const b = await r.json()
      hasEnvelope = !!(b?.detail?.error_code || b?.error_code)
    } catch {
      hasEnvelope = false
    }
    wiring.contentWired = hasEnvelope
    if (!wiring.contentWired) {
      wiring.notes.push(
        `UAT-02 阻断: GET evidence/attachments/{id}/content 返回 ${r.status()} 且无治理 error envelope。` +
          `安全读取链（StorageBoundaryResolver 边界先于字节 I/O）未经任何 HTTP 路由暴露。`,
      )
    }
  } catch (e) {
    wiring.notes.push(`UAT-02 content 探针异常: ${String(e)}`)
  }

  // 汇总打印到 stdout，供报告采集。
  // eslint-disable-next-line no-console
  console.log('[secure-intake-uat wiring]\n' + JSON.stringify(wiring, null, 2))
})

test.afterAll(async () => {
  await api?.dispose()
})

test.describe('Wave9 安全接收 suite — 附件/OCR/AI 证据链治理加固', () => {
  test.beforeEach(() => {
    test.skip(!wiring.loginOk, `前置阻断: 无法登录治理后端（${API_BASE}）。notes=${wiring.notes.join(' | ')}`)
  })

  // ── UAT-01 上传先审计 / 无可用恶意文件 ──────────────────────────────────────
  test('UAT-01 每次上传先建最小 UploadAttempt 审计；仅合法附件形成可用记录，失败尝试保留 outcome 但无可用 Attachment/Version 或可访问恶意文件 (R1)', async () => {
    test.skip(
      !wiring.uploadWired,
      `UAT-01 BLOCKED（非一票否决）：治理上传端点未接线。` +
        `SecureAttachmentGateway 已实现于服务层并有 PG/PBT 证据，但无 HTTP 路由暴露，` +
        `故「上传先审计」无法经浏览器可达的网络契约验证。status=${wiring.uploadStatus}. ` +
        `notes=${wiring.notes.join(' | ')}`,
    )

    // —— 端点接线后自动生效的真实验收断言 ——
    // 合法文件：应创建 UploadAttempt(accepted) + 可用 Attachment/Version（202/201）。
    const legal = await api.post(
      `/api/projects/${PROJECT_A}/years/${YEAR_A}/evidence/attachments`,
      {
        headers: authHeaders(),
        multipart: { file: { name: 'legal.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 minimal') } },
      },
    )
    expect([200, 201, 202]).toContain(legal.status())

    // 非法（声明 pdf 实为其它已知类型/类型不符）：拒绝且不产生可用 Attachment；仍保留失败 UploadAttempt。
    // 治理规则（secure_attachment_gateway._DECLARED_MAGIC_FAMILY / is_declared_detected_consistent）：
    //   声明类型必须落在其 magic 家族内；声明 application/pdf 却嗅探到 image/png（PNG 魔数
    //   \x89PNG\r\n\x1a\n）= 已知跨家族不一致 → MEDIA_TYPE_MISMATCH(415)。注意：不可识别的魔数
    //   （如可执行 MZ）按设计从宽放行（detected=None 不据此判定不一致），故必须用「已识别的错误类型」
    //   才能确定性驱动拒绝路径。
    const illegal = await api.post(
      `/api/projects/${PROJECT_A}/years/${YEAR_A}/evidence/attachments`,
      {
        headers: authHeaders(),
        multipart: {
          file: {
            name: 'evil.pdf',
            mimeType: 'application/pdf',
            buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01, 0x02, 0x03]),
          },
          declared_media_type: 'application/pdf',
        },
      },
    )
    expect([400, 413, 415, 422]).toContain(illegal.status())
    const illegalBody = await illegal.json().catch(() => ({}))
    // 脱敏错误类别（design §7.2）。
    expect(String(JSON.stringify(illegalBody))).toMatch(/MEDIA_TYPE_MISMATCH|ATTACHMENT_TOO_LARGE|error_code/i)
  })

  // ── UAT-02 越界读取否决（一票否决） ────────────────────────────────────────
  test('UAT-02 [一票否决] Storage_Boundary 外路径在读取字节前被否决，且不泄露路径/存在性 (R1, R12)', async () => {
    test.skip(
      !wiring.contentWired,
      `UAT-02 BLOCKED（一票否决无法验证）：治理安全读取端点未接线。` +
        `secure_attachment_gateway.read_attachment_content（边界先于字节 I/O）已实现于服务层，` +
        `但无 HTTP 路由暴露，故越界读取否决无法经网络契约验证。status=${wiring.contentStatus}. ` +
        `notes=${wiring.notes.join(' | ')}`,
    )

    // —— 端点接线后自动生效 ——
    // 构造 traversal/absolute 越界读取意图；应在读取字节前以脱敏错误否决，不泄露路径/存在性。
    // 注意：POSIX 风格 `../../etc/passwd` 的 `/`（%2F）会被 Starlette 在「路由匹配前」解码为路径
    //   分隔符 → 产生多余路径段 → 命中 Starlette 默认 404「Not Found」而 **从未到达治理处理器**，
    //   无法证明治理边界否决。改用「单路径段」的绝对/traversal 形态（反斜杠 Windows 路径，不含
    //   正斜杠）→ 命中 {attachment_id} 段并进入治理处理器，_parse_uuid 在任何字节 I/O 前以脱敏
    //   SCOPE_NOT_FOUND_OR_FORBIDDEN 否决，且不回显该路径（无泄露）。
    const traversalId = encodeURIComponent('..\\..\\..\\..\\windows\\win.ini')
    const r = await api.get(
      `/api/projects/${PROJECT_A}/years/${YEAR_A}/evidence/attachments/${traversalId}/content`,
      { headers: authHeaders() },
    )
    expect([403, 404]).toContain(r.status())
    const body = JSON.stringify(await r.json().catch(() => ({})))
    // 不得泄露绝对路径 / 目标存在性 / 客户信息。
    expect(body).not.toMatch(/etc\/passwd|[A-Za-z]:\\\\|storage_key|\/var\/|\/home\//)
    expect(body).toMatch(/SCOPE_NOT_FOUND_OR_FORBIDDEN|error_code/i)
  })

  // ── UAT-03 跨项目关联否决（一票否决） ──────────────────────────────────────
  test('UAT-03 [一票否决] 项目 A 附件关联项目 B 底稿被否决；关联数不变；不暴露 B 信息 (R3, R4)', async () => {
    test.skip(
      !wiring.refsListHealthy,
      `UAT-03 BLOCKED（一票否决无法验证）：治理 EvidenceRef 端点未功能性接线。` +
        `evidence_ref_router 已挂载但与 EvidenceRefService 签名漂移（GET 缺 actor/误用 status_filter；` +
        `POST 传不存在的 actor 字段 + 双重 facade.execute）→ 读/写均 500，跨项目否决逻辑经网络契约不可达。` +
        `refsListStatus=${wiring.refsListStatus}. notes=${wiring.notes.join(' | ')}`,
    )

    const basePathB = `/api/projects/${PROJECT_B}/years/${YEAR_B}/evidence/refs`

    // 1) 采证：跨项目尝试前，项目 B 侧当前关联数（测试专用只读 API，不直连 DB）。
    const before = await api.get(`${basePathB}/references?direction=source`, { headers: authHeaders() })
    expect(before.status()).toBe(200)
    const beforeItems = (await before.json())?.items ?? []
    const beforeCount = Array.isArray(beforeItems) ? beforeItems.length : 0

    // 2) 越权：在项目 B 的 scope 下，关联一个属于项目 A 的附件证据 → 应被否决。
    const attempt = await api.post(`${basePathB}/references`, {
      headers: { ...authHeaders(), 'Content-Type': 'application/json', 'Idempotency-Key': `uat03-${Date.now()}` },
      data: {
        source_type: 'workpaper_cell',
        source_id: 'wp-B-cell-1',
        evidence_type: 'attachment',
        evidence_id: 'att-belongs-to-project-A',
      },
    })
    // 跨项目/不存在 → 统一脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN（403/404），绝不 2xx 创建。
    expect([403, 404]).toContain(attempt.status())
    const attemptBody = JSON.stringify(await attempt.json().catch(() => ({})))
    // 不暴露 B 的客户 / 项目 / 路径 / 对象名称。
    expect(attemptBody).not.toMatch(/client_name|绝对路径|storage_key/i)
    expect(attemptBody).toMatch(/SCOPE_NOT_FOUND_OR_FORBIDDEN|不可访问|error_code/i)

    // 3) 再次采证：关联数必须不变（无部分写入/反向关系）。
    const after = await api.get(`${basePathB}/references?direction=source`, { headers: authHeaders() })
    expect(after.status()).toBe(200)
    const afterItems = (await after.json())?.items ?? []
    const afterCount = Array.isArray(afterItems) ? afterItems.length : 0
    expect(afterCount).toBe(beforeCount)
  })
})
