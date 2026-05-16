# UAT Pending Triggers

R10 复盘 S2 沉淀：spec 完成时自动建 `.kiro/uat-pending/{spec_id}.md` 触发清单，避免"代码完成但 UAT 永远卡住"。

## 工作流

1. spec 实施完成时 orchestrator 在此目录建 `{spec_id}.md` 列待 UAT 项
2. CI 在 spec 末次 commit 时自动评论 PR @责任人（未来工具化）
3. 责任人执行 UAT 后回写 `tasks.md` 状态从 `○ pending-uat` → `✓ pass` / `✗ fail`
4. 全部 ✓ pass 后删除本目录下的对应文件

## SLA 规约

- P0 spec：UAT 必须在 7 天内执行
- P1 spec：UAT 必须在 14 天内执行
- 超 SLA 报警（未来工具化），并阻断该 spec 上线

## 当前 pending 清单

- `v3-r10-linkage-and-tokens.md`（Spec B，8 项 UAT）
- `v3-r10-editor-resilience.md`（Spec C，5 项 UAT）
