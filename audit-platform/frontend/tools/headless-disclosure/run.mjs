/**
 * 离屏披露 Node 执行器命令行（spec note-disclosure-pull-regression-and-headless-backend 任务 11~13，design §5.2 / §5.4）。
 * 用 `node run.mjs …` 调用，不写 shebang：Windows 上 autocrlf 检出成 CRLF 后，vitest 转换模块时剥不掉 `#!…\r` 而报语法错。
 * 先构建：node node_modules/vite/bin/vite.js build --config tools/headless-disclosure/vite.config.ts
 *
 *   node tools/headless-disclosure/run.mjs probe   --ctx <ctx.json>                        逐个 provider 实跑，写请求拦下（不写库）
 *   node tools/headless-disclosure/run.mjs capture --project <id> --year <年> [--section <章节>]  prepare + 离屏同步，写请求拦下
 *   node tools/headless-disclosure/run.mjs refresh --project <id> --year <年> [--section <章节>]  prepare → 离屏同步 → push → 重算（写库）
 *   公共：[--out <结果.json>]
 *
 * 环境变量：GT_HEADLESS_TOKEN（服务端发的短期令牌，必填）、GT_HEADLESS_API_BASE（缺省 http://127.0.0.1:9980，只认环回地址）。
 * 写请求只发 `headlessWriteAllowlist` 里本次运行的那几个端点；构建产物与源码不一致时拒绝运行。
 * 结果 JSON 写 stdout（或 --out）；令牌不进输出。
 * 退出码：0 = 跑完（结果里的 ok 说明成败）；1 = 运行出错；2 = 参数错误；3 = 未构建或构建产物已过期。
 *
 * 编排在 `runCommand`（测试直接调它，入口模块换成源码版，见 executor.spec.ts）；直接执行本文件时才读 argv / 退出进程。
 */
import { randomUUID } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { BUILD_HINT, checkBuild } from './buildCheck.mjs'

const DIST = new URL('./dist/', import.meta.url)
const FRONTEND_ROOT = fileURLToPath(new URL('../../', import.meta.url))
export const EXIT_OK = 0
export const EXIT_ERROR = 1
export const EXIT_USAGE = 2
export const EXIT_BUILD = 3

class UsageError extends Error {}

function parseArgs(argv) {
  const [command, ...rest] = argv
  const opts = {}
  for (let i = 0; i < rest.length; i += 1) {
    const key = rest[i]
    if (!key.startsWith('--') || rest[i + 1] === undefined) throw new UsageError(`参数格式不对：${key}`)
    opts[key.slice(2)] = rest[i + 1]
    i += 1
  }
  return { command, opts }
}

function requireOpt(opts, name) {
  if (!opts[name]) throw new UsageError(`缺少 --${name}`)
  return opts[name]
}

function runScope(opts) {
  const year = Number(requireOpt(opts, 'year'))
  if (!Number.isInteger(year)) throw new UsageError(`--year 须为整数年度：${opts.year}`)
  return { projectId: requireOpt(opts, 'project'), year, section: opts.section ?? null }
}

const defaults = {
  env: process.env,
  verifyBuild: () => checkBuild(fileURLToPath(DIST), FRONTEND_ROOT),
  loadEntry: () => import(new URL('entry.mjs', DIST).href),
  stdout: (text) => process.stdout.write(text),
  stderr: (text) => process.stderr.write(text),
}

/** 跑一条命令，返回退出码（见文件头）。`deps` 只给测试替换：构建核对、入口模块、输出。 */
export async function runCommand(argv, deps = {}) {
  const { env, verifyBuild, loadEntry, stdout, stderr } = { ...defaults, ...deps }
  try {
    const { command, opts } = parseArgs(argv)
    if (!['probe', 'capture', 'refresh'].includes(command)) {
      throw new UsageError('用法：run.mjs probe|capture|refresh …（见文件头）')
    }
    const ctxList = command === 'probe' ? JSON.parse(readFileSync(requireOpt(opts, 'ctx'), 'utf8')) : null
    const scope = command === 'probe' ? null : runScope(opts)
    const build = verifyBuild()
    if (!build.ok) {
      const head = build.changed.slice(0, 5).join('、')
      stderr(`[headless-disclosure] ${build.reason}${head ? `：${head}${build.changed.length > 5 ? ' 等' : ''}` : ''}。${BUILD_HINT}\n`)
      return EXIT_BUILD
    }
    const mod = await loadEntry()
    const captured = []
    const intercept = command === 'refresh'
      ? undefined
      : (req) => {
          if (req.url.includes('/pull-from-workpapers') && req.params?.phase === 'prepare') return mod.PASS
          captured.push({ method: req.method, url: req.url, body: req.body })
          return { section_id: req.body?.section_id ?? null, rows_synced: 0, captured: true }
        }
    mod.configureNodeHttp({
      baseUrl: env.GT_HEADLESS_API_BASE || 'http://127.0.0.1:9980',
      token: env.GT_HEADLESS_TOKEN || '',
      clientInstance: `headless-node-${randomUUID()}`,
      allowWrite: mod.headlessWriteAllowlist(ctxList ? ctxList.map((c) => ({ projectId: c.projectId, year: c.year })) : [scope]),
      intercept,
    })
    let result
    if (command === 'probe') {
      result = []
      for (const ctx of ctxList) {
        const before = captured.length
        const started = Date.now()
        try {
          const res = await mod.runProvider(ctx.wpCode, ctx)
          result.push({ code: ctx.wpCode, ok: true, ms: Date.now() - started, sections: res.sections,
            payloads: captured.slice(before) })
        } catch (err) {
          result.push({ code: ctx.wpCode, ok: false, ms: Date.now() - started, error: String(err?.message || err),
            stack: String(err?.stack || '').split('\n').slice(0, 8).join('\n'), payloads: captured.slice(before) })
        }
      }
    } else {
      const run = await mod.refreshNotes({ ...scope, headlessOnly: command === 'capture' })
      result = { ...run, captured: command === 'capture' ? captured : undefined }
    }
    const text = JSON.stringify(result, null, 1)
    if (opts.out) writeFileSync(opts.out, text, 'utf8')
    else stdout(text + '\n')
    return EXIT_OK
  } catch (err) {
    stderr(`[headless-disclosure] ${err instanceof UsageError ? err.message : err?.stack || err}\n`)
    return err instanceof UsageError ? EXIT_USAGE : EXIT_ERROR
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runCommand(process.argv.slice(2)).then((code) => {
    process.exitCode = code
    // 输出已写完；若 provider 留下了定时器等句柄，1 秒后强制退出，不让父进程等到超时
    setTimeout(() => process.exit(code), 1000).unref()
  })
}
