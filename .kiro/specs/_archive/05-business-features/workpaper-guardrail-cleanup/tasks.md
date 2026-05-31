# 实施计划：底稿模块防退化卡点治理（workpaper-guardrail-cleanup）

## 概述

纯治理 spec，零/低业务风险。按依赖排序：白名单配置 → float 卡点重建 → EDITOR_MAP 清理 → 路径 bug 排查 → INDEX 刷新 → 验证。

## 任务

- [x] 1. 白名单基线收紧 + 游离子组件登记
  - [x] 1.1 实测当前行数（立项时重测，不信旧数字）
    - `wc -l` 对 WorkpaperEditor.vue / WorkpaperList.vue / GtDFormConfirmation.vue / GtEControlTest.vue
    - 记录实测值作为基线依据
    - _Bugfix: Bug 1, Bug 2_
  - [x] 1.2 修改 `backend/scripts/file_size_whitelist.txt`
    - WorkpaperEditor.vue：收紧到实测值 + ~8% 余量
    - WorkpaperList.vue：收紧到实测值 + ~9% 余量
    - 新增 GtDFormConfirmation.vue：实测值 + 5%，注释 `# 待拆 → gtdform-test-and-shrink`
    - 新增 GtEControlTest.vue：实测值 + 5%，注释 `# 待拆 → gtdform-test-and-shrink`
    - _Bugfix: Bug 1, Bug 2_
  - [x] 1.3 验证 `python backend/scripts/check/check_file_size.py` 全绿
    - _Bugfix: Bug 1, Bug 2; Property 1_

- [x] 2. 重建 float 金额防退化卡点
  - [x] 2.1 新建 `backend/scripts/check/check_no_float_amount.py`
    - 扫描 `backend/app/services/wp_*.py` + `workpaper_*.py` 中 `float(` 调用
    - 排除安全模式（JSON 序列化 / 日志 / 字符串格式化 / 注释）
    - 输出违规行列表 + 退出码（超 baseline 则 exit 1）
    - ROOT 路径用 `Path(__file__).resolve().parents[3]`
    - _Bugfix: Bug 3_
  - [x] 2.2 首次运行定 baseline
    - 运行脚本 → 输出当前违规数 → 写入 `backend/scripts/check/float_amount_baseline.txt`
    - 人工复核：区分安全（序列化）vs 需复核（差额计算），安全项加入豁免列表
    - _Bugfix: Bug 3_
  - [x] 2.3 接入 `.pre-commit-config.yaml`
    - 与 check_file_size 同模式（`language: system`, `entry: python backend/scripts/check/check_no_float_amount.py`）
    - _Bugfix: Bug 3_
  - [x]* 2.4 编写 check_no_float_amount 单元测试
    - 构造含 float() 的 mock 文件 → 断言检出
    - 构造安全模式（json.dumps(float(...))）→ 断言不检出
    - _Bugfix: Bug 3; Property 3_

- [x] 3. EDITOR_MAP 死路由清理
  - [x] 3.1 grep 确认无活跃运行时引用
    - `grep -rn "EDITOR_MAP\|WorkpaperTableEditor\|WorkpaperFormEditor\|WorkpaperWordEditor\|WorkpaperHybridEditor" audit-platform/frontend/src/ --include="*.ts" --include="*.vue"` 排除 SFC 文件自身定义
    - 确认 router/index.ts 无动态 import 这 4 个编辑器
    - _Bugfix: Bug 4_
  - [x] 3.2 删除 WorkpaperEditor.vue 中 EDITOR_MAP 定义 + 相关分支
    - 删除 EDITOR_MAP 对象定义
    - 删除 template 中引用 EDITOR_MAP 的 `v-if` / `<component :is>` 分支
    - **保留** 4 个 SFC 文件本身（不删文件，只断路由）
    - _Bugfix: Bug 4_
  - [x] 3.3 清理 useEditorMode.ts 中相关注释/分支（如有）
    - _Bugfix: Bug 4_
  - [x] 3.4 验证 vue-tsc + vitest 全绿 + grep EDITOR_MAP = 0
    - `npx vue-tsc --noEmit` 0 errors
    - `python -m pytest` 相关前端测试 0 fail
    - `grep -rn "EDITOR_MAP" audit-platform/frontend/src/` = 0
    - _Bugfix: Bug 4; Property 4_

- [x] 4. backend/scripts/ 子目录路径 bug 排查
  - [x] 4.1 grep 全子目录排查
    - `grep -rn "Path(__file__).parent" backend/scripts/*/`
    - `grep -rn "parents\[" backend/scripts/*/`
    - 对每个命中项判断：读同目录文件（合法）vs 读外部数据文件（需修）
    - _Bugfix: Bug 5_
  - [x] 4.2 逐个修复（改为 ROOT 显式路径）
    - 模式：`ROOT = Path(__file__).resolve().parents[3]`（从 check/ 子目录到仓库根 = 3 层）
    - 数据文件路径：`ROOT / "backend" / "scripts" / "file_size_whitelist.txt"` 等
    - _Bugfix: Bug 5_
  - [x] 4.3 验证修复后脚本正常运行
    - 逐个运行修复的脚本确认不报 FileNotFoundError / 不返回空结果
    - _Bugfix: Bug 5_

- [x] 5. INDEX.md 计数刷新
  - [x] 5.1 实测关键数字
    - `wc -l` WorkpaperEditor.vue / WorkpaperList.vue
    - `ls .kiro/specs/ | wc -l`（active spec 数）
    - 其他 INDEX.md 引用的过时数字
    - _Bugfix: Bug 6_
  - [x] 5.2 更新 `.kiro/specs/INDEX.md` 对应章节
    - §1 WorkpaperEditor 行数 / §2 WorkpaperList 行数 / §4 active spec 数
    - _Bugfix: Bug 6_

- [x] 6. Final Checkpoint
  - `python backend/scripts/check/check_file_size.py` 全绿
  - `python backend/scripts/check/check_no_float_amount.py` 不超 baseline
  - `npx vue-tsc --noEmit` 0 errors（EDITOR_MAP 删除无回归）
  - vitest 0 fail
  - grep 断言：EDITOR_MAP=0 / `Path(__file__).parent` 在子目录下仅合法用法
  - INDEX.md 数字与实测一致

## 说明

- 标 `*` 为可选任务（单元测试），其余必需
- 纯治理 spec，不改业务逻辑，不改 DB schema
- 实施时所有行数需按当时分支重测（"实测有效期=单次 grep 时刻"铁律）
- EDITOR_MAP 删除保留 SFC 文件（后续 composable 素材），只断路由
- float 卡点是"建卡点 + 定 baseline"，不改业务代码中的 float()（Decimal 化改造是另一个 spec）
