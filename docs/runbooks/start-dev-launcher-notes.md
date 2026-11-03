# start-dev.bat 运维说明

`start-dev.bat` 必须保持**纯 ASCII**。本文承载被从脚本里移出的中文说明与实测数据。

## 一、为什么 bat 不能写中文（2026-09-05 事故）

### 现象

脚本被加入中文 REM 注释后，启动时打出：

```
[1/5] Stopping old processes...
      Done.
[2/5] Starting backend on :9980 ...
'??' is not recognized as an internal or external command,
[3/5] Waiting for backend health (max 60s, migrations may take 20-40s)...
'*在' is not recognized as an internal or external command,
'连接失败。' is not recognized as an internal or external command,
'[WARN]' is not recognized as an internal or external command,
```

那些「命令」全是中文 REM 注释的**后半截**，被 cmd 当命令执行了。

### 根因

cmd.exe 先按**父 console 当前代码页**打开并逐行解析 bat。第 3 行 `chcp 65001`
把代码页换成 UTF-8 后，cmd 的「字符数 vs 字节数」记账失去同步。解析
`( ... )` 块（`for /L` + `if`）时它需要回退文件指针重读，错位的指针落到某行
中间，于是从中文注释的中段恢复解析。

### 2×2 因子实验（实测）

| 块内多字节字符 | 解析中途 `chcp 65001` | 结果 |
|---|---|---|
| 有 | 有 | **碎（复现残片）** |
| 有 | 无 | 干净 |
| 无 | 有 | 干净 |

两个因子**缺一不可**。另外中文放在括号块**外**也不碎——但不要依赖这点，
块的边界会随后续编辑漂移。

### 触发依赖父进程代码页

| 父 console CP | 结果 |
|---|---|
| 936（中文 Windows 默认，双击 bat 的真实情形） | **碎** |
| 65001（已切 UTF-8 的终端） | 不碎 |
| python subprocess + 管道 / detached 无 console | 不碎 |

**排查启示**：在已切 UTF-8 的终端里手动跑脚本可能完全正常，用户双击却必碎。
复现时必须显式 `chcp 936`。

### 结论

无法在 bat 内部规避，只能保证文件纯 ASCII。守卫：
`backend/tests/test_start_dev_bat_ascii_guard.py`（6 条，含 CP936 下的反向自检
与真实脚本端到端 dry-run）。

## 二、前后端统一使用 IPv4 loopback（2026-10-19 勘误）

旧记录认为 Vite 默认只监听 `::1`，因此前端探测必须用 `localhost`。2026-10-19
真实复现证明该结论已经不适用于当前机器：`netstat` 虽显示 `[::1]:3030 LISTENING`，
但 `curl`、浏览器和 `Test-NetConnection` 对 `::1` 全部拒绝，启动器因此稳定报
`[WARN] Frontend not responding`，页面打不开。

现行统一契约：

| 服务 | 监听 | 探测/工具地址 |
|---|---|---|
| 后端 uvicorn | `0.0.0.0:9980` | `127.0.0.1:9980` |
| 前端 Vite | `0.0.0.0:3030` | `127.0.0.1:3030` |

`vite.config.ts` 固定 `host: '0.0.0.0'`；`start-dev.bat`、Playwright 和 Vite transform
检查都走 `127.0.0.1`。浏览器使用 `localhost:3030` 通常仍可回落 IPv4，但自动化与
健康探针禁止依赖该回落。启动器的 PowerShell 探针还必须设置
`$ProgressPreference='SilentlyContinue'`，否则 `Invoke-WebRequest` 的 Host progress
流会绕过普通重定向，在终端里表现成大段错位/疑似乱码。

## 三、后端健康等待为何是 60s

启动时 MigrationRunner 要跑全部 `V*.sql`（已 150+ 个）+ schema drift 检查，
冷启动实测超过 30s。30s 上限会在后端其实正常的情况下打出
`[WARN] Backend not responding`，把排查方向带到后端上。

## 四、括号块内 echo 的圆括号必须转义

`if ... ( ... ) else ( ... )` 多行块内任何裸 `)` 都会被当成块结束符：

```bat
REM 错误：(vendor read-only) 里的 ) 提前闭合 if 块，残留的 . 成为孤立 token
echo [3.5] DSH SDK runtime detected (vendor read-only).
REM 正确
echo [3.5] DSH SDK runtime detected ^(vendor read-only^).
```

错误写法让 cmd 报 `. was unexpected at this time.` 并**整体终止脚本
（exit 255）**，于是 `[4/5]` 启动前端那行永远不执行 ——
现象是「后端起来了、前端根本没起」。这发生在**解析阶段**，所以连 `[3.5]`
自己的 echo 都不会打印，唯一线索是紧跟 `[3/5]` 之后的一行报错，极易被忽略。

## 五、`:wait_port_free` 的性能约束

轮询必须保持在**单次 powershell 调用内**，且只能用
`IPGlobalProperties.GetActiveTcpListeners()`：

- bat 的 for 循环每轮重启 powershell，约 2s/轮，不可接受
- `Get-NetTCPConnection` 是 CIM 查询，约 1.2s/次
- `TcpListener` bind 只绑一个地址族，可能给出错误结论
- `GetActiveTcpListeners()` 是纯 .NET 调用（毫秒级），返回所有地址族

vite 配了 `strictPort`，端口被占就直接退出（不会漂到 3031）；`taskkill` 后
socket 未必立即释放，所以必须显式等端口空闲。

## 六、`:kill_port` 必须清掉 uvicorn 孤儿 worker（2026-10-19 实测）

现象：重启后 `netstat -ano` 出现两条 `0.0.0.0:9980 LISTENING`，其中一条的 PID
早已不存在；请求随机落到旧进程，旧进程读的是改 `.env` 之前的配置（当时
`ENCRYPTION_KEY` 为空，保存模型 API Key 直接 503）。

根因链：

1. uvicorn `--reload` 的 supervisor 创建监听 socket，经 multiprocessing spawn 把
   句柄复制给 worker（worker 命令行形如
   `spawn_main(parent_pid=<supervisor>, pipe_handle=...)`）。
2. 旧 `:kill_port` 对 owner 执行 `taskkill /F` **不带 `/T`**：杀掉 supervisor 后
   worker 成孤儿，继续持有监听句柄、继续跑旧代码与旧 `.env`。
3. netstat 仍把该 socket 记在**已死的 supervisor PID** 名下，下次 `:kill_port`
   杀已死 PID 是空操作，孤儿永远杀不掉。
4. uvicorn 以 `SO_REUSEADDR` 绑定，新后端能绑到同一端口，与孤儿共享连接。
5. `Get-NetTCPConnection` 会把同地址的重复绑定折叠成一条，只显示其中一个 owner；
   取 owner 必须用 `netstat -ano`。

现行规则：先按启动器专用窗口标题清理自己创建的进程树；`:kill_port` 只清理
socket 记录的 owner 已死亡、且命令行匹配 `spawn_main(parent_pid=<owner>,` 的孤儿
worker。端口上仍存活的 listener 一律视为未知进程，不再强杀。随后对 9980 和 3030
执行 `:wait_port_free`；端口仍被占用时启动器打印 `[ERROR]` 并以非零状态退出，避免
误杀其他程序，也避免新旧服务共享端口。

守卫：`backend/tests/test_start_dev_kill_port_orphan_guard.py` 真实复现
「supervisor 先死、worker 持句柄存活」，执行从 bat 原样提取的 `:kill_port`
命令；把命令换回旧逻辑时该测试打红（变异已验证）。
`test_start_dev_bat_ascii_guard.py` 的 dry-run 打桩正则容忍任意 powershell
开关，并断言打桩后不残留可执行的 powershell / taskkill / start —— 旧正则漏掉
带 `-NonInteractive` 的 3 处调用，dry-run 会真按标签杀掉正在运行的开发服务器。

## 七、后端热重载开关 `GT_BACKEND_NO_RELOAD`（2026-10-25）

默认照旧带 `--reload`。在 cmd 里先 `set GT_BACKEND_NO_RELOAD=1` 再运行 start-dev.bat，后端就不带任何 `--reload*` 参数启动（其余参数逐字相同），窗口里多一行 `Hot reload OFF` 提示；改了后端代码要重新运行 start-dev.bat 才生效。

用途：在线编辑验收与计时。每次热重载都会丢掉进程内的注册缓存与解析缓存，紧接着的那次 OnlyOffice 保存要重付冷成本（2026-10-24 实测重载后第一个保存回调 51 s）；多会话共用开发环境时，别的会话改代码会频繁触发重载。

守卫：`backend/tests/test_start_dev_backend_reload_switch.py`（从 bat 原样取出开关与启动行，cmd 里两种模式各展开一次比对）。

## 八、启动成功判据与退出码

前端的 `VITE_API_BASE_URL` / `VITE_DEV_PORT` 在父进程中使用 `set "NAME=value"`
赋值后再启动子窗口。不要写成 `set NAME=value && ...`：`&&` 前的空格会进入变量值，
Vite 会原样保留，进而使 `/api` 的绝对 `Location` 重写匹配失败。

后端探针不只检查 HTTP 200，还要求 `/api/health` 的业务状态为 `healthy`；
`degraded` 不再被误报为启动成功。9980 或 3030 未就绪时，启动器最终返回非零退出码，
调用脚本可以据此判定失败。退役的 DSH Web UI 3080 不再由启动器清理、注入或展示；
DSH Agent 统一由后端运行时管理。
