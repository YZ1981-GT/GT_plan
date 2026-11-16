# Phase 6 OnlyOffice 环境就绪探针

日期：2026-11-01

## 环境确认

| 项 | 状态 |
|---|---|
| 后端 health | degraded（与同步链无关，见 phase6-environment-readiness） |
| OnlyOffice 容器 | healthy |
| 前端 3030 | 200 |
| PG audit_platform | connected |
| 登录 admin/admin123 | 成功 |
| 项目列表 | 可达，9 个有底稿的项目 |

## 底稿分布

| 项目 | 底稿数 | 类型 |
|---|---|---|
| 重药安徽 | 1060 | 真实业务 |
| 宜宾大药房 | 1026 | 真实业务 |
| 和平药房 2024 | 1017 | 真实业务 |
| 和平药房 2025 | 324 | 真实业务 |
| 【测试】公式同步乙 | 3 | 测试 |
| 【测试】公式同步甲 | 2 | 测试 |

## 6.3 的阻塞点

PG `working_paper_sync_test_run` = **0 行**。67 条 bidirectional independent entry 全部
`evidence_missing`。

要做 6.3 需要：
1. 在一个【测试】项目里生成 bidirectional entry 对应的底稿
2. 该底稿有 published representation（需要先跑 publish 路径）
3. 在浏览器里切到 OO 模式、编辑、保存回表单
4. 查 DB 确认 representation 和 artifact 正确
5. 把结果写进 working_paper_sync_test_run

步骤 1~4 都是真实浏览器 + 后端操作，不是脚本能自动完成的。
【测试】项目当前只有 2~3 个底稿，且可能不在 bidirectional entry 的 wp_code 覆盖范围内。

## 结论

6.3/6.4/6.5 的环境全部就绪，阻塞在**人工操作**——具体是「在【测试】项目里为至少一个
bidirectional entry 走完 HTML→OO→保存→回读→核对的全流程，然后用 Playwright 脚本
把同一流程自动化」。这不是假绿可以替代的。
