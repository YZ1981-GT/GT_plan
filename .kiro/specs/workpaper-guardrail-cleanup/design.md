# 设计文档：底稿模块防退化卡点治理

## 概述

本 spec 是纯治理性质——不改业务逻辑，只修复/重建/清理防退化卡点。设计极简：改配置文件 + 新建一个检查脚本 + 删死代码 + grep 排查路径 bug。零/低风险，半天到 1.5 天可完成。

## 设计决策

### Bug 1+2：白名单基线调整（纯配置）

修改 `backend/scripts/file_size_whitelist.txt`：
- WorkpaperEditor.vue：2342 → **820**（实测 758 + ~8% 余量）
- WorkpaperList.vue：3464 → **520**（实测 476 + ~9% 余量）
- 新增 GtDFormConfirmation.vue：**1380**（实测 1311 + 5%，注释 `# 待拆 → gtdform-test-and-shrink`）
- 新增 GtEControlTest.vue：**1350**（实测 1279 + 5%，注释 `# 待拆 → gtdform-test-and-shrink`）

验证：`python backend/scripts/check/check_file_size.py` 全绿。

### Bug 3：重建 float 金额卡点

新建 `backend/scripts/check/check_no_float_amount.py`：
- 扫描 `backend/app/services/wp_*.py` + `backend/app/services/workpaper_*.py` 中的 `float(` 调用
- 排除已知安全模式（JSON 序列化、日志、字符串格式化）
- 输出违规行 + 文件 + 行号
- 首次运行定 baseline（写入 `backend/scripts/check/float_amount_baseline.txt`）
- 后续运行：新增违规 > baseline 则 exit 1（只增不减）

接入 `.pre-commit-config.yaml`（与 check_file_size 同模式）。

ROOT 路径用 `Path(__file__).resolve().parents[3]`（从 `backend/scripts/check/` 到仓库根 = 3 层）。

### Bug 4：EDITOR_MAP 死路由清理

步骤：
1. `WorkpaperEditor.vue`：删除 EDITOR_MAP 定义 + 相关 `v-if` / `<component :is>` 分支
2. `useEditorMode.ts`：删除 table/form/word/hybrid 相关注释与分支逻辑（如有）
3. **保留** `WorkpaperTableEditor.vue` / `WorkpaperFormEditor.vue` / `WorkpaperWordEditor.vue` / `WorkpaperHybridEditor.vue` 文件本身（不删 SFC，只断路由）
4. 验证：vue-tsc 0 errors + vitest 0 fail + grep `EDITOR_MAP` 在 src/ 下 = 0

### Bug 5：路径 bug 排查

执行 grep：
```bash
grep -rn "Path(__file__).parent" backend/scripts/*/
grep -rn "parents\[" backend/scripts/*/
```

对每个命中项检查：是否读同目录文件（合法）还是读外部数据文件（需改为 ROOT 显式路径）。逐个修复。

### Bug 6：INDEX.md 刷新

用 `wc -l` 实测关键文件行数 + `ls .kiro/specs/ | wc -l` 计 active spec 数，更新 INDEX.md 对应章节。

## 正确性属性

### Property 1: 白名单收紧后卡点真生效
对任意文件，若其行数超过 whitelist 登记的基线值，则 `check_file_size.py` 返回非零退出码。

### Property 2: 幂等——重复运行卡点结果一致
对同一代码状态，连续两次运行 `check_file_size.py` 的退出码与输出一致。

### Property 3: float 卡点只增不减
对任意代码变更，若新增 float() 金额调用超过 baseline，则 `check_no_float_amount.py` 返回非零退出码；若未超过则通过。

### Property 4: EDITOR_MAP 删除后无引用残留
删除后 `grep -r "EDITOR_MAP" audit-platform/frontend/src/` = 0 命中。

## 测试策略

- Bug 1+2+6：纯配置/文档变更，验证 = `check_file_size.py` 全绿 + INDEX 数字与实测一致
- Bug 3：新脚本的单元测试（构造含 float() 的 mock 文件 → 断言检出 / 构造安全模式 → 断言不检出）
- Bug 4：vue-tsc + vitest 全绿 = 无回归；grep 断言无残留
- Bug 5：修复后 grep 断言 `Path(__file__).parent` 在子目录下仅合法用法

## 错误处理

- check_no_float_amount.py 遇不可解析文件时 skip + warning（不中断整批扫描）
- EDITOR_MAP 删除前先 grep 确认无运行时引用（如 router/index.ts 动态 import），有则保留并标注

## 环境约定

- Windows：python 非 python3
- 测试：`python -m pytest backend/tests/ -v --tb=short`
- 前端：`npx vue-tsc --noEmit`（权威）+ vitest
