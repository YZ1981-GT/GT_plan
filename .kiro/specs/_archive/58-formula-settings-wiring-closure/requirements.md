# 需求文档：公式设置接线收口与 stash 事故抢救（formula-settings-wiring-closure）

> 来源：2026-10-21 公式管理全面评估（对话）→ 用户「按建议来」，执行第 0 步「止血」。
> 类型：缺陷修复 + 事故恢复。不新增公式能力，不改公式语法。

## 背景（现扫，2026-10-21）

- `formula-global-settings-sync`（记录 35/36、146 测试全绿）在 HEAD 上实跑 128 passed / 7 failed / 11 errors：表间审核用户规则不执行、底稿全局公式不进预填、附注域 ImportError、合并附注 ORM 缺 version（接口 500）、主模板同步不发事件、公式历史回滚仍按 row_code `LIMIT 1` 直改全局行、自定义预设仍写仓库 JSON。
- 根因（reflog + 悬空对象实证）：17:56:04 一次 `git stash push -m temp-for-push-reconcile`（112bfabec，386 个文件）与 19:50:05 一次 `git stash`（4cbd8029d）收走了多个会话尚未提交的改动且从未还原；HEAD 已提交的代码又引用了其中的符号 ⇒ 后端导入 `report_config` 路由即 ImportError（开发服务 health 000），前端 `createKeyedSingleFlight` / `consolNoteReuse` 未定义。
- 并发会话的 `formula-management-ux-improvements`（任务全打勾）有 4 处缺陷：表间审核历史接口 500、依赖查询接口对报表地址 500、推送覆盖率恒 100%、新编辑器把 SUM_TB / PREV / IF 等合法函数标成「未知函数」。

## R1 事故抢救

1. 悬空 stash SHALL 打本地救援标签防 gc；恢复内容 SHALL 与悬空 stash 逐文件一致（去 BOM、统一换行比对）。
2. HEAD 引用的缺失符号 SHALL 先恢复，使 `import app.main` 通过、开发服务恢复。
3. 公式域文件 SHALL 按 `git stash apply` 语义恢复：HEAD 未再改过的取 stash 版本；之后又提交过的做三方合并，冲突逐个裁决并记录。
4. 非公式域的其余丢失改动 SHALL 列清单交用户决定，不擅自恢复。

## R2 接线成立（以 `formula-global-settings-sync` 自带测试为判据）

1. `tests/formula_settings` SHALL 在 HEAD 全绿。
2. 对照 HEAD 干净检出跑同一批相关测试，SHALL 无新增失败；与新契约冲突的旧测试按新契约改写，不降级断言。

## R3 并发会话 4 处缺陷

1. 表间审核历史：按真实列（`operated_at`、`left_amount` / `right_amount` / `difference`）读取并按年度过滤，SHALL 不再 500 且金额非空。
2. 依赖查询：报表地址 SHALL 按本项目有效定义取公式（不查不存在的 `ReportConfig.project_id`）；地址 SHALL 精确匹配，禁子串；科目地址 SHALL 返回引用它的报表行。
3. 推送覆盖率：分母 SHALL 为真实底稿编码集合，SHALL 不再恒为 100%。
4. 编辑器函数清单 SHALL 与后端语法一致（含 SUM_TB / PREV / IF / ABS / ROUND / MAX / MIN，以及附注用的 PRIOR / AGING），参数个数口径与后端一致。
5. `FormulaManagerDialog.vue` SHALL 回到行数门以内（新增逻辑抽到独立组件）。

## R4 守卫

1. SHALL 有守卫：供执行层使用的有效定义函数必须存在非测试调用方（本次「测试直接调函数、生产从未调用」的直接防线），并配变异证明。
2. `WIRED_DOMAINS` 标为已接入的域 SHALL 与守卫结论一致。

## R5 验证

1. 后端：`tests/formula_settings` + 公式域套件；对照基线无新增失败。
2. 前端：公式域 vitest、改动文件 ESLint、单区域 vue-tsc（含变异证明）。
3. 开发服务只读接口实测；写入型验收只用【测试】项目，结束后按写入表逐项清理。
