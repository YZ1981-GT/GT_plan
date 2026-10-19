#!/usr/bin/env node
/**
 * typecheck-region.mjs — 对指定前端文件做**单区域** vue-tsc 类型检查。
 *
 * 为什么需要它：
 *   本仓库前端体量大，`vue-tsc --noEmit`（全量）在 4GB / 8GB 堆下**都会 OOM**，
 *   stdout 里的 `error TS` 计数会显示 0，真实输出是 `FATAL ERROR: heap out of memory`
 *   —— 很容易被误读成"类型检查通过"。因此改前端文件后无法用全量 tsc 验证类型。
 *
 *   过去的权宜之计是每次手工建一个 `tsconfig._xxx.json` 单区域 config，用完往往不删，
 *   仓库里因此堆了十几个 `tsconfig._*-*.json`，而且各自编译选项措辞不一致（不少还漏了
 *   OOM 规避关键项 `assumeChangesOnlyAffectDirectDependencies`，依旧会 OOM 或极慢）。
 *
 * 本工具把这件事收敛成一条命令：接受文件清单 → 生成临时 config（含 OOM 规避项）→
 * 跑 vue-tsc → 无论成败都删临时 config → 透传 vue-tsc 退出码。
 *
 * 用法：
 *   node scripts/typecheck-region.mjs <file1> [file2 ...]
 *   npm run typecheck:region -- src/components/foo/Bar.vue src/utils/baz.ts
 *
 * 退出码：
 *   0 = 无类型错误；非 0 = vue-tsc 报错（真实类型错误，而非 OOM 假象）。
 *
 * 说明：
 *   - 文件路径相对 frontend/ 根（与现有 tsconfig include 写法一致）。
 *   - 自动把 src/env.d.ts 并入 include（提供 .vue / Vite 环境的类型声明）。
 *   - 自动设 NODE_OPTIONS=--max-old-space-size=4096（单区域足够，不会 OOM）。
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_ROOT = resolve(fileURLToPath(new URL('..', import.meta.url)));
const ENV_D_TS = 'src/env.d.ts';

function main() {
  const files = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  if (files.length === 0) {
    console.error('用法: node scripts/typecheck-region.mjs <file1> [file2 ...]');
    console.error('  例: node scripts/typecheck-region.mjs src/components/foo/Bar.vue');
    process.exit(2);
  }

  // include：去重 + 始终并入 env.d.ts
  const include = Array.from(new Set([...files, ENV_D_TS]));

  const config = {
    compilerOptions: {
      target: 'ES2020',
      module: 'ESNext',
      moduleResolution: 'bundler',
      allowImportingTsExtensions: true,
      strict: true,
      skipLibCheck: true,
      noEmit: true,
      isolatedModules: true,
      moduleDetection: 'force',
      jsx: 'preserve',
      lib: ['ES2022', 'DOM', 'DOM.Iterable'],
      paths: { '@/*': ['./src/*'] },
      baseUrl: '.',
      // 🔴 OOM 规避关键项：只重算直接依赖，避免 vue-tsc 回退到全图分析。
      assumeChangesOnlyAffectDirectDependencies: true,
    },
    include,
  };

  // 临时 config 写进系统临时目录，不污染仓库（根除"tsconfig._* 残留"）。
  const dir = mkdtempSync(join(tmpdir(), 'tsc-region-'));
  const configPath = join(dir, 'tsconfig.region.json');

  let exitCode = 1;
  try {
    // config 放仓库外时，相对 include/baseUrl 会以 config 所在目录为基准 —— 不对。
    // 用绝对 baseUrl 指回 frontend 根，include 仍写相对 frontend 的路径。
    config.compilerOptions.baseUrl = FRONTEND_ROOT;
    config.compilerOptions.paths = { '@/*': [join(FRONTEND_ROOT, 'src') + '/*'] };
    config.include = include.map((f) => join(FRONTEND_ROOT, f));
    writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');

    // Windows 下 npx 是 .cmd，不能直接 spawn（EINVAL），必须经 shell。
    // shell:true 时用字符串命令，configPath 加引号以容忍临时目录里的空格。
    const result = spawnSync(
      `npx vue-tsc --noEmit -p "${configPath}"`,
      {
        cwd: FRONTEND_ROOT,
        stdio: 'inherit',
        shell: true,
        env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=4096' },
      },
    );

    if (result.error) {
      console.error('启动 vue-tsc 失败:', result.error.message);
      exitCode = 1;
    } else {
      exitCode = result.status ?? 1;
    }
  } finally {
    // 🔴 必须在 finally 里清理，且**不能**在 try 里调 process.exit —— process.exit
    //    会立即终止进程、跳过 finally，导致临时目录永久残留在 tmpdir（实测踩过）。
    rmSync(dir, { recursive: true, force: true });
  }
  process.exit(exitCode);
}

main();
