#!/usr/bin/env node
/**
 * 前端死链检查脚本 [R6 Task 18]
 *
 * 扫描 apiPaths.ts 中所有 API 端点常量，断言均能在
 * router_registry.py 注册树中找到对应 prefix。
 * 找不到则 exit 1。
 *
 * 用法: node scripts/dead-link-check.js
 * 无需额外 npm 依赖。
 */

const fs = require('fs');
const path = require('path');

// ─── 配置 ────────────────────────────────────────────────────────────────────

const API_PATHS_FILE = path.join(__dirname, '..', 'audit-platform', 'frontend', 'src', 'services', 'apiPaths.ts');
const ROUTER_REGISTRY_FILE = path.join(__dirname, '..', 'backend', 'app', 'router_registry.py');
const ROUTERS_DIR = path.join(__dirname, '..', 'backend', 'app', 'routers');

// ─── 1. 从 apiPaths.ts 提取所有 API 路径 ────────────────────────────────────

function extractApiPaths(content) {
  const paths = [];

  // 匹配静态字符串: '/api/...'
  const staticRegex = /['"`](\/(api|wopi)\/[^'"`${}]+)['"`]/g;
  let match;
  while ((match = staticRegex.exec(content)) !== null) {
    paths.push(match[1]);
  }

  // 匹配模板字面量前缀: `/api/...${  (取 ${ 之前的静态部分)
  const templateRegex = /`(\/(api|wopi)\/[^`]*?)\$\{/g;
  while ((match = templateRegex.exec(content)) !== null) {
    paths.push(match[1]);
  }

  // 去重
  return [...new Set(paths)];
}

/**
 * 从 API 路径中提取用于匹配的"静态前缀"。
 * 例如:
 *   /api/projects/${pid}/archive/orchestrate → /api/projects
 *   /api/staff → /api/staff
 *   /api/consolidation/scope → /api/consolidation/scope
 *
 * 策略: 取路径的前 N 段（至少 2 段: /api/xxx），直到遇到动态参数占位符。
 */
function extractStaticPrefix(apiPath) {
  // 去掉尾部斜杠
  const cleaned = apiPath.replace(/\/$/, '');
  const segments = cleaned.split('/').filter(Boolean); // ['api', 'projects', '...']

  // 收集静态段（不含路径参数占位符如 {pid}）
  const staticSegments = [];
  for (const seg of segments) {
    if (seg.startsWith('{') || seg.startsWith('$')) break;
    staticSegments.push(seg);
  }

  if (staticSegments.length === 0) return apiPath;
  return '/' + staticSegments.join('/');
}

// ─── 2. 从 router_registry.py + 各 router 文件提取注册前缀 ─────────────────

function extractRegisteredPrefixes() {
  const prefixes = new Set();

  // 2a. 从 router_registry.py 提取 include_router 的 prefix 参数
  const registryContent = fs.readFileSync(ROUTER_REGISTRY_FILE, 'utf-8');

  // 解析 include_router 调用中的 prefix
  const includeRegex = /app\.include_router\([^)]*prefix\s*=\s*["']([^"']+)["']/g;
  let match;
  const registryPrefixes = [];
  while ((match = includeRegex.exec(registryContent)) !== null) {
    registryPrefixes.push(match[1]);
  }

  // 2b. 从各 router 文件提取 APIRouter(prefix=...) 声明
  const routerFiles = getAllRouterFiles(ROUTERS_DIR);
  const routerInternalPrefixes = [];

  for (const file of routerFiles) {
    const content = fs.readFileSync(file, 'utf-8');

    // 提取 APIRouter(prefix="...")
    const prefixMatch = content.match(/APIRouter\([^)]*prefix\s*=\s*["']([^"']+)["']/);
    if (prefixMatch) {
      routerInternalPrefixes.push(prefixMatch[1]);
    }

    // 提取无 prefix 的 router 中的直接路径声明 @router.get("/api/...")
    const directRouteRegex = /@router\.(get|post|put|delete|patch)\(\s*["'](\/api\/[^"']+)["']/g;
    let routeMatch;
    while ((routeMatch = directRouteRegex.exec(content)) !== null) {
      routerInternalPrefixes.push(routeMatch[2]);
    }
  }

  // 2c. 合并: 对于在 registry 中用 prefix="/api" 注册的 router，
  //     其最终路径 = registry_prefix + router_internal_prefix
  //     对于 router 内部已含 /api 的，直接使用
  //     这里我们简化处理：收集所有可能的前缀组合

  // 直接添加所有 router 内部前缀（已含 /api 的）
  for (const p of routerInternalPrefixes) {
    if (p.startsWith('/api') || p.startsWith('/wopi')) {
      prefixes.add(normalizePrefix(p));
    }
  }

  // 对于 registry 中 prefix="/api" 的情况，router 内部前缀不含 /api
  // 需要组合: /api + /gate → /api/gate
  for (const p of routerInternalPrefixes) {
    if (!p.startsWith('/api') && !p.startsWith('/wopi')) {
      // 这些 router 在 registry 中通过 prefix="/api" 注册
      prefixes.add(normalizePrefix('/api' + p));
    }
  }

  // 也添加 registry 中直接声明的 prefix（如 /api/auth, /api/users 等）
  for (const p of registryPrefixes) {
    prefixes.add(normalizePrefix(p));
  }

  // 添加已知的特殊路由（main.py 中直接定义的）
  prefixes.add('/api/version');

  return prefixes;
}

function normalizePrefix(p) {
  // 去掉路径参数占位符，只保留静态部分
  const segments = p.split('/').filter(Boolean);
  const staticSegments = [];
  for (const seg of segments) {
    if (seg.startsWith('{')) break;
    staticSegments.push(seg);
  }
  return '/' + staticSegments.join('/');
}

function getAllRouterFiles(dir) {
  const files = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Recurse into subdirectories (e.g., eqcr/)
      files.push(...getAllRouterFiles(fullPath));
    } else if (entry.name.endsWith('.py') && entry.name !== '__pycache__') {
      files.push(fullPath);
    }
  }
  return files;
}

// ─── 3. 匹配逻辑 ────────────────────────────────────────────────────────────

/**
 * 检查一个 API 路径是否能匹配到任何注册的 router 前缀。
 * 匹配规则: API 路径的静态前缀必须以某个注册前缀开头。
 */
function isPathCovered(apiPath, registeredPrefixes) {
  const staticPrefix = extractStaticPrefix(apiPath);

  for (const registered of registeredPrefixes) {
    // 精确前缀匹配: 注册前缀是 API 路径静态前缀的前缀
    if (staticPrefix === registered) return true;
    if (staticPrefix.startsWith(registered + '/')) return true;
    // 反向: API 路径前缀是注册前缀的前缀（如 /api/projects 覆盖 /api/projects/xxx）
    if (registered.startsWith(staticPrefix + '/')) return true;
    if (registered === staticPrefix) return true;
  }
  return false;
}

// ─── 主流程 ──────────────────────────────────────────────────────────────────

function main() {
  console.log('🔍 前端死链检查: apiPaths.ts ↔ router_registry.py\n');

  // 检查文件存在
  if (!fs.existsSync(API_PATHS_FILE)) {
    console.error(`❌ 找不到 apiPaths.ts: ${API_PATHS_FILE}`);
    process.exit(1);
  }
  if (!fs.existsSync(ROUTER_REGISTRY_FILE)) {
    console.error(`❌ 找不到 router_registry.py: ${ROUTER_REGISTRY_FILE}`);
    process.exit(1);
  }

  // 提取前端 API 路径
  const apiPathsContent = fs.readFileSync(API_PATHS_FILE, 'utf-8');
  const apiPaths = extractApiPaths(apiPathsContent);
  console.log(`📋 apiPaths.ts 中发现 ${apiPaths.length} 个 API 端点\n`);

  // 提取后端注册前缀
  const registeredPrefixes = extractRegisteredPrefixes();
  console.log(`🌳 router_registry 中发现 ${registeredPrefixes.size} 个注册前缀\n`);

  // 逐一检查
  const deadLinks = [];
  for (const apiPath of apiPaths) {
    if (!isPathCovered(apiPath, registeredPrefixes)) {
      deadLinks.push(apiPath);
    }
  }

  // 输出结果
  if (deadLinks.length === 0) {
    console.log('✅ 所有前端 API 路径均有对应后端路由注册，无死链。');
    process.exit(0);
  } else {
    console.log(`❌ 发现 ${deadLinks.length} 个死链（前端路径无对应后端路由）:\n`);
    for (const link of deadLinks) {
      console.log(`   • ${link}`);
    }
    console.log('\n请检查以上路径是否已在 router_registry.py 中注册。');
    process.exit(1);
  }
}

main();
