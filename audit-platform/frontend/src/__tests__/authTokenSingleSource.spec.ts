/**
 * 鉴权 token 存储访问单一入口守卫
 *
 * ## 它防的是什么
 *
 * `stores/auth.ts`（2026-05-05）把 token 从 localStorage 迁到 sessionStorage，并在迁移时
 * **删除** localStorage 副本。此后凡是自己读 `localStorage.getItem('token')` 的原生请求
 * （fetch / XHR / el-upload `:headers` / EventSource `?token=`）恒拿到 null → 不带
 * Authorization → 后端 401。多数调用点把失败吞掉，用户只看到「传不上 / 点了没反应」。
 *
 * 2026-09-29 Playwright 实测：知识库「新建文件夹后上传不了文档」即此根因 —— 同一页
 * `api.get` 200，原生 XHR 上传 401 `Not authenticated`，请求头里根本没有 Authorization。
 * 同类全仓 grep 另有 6 处上传/下载/导出站点同病（盘点/访谈附件、A17-3 附件、D/F/K 期后
 * 序时账、Word 底稿导入导出、链式执行 SSE），已统一改走 `utils/authToken.ts`。
 *
 * ## 判据
 *
 * 生产源码中直接读写 token 存储（local/sessionStorage 的 token/refreshToken 键）只允许出现在：
 *   - `stores/auth.ts`：唯一写入方 + 一次性迁移逻辑
 *   - `utils/authToken.ts`：原生请求的唯一读取入口
 * 以及 `KNOWN_DORMANT_SITES` 登记的**有意未修**站点（只减不增，且必须仍然存在）。
 *
 * 带反向自检（判据自己不能恒真/恒假）与扫描面非空断言。
 */
import { describe, it, expect } from 'vitest'
import {
  FRONTEND_SRC,
  walkSourceFiles,
  readSource,
  isTestFile,
  stripJsComments,
  stripHtmlComments,
  toSrcRelative,
} from './_helpers/frontendSourceScan'

/** 直接访问 token 存储的三种写法：方法调用 / 下标 / 属性 */
const TOKEN_KEYS = '(?:token|refreshToken|access_token|auth_token)'
const TOKEN_STORAGE_ACCESS_RE = new RegExp(
  [
    `(?:local|session)Storage\\s*\\.\\s*(?:getItem|setItem|removeItem)\\s*\\(\\s*['"\`]${TOKEN_KEYS}['"\`]`,
    `(?:local|session)Storage\\s*\\[\\s*['"\`]${TOKEN_KEYS}['"\`]\\s*\\]`,
    `(?:local|session)Storage\\s*\\.\\s*${TOKEN_KEYS}\\b`,
  ].join('|'),
  'g',
)

function findTokenStorageAccess(source: string, isVue: boolean): number[] {
  const code = stripJsComments(isVue ? stripHtmlComments(source) : source)
  const lines: number[] = []
  for (const m of code.matchAll(TOKEN_STORAGE_ACCESS_RE)) {
    lines.push(code.slice(0, m.index).split('\n').length)
  }
  return lines
}

/** 允许直接访问 token 存储的文件（真源 + 单一读取入口） */
const ALLOWED_FILES = new Set(['stores/auth.ts', 'utils/authToken.ts'])

/**
 * 有意未修的站点（只减不增；现为空，新增条目须写明理由并经评审）。
 *
 * 2026-09-29 清零：原登记的两处都是 Univer 底稿保存时的 xlsx 回写（POST
 * .../template-file/upload-xlsx，`useEditorSave.ts` 与零调用方的 `useEditorActions.ts`）——
 * 自 token 迁移起恒 401、从未生效；修好鉴权即会启用「每次保存都用 Univer 导出的 xlsx 覆盖
 * 服务端底稿原文件」这一有损、不可回滚的行为。用户裁定**删除而非启用**：前端回写块、
 * `useEditorActions.ts`、后端 `upload_xlsx_file` 端点一并删除（见 useEditorSave.spec 的回归用例）。
 */
const KNOWN_DORMANT_SITES: ReadonlyArray<{ file: string; reason: string }> = []
const DORMANT_FILE_SET = new Set(KNOWN_DORMANT_SITES.map((d) => d.file))

const ALL_SOURCE_FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => !isTestFile(f))

function scanAll(): Array<{ file: string; line: number }> {
  const hits: Array<{ file: string; line: number }> = []
  for (const abs of ALL_SOURCE_FILES) {
    const rel = toSrcRelative(abs)
    for (const line of findTokenStorageAccess(readSource(abs), rel.endsWith('.vue'))) {
      hits.push({ file: rel, line })
    }
  }
  return hits
}

describe('token 存储访问守卫 · 判据自身不空洞', () => {
  it('扫描面覆盖足够多的生产源文件', () => {
    expect(ALL_SOURCE_FILES.length).toBeGreaterThan(2000)
  })

  it('反向自检：各种直接访问写法都能识别', () => {
    const positives = [
      "const t = localStorage.getItem('token')",
      'const t = sessionStorage.getItem("token") || ""',
      'sessionStorage.setItem(`refreshToken`, x)',
      "localStorage.removeItem('auth_token')",
      "const t = localStorage['token']",
      'const t = sessionStorage.token',
    ]
    for (const sample of positives) {
      expect(findTokenStorageAccess(sample, false), sample).toHaveLength(1)
    }
  })

  it('反向自检：注释、非 token 键、单一入口调用不误报', () => {
    const negatives = [
      "// const t = localStorage.getItem('token')",
      "/* sessionStorage.getItem('token') */",
      "localStorage.getItem('gt_display_prefs')",
      "sessionStorage.getItem('user')",
      "localStorage.getItem('tokenizer_cache')",
      'const headers = getAuthHeaders()',
    ]
    for (const sample of negatives) {
      expect(findTokenStorageAccess(sample, false), sample).toHaveLength(0)
    }
    expect(
      findTokenStorageAccess("<template><!-- localStorage.getItem('token') --></template>", true),
    ).toHaveLength(0)
  })

  it('真源文件确实命中（否则说明扫描器读不到它们，守卫形同虚设）', () => {
    const files = new Set(scanAll().map((h) => h.file))
    expect(files.has('stores/auth.ts')).toBe(true)
    expect(files.has('utils/authToken.ts')).toBe(true)
  })
})

describe('token 存储访问只允许走单一入口', () => {
  const hits = scanAll()

  it('除真源与已登记站点外，不存在直接读写 token 存储的代码', () => {
    const unexpected = hits.filter((h) => !ALLOWED_FILES.has(h.file) && !DORMANT_FILE_SET.has(h.file))
    const detail = unexpected.map((h) => `${h.file}:${h.line}`).join('\n')
    expect(
      unexpected,
      `以下位置直接读写 token 存储（原生请求读 localStorage 恒为空 → 401）：\n${detail}\n` +
        '修法：原生 fetch/XHR/el-upload 改用 `getAuthHeaders()` / `getAuthToken()`（@/utils/authToken）。',
    ).toEqual([])
  })

  it('已登记的有意未修站点仍然存在（名单无失效条目，修好后须从名单移除）', () => {
    const files = new Set(hits.map((h) => h.file))
    const stale = KNOWN_DORMANT_SITES.filter((d) => !files.has(d.file)).map((d) => d.file)
    expect(stale, `这些站点已不再直接访问 token 存储，请从 KNOWN_DORMANT_SITES 移除：${stale.join(', ')}`).toEqual([])
  })

  it('已登记站点每处都写明了理由', () => {
    expect(KNOWN_DORMANT_SITES.every((d) => d.reason.trim().length > 10)).toBe(true)
  })

  it('已删除的 xlsx 覆盖回写不得复活（生产源码不再出现 template-file/upload-xlsx）', () => {
    const revived = ALL_SOURCE_FILES.filter((f) => readSource(f).includes('template-file/upload-xlsx'))
    expect(revived.map(toSrcRelative)).toEqual([])
  })
})
