/**
 * 浏览器原生加载 / 跳转带不上 Bearer 头 —— 全前端守卫（spec attachment-security-baseline 任务 12）
 *
 * iframe / img 的 src、a / el-link 的 href、window.open / location.href 都不经 axios；
 * 后端鉴权只认 Authorization 头（HTTPBearer，没有 cookie / 查询串令牌），这些写法指向 /api 一律 401。
 * 2026-10-27 走查实测：附件 OCR 确认弹窗的原件区显示 {"code":401,"message":"Not authenticated"}。
 * 全仓同类 18 处已改为 useAuthedObjectUrl（内嵌预览）/ downloadFile、downloadAttachment（下载）。
 *
 * 判据：
 *  A. 模板：媒体标签（iframe/img/embed/object/video/audio/source/el-image）的 src/data、
 *     链接标签（a/el-link/el-button/router-link）的 href，值里出现 `/api/` ⇒ 违规；
 *     绑定表达式逐条登记在 TEMPLATE_BINDINGS（写明来源类别），未登记的新绑定 ⇒ 打红。
 *  B. 脚本：window.open( / location.href = / location.assign( 的目标出现 `/api` ⇒ 违规；
 *     其余调用点逐条登记在 SCRIPT_NAVIGATIONS；`x.href = …` 的右值出现 `/api` ⇒ 违规。
 *  C. 登记项必须仍然存在（防失效条目）；类别 object-url 的文件必须真的调用了
 *     useAuthedObjectUrl 或 createObjectURL（可伪证，不是写句理由就放行）。
 *  D. 扫描器自检：合成源码里的违规写法必须被抓到（防扫描器失明恒绿）。
 *
 * 新增一处原生加载时：指向 /api 的改走上面两个函数；确属前端路由 / 外链 / blob 地址的，按类别登记。
 */
import { describe, it, expect } from 'vitest'
import {
  FRONTEND_SRC,
  readSource,
  stripHtmlComments,
  stripJsComments,
  toSrcRelative,
  walkSourceFiles,
} from './_helpers/frontendSourceScan'

type Kind =
  | 'object-url' // blob: 地址（useAuthedObjectUrl / createObjectURL 产出）
  | 'external' // 站外地址（带签名的嵌入地址、外部文档）
  | 'user-link' // 用户填写的链接文本
  | 'frontend-route' // 站内前端路由（SPA 页面，不是 /api）
  | 'blank-window' // 空白窗口（打印预览自己写内容）
  | 'dormant' // 目标字段当前无写入方，接线时须按 /api 与否选下载方式

interface Entry {
  file: string
  expr: string
  count?: number
  kind: Kind
  why: string
}

const TEMPLATE_BINDINGS: Entry[] = [
  { file: 'components/attachment/BatchUploadResultDialog.vue', expr: 'previewSrc', count: 2, kind: 'object-url', why: 'useAuthedObjectUrl' },
  { file: 'components/attachment/OcrConfirmDialog.vue', expr: 'previewSrc', count: 2, kind: 'object-url', why: 'useAuthedObjectUrl' },
  { file: 'components/attachment/preview/AttachmentPreviewCore.vue', expr: 'previewSrc', kind: 'object-url', why: 'client 预览 api.get(blob) + createObjectURL' },
  { file: 'components/attachment/preview/AttachmentPreviewCore.vue', expr: 'serverObjectUrl', count: 2, kind: 'object-url', why: 'useAuthedObjectUrl' },
  { file: 'components/template-library/WpTemplateDetail.vue', expr: 'previewObjectUrl', kind: 'object-url', why: 'useAuthedObjectUrl' },
  { file: 'views/KnowledgeBase.vue', expr: 'previewUrl', count: 2, kind: 'object-url', why: 'api.get(blob) + createObjectURL' },
  { file: 'components/extension/MetabaseDashboard.vue', expr: 'embedUrl', kind: 'external', why: '后端签发的 Metabase 嵌入地址（自带签名）' },
  { file: 'components/workpaper/confirmation/reliability/ReliabilityGrid.vue', expr: "tooltipMap['注2'].link.url", kind: 'external', why: '致同技术提示外部文档' },
  // 以下由「脚本在前的 SFC 也扫模板」新扫出（spec attachment-evidence-intake 需求 6.2）
  { file: 'components/workpaper/d2/D2VcCardView.vue', expr: 'att.thumbnailUrl', kind: 'dormant', why: 'VcAttachment.thumbnailUrl 无写入方（缩略图未接线；接线时指向 /api 须改 useAuthedObjectUrl）' },
]

const SCRIPT_NAVIGATIONS: Entry[] = [
  { file: 'components/ai/ChatContextInspector.vue', expr: 'item.jump_route', kind: 'frontend-route', why: '上下文条目的站内跳转路由' },
  { file: 'components/ai/ChatNoteSaveDialog.vue', expr: 'route', kind: 'frontend-route', why: '前面已校验以 / 开头的站内路径' },
  { file: 'components/ai/DshPanel.vue', expr: "`/ai-chat${query ? `?${query}` : ''}`", kind: 'frontend-route', why: '/ai-chat 页面' },
  { file: 'components/ai/KnowledgeBasePanel.vue', expr: 'result.url', kind: 'dormant', why: '零挂载组件（检索结果是写死的样例，无 url）' },
  { file: 'components/ai/PlatformAiChatPanel.vue', expr: 'result.jumpRoute', count: 2, kind: 'frontend-route', why: '笔记页路由' },
  { file: 'components/common/GtPrintPreview.vue', expr: "''", kind: 'blank-window', why: '打印预览自己写入内容' },
  { file: 'components/ledger-import/DiagnosticPanel.vue', expr: 'route.href', kind: 'frontend-route', why: 'router.resolve 结果' },
  { file: 'components/ledger-import/ErrorDialog.vue', expr: 'route.href', kind: 'frontend-route', why: 'router.resolve 结果' },
  { file: 'components/query/queryResultLinks.ts', expr: 'router.resolve(resolved.location).href', kind: 'frontend-route', why: '高级查询结果行下钻：router.resolve 结果（账簿 / 报表 / 附注 / 调整分录 / 底稿页，advanced-query-linkage-closure 任务 27）' },
  { file: 'components/workpaper/composables/g7ConsolLinkageEntry.ts', expr: '`/projects/${projectId.value}/consolidation*', kind: 'frontend-route', why: '合并页（查询串写法随审计年度改动，前缀匹配）' },
  { file: 'composables/useAcnrDrill.ts', expr: 'route', kind: 'frontend-route', why: '地址穿透的站内路由' },
  { file: 'stores/auth.ts', expr: "'/login'", kind: 'frontend-route', why: '登录页' },
  { file: 'utils/http.ts', expr: "'/login'", count: 3, kind: 'frontend-route', why: '登录页' },
  { file: 'utils/openLedgerWindow.ts', expr: 'resolved.href', kind: 'frontend-route', why: 'router.resolve 结果' },
  { file: 'views/ConsolidationIndex.vue', expr: 'finalRoute', kind: 'frontend-route', why: '地址库跳转路由' },
  { file: 'views/LedgerStandalonePage.vue', expr: '`/projects/${projectId.value}/ledger`', kind: 'frontend-route', why: '账表页' },
  { file: 'views/LedgerStandalonePage.vue', expr: "'/login'", kind: 'frontend-route', why: '登录页' },
]

// ─── 扫描器 ───────────────────────────────────────────────────────────────

const MEDIA_TAGS = ['iframe', 'img', 'embed', 'object', 'video', 'audio', 'source', 'el-image']
const LINK_TAGS = ['a', 'el-link', 'el-button', 'router-link']
const TAG_START = new RegExp(`<(${[...MEDIA_TAGS, ...LINK_TAGS].join('|')})(?=[\\s>/])`, 'gi')
const ATTR = /(?:^|\s)(:|v-bind:)?(src|data|href)\s*=\s*"([^"]*)"/g

interface Hit { file: string; expr: string; bound?: boolean; tag?: string; attr?: string }

/**
 * 模板段：去掉 `<script>` / `<style>` 块后的其余部分；按引号配平找标签结尾。
 *
 * 原先取「`<script` 之前的部分」（假设模板在前）：脚本在前的 SFC 整份模板被跳过 ——
 * `GtB212Evaluation.vue` 的 `<a :href="/api/attachments/{id}/preview">` 因此漏网（spec attachment-evidence-intake 需求 6.2）。
 */
export function scanTemplate(file: string, source: string): Hit[] {
  const tpl = stripHtmlComments(
    source.replace(/<script[^>]*>[\s\S]*?<\/script>/g, '').replace(/<style[^>]*>[\s\S]*?<\/style>/g, ''),
  )
  const hits: Hit[] = []
  for (const m of tpl.matchAll(TAG_START)) {
    const tag = m[1].toLowerCase()
    let i = (m.index ?? 0) + m[0].length
    let quote: string | null = null
    for (; i < tpl.length; i++) {
      const ch = tpl[i]
      if (quote) { if (ch === quote) quote = null } else if (ch === '"' || ch === "'") quote = ch
      else if (ch === '>') break
    }
    const raw = tpl.slice(m.index ?? 0, i + 1)
    for (const a of raw.matchAll(ATTR)) {
      const attr = a[2]
      if (MEDIA_TAGS.includes(tag) === (attr === 'href')) continue // 媒体标签看 src/data，链接标签看 href
      hits.push({ file, tag, attr, bound: Boolean(a[1]), expr: a[3].trim() })
    }
  }
  return hits
}

/** 取 `(` 之后第一个顶层实参（括号 / 引号 / 模板串配平）。 */
function firstArg(code: string, from: number): string {
  let depth = 0
  let quote: string | null = null
  let i = from
  for (; i < code.length; i++) {
    const ch = code[i]
    if (quote) {
      if (ch === '\\') { i++; continue }
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue }
    if (ch === '(' || ch === '[' || ch === '{') depth++
    else if (ch === ')' || ch === ']' || ch === '}') { if (depth === 0) break; depth-- }
    else if (ch === ',' && depth === 0) break
  }
  return code.slice(from, i).replace(/\s+/g, ' ').trim()
}

function scriptPart(file: string, source: string): string {
  if (!file.endsWith('.vue')) return stripJsComments(source)
  return [...source.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => stripJsComments(m[1])).join('\n')
}

/** window.open( / location.assign( 的第一参数，location.href = 的右值。 */
export function scanNavigations(file: string, source: string): Hit[] {
  const code = scriptPart(file, source)
  const hits: Hit[] = []
  for (const m of code.matchAll(/\b(?:window\.open|location\.assign)\(/g)) {
    hits.push({ file, expr: firstArg(code, (m.index ?? 0) + m[0].length) })
  }
  for (const m of code.matchAll(/\blocation\.href\s*=(?!=)\s*/g)) {
    const rest = code.slice((m.index ?? 0) + m[0].length)
    hits.push({ file, expr: (rest.split(/\n|;/)[0] ?? '').trim() })
  }
  return hits
}

/** `x.href = …` 右值里出现 /api（创建 a 元素后点击、或改 location 的另一种写法）。 */
export function scanHrefAssignments(file: string, source: string): Hit[] {
  const code = scriptPart(file, source)
  const hits: Hit[] = []
  for (const m of code.matchAll(/\.href\s*=(?!=)\s*([^\n;]*)/g)) {
    if (/\/api\b/.test(m[1]) || /\bP_\w+\.|apiPaths/.test(m[1])) hits.push({ file, expr: m[1].trim() })
  }
  return hits
}

// ─── 全仓数据 ─────────────────────────────────────────────────────────────

const FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => /\.(vue|ts)$/.test(f) && !f.endsWith('.d.ts'))
const SOURCES = new Map(FILES.map((f) => [toSrcRelative(f), readSource(f)]))
const TEMPLATE_HITS = [...SOURCES].filter(([f]) => f.endsWith('.vue')).flatMap(([f, s]) => scanTemplate(f, s))
const NAV_HITS = [...SOURCES].flatMap(([f, s]) => scanNavigations(f, s))
const HREF_HITS = [...SOURCES].flatMap(([f, s]) => scanHrefAssignments(f, s))

/**
 * 实际命中与登记逐条对账。登记的 expr 以 `*` 结尾表示前缀匹配：站内路由拼接查询串这类无害改写
 * （如追加 `?year=`）不必每次改登记；改出 /api 仍由判据 B 的 /api 检查拦住。
 */
function diff(hits: Hit[], entries: Entry[]) {
  const owner = (h: Hit) => entries.find((e) => e.file === h.file
    && (e.expr.endsWith('*') ? h.expr.startsWith(e.expr.slice(0, -1)) : h.expr === e.expr))
  const counts = new Map<Entry, number>()
  const unregisteredTally = new Map<string, number>()
  for (const h of hits) {
    const e = owner(h)
    if (e) counts.set(e, (counts.get(e) ?? 0) + 1)
    else unregisteredTally.set(`${h.file} :: ${h.expr}`, (unregisteredTally.get(`${h.file} :: ${h.expr}`) ?? 0) + 1)
  }
  const unregistered = [...unregisteredTally].map(([k, n]) => `${k} ×${n}`)
  const countMismatch = entries.filter((e) => counts.has(e) && counts.get(e) !== (e.count ?? 1))
    .map((e) => `${e.file} :: ${e.expr}：实际 ×${counts.get(e)}，登记 ×${e.count ?? 1}`)
  const stale = entries.filter((e) => !counts.has(e)).map((e) => `${e.file} :: ${e.expr}`)
  return { unregistered, countMismatch, stale }
}

describe('浏览器原生加载 / 跳转不得指向 /api（带不上 Bearer 头，恒 401）', () => {
  it('扫描面非空（防扫描器失明恒绿）', () => {
    expect(FILES.length).toBeGreaterThan(1000)
    expect(TEMPLATE_HITS.length).toBeGreaterThanOrEqual(TEMPLATE_BINDINGS.length)
    expect(NAV_HITS.length).toBeGreaterThanOrEqual(SCRIPT_NAVIGATIONS.length)
  })

  it('A：模板 src / href 的值里没有 /api/ 路径', () => {
    const bad = TEMPLATE_HITS.filter((h) => h.expr.includes('/api/')).map((h) => `${h.file} <${h.tag} ${h.attr}="${h.expr}">`)
    expect(bad, '改用 useAuthedObjectUrl（内嵌预览）或 downloadFile / downloadAttachment（下载）').toEqual([])
  })

  it('A：模板里每个绑定的 src / href 都已登记来源类别，且登记无失效条目', () => {
    const bound = TEMPLATE_HITS.filter((h) => h.bound)
    const { unregistered, countMismatch, stale } = diff(bound, TEMPLATE_BINDINGS)
    expect(unregistered, '新的原生加载绑定：指向 /api 的改走 useAuthedObjectUrl / downloadFile，其余按类别登记').toEqual([])
    expect(countMismatch).toEqual([])
    expect(stale, '登记条目已不存在，请删除').toEqual([])
  })

  it('B：window.open / location 的目标里没有 /api', () => {
    const bad = NAV_HITS.filter((h) => /\/api\b/.test(h.expr) || /\bP_\w+\.|apiPaths/.test(h.expr)).map((h) => `${h.file} :: ${h.expr}`)
    expect(bad, '下载改用 downloadFile / downloadAttachment').toEqual([])
    expect(HREF_HITS.map((h) => `${h.file} :: ${h.expr}`)).toEqual([])
  })

  it('B：每个 window.open / location 调用点都已登记，且登记无失效条目', () => {
    const { unregistered, countMismatch, stale } = diff(NAV_HITS, SCRIPT_NAVIGATIONS)
    expect(unregistered, '新的原生跳转：指向 /api 的改走 downloadFile，站内路由 / 外链按类别登记').toEqual([])
    expect(countMismatch).toEqual([])
    expect(stale, '登记条目已不存在，请删除').toEqual([])
  })

  it('C：object-url 类登记可伪证 —— 文件里真的生成了 blob: 地址', () => {
    const fake = TEMPLATE_BINDINGS.filter((e) => e.kind === 'object-url').filter((e) => {
      const src = stripJsComments(SOURCES.get(e.file) ?? '')
      return !/useAuthedObjectUrl\(|createObjectURL\(/.test(src)
    }).map((e) => e.file)
    expect(fake).toEqual([])
  })

  it('D：扫描器能抓到合成源码里的违规写法', () => {
    const sfc = [
      '<template>',
      '  <!-- <iframe :src="P_att.preview(x)" /> 注释里的不算 -->',
      '  <iframe',
      '    class="x"',
      '    :src="`/api/attachments/${id}/preview`"',
      '  />',
      '  <img :src="P_att.preview(id)">',
      '  <a :href="downloadUrl(att.id)" target="_blank">下载</a>',
      '  <el-link :href="\'/api/x\'">x</el-link>',
      '</template>',
      '<script setup lang="ts">',
      "// window.open('/api/commented')",
      "window.open(`/api/exports/${id}`, '_blank')",
      'window.location.href = P_att.download(id)',
      "a.href = '/api/x/download'",
      '</script>',
    ].join('\n')
    const t = scanTemplate('synthetic.vue', sfc)
    expect(t.map((h) => h.expr)).toEqual(['`/api/attachments/${id}/preview`', 'P_att.preview(id)', 'downloadUrl(att.id)', "'/api/x'"])
    expect(t.filter((h) => h.expr.includes('/api/'))).toHaveLength(2)
    const n = scanNavigations('synthetic.vue', sfc)
    expect(n.map((h) => h.expr)).toEqual(['`/api/exports/${id}`', 'P_att.download(id)'])
    // location.href = … 同时被两条判据看到（重复覆盖无害）
    expect(scanHrefAssignments('synthetic.vue', sfc).map((h) => h.expr)).toEqual(['P_att.download(id)', "'/api/x/download'"])
  })

  it('D：脚本在前的 SFC 也扫模板（原先只取 <script 之前的部分，整份模板被跳过）', () => {
    const scriptFirst = [
      '<script setup lang="ts">',
      "const css = '<a :href=\"/api/in-script\">'",
      '</script>',
      '<template>',
      '  <a :href="`/api/attachments/${id}/preview`" target="_blank">📎</a>',
      '  <img :src="thumbUrl">',
      '</template>',
      '<style scoped>.x { background: url("/api/not-a-tag"); }</style>',
    ].join('\n')
    expect(scanTemplate('script-first.vue', scriptFirst).map((h) => h.expr)).toEqual([
      '`/api/attachments/${id}/preview`', 'thumbUrl',
    ])
  })

  it('D：前缀登记只放行同文件、同前缀的写法；精确登记要求逐字一致；计数与失效照常判', () => {
    const entries: Entry[] = [
      { file: 'a.ts', expr: '`/projects/${pid}/x*', count: 2, kind: 'frontend-route', why: '' },
      { file: 'a.ts', expr: "'/login'", kind: 'frontend-route', why: '' },
      { file: 'a.ts', expr: "'/gone'", kind: 'frontend-route', why: '' },
    ]
    const hits: Hit[] = [
      { file: 'a.ts', expr: '`/projects/${pid}/x?year=${y}`' },
      { file: 'a.ts', expr: '`/projects/${pid}/x`' },
      { file: 'b.ts', expr: '`/projects/${pid}/x`' }, // 别的文件：不受 a.ts 的前缀登记放行
      { file: 'a.ts', expr: "'/login' " },             // 精确登记不放行近似写法
    ]
    const r = diff(hits, entries)
    expect(r.unregistered).toEqual(['b.ts :: `/projects/${pid}/x` ×1', "a.ts :: '/login'  ×1"])
    expect(r.countMismatch).toEqual([])
    expect(r.stale).toEqual(["a.ts :: '/login'", "a.ts :: '/gone'"])
    expect(diff(hits.slice(0, 1), entries).countMismatch).toEqual(['a.ts :: `/projects/${pid}/x*：实际 ×1，登记 ×2'])
  })
})
