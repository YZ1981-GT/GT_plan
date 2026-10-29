# 附注披露取数、公式与合并拉数闭环 — 任务

## A. 数据链与注册表

- [x] 1. 建立本轮现状基线：四版模板、D2 子表、表头库、公式与合并拉数断点（R1/R7）
- [x] 2. 注册表复数章节单一访问器；pull/readiness/sheet/status/stale 全部接入（R3）
- [x] 3. `pull-from-workpapers` 增加 prepare/push/all 两阶段兼容编排（R2.1/R2.3）
- [x] 4. refill 后统一执行 note 预设/用户公式，修正最终计算顺序（R1.3/R2.1）
- [x] 5. 标准单/批 sync 清 stale，并在提交后发布逐章节 `NOTE_SECTION_SAVED`（R4）
- [x] 6. formula push 提交后发布逐章节 `NOTE_SECTION_SAVED`，保留原运行记录/SSE（R4）

## B. 表头与公式管理

- [x] 7. workpaper raw 值投影保留服务端模板结构字段，验证 D2 多级表头不被覆盖（R1.4/R7.3）
- [x] 8. 公式管理 note 应用按钮改走 note 端点；wp/push/note/consol_note 域映射正确（R5）
- [x] 9. 退役 Word 同步工具的旧位置式 standalone title 写路径，统一到 Word 树门禁（R7.2）
- [x] 10. 生成、手动重试、stale 重算和保存事件回调复用完整披露同步编排（R2.2/R2.4）

## C. 合并附注

- [x] 11. 来源表按各单体项目自身国企/上市口径解析；标题/header 行不参与映射（R6.1/R6.2）
- [x] 12. apply 强制复核来源 hash、规则/模板版本和作用域，结构变化标 stale（R6.3）
- [x] 13. pending/stale/no-binding 叶子向祖先传播 incomplete；前 N 名补 stale 影响面（R6.4/R6.5）

## D. 验收

- [x] 14. 重跑后端/前端相关既有测试和三项生成/对齐 `--check`，修复本轮回归
- [ ]* 15. 用【测试】项目做浏览器实测：单体 D2 刷新、表头、公式和生成均已通过；合并项目的映射入口、15 张表与重新汇总接口已验证，但该章节没有明细模板绑定和可汇总单体数据，真实合并写入待有可用测试数据后补测
- [x] 16. 干净候选树复核并发边界；逐项对照用户目标，登记未纳入本轮的 11 个 provider 与后续优化
