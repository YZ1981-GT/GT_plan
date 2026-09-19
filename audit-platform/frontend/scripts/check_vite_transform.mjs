#!/usr/bin/env node
/**
 * Vite transform 编译扫描 —— 拦「四层静态检查全绿但浏览器 500」的编译错误
 *
 * ## 为什么需要它
 *
 * 2026-08-14 实测（spec: frontend-excel-io-single-entry-convergence Task 18）：
 * `ReportLineMappingDialog.vue` 的两个函数各多一个 `}`（改造中先加裸块 `{` 又删掉，
 * 结尾 `}` 没跟着删）⇒ Vite transform 500 → 整个 TrialBalance 路由崩
 * （console：`Failed to fetch dynamically imported module: /src/views/TrialBalance.vue`）。
 *
 * 而 `get_diagnostics`（Volar）全绿、vitest 107/107 全绿、变异 13/13 全 RED ——
 * **三者都查不出**。只有 `vue/compiler-sfc` 自己会报。
 *
 * memory 铁律已有同类记载：「Vite transform 500 → ErrorBoundary 崩溃，vitest/Volar
 * 解析方式不同故漏检，必须浏览器/CI 兜底」。本脚本把那句「浏览器兜底」变成可脚本化
 * 的一步：请求 dev server 的 transform URL，500 响应体带 `message` + `frame`
 * （精确到 行:列）。
 *
 * ## 用法
 *
 *   node scripts/check_vite_transform.mjs                     # 扫 git 改动的前端文件（本地开发用）
 *   node scripts/check_vite_transform.mjs --from-baseline     # 扫收敛基线记录的全部文件（CI 用）
 *   node scripts/check_vite_transform.mjs --files a.vue b.ts  # 扫指定文件（src/ 下相对路径）
 *   node scripts/check_vite_transform.mjs --port 3030
 *
 * 🔴 CI 必须用 `--from-baseline`：PR checkout 后工作树干净，「git 改动」模式会
 * 报「无待扫文件」直接退出 0 —— 那是空转假绿。
 *
 * 需要 dev server 已在跑。**Vite 只监听 IPv6**，故用 localhost 而非 127.0.0.1
 * （实测 `127.0.0.1:3030` 会「连接被拒绝」，极易误判成服务没起）。
 *
 * 退出码：0 全通过 / 1 有编译失败 / 2 dev server 不可达（无法判定）
 */
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const SRC_PREFIX = 'audit-platform/frontend/src/'

function findRoot() {
  let dir = process.cwd()
  for (let i = 0; i < 12; i += 1) {
    if (fs.existsSync(path.join(dir, 'audit-platform', 'frontend', 'package.json'))) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repo root not found')
}

/**
 * 从收敛基线 JSON 读本 spec 迁移过的全部文件
 *
 * 🔴 CI 里**不能**用「git 改动」模式：PR checkout 后工作树是干净的，
 * `git status --porcelain` 返回空 ⇒ 脚本报「无待扫文件」并退出 0 = **空转假绿**。
 *
 * 也不手抄文件清单 —— 那会随重命名 stale。基线 JSON 的 `_progress[].files`
 * 已逐批记录全部迁移文件，是单一真源。
 */
function collectFromBaseline(root) {
  const p = path.join(
    root,
    'audit-platform/frontend/src/composables/__tests__/_baseline/excelIoConvergence.baseline.json',
  )
  if (!fs.existsSync(p)) {
    console.error(`🔴 基线 JSON 不存在：${p}`)
    return null
  }
  const baseline = JSON.parse(fs.readFileSync(p, 'utf-8'))
  const rels = new Set(['composables/useExcelIO.ts']) // 入口本身
  for (const entry of baseline._progress || []) {
    for (const f of entry.files || []) rels.add(f)
  }
  const missing = [...rels].filter(
    (r) => !fs.existsSync(path.join(root, SRC_PREFIX, r)),
  )
  if (missing.length) {
    console.error(
      `🔴 基线记录的 ${missing.length} 个文件在磁盘上不存在（重命名/删除后未同步基线）：`,
    )
    for (const m of missing) console.error(`     ${m}`)
    return null
  }
  return [...rels]
}

/** 取待扫文件：--files > --from-baseline > git 改动 */
function collectTargets(args, root) {
  const filesIdx = args.indexOf('--files')
  if (filesIdx >= 0) {
    return args.slice(filesIdx + 1).filter((a) => !a.startsWith('--'))
  }
  if (args.includes('--from-baseline')) {
    return collectFromBaseline(root)
  }

  let out = ''
  try {
    out = execSync('git status --porcelain', {
      cwd: root,
      encoding: 'utf-8',
      maxBuffer: 32 * 1024 * 1024,
    })
  } catch {
    return null // 交给调用方报错
  }

  const rels = []
  for (const line of out.split('\n')) {
    const p = line.slice(3).trim()
    if (!p.startsWith(SRC_PREFIX)) continue
    if (!/\.(vue|ts)$/.test(p)) continue
    if (p.includes('__tests__/') || /\.(spec|test)\.ts$/.test(p)) continue
    rels.push(p.slice(SRC_PREFIX.length))
  }
  return [...new Set(rels)]
}

/** 从 Vite 的 500 响应体里抠出编译错误信息 */
function extractViteError(body, status) {
  const m = body.match(/"message":"(.*?)","stack/s)
  if (!m) return `HTTP ${status}`
  try {
    return JSON.parse(`"${m[1]}"`)
  } catch {
    return m[1]
  }
}

async function main() {
  const args = process.argv.slice(2)
  const portIdx = args.indexOf('--port')
  const port = portIdx >= 0 ? args[portIdx + 1] : '3030'
  const base = `http://localhost:${port}/src/`
  const root = findRoot()

  const targets = collectTargets(args, root)
  if (targets === null) {
    // 🔴 两条失败路径都返回 null，但原因不同 —— 分开报，否则「基线列了已删文件」
    // 会被误读成「git status 失败」，排查方向直接跑偏（2026-08-14 实测踩到）。
    // collectFromBaseline 自己已打印具体缺失文件清单，这里只补处置建议。
    if (args.includes('--from-baseline')) {
      console.error(
        '⇒ 基线 `_progress[].files` 与磁盘不一致。若该文件是**有意删除**的，' +
          '请从 files 数组移出（可在同级加 `_files_removed_later` 记录原因）；' +
          '若是重命名，请同步新路径。',
      )
    } else {
      console.error('git status 失败 —— 请用 --files 或 --from-baseline 显式指定文件')
    }
    return 2
  }
  if (targets.length === 0) {
    console.log('无待扫文件（git 无 src/ 下改动）')
    return 0
  }

  // dev server 存活检查 —— 否则「全部失败」会被误读成「代码全崩」
  try {
    const probe = await fetch(`http://localhost:${port}/`, { signal: AbortSignal.timeout(8000) })
    if (!probe.ok) throw new Error(`HTTP ${probe.status}`)
  } catch (e) {
    console.error(
      `🔴 dev server 不可达（localhost:${port}）：${e.message}\n` +
        '   本脚本需要 dev server 在跑。注意 Vite **只监听 IPv6**，须用 localhost 而非 127.0.0.1。',
    )
    return 2
  }

  console.log(`扫描 ${targets.length} 个文件的 Vite transform（localhost:${port}）...\n`)

  const bad = []
  for (const rel of targets) {
    try {
      const r = await fetch(base + rel, { signal: AbortSignal.timeout(60000) })
      if (r.ok) continue
      bad.push({ rel, msg: extractViteError(await r.text(), r.status) })
    } catch (e) {
      bad.push({ rel, msg: `${e.name}: ${e.message}` })
    }
  }

  if (bad.length === 0) {
    console.log(`✅ ${targets.length}/${targets.length} 个文件 Vite 编译通过`)
    return 0
  }

  console.log(`🔴 ${bad.length}/${targets.length} 个文件编译失败：\n`)
  for (const { rel, msg } of bad) {
    console.log(`  ${rel}`)
    for (const line of String(msg).split('\n').slice(0, 8)) console.log(`      ${line}`)
    console.log()
  }
  console.log(
    '注意：这类错误 get_diagnostics / vitest 都查不出（解析器不同）。\n' +
      'vue/compiler-sfc 报的位置常是**函数结尾**而非出错处，须顺着往上找括号配平。',
  )
  return 1
}

// 🔴 用 exitCode 让进程自然退出，**不要** process.exit()
//
// Windows + Node 上 `process.exit()` 会在 fetch 的 keep-alive socket 还开着时触发
// libuv assertion：`Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)`，
// 退出码变成 0xC0000409（-1073740791）—— CI 会把「编译全通过」误判成崩溃。
// 实测：改用 exitCode 后进程等连接池空闲再干净退出。
process.exitCode = await main()
