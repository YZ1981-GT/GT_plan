#!/usr/bin/env node
/**
 * runtime_import_smoke.mjs — Runtime Import Smoke（ESM 运行时加载检测）
 *
 * 设计 §7.2：Vite transform 只能抓 SFC 编译错误(200/500)，无法发现
 * named-export ESM 运行时错误（如 `import { http } from '@/utils/http'`
 * transform 200 但 ESM 加载时 SyntaxError: does not provide an export named 'http'）。
 *
 * 本脚本以 Vite middleware mode 启动，对 htmlRendererRegistry 中每个专属
 * componentType 的 .vue 文件执行 ssrLoadModule（ESM runtime load），
 * 捕获 named-export 缺失、循环依赖、模块初始化错误等 Vite transform 遗漏。
 *
 * Property P11: 目标集合与 DEDICATED_COMPONENT_TYPES 注册集合相等。
 *
 * Requirements: 5.3, 5.4
 * Feature: workpaper-maintainability-convergence
 *
 * Usage:
 *   node backend/scripts/check/runtime_import_smoke.mjs
 *
 * Exit codes:
 *   0 — 全部通过
 *   1 — 有加载失败
 */

import { resolve, relative } from 'node:path';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// ─── Configuration ──────────────────────────────────────────────────────────

const FRONTEND_ROOT = resolve(import.meta.dirname, '../../../audit-platform/frontend');
const REGISTRY_PATH = resolve(
  FRONTEND_ROOT,
  'src/components/workpaper/htmlRendererRegistry.ts',
);

// DEDICATED_COMPONENT_TYPES — 与 backend/app/services/dedicated_component_types.py 对齐
const DEDICATED_COMPONENT_TYPES = new Set([
  'a10-bundle', 'a11-bundle', 'a12-bundle', 'a15-bundle', 'a16-bundle', 'a17-bundle',
  'b2-bundle', 'b13-bundle', 'b19-bundle', 'b51-bundle',
  'c1-entity-level-control', 'c-control-test', 'c22-itgc-bundle',
  'c23-journal-entry-control', 'c24-journal-entry-detail',
  'h1-fixed-assets', 'h2-construction-in-progress', 'h3-investment-property',
  'h4-engineering-materials', 'h6-asset-disposal-clearing', 'h8-right-of-use-assets',
  'h9-lease-liabilities', 'h10-asset-disposal-income', 'h5-oil-gas-assets', 'h7-biological-assets',
  'i1-intangible-assets', 'i2-development-expenditure', 'i3-goodwill',
  'i4-long-term-prepaid', 'i5-other-noncurrent-assets', 'i6-research-development-expense',
  'j1-employee-compensation', 'j2-defined-benefit-plan', 'j3-share-based-payment',
  'k1-other-receivables', 'k2-other-current-assets', 'k3-other-payables',
  'k4-other-current-liabilities', 'k5-provisions', 'k6-held-for-sale', 'k7-deferred-income',
  'k8-selling-expenses', 'k9-admin-expenses', 'k10-other-income',
  'k11-asset-impairment-loss', 'k12-non-operating-income', 'k13-non-operating-expense',
  'l1-short-term-loans', 'l2-interest-payable', 'l3-long-term-loans', 'l4-bonds-payable',
  'l5-long-term-payables', 'l6-special-payables', 'l7-other-noncurrent-liabilities', 'l8-financial-expenses',
  'm1-dividends-payable', 'm2-paid-in-capital', 'm3-treasury-stock', 'm4-capital-reserve',
  'm5-surplus-reserve', 'm6-retained-earnings', 'm7-special-reserve', 'm8-general-risk-reserve',
  'm9-other-comprehensive-income', 'm10-other-equity-instruments',
  'n1-deferred-tax-assets', 'n2-taxes-payable', 'n3-deferred-tax-liabilities',
  'n4-taxes-and-surcharges', 'n5-income-tax-expense',
  's3-policy-change', 's4-nonmonetary-exchange', 's5-debt-restructuring', 's6-fund-occupation',
  's12-cpa-expert', 's13-mgmt-expert', 's14-accounting-estimate', 's15-eps-roe',
  's20-revenue-deduction', 's21-data-asset', 's32-fraud-bundle', 's33-ann14-bundle',
]);

// ─── Parse registry to extract import paths ─────────────────────────────────

/**
 * 从 htmlRendererRegistry.ts 解析每个专属 componentType 的 import 路径。
 * 匹配模式: componentType: 'xxx' 之后紧跟的 import('...') 路径。
 */
function parseRegistryImports() {
  const content = readFileSync(REGISTRY_PATH, 'utf-8');

  // 定位 REGISTRY_LIST 段
  const startIdx = content.indexOf('const REGISTRY_LIST');
  const endIdx = content.indexOf('export const HTML_RENDERER_REGISTRY');
  if (startIdx < 0 || endIdx < 0) {
    console.error('[ERROR] Cannot locate REGISTRY_LIST in htmlRendererRegistry.ts');
    process.exit(1);
  }
  const registryText = content.slice(startIdx, endIdx);

  // 提取 componentType → import path 映射
  // Pattern: componentType: 'xxx' ... import('path')
  const entries = new Map();
  const entryRe = /componentType:\s*'([^']+)'/g;
  const importRe = /import\(\s*'([^']+)'\s*\)/g;

  let match;
  const componentTypes = [];
  while ((match = entryRe.exec(registryText)) !== null) {
    componentTypes.push({ type: match[1], index: match.index });
  }

  // For each componentType, find the nearest import() after it
  for (let i = 0; i < componentTypes.length; i++) {
    const ct = componentTypes[i];
    const nextStart = ct.index;
    const nextEnd = i < componentTypes.length - 1
      ? componentTypes[i + 1].index
      : registryText.length;

    const segment = registryText.slice(nextStart, nextEnd);
    const importMatch = /import\(\s*'([^']+)'\s*\)/.exec(segment);
    if (importMatch) {
      entries.set(ct.type, importMatch[1]);
    }
  }

  return entries;
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log('[runtime-import-smoke] Starting Runtime Import Smoke...');
  console.log(`[runtime-import-smoke] Frontend root: ${FRONTEND_ROOT}`);

  // Parse registry
  const registryImports = parseRegistryImports();
  console.log(`[runtime-import-smoke] Registry entries parsed: ${registryImports.size}`);

  // P11 集合等价验证
  const targetTypes = new Set();
  for (const [ct] of registryImports) {
    if (DEDICATED_COMPONENT_TYPES.has(ct)) {
      targetTypes.add(ct);
    }
  }

  const missingInRegistry = [...DEDICATED_COMPONENT_TYPES].filter((ct) => !targetTypes.has(ct));
  if (missingInRegistry.length > 0) {
    console.error('[runtime-import-smoke] P11 VIOLATION: 以下专属 componentType 未在 registry 中注册:');
    for (const ct of missingInRegistry) {
      console.error(`  - ${ct}`);
    }
    process.exit(1);
  }
  console.log(`[runtime-import-smoke] P11 集合等价验证通过: ${targetTypes.size} 专属 componentType`);

  // Resolve vite from the frontend's node_modules
  const require = createRequire(resolve(FRONTEND_ROOT, 'package.json'));
  const vitePath = require.resolve('vite');
  const { createServer } = await import(pathToFileURL(vitePath).href);

  // Create Vite server in middleware mode
  let server;
  try {
    server = await createServer({
      root: FRONTEND_ROOT,
      server: { middlewareMode: true },
      logLevel: 'error',
      optimizeDeps: { noDiscovery: true },
    });
  } catch (err) {
    console.error(`[ERROR] Failed to create Vite server: ${err.message}`);
    process.exit(1);
  }

  // 动态加载每个专属 componentType
  const failures = [];
  let processed = 0;
  const total = targetTypes.size;

  for (const ct of targetTypes) {
    const importPath = registryImports.get(ct);
    if (!importPath) {
      failures.push({ type: ct, error: 'No import path found in registry' });
      processed++;
      continue;
    }

    // Resolve the import path relative to the registry file location
    const registryDir = 'src/components/workpaper';
    const resolvedPath = importPath.startsWith('./')
      ? `/${registryDir}/${importPath.slice(2)}`
      : importPath.startsWith('../')
        ? `/${registryDir}/${importPath}`
        : `/${importPath}`;

    try {
      // ssrLoadModule 执行完整 ESM 加载（含所有 import 链解析）
      // 能抓到 named-export 缺失、模块初始化错误等 Vite transform 遗漏
      await server.ssrLoadModule(resolvedPath);
    } catch (err) {
      const errMsg = err.message || String(err);
      // 区分 "module not found" 与 "named export" 错误
      const isNamedExport = errMsg.includes('does not provide an export named') ||
        errMsg.includes('SyntaxError') ||
        errMsg.includes('is not defined');
      const severity = isNamedExport ? 'CRITICAL' : 'ERROR';
      failures.push({ type: ct, error: `[${severity}] ${errMsg.slice(0, 300)}` });
    }

    processed++;
    if (processed % 10 === 0) {
      console.log(`[runtime-import-smoke] Progress: ${processed}/${total}`);
    }
  }

  // Close Vite server
  await server.close();

  // Report results
  console.log('');
  console.log('[runtime-import-smoke] ===== RESULTS =====');
  console.log(`[runtime-import-smoke] Total dedicated componentTypes: ${total}`);
  console.log(`[runtime-import-smoke] Passed: ${total - failures.length}`);
  console.log(`[runtime-import-smoke] Failed: ${failures.length}`);

  if (failures.length > 0) {
    console.log('');
    console.log('[runtime-import-smoke] FAILED COMPONENTS:');
    for (const { type, error } of failures) {
      console.log(`  [FAIL] ${type}`);
      console.log(`         ${error}`);
    }
    console.log('');
    console.log('[runtime-import-smoke] FAIL: Runtime import errors detected.');
    console.log('[runtime-import-smoke] These errors are invisible to Vite transform smoke (HTTP 200)');
    console.log('[runtime-import-smoke] but will crash at runtime when the component is loaded.');
    process.exit(1);
  } else {
    console.log('');
    console.log('[runtime-import-smoke] PASS: All dedicated componentTypes load successfully.');
    process.exit(0);
  }
}

main().catch((err) => {
  console.error(`[runtime-import-smoke] Unhandled error: ${err.message}`);
  console.error(err.stack);
  process.exit(1);
});
