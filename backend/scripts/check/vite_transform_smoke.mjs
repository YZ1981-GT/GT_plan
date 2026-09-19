#!/usr/bin/env node
/**
 * vite_transform_smoke.mjs — Vite 全树冒烟（transform 级崩溃检测）
 *
 * 以 Vite middleware mode 启动 dev server，对底稿源码树每个 .vue/.ts 文件
 * 调 transformRequest(url) 遍历，收集抛错文件。
 * 任一文件 transform 失败（等价 HTTP 500）→ 退出码非 0 并列出文件路径。
 *
 * 比 Volar/get_diagnostics 更权威的崩溃检测手段，能抓 import 解析失败/模板内嵌引号/结构损坏。
 *
 * Usage:
 *   node backend/scripts/check/vite_transform_smoke.mjs
 *
 * Requirements: 3.2
 * Feature: platform-global-hardening
 */

import { resolve, relative } from 'node:path';
import { readdir, stat } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// Resolve vite from the frontend's node_modules (script lives in backend/scripts/check/)
const FRONTEND_ROOT = resolve(import.meta.dirname, '../../../audit-platform/frontend');
const require = createRequire(resolve(FRONTEND_ROOT, 'package.json'));
const vitePath = require.resolve('vite');
const { createServer } = await import(pathToFileURL(vitePath).href);

// --- Configuration ---
const SCAN_DIR = resolve(FRONTEND_ROOT, 'src/components/workpaper');
const EXTENSIONS = new Set(['.vue', '.ts']);
// Exclude test files, declaration files, and spec files from transform check
const EXCLUDE_PATTERNS = [
  /\.test\.[jt]sx?$/,
  /\.spec\.[jt]sx?$/,
  /\.pbt\.spec\.[jt]sx?$/,
  /\.d\.ts$/,
  /__tests__\//,
];

// --- Helpers ---

/**
 * Recursively collect all .vue and .ts files under a directory.
 */
async function collectFiles(dir) {
  const entries = [];
  let items;
  try {
    items = await readdir(dir, { withFileTypes: true });
  } catch (err) {
    // fail-open: unreadable directory → skip
    console.warn(`[WARN] Cannot read directory: ${dir} (${err.code || err.message})`);
    return entries;
  }

  for (const item of items) {
    const fullPath = resolve(dir, item.name);
    if (item.isDirectory()) {
      // Skip node_modules or hidden directories
      if (item.name.startsWith('.') || item.name === 'node_modules') continue;
      const sub = await collectFiles(fullPath);
      entries.push(...sub);
    } else if (item.isFile()) {
      const ext = item.name.slice(item.name.lastIndexOf('.'));
      if (!EXTENSIONS.has(ext)) continue;
      // Check exclusion patterns
      const relPath = relative(FRONTEND_ROOT, fullPath).replace(/\\/g, '/');
      const excluded = EXCLUDE_PATTERNS.some((pat) => pat.test(relPath));
      if (excluded) continue;
      entries.push(fullPath);
    }
  }
  return entries;
}

// --- Main ---
async function main() {
  console.log('[vite-transform-smoke] Starting Vite in middleware mode...');
  console.log(`[vite-transform-smoke] Frontend root: ${FRONTEND_ROOT}`);
  console.log(`[vite-transform-smoke] Scan directory: ${SCAN_DIR}`);

  // Verify scan directory exists
  try {
    const s = await stat(SCAN_DIR);
    if (!s.isDirectory()) {
      console.error(`[ERROR] Scan path is not a directory: ${SCAN_DIR}`);
      process.exit(1);
    }
  } catch (err) {
    console.error(`[ERROR] Scan directory not found: ${SCAN_DIR}`);
    process.exit(1);
  }

  // Create Vite server in middleware mode (no HTTP server)
  let server;
  try {
    server = await createServer({
      root: FRONTEND_ROOT,
      server: { middlewareMode: true },
      // Suppress most logs during smoke test
      logLevel: 'error',
      // Disable HMR for smoke testing
      optimizeDeps: { noDiscovery: true },
    });
  } catch (err) {
    console.error(`[ERROR] Failed to create Vite server: ${err.message}`);
    process.exit(1);
  }

  // Collect all target files
  const files = await collectFiles(SCAN_DIR);
  console.log(`[vite-transform-smoke] Found ${files.length} files to check.`);

  if (files.length === 0) {
    console.warn('[WARN] No files found to check. Exiting with success.');
    await server.close();
    process.exit(0);
  }

  const failures = [];
  let processed = 0;
  const total = files.length;
  const reportInterval = Math.max(1, Math.floor(total / 10));

  for (const filePath of files) {
    // Convert absolute path to Vite URL (relative to root, prefixed with /)
    const relPath = relative(FRONTEND_ROOT, filePath).replace(/\\/g, '/');
    const url = `/${relPath}`;

    try {
      await server.transformRequest(url);
    } catch (err) {
      failures.push({ file: relPath, error: err.message || String(err) });
    }

    processed++;
    if (processed % reportInterval === 0) {
      console.log(`[vite-transform-smoke] Progress: ${processed}/${total} (${failures.length} failures so far)`);
    }
  }

  // Close Vite server
  await server.close();

  // Report results
  console.log('');
  console.log(`[vite-transform-smoke] ===== RESULTS =====`);
  console.log(`[vite-transform-smoke] Total files: ${total}`);
  console.log(`[vite-transform-smoke] Passed: ${total - failures.length}`);
  console.log(`[vite-transform-smoke] Failed: ${failures.length}`);

  if (failures.length > 0) {
    console.log('');
    console.log('[vite-transform-smoke] FAILED FILES:');
    for (const { file, error } of failures) {
      // Truncate long error messages
      const shortErr = error.length > 200 ? error.slice(0, 200) + '...' : error;
      console.log(`  [500] ${file}`);
      console.log(`        ${shortErr}`);
    }
    console.log('');
    console.log(`[vite-transform-smoke] FAIL: ${failures.length} file(s) failed Vite transform.`);
    process.exit(1);
  } else {
    console.log('');
    console.log('[vite-transform-smoke] PASS: All files transform successfully.');
    process.exit(0);
  }
}

main().catch((err) => {
  console.error(`[vite-transform-smoke] Unhandled error: ${err.message}`);
  console.error(err.stack);
  process.exit(1);
});
