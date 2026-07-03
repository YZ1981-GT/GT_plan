# 显示格式化单一真源 — Tasks

## 阶段一：建统一出口

- [x] 1. 扩展 displayPrefs `fmt`：补 null/非数字返回 `'—'`、`opts.rawUnit` 选项、`fmtAmount` 别名
  - 文件：`audit-platform/frontend/src/stores/displayPrefs.ts`
  - 需求 1

- [x] 2. displayPrefs 新增 `fmtPercent(v, d=1)` 并转发 `fmtDateTime`
  - 文件：`audit-platform/frontend/src/stores/displayPrefs.ts`
  - 需求 2、3

- [x] 3. `utils/formatters.ts` 的 `fmtDateTime` 补 null/非法日期返回 `'-'`，标注金额函数 `@deprecated`
  - 文件：`audit-platform/frontend/src/utils/formatters.ts`
  - 需求 2、4

- [x] 4. `utils/formatAmount.ts` 改为转发同源逻辑（不再裸 toLocaleString），保留导出名
  - 文件：`audit-platform/frontend/src/utils/formatAmount.ts`
  - 需求 4

- [x] 5. 单元测试：`fmt`(null/单位/rawUnit/负数)、`fmtPercent`、`fmtDateTime`(null/非法)
  - 文件：`audit-platform/frontend/src/__tests__/displayPrefs.spec.ts`
  - 需求 1、2、3

- [ ]* 5.1 PBT：任意数值经 `fmt` 不抛错且去单位后可解析回数值
  - 需求 1

## 阶段二：CI 守卫

- [x] 6. 编写守卫脚本 `check-format-single-source.mjs` + 存量豁免清单 `format-legacy-allowlist.json`
  - 文件：`audit-platform/frontend/scripts/check-format-single-source.mjs`、`audit-platform/frontend/scripts/format-legacy-allowlist.json`
  - 需求 6

- [x] 7. 守卫脚本自测（构造命中片段断言捕获 + 豁免行不报）并接入 package.json lint 脚本
  - 文件：`audit-platform/frontend/scripts/__tests__/`（或脚本内 --self-test）、`package.json`
  - 需求 6

## 阶段三：存量迁移（分批，每批后验证）

- [x] 8. 批 1 迁移：TrialBalance.vue + ReviewWorkbench.vue 改用 `prefs.fmt`/`prefs.fmtDateTime`，删本地 formatAmount
  - 需求 5
  - 验证：跑相关 vitest + Playwright 抽测单位切换跟随

- [x] 9. 批 2 迁移：components/workpaper 计算弹窗群（~20 个 *Dialog.vue）改用统一出口
  - 需求 5
  - 验证：每个弹窗金额显示与迁移前一致

- [x] 10. 批 3 迁移：confirmation 组件群 + dashboard + 剩余 views，并从豁免清单移除已清理项
  - 需求 5、6

- [x] 11. 全量回归：运行前端 vitest 全绿 + 守卫脚本豁免清单清零（或仅剩合理例外）+ Playwright 实测主表/弹窗单位切换一致
  - 需求 5、6

- [x]* 12. 更新 `docs/平台全局体验与一致性建议.md` §1.2/§7.3 标记本项完成
