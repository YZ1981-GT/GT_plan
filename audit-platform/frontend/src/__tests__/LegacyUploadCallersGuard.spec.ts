/**
 * 底稿内上传只走证据入口 —— 旧附件上传端点的调用方白名单
 * （spec attachment-evidence-intake 需求 5.5、ADR-AEI-08，变异 #14）
 *
 * 回归背景：底稿组件各自调 `/api/projects/{pid}/attachments/upload`（或 commonApi.uploadAttachment），
 * 再按 title 过滤（后端从不保存 title ⇒ 上传后看不见）、另调 associate（编制人恒 404）、
 * 发后端不认的 wp_id / type 字段、或用 el-upload 原生上传拿被信封包着的回执（附件编号恒空）——
 * 附件不关联底稿、行上看不见。底稿内上传一律走 `components/attachment/workpaperEvidence.uploadWorkpaperEvidence`。
 *
 * 判据：
 *  A. 剥注释后的代码里出现旧上传写法（端点路径字面量、apiPaths 的 upload(…)、从 commonApi 导入 uploadAttachment），
 *     只允许在白名单文件里；
 *  B. 白名单无失效条目（登记的文件真的还在用旧写法）；
 *  C. 扫描器自检：合成源码里的旧写法必须被抓到，注释里的不算；
 *  D. 证据入口的使用面非空（防迁移被整体回退而本守卫恒绿）。
 */
import { describe, expect, it } from 'vitest'
import {
  FRONTEND_SRC,
  readSource,
  stripHtmlComments,
  stripJsComments,
  toSrcRelative,
  walkSourceFiles,
} from './_helpers/frontendSourceScan'

/** 允许继续用旧上传端点的文件（都不在底稿上下文里）。 */
const ALLOWED: Record<string, string> = {
  'services/apiPaths/system.ts': '旧端点路径定义本身',
  'services/commonApi.ts': 'uploadAttachment 定义本身',
  'views/AttachmentManagement.vue': '项目附件库：上传到项目，不属于某张底稿',
  'components/workpaper/confirmation/ConfirmationAttachmentDrawer.vue': '函证发函 / 回函件：由函证模块挂载（confirmation_attachment_link）',
}

const PATTERNS: Array<{ label: string; re: RegExp }> = [
  { label: '旧上传端点路径', re: /\/attachments\/upload\b/g },
  { label: 'apiPaths 的 upload(…)', re: /\b(?:P_att|P_attachments)\.upload\(/g },
  { label: '从 commonApi 导入 uploadAttachment', re: /import\s*\{[^}]*\buploadAttachment\b[^}]*\}\s*from\s*['"]@\/services\/commonApi['"]/g },
]

interface Hit { file: string; label: string }

/** 剥注释：.vue 的模板段剥 HTML 注释、脚本段剥 JS 注释（模板文字里的单引号不会干扰脚本段）。 */
function codeOf(file: string, source: string): string {
  if (!file.endsWith('.vue')) return stripJsComments(source)
  const SCRIPT = /<script[^>]*>([\s\S]*?)<\/script>/g
  const scripts = [...source.matchAll(SCRIPT)].map((m) => stripJsComments(m[1]))
  return [stripHtmlComments(source.replace(SCRIPT, '')), ...scripts].join('\n')
}

export function scanLegacyUploads(file: string, source: string): Hit[] {
  const code = codeOf(file, source)
  const hits: Hit[] = []
  for (const { label, re } of PATTERNS) {
    re.lastIndex = 0
    for (const _ of code.matchAll(re)) hits.push({ file, label })
  }
  return hits
}

const FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => /\.(vue|ts)$/.test(f) && !f.endsWith('.d.ts'))
const SOURCES = new Map(FILES.map((f) => [toSrcRelative(f), readSource(f)]))
const HITS = [...SOURCES].flatMap(([f, s]) => scanLegacyUploads(f, s))

describe('底稿内上传只走证据入口（旧附件上传端点调用方白名单）', () => {
  it('A：白名单之外没有旧上传写法', () => {
    const bad = HITS.filter((h) => !(h.file in ALLOWED)).map((h) => `${h.file} :: ${h.label}`)
    expect(bad, '底稿内上传改用 uploadWorkpaperEvidence（components/attachment/workpaperEvidence.ts）').toEqual([])
  })

  it('B：白名单无失效条目', () => {
    const used = new Set(HITS.map((h) => h.file))
    expect(Object.keys(ALLOWED).filter((f) => !used.has(f)), '登记的文件已不再用旧写法，请删除该条').toEqual([])
  })

  it('C：扫描器抓得到代码里的旧写法，注释里的不算', () => {
    const vue = [
      '<template>',
      '  <!-- <el-upload action="/api/projects/1/attachments/upload" /> -->',
      '  <el-upload :action="`/api/projects/${pid}/attachments/upload`" />',
      '</template>',
      '<script setup lang="ts">',
      "import { uploadAttachment } from '@/services/commonApi'",
      '// await api.post(`/api/projects/${pid}/attachments/upload`, fd)',
      '/* P_att.upload(pid) */',
      'await http.post(P_att.upload(pid), fd)',
      "const url = 'https://example.com/a' // 引号里的 // 不是注释",
      '</script>',
    ].join('\n')
    expect(scanLegacyUploads('synthetic.vue', vue).map((h) => h.label)).toEqual([
      '旧上传端点路径', 'apiPaths 的 upload(…)', '从 commonApi 导入 uploadAttachment',
    ])
    expect(scanLegacyUploads('clean.ts', "// '/attachments/upload'\nconst x = 1\n")).toEqual([])
  })

  it('D：证据入口的使用面非空', () => {
    const users = [...SOURCES].filter(([f, s]) =>
      !f.startsWith('components/attachment/workpaperEvidence') && /\buploadWorkpaperEvidence\(/.test(stripJsComments(s)))
    expect(users.length).toBeGreaterThanOrEqual(18)
    expect(FILES.length).toBeGreaterThan(1000)
  })
})
