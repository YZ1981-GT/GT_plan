# Task 4 · 真实 OnlyOffice 9.4 两用户同 room callback 黑盒实证

对应 design.md §多用户 callback 黑盒真值门、Requirement 4.3 / 4.9 / 4.10 / 5.1 / 5.4 / 10.2 / 10.4 / 10.9。
本目录是**实证 evidence**，不是推理。每条结论都能在 `callbacks.jsonl` / `commands.jsonl` /
`artifact_analysis.json` / `artifacts/*.xlsx` 里逐条复核。

## 0. 环境与 build（`oo_build.json`）

| 项 | 值 | 取证方式 |
|---|---|---|
| DocumentServer | `onlyoffice-documentserver 9.4.0-129` | `docker exec audit-onlyoffice dpkg -l onlyoffice-documentserver` |
| web-apps build | `9.4.0-17bd46f468bf1ff77e010159b8920986`（`?_dc=9.4.0-129`） | 浏览器编辑器 iframe src |
| callback 自报 | `history.serverVersion = "9.4.0"` | status 6 / 2 payload |
| 镜像 | `onlyoffice/documentserver:latest` @ `sha256:e3da62a8…` | `docker inspect` |
| JWT | 容器 `JWT_ENABLED=true`，inbox/outbox/browser 同一 secret，header `Authorization`，`inBody=false` | 容器 env + `local.json` |
| 探针文档 | `backend/wp_templates/A/A31 审计标识一览表.xlsx`，sha256 `fd4d5d61b151d9b5e46eb38d632153f0362b49fd3bfa0221c8fe3591acb1e870`（12 620 B） | 真实平台模板副本 `seed_document.xlsx` |

探针不接触生产 callback / 生产存储 / 业务库：自带 document host（`/doc`）与 callback collector（`/callback`），
文档字节取自平台真实模板。脚本 = `backend/scripts/diagnose/probe_oo94_multiuser_callback.py`。

**顺带取得的一条安全事实**：容器 `default.json` 默认 `request-filtering-agent.allowPrivateIPAddress=false`、
`externalRequest.action.blockPrivateIP=true`，但 `externalRequest.directIfIn.jwtToken=true` —— 因此
`document.url` / `callbackUrl` 只要来自 **JWT 签名过的 config**，OO 就按 direct 请求处理并**绕过私网封锁**，
这正是平台能用 `host.docker.internal` 的原因。即：OO 侧对回调/下载地址**没有** allowlist 保护，
SSRF 面完全由平台自己的 URL 校验决定。

## 1. 两用户确实在同一 room（同 doc_key）

- `doc_key = t4probe1787582477`，alice / bob 两个独立浏览器 tab、两个不同 `editorConfig.user.id`。
- 实测协同：bob 端读回 `Z90` = `ALICE-EDIT-Z90`（alice 写的格），alice 端读回 `Z92` = `BOB-EDIT-Z92`。
- `c=info` 返回 `users: ["alice","bob"]` —— room 级参与者视图，**无任何 per-user 权限/mode 信息**。

## 2. status 6 vs status 2 的 payload 差异（实测）

| 字段 | status 1 | status 4 | status 6（forcesave） | status 2（最终保存） |
|---|---|---|---|---|
| `url` / `changesurl` | ✗ | ✗ | ✓ | ✓ |
| `userdata` | ✗ | ✗ | **仅当 Command Service 传了才有** | ✗（实测恒无） |
| `forcesavetype` | ✗ | ✗ | ✓（`0` = Command Service 触发） | ✗ |
| `actions` | ✓（`type:1` 连接 / `type:0` 断开） | ✓（`type:0`） | **✗** | ✓（`type:0` 最后一人断开） |
| `notmodified` | ✗ | ✗ | ✗ | ✓（`true`/`false`） |
| `users` | ✓ 累积在线用户 | **✗** | ✓ **只有"最后编辑者"一人** | ✓ 只有关闭时那一人 |
| `history.changes[].user` | ✗ | ✗ | ✓ **全体贡献者** | ✓ **全体贡献者** |
| `lastsave` | ✗ | ✗ | ✓ | ✓ |
| body 内 `token` | ✓ | ✓ | ✓ | ✓ |

原始行：`callbacks.jsonl` phase1 seq1–10、phase2 seq1–2、phase3 seq1–3。

**status 6 可以没有 `userdata`**（phase1 seq5：不带 userdata 的 Command Service forcesave）⇒
真值表不能假设"status 6 必有 userdata"。

## 3. 聚合语义：callback 是 room 级事件，不是 participant 级

- phase1 seq3：由**服务端 Command Service** 发起 forcesave（`userdata=req-001-initiated-by-alice`），
  回传 artifact 同时含 `Z90=ALICE-EDIT-Z90` 与 `Z92=BOB-EDIT-Z92` ⇒
  **A 发起的 forcesave 产出的 artifact 里包含 B 的并发修改**。
- 同一 payload 的 `users` 只有 `["bob"]`（最后编辑者），`history.changes` 才是 `[alice, bob]`。
- Command Service `forcesave` 请求体**没有任何"发起人"字段**（只有 `c` / `key` / `userdata`），
  OO 也不回传发起人。

⟹ **结论（锁死）**：callback 是 **room/generation route 事件**。
`users` 既不是发起人、也不是贡献者全集；把 callback 里的任一 participant 当作聚合 artifact 的
唯一作者或唯一授权依据在 OO 9.4 上是**事实错误**（design「明确拒绝的方案」第 18 条得到实证支持）。
如需 contributor snapshot，唯一可用来源是 `history.changes[].user`（且它包含已被撤销的用户）。

## 4. 撤销（`c=drop`）语义：能挡未来写入，**不能**移除既有贡献

| 观察 | 结果 | 证据 |
|---|---|---|
| `c=drop {users:["bob"]}` | `error: 0` | `commands.jsonl` |
| 随后 `c=info` | `users: ["alice"]`（bob 已移出会话） | `commands.jsonl` |
| callback | phase1 seq6 = `status 1` + `actions:[{type:0,userid:"bob"}]` ⇒ **OO 提供可验证的 drop 取证** | `callbacks.jsonl` |
| bob 端 UI | "该文件现在无法访问"，客户端拒绝继续编辑 | 浏览器实测 |
| bob drop 后再输入 `Z94` | 本地都写不进（读回为空），后续所有 artifact 中 `Z94` 恒 `null` | `artifact_analysis.json` |
| **bob drop 前写的 `Z92`** | phase1 seq8（drop 后的 forcesave）与 seq10（最终 status 2）**仍含 `BOB-EDIT-Z92`** | `artifacts/cb08_status6.xlsx`、`artifacts/cb10_status2.xlsx` |
| `history.changes` | drop 后仍列出 bob | phase1 seq8/seq10 payload |

⟹ **结论（锁死）**：`c=drop` 只是"逐出会话 + 冻结其后续写入"，
**无法证明被撤销用户已从聚合文档中移除**——其已合入的内容会继续出现在此后每一次
forcesave / 最终保存的 artifact 里。

因此按 Task 4 与 Requirement 4.7 / 10.4 的要求，**固定采用**：
`提升 write_fence_epoch + 取消 outstanding request + supersede/rotate generation + 其余用户重开`。
**不得**设计 participant-bound callback authorization、也**不得**做"选择性 participant 内容应用"。

## 5. host 返回非零 error：OO 9.4 **不会重发**

- phase3 seq2（status 6）与 seq3（status 2）都由 collector 返回 `{"error":1}`。
- 分别等待 ~95 s 与 ~180 s：**没有任何重投**（phase3 callback 总数恒为 3）。
- 同时 OO 客户端 UI 仍显示"所有更改已保存"。

⟹ 两条硬结论：
1. 「返回非零让 OO 重发」在 9.4 上不成立 ⇒ durable 之后再返回非零 = **静默丢件**
   （design「明确拒绝的方案」第 8 条从另一侧被实证：不是"会造成重复"，而是"根本不会重发"，
   两种情形都要求 durable 后必须 `error=0` 并把失败留在 operation 上可重试）。
2. UI 不能采信 OO 自己的"已保存"文案，必须由平台 operation 状态给 durable ack（Requirement 4.12）。

## 6. Command Service 返回码（实测）

| 场景 | 返回 |
|---|---|
| 正常 forcesave（房间开着且有新变更） | `{"error":0}` + 随后一次 status 6 callback |
| 无 JWT | `{"error":6}`（invalid token），HTTP 仍 200 |
| JWT 用 flat claim（`jwt(body)` 而非 `jwt({"payload":body})`） | 通过鉴权（返回 `error:4`）⇒ **两种 claim 形态 9.4 都接受** |
| 距上次保存无新变更 | `{"error":4}` + **不产生 callback** |
| 文档已关闭 / key 不在线（`forcesave`、`info`） | `{"error":1}` |

⟹ `error:4` 与 `error:1` 都表示"**不会有 callback 到来**"，前端/后端必须靠 timeout + 明确
错误分类收敛，不能无限等 callback（Requirement 4.4 / 4.9 的 timeout、in-flight grace 前置判据）。

## 7. 幂等前置判据：`userdata` 与 incoming sha 都不足以判等

- **重复 `userdata`**：两次 forcesave 用同一 `userdata=req-001-initiated-by-alice`
  （phase1 seq3 与 seq9），OO 原样回显、毫无阻拦，且两次 artifact 字节不同
  ⇒ `userdata/request_id` 不是幂等键，必须由平台自己的 frozen request + delivery key 定序。
- **同内容不同字节**（两个 phase 各自独立复现）：
  | 组 | labels | statuses | content_sha256 | byte sha256 |
  |---|---|---|---|---|
  | 1 | `phase1#9`,`phase1#10` | 6, 2 | `7fbf0736…` | `bf686be0…` / `1a4fc9a3…` |
  | 2 | `phase3#2`,`phase3#3` | 6, 2 | `f54f1cd8…` | `51f85339…` / `51439a2a…` |

  即：紧随 forcesave 之后的关闭保存，即便 `notmodified:true`、内容完全一致（全 sheet 非空单元格
  排序后 hash 相等）、字节长度相同，**字节 sha256 仍不同**（xlsx 重新序列化）。

⟹ design 里"status 6 / status 2 / 网络重试 在同一 frozen identity 下折叠为一个 application"
只在**同一 delivery 的网络重试**（同 url、同字节）成立；**status 6 之后的 status 2 必然产生
不同的 application key**（因为 key 含 incoming sha）。Task 22/23 必须按此实现：
status 2 的 no-userdata 归组走 close-capture / frozen-identity 规则，
**不能**期望它靠 incoming sha 命中 status 6 的 application。

## 8. 未复现的状态（不得假绿）

`status 3`（保存出错）与 `status 7`（强制保存出错）本次**未能在受控条件下触发**
（需要 DS 自身生成输出失败）。真值表把它们标 `oo94_observed: false`，
处置固定为「不下载 / 不建 application / delivery 记 terminal error / 告警可见」，
并由 `unknown_status_policy = fail_visible` 兜住任何未登记状态。

## 9. 生产下载路径的安全 characterization（离线，未接通生产 callback）

测试：`backend/tests/test_workpaper_callback_download_security.py`（15 例，真实执行 + AST 数据流锚点）。
被 characterize 的生产调用点：`wp_onlyoffice_router.post_sheet_onlyoffice_callback`
（`_rewrite_onlyoffice_download_url` → `httpx.AsyncClient(timeout=60).get(url)` → `resp.content` → `write_bytes`）。

| 维度 | 实测结论 |
|---|---|
| SSRF | 只有 netloc 被换成 `ONLYOFFICE_URL`，path/query（含 `../`）原样保留；`ONLYOFFICE_URL` 为空时 host 完全由 payload 决定；环回目标无拦截 |
| DNS rebinding | 猴补解析把伪域名指向环回后请求照常成功 —— 无解析后 IP 复核 |
| redirect | **纸面推断被实测纠正**：httpx 0.28 在 `follow_redirects=False` 下 `raise_for_status()` **对 3xx 也抛错**，故 302 页面**不会**被写盘；但这是客户端库行为的隐式依赖，反证实测「一旦 `follow_redirects=True` 就会抵达重定向目标」⇒ 契约仍要求显式 `max_redirects=0` |
| 流式超限 | `resp.content` 整包入内存，8 MiB 全量 materialize，无上限、无截断 |
| 超时 | 单一 60 s 覆盖 connect/read/write/pool；契约要求 5 s / 30 s 分离 |
| OOXML | `text/plain` 内容照样被完整接收，下载层无 magic/MIME/zip 校验 |
| **代理（意外发现）** | 生产未关 `trust_env` ⇒ Windows 下 `urllib.request.getproxies()` 读**注册表系统代理**（本机 `http://127.0.0.1:7897`）并劫持下载，实测返回 **502**。既是「OO 保存失败」的现实诱因，也让底稿字节流经第三方代理（Requirement 10.7） |
| Property 16 现状 | 生产实参就是 `claim_version=None`，而 `verify_callback_preconditions` 对 `None` 直通（传真实版本时能拦住旧版本覆盖）⇒ 校验机制在、接线绕过 |
| Property 17 现状 | 下载字节由 `write_bytes` 直写共享 canonical 文件，函数内无任何 staging/quarantine/incoming/durable 调用 |

## 10. 变异检验

`backend/scripts/diagnose/mutate_task4_callback_contract_guards.py --run`：15 条变异，
**14 RED + 1 GREEN（对照项）**，0 ANCHOR-MISS、0 WRONG-TEST，报告见 `mutation_report.json`。
变异覆盖真值表（schema 版本、observed 声明、userdata 形态、命令返回码、撤销结论、
application key 组件、timers、claim schema、redirect 策略）、evidence 篡改与生产源码漂移
（`timeout=60`、`claim_version=None`）。生产 router 变异后按字节还原并核对 sha256。

## 11. 文件清单

| 文件 | 内容 |
|---|---|
| `run_meta_phase1.json` / `run_meta_phase2.json` / `run_meta_phase3.json` | 每个 phase 的 doc_key、seed sha256、端口、marker 单元格、OO 端点探测 |
| `oo_build.json` | build / JWT / externalRequest 与 request-filtering 默认值 |
| `callbacks.jsonl` | 15 条 callback 全量 payload（`token` 与 URL 签名参数已换成 `sha256:` 引用） |
| `commands.jsonl` | 12 次 Command Service 请求与返回 |
| `artifacts/*.xlsx` | 7 个 OO 回传 artifact 原件 |
| `artifact_analysis.json` | 逐 artifact 字节 sha / 内容 sha / zip 条目 sha / marker 单元格 + 同内容异字节分组 |
| `observations.json` | 机器可读投影（statuses、body key 全集、artifact digest、commands） |
| `mutation_report.json` | 15 条变异的四态判定（14 RED / 1 GREEN 对照） |
| `seed_document.xlsx` | 探针输入文档（平台真实模板副本） |

契约与守卫（不在本目录，属代码库）：

| 路径 | 作用 |
|---|---|
| `backend/data/onlyoffice_callback_state_contract.json` | 版本化真值表单一真源（schema_version 1） |
| `backend/tests/test_workpaper_callback_state_contract.py` | 真值表 ↔ 本目录 evidence 双向互锁守卫（21 例） |
| `backend/tests/test_workpaper_callback_download_security.py` | 下载安全 characterization（15 例，离线） |
| `backend/scripts/diagnose/probe_oo94_multiuser_callback.py` | 本目录 evidence 的采集探针 |
| `backend/scripts/diagnose/mutate_task4_callback_contract_guards.py` | 变异检验 runner |
