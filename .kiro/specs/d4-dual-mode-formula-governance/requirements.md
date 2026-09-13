# D4 双模式公式治理与36底稿覆盖总纲

## Introduction
本总纲是D4-1..D4-36的共同契约与编排入口。它只约束HTML/Excel双模式、公式、联动、身份、权限、版本和验收集成，不实现平台引擎，不要求平台77项任务全绿。运行时模板必须由`wp_template_finder`及索引选择，权威模板仅为`backend/wp_templates/`，不得使用参考副本虚构内容。

## Requirements
### Requirement 1 — 范围与逐表owner矩阵
1. SHALL 为D4-1..D4-36逐`wp_code`登记owner、目标、状态（已覆盖/待核定/N/A）；N/A必须保留分母，不得抹除。
2. 已有owner不得重复立项：D4-2由`d4-revenue-matrix-bidirectional`、D4-9由`d4-9-customer-structure-bidirectional-writeback`、D4-10/11由`d4-price-analysis-writeback-linkage`负责；D4-5等已覆盖项不得新建gap。
3. D4-4、D4-8、D4-12若无明确owner，必须进入gap closure；仅以源模板和运行时finder核定后冻结。

### Requirement 2 — 共享同步与冲突
1. HTML与Excel均经`ContentMutationService`及`useWorkpaperSyncBridge`。
2. 不同字段自动合并；同字段冲突保留base/current/incoming、决策和轨迹，禁止Excel优先或最后写胜出。
3. durable ack仅表示决策已持久化，不等于applied；canonical rematerialize及目标content version确认后才算applied。

### Requirement 3 — 公式定义与custom
1. 有效定义 key 固定为`wp_id + stable_sheet_key + row_key + field_key + custom`；`preset_version`是定义版本，不是业务target identity的一部分；普通值override属于另域。
2. F-SHELL v2仅允许白名单命令表达式/引用/参数；禁止remark或field_overrides充当公式库，编辑schema禁止eval和外链。缺失公式与损坏公式分态，输入版本stale不得静默接受。
3. OO模板公式是同一公式定义的投影；mask保护公式值。Excel用户改公式必须解析、校验、CAS审计；不能保留原字节时显式blocked，不得静默仅存值。
4. 预设升级保留custom；删除custom后恢复preset；依赖版本变化产生stale。

### Requirement 4 — 表内/表间DAG
1. 表内、表间均可编辑；同scope只有一个公式writer。
2. 执行依赖必须是实际DAG，不能按表号禁止合理引用；循环和stale必须显式失败或标记。

### Requirement 5 — 联动边界与发布
1. 风险发现不等于错报；TB/A13发布必须显式确认且幂等、durable ack；模式切换不得发布。
2. 四表取数必须复用`app/services/four_table/`及`ReportLineAccountSpec`，不得复制科目SQL。

### Requirement 6 — 导入结构身份
导入导出必须保留sheet/table/区域/稳定row key/公式mask身份；结构变更走`ContentMutationService` mutation plan，拒绝位置猜测和静默扁平化。

### Requirement 7 — 权限、版本、迁移
按角色、scope、版本校验读写；拒绝过期CAS并记录审计。迁移必须幂等、可回滚，且不得把平台全局未完成作为D4全局阻塞。

### Requirement 8 — 逐表验收与milestone
每个wp_code必须有模板证据、contract/identity、HTML→Excel→HTML roundtrip、公式/冲突、权限及Playwright验收状态。按可验证milestone解锁子组；不可验证记UNVERIFIABLE，不得假绿。

## Acceptance Coverage
每条Requirement均由总纲设计R1-R8和tasks验收映射；逐表矩阵不得省略待核定项。
