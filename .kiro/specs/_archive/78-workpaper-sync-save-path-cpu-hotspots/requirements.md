# 双向回写 CPU 热点与事件循环阻塞 — Requirements

## 背景（2026-10-23 实测，重药安徽 D2-2：500 行 / 19,526 个受管字段 / 4 个 binding）

- OO 里改一格 → 点「结构化视图」→ 看到新值：**20.5 s**。其中平台合并 18.5 s（三方提取 5.6 + 合并 2.0 + CPU 段 10.5 + 提交 0.5），平台以外（OO 组装回传 + 下载落盘 + 轮询重载）约 2.5 s。
- 打开在线编辑：HTML 没改 7.1 s（服务端 2.9 s，OnlyOffice 自身加载约 4 s）；HTML 改过再打开，服务端多一次物化（离线 9.2 s）。
- 三方提取与合并（7.6 s）在**事件循环上同步执行**；docker-compose 是 `--workers 1` ⇒ 每次 OO 保存全平台所有请求停 7.6 s（浏览器自己的轮询在 1.9 s→10.0 s 之间没有一次响应）。
- 函数级剖析：openpyxl 解析只占保存链路约 20%；大头是平台自己代码里的三处算法问题（见 design §2）。

## R1 物化逐格解析不得逐格编译正则

1. `excel_materialize._cell_view` 的结果与现实现逐字段相同（含 `raw` / `attrs` / `body` / 公式文本 / 共享公式 ref / 找不到返回 `None`），但不再为每个坐标 `re.compile`。
2. 三个调用点（坐标索引切片 / 整份 sheet XML 写入 / footer 公式检查）全部生效。

## R2 契约键匹配走一次建成的索引

1. `SyncContract` 上惰性建一份「段数 + 占位位置 + 固定段」索引（同 `_stable_key_index` 写法），按键返回候选模板（超集，按 `all_fields()` 原序）。
2. 三个消费方保留各自原判据，只在候选上判：`Projection.assert_matches_contract`、`merge.ContractIndex.resolve`、`endpoint_payloads._resolve_stable_key`；结论、报错类型与文案、多命中时选谁，与线性扫描逐条相同。

## R3 同一次保存不重复提取

1. 三方提取里 current 与 base 的 artifact sha 相同 ⇒ current 直接复用 base 的投影（journal 照记 `current_extracted`）。
2. `ExcelSyncAdapter.extract` 读 published 形态时不再先算 baseline；读冻结 base 文件的主 binding 时，用这次结果填 baseline 缓存（与 `derive_baseline_from_representation` 入参逐项相同）。

## R4 保存链路的整簿提取与合并不得占用事件循环

1. `extract_three_way` 的三次提取与 `merge_projections` 移到工作线程；DB 访问仍在事件循环上，阶段顺序与 journal 记录不变。
2. 同时适用于回调后 apply、冲突裁决 resolve、retry（同一协调器入口）。

## R5 等价与实测

1. 每项改动配「新旧实现逐条对拍」守卫与磁盘变异；golden digest 不变；行数门过。
2. 用真实 D2 产物离线复跑：合并结果 / 反读结果 / 产物字节 / structure hash 四个摘要与改动前相同。
3. 浏览器实测重药安徽 D2-2：保存回表单、HTML 改过后打开两条路径，改动前后各测一次。

## 不在范围

- OnlyOffice 自身加载（约 4 s）与 forcesave 组装回传（约 1.5 s）。
- 「保存后先回表单、后台合并」（`_archive/44` P3，需迁移 + 17 个宿主接线）。
- 跨请求的 base 投影缓存、物化计划阶段复用 incoming 提取（见 design §6，另立）。
