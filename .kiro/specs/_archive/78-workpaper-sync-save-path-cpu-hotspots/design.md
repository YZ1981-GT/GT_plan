# 双向回写 CPU 热点与事件循环阻塞 — Design

## §1 实测

浏览器（重药安徽 D2-2，2026-10-23 03:05）：

| 路径 | 用户等待 | 构成 |
|---|---|---|
| OO 改格 → 结构化视图看到新值 | 20.5 s | forcesave 0.3 · OO 组装回传 + 下载落盘约 2 · **apply 18.5**（base 2.27 / current 1.20 / incoming 2.09 / merge 1.98 / CPU 段 10.45 / 提交等 0.5）· 轮询重载 0.2 |
| 打开在线编辑（HTML 没改） | 7.1 s | 服务端 2.9（投影构造 1.4）· OnlyOffice 加载约 4 |

离线复跑同一份真实产物（`oo_apply_breakdown.py` / `html_open_breakdown.py`，四个输出摘要逐项相同）：

| 保存链路 CPU | base | current | incoming | merge | 物化 | 反读 | 未管理区 | 结构 hash | 合计 |
|---|---|---|---|---|---|---|---|---|---|
| 现状 | 2.35 | 1.16 | 1.21 | 1.94 | 5.37 | 1.14 | 0.58 | 0.46 | **14.20** |
| 只修 §2① | 2.27 | 1.21 | 1.04 | 1.86 | 2.24 | 1.15 | 0.45 | 0.46 | 10.67 |
| 只修 §2② | 1.70 | 0.93 | 0.76 | 0.99 | 4.99 | 0.89 | 0.58 | 0.32 | 11.18 |
| 只修 §2③ | 2.26 | 1.23 | 1.09 | 1.41 | 5.30 | 1.26 | 0.44 | 0.47 | 13.44 |
| ①②③ | 1.75 | 0.95 | 0.80 | 0.57 | 1.96 | 0.85 | 0.59 | 0.33 | **7.79** |
| ①②③ + 去重复提取 | 1.26 | 0.00 | 0.87 | 0.54 | 1.91 | 0.83 | 0.62 | 0.31 | **6.35** |

HTML 改过再打开（服务端投影 + 物化 CPU 段）：现状 1.33 + 7.88 = 9.2 s → ①②④ 0.30 + 4.04 = 4.3 s。

## §2 根因（cProfile，按累计耗时）

1. **物化逐格编译正则**：`_cell_view` 每格 `re.compile(_CELL_RE_TPL.format(coord=…))`，一次保存 39,619 次；Python 正则缓存只有 512 条，坐标各不相同 ⇒ 次次新编译（实测 74 µs/次）。`SheetCellIndex` 去掉了整表搜索，但切片上仍调这个函数，收益被吃掉一半。
2. **契约校验逐键扫全部模板**：`Projection.assert_matches_contract` 对每个键遍历全部模板（一次保存调 24 次，内层生成器 1,400 万次）。
3. **合并定位同样线性扫**：`merge.ContractIndex.resolve` → `_segments_match` 142 万次。
4. **HTML→OO 投影构造同样线性扫**：`endpoint_payloads._resolve_stable_key` 逐键遍历行域模板集合。
5. **重复提取**：一次保存 `extract_projection` 21 次，不同输入只有 base / incoming / 产物 3 份 × 4 binding；current 与 base 是同一 artifact，`_baseline_pair` 又把 base 主 binding 提一遍。
6. **事件循环阻塞**：`extract_three_way` 与 `merge_projections` 同步执行，单 worker 部署下整段（现状 7.6 s，修后约 2.7 s）全平台无响应。

同类教训：ROI-5a 只修了 `field_by_stable_key` 的 O(字段²)，同样「逐键扫模板」的另外三处没跟着修。

## §3 设计

- **①** `_cell_view(xml, coord)`：先 `xml.find('<c r="{coord}"')`，再用预编译的「尾部」正则在其后 `match`；不中则找下一处。模板 = 字面前缀 + 尾部，故「第一处整式命中」与 `pattern.search` 等价。`coord` 只拼进字面量，不再进正则。
- **②③④** `SyncContract.template_candidate_indices(key)`：惰性建 `{段数: {占位位置: {固定段: [all_fields 下标]}}}`，返回升序下标。候选是超集（占位段匹配任何值，含空串）：
  - `assert_matches_contract`：在候选上跑原 `_matches_any_template` ⇒ 结论相同（非候选必不命中：段数不同 / 固定段不同 / 行域标志不符）；
  - `ContractIndex.resolve`：`_templates` 与 `all_fields()` 同序（构造时逐项核对，不齐则退回全量扫），在候选上跑原 `_segments_match`（它要求占位段非空，比候选更严）⇒ 命中列表与顺序相同；
  - `_resolve_stable_key`：候选 ≤ 1 直接判；> 1 退回原循环（原循环遍历 set，多命中时选谁取决于迭代序，不改它）。
- **⑤** current 与 base 的 `artifact_sha256` 相同 ⇒ `current = base`（两者都按 published 形态、无 baseline 提取，同字节同结果）。`ExcelSyncAdapter.extract` 先判形态：published 不调 `_baseline_pair`；读的正是冻结 base 文件时，主 binding 的提取结果填进 `_baseline["pair"]`（入参与 `derive_baseline_from_representation` 逐项相同）。
- **⑥** `extract_three_way`：两次 resolve（DB）照旧在事件循环上做完，三次提取 + journal 记录放进一个 `asyncio.to_thread`；`apply_durable_incoming` 的 `merge_projections` 同样放线程。提取与合并不触库（`ExcelSyncAdapter` 只读文件；`_baseline` 缓存只被本次 apply 使用）。

## §4 守卫

- 新旧对拍：旧算法原样保留在测试里作参照；真实契约（D2 / D4）全部键 + 构造的边界键（空占位段、段数不符、非行域精确键、多占位模板、未登记键）逐条比结论与异常。
- `_cell_view`：真实 sheet XML 每个坐标 + 不存在坐标 + 自闭合格 + 共享公式，新旧逐字段相同。
- ⑤⑥：替身 adapter 记录调用次数与线程；current 同 sha 时提取次数 = 2×binding、不同 sha 时 3×；提取与合并不在事件循环线程；journal 阶段序列不变。
- 变异：①去掉坐标核对 / ②候选漏一组 / ③不按原序 / ⑤ sha 不同也复用 / ⑥退回同步，各自打红。

## §5 预期

保存回表单 20.5 s → 约 10.5 s（apply 18.5 × 6.35/14.20 ≈ 8.3 s）；HTML 改过再打开约 13 s → 约 8 s；没改直接打开 7.1 s → 约 6 s（OnlyOffice 加载约 4 s 是下限）。保存时全平台停顿 7.6 s → 0。

修完后剩余以 openpyxl 解析为主（剖析约 45%），再往下要动结构，见 §6。

## §6 后续可选（本 spec 不做）

| 方向 | 估计收益 | 前提 / 风险 |
|---|---|---|
| 物化计划阶段复用 incoming 提取（现再提 4 次） | 约 0.7 s | 须证明 baseline 只影响受保护格判定 |
| 跨请求 base 投影缓存（发布时反读结果按 sha 入缓存） | 约 1.3 s | 单 worker 才稳定命中；须证明两个方向 adapter 对 published 产物提取一致 |
| 保存后先回表单、后台合并（`_archive/44` P3） | 用户感知约 1 s | 合并期间表单为旧值，需要待合并态与冲突处理；迁移 + 17 宿主 |

## §7 拒绝方案

- 进程池：数据要序列化（2 万键投影），单用户延迟不降，`_archive/44` §8 已评估。
- 换 lxml / 自写解析器：重写面太大，剩余收益约 2 s。
- 跳过反读等值或未管理区域校验：那是正确性闸门，不砍。

## §8 实施结果（2026-10-23）

改动：契约候选索引（`contracts.py` / `adapters/base.py` / `merge.py` / `endpoint_payloads.py`）、`_cell_view` 字面前缀（`excel_materialize.py`）、current 复用 base 与 published 不算 baseline（`oo_to_html.py` / `adapters/excel.py`）、三方提取与合并进工作线程（`oo_to_html.py`）。CPU 段（`_stage_cpu_segment`）原本就在工作线程，本 spec 之后保存链路的整簿计算全部不占事件循环。

与 §3 / R3.1 的偏离：⑤ 实施时按 **artifact_id 相同**复用，不按 sha —— 路径不同时 OO→HTML adapter 按 `_substrate_shape_of` 判形态，同 sha 的另一份文件可能被当作 incoming 形态读，结果不保证相同。

随本 spec 修掉的 D2 spec 回归（179 文件对比发现，详见 `d2-skeleton-slot-reuse-and-writeback-speed` design 勘误）：复用骨架行的公式格保留模板缓存 `<v>`（新写入形态 `cached_value_cleared`）；before-digest 键段顺序。

守卫：`test_save_path_cpu_hotspots.py` 62 例（新旧对拍、替身 adapter 次数与线程、AST 卡住 `to_thread`）；磁盘变异 11/11 全杀；179 个相关测试文件 HEAD 对比零新增失败（379 条共同预存）；golden digest 242 / 37 家不变；行数门过。

离线同会话对照（改动前 = HEAD + 暂存区，同一份重药安徽 D2 产物；四个摘要 `a485253b…` / `a485253b…` / `7b77aa6d…` / `181a7ca4…` 前后逐字节相同）：

| 保存链路 CPU | base | current | incoming | merge | 物化 | 反读 | 未管理区 | 结构 hash | 合计 |
|---|---|---|---|---|---|---|---|---|---|
| 改动前 | 2.34 | 1.26 | 1.08 | 1.90 | 5.28 | 1.29 | 0.46 | 0.47 | **14.07** |
| 改动后 | 1.06 | 0.00 | 1.01 | 0.61 | 1.99 | 0.97 | 0.59 | 0.47 | **6.69** |

HTML 改过再打开：服务端投影 冷 2.57 → 1.20 s、暖 1.29 → 0.22 s；物化 CPU 段 7.54 → 4.12 s（五个摘要前后相同）。

浏览器（开发服务器，worker 预热完、测量期间无重载）：

| 路径 | 改动前 | 改动后 |
|---|---|---|
| OO 改格 → 结构化视图看到新值 | 20.5 s（apply 18.49） | **13.0 s**（apply 10.81：base 1.06 / current 0.01 / incoming 1.06 / merge 1.84 / CPU 段 6.18）；另一次 apply 10.33 s |
| 打开在线编辑，HTML 没改（服务端） | 2.92 s（投影 1.42） | 0.65 / 0.74 s（投影 0.21 / 0.25）；指纹直通 0.15 s |
| HTML 改过再打开（服务端） | 只有离线数据（9.2 s） | 6.21 / 8.71 s；点击到可编辑 11.4 / 13.3 s |

- 保存期间本页轮询 21 次 200、5 次被下一次轮询取消，不再出现整段无响应；每秒一次的健康探针在 apply 期间最长 1.7 s（GIL 争用与同时段他会话请求未区分）；改动前同一段轮询 8 s 无一次响应。
- 比 §5 预期（约 10.5 s）慢 2.5 s：线上 apply 10.3~10.8 s 而离线链路 6.7 s，差在线上 CPU 段含计划组装等离线没跑的部分、与同进程其他请求争 GIL；两次 merge 1.84 / 0.55 s 差异属同类波动。
- 测试编辑已还原：HTML 侧清空第 1 行公司代码，store 与其余 499 行同为 `""`；随后打开生成的 content version r26 投影摘要 `4ba8628f6d3f6daa`，与测试前 r16 / r18 相同。

## §9 实测中看到的范围外问题（未改，供另立）

1. **开发服务器重载**：`--reload-dir app` 下并发会话改 `app/` 约每 10 分钟重载一次；新 worker 冷注册预热 53~83 s、基线 projection 预热 32~35 s，期间到达的 OO 回调排队（一次回调请求 95.7 s，其中 apply 22 s），前端提示「等待 OnlyOffice 回传结果超时」。生产不热重载，但每次重启后的头一分半钟同样排队。
2. **单 worker 被其他重端点占住**：一次保存点击后 11 s 回调才到，同时段他会话的 `python-httpx` 连发 `GET /api/address-registry`，每次 3.2~4.6 s 并占住事件循环。保存慢的一部分来自同进程里别的同步重计算，属平台级。
3. **复用 generation 时文档服务给了旧文档**：共享浏览器把我的标签强关（未发 leave）后重新打开，平台复用 room g12 的 doc key，OnlyOffice 提示「版本已更改，该页面将被重新加载」，确认后载入的是上一版（C13 = PERF-T1，store 与当前表示均为 PERF-T2），工具栏呈禁用态；离开再进入恢复正常。未确认此状态能否保存；若能，旧文档与表示的差异会被当成 OO 修改合并回去。
4. **一次 HTML 保存挂起**：表格编辑模式清空一格后「保存中…」持续约 5 分钟，旧 worker 被重载后请求重发成功；同操作复测 PUT 159 ms。同时段旧 worker 没有日志，未定位原因，只记录。
5. **GC**：离线 CPU 链 7.83 s 中循环 GC 占 2.26 s（gen2 共 12 次、每次约 0.15 s）；线上堆约 1.5 GB，gen2 触发少但单次更贵。可评估调阈值或 CPU 段局部收集。
