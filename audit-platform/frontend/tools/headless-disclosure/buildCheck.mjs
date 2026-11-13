/**
 * 离屏执行器构建产物新鲜度核对（spec note-disclosure-pull-regression-and-headless-backend 任务 13，design §5.4）。
 *
 * dist/source-manifest.json 由构建时的插件写出（见 vite.config.ts）：打进包里的每个源文件的 sha256。运行前逐个核对 ——
 * 源码改了没重新构建，离屏算出的就是旧版 builder 的数，写进附注是静默错数，所以宁可不跑。
 */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

export const BUILD_HINT = '在 audit-platform/frontend 下执行：node node_modules/vite/bin/vite.js build --config tools/headless-disclosure/vite.config.ts'

/**
 * @param {string} distDir 构建输出目录
 * @param {string} frontendRoot 前端目录（清单里的路径相对它）
 * @returns {{ ok: true, files: number } | { ok: false, reason: string, changed: string[] }}
 */
export function checkBuild(distDir, frontendRoot) {
  const entry = join(distDir, 'entry.mjs')
  const manifestPath = join(distDir, 'source-manifest.json')
  if (!existsSync(entry) || !existsSync(manifestPath)) {
    return { ok: false, reason: `离屏执行器尚未构建（缺 ${existsSync(entry) ? 'source-manifest.json' : 'entry.mjs'}）`, changed: [] }
  }
  let manifest
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  } catch (err) {
    return { ok: false, reason: `离屏执行器构建清单无法解析：${err?.message || err}`, changed: [] }
  }
  const files = Array.isArray(manifest?.files) ? manifest.files : []
  if (manifest?.schema !== 'headless-disclosure-source-manifest/v1' || files.length === 0) {
    return { ok: false, reason: '离屏执行器构建清单格式不对或为空', changed: [] }
  }
  const changed = []
  for (const { path, sha256 } of files) {
    const full = join(frontendRoot, path)
    const now = existsSync(full) ? createHash('sha256').update(readFileSync(full)).digest('hex') : null
    if (now !== sha256) changed.push(now === null ? `${path}（已删除）` : path)
  }
  if (changed.length) {
    return { ok: false, reason: `离屏执行器构建产物已过期：构建后有 ${changed.length} 个源文件改动`, changed }
  }
  return { ok: true, files: files.length }
}
