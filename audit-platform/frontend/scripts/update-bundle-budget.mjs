#!/usr/bin/env node
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = resolve(SCRIPT_DIR, '..')
const VITE_BIN = resolve(FRONTEND_ROOT, 'node_modules', 'vite', 'bin', 'vite.js')

function runNode(args) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(process.execPath, args, {
      cwd: FRONTEND_ROOT,
      env: process.env,
      stdio: 'inherit',
    })
    child.once('error', reject)
    child.once('exit', (code) => {
      if (code === 0) resolveRun()
      else reject(new Error(`子进程退出码：${code ?? '无'}`))
    })
  })
}

async function main() {
  if (!existsSync(VITE_BIN)) throw new Error('缺少 Vite，请先在前端目录执行 npm ci')
  console.log('正在按当前源码生成真实生产产物…')
  await runNode(['--max-old-space-size=16384', VITE_BIN, 'build', '--mode', 'production'])
  await runNode([resolve(SCRIPT_DIR, 'check-bundle-budget.mjs'), '--update', '--dir', 'dist'])
}

main().catch((error) => {
  console.error(`[ERROR] 包体基线未更新：${error instanceof Error ? error.message : String(error)}`)
  process.exitCode = 1
})
