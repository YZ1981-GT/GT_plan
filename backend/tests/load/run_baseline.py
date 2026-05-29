"""
基线压测执行脚本 — 100 用户 / 60 秒

使用方法:
    python tests/load/run_baseline.py

可选参数:
    --host       目标主机 (默认 http://localhost:9980)
    --users      并发用户数 (默认 100)
    --spawn-rate 加压速率 (默认 20)
    --run-time   运行时长秒数 (默认 60)
    --output     报告输出路径 (默认 tests/load/baseline_report.md)

功能:
    1. 以无头模式运行 Locust 基线压测
    2. 收集 P50/P95/P99 响应时间、RPS、错误率
    3. 将结果填入 baseline_report.md 模板
"""

import argparse
import subprocess
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LOCUSTFILE = SCRIPT_DIR / "locustfile.py"
REPORT_TEMPLATE = SCRIPT_DIR / "baseline_report.md"

DEFAULT_HOST = "http://localhost:9980"
DEFAULT_USERS = 100
DEFAULT_SPAWN_RATE = 20
DEFAULT_RUN_TIME = 60


def parse_args():
    parser = argparse.ArgumentParser(description="运行 Locust 100 用户基线压测")
    parser.add_argument("--host", default=DEFAULT_HOST, help="目标主机地址")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="并发用户数")
    parser.add_argument("--spawn-rate", type=int, default=DEFAULT_SPAWN_RATE, help="加压速率 (users/s)")
    parser.add_argument("--run-time", type=int, default=DEFAULT_RUN_TIME, help="运行时长 (秒)")
    parser.add_argument("--output", default=str(REPORT_TEMPLATE), help="报告输出路径")
    return parser.parse_args()


def run_locust(host: str, users: int, spawn_rate: int, run_time: int) -> dict:
    """以无头模式运行 Locust，返回统计数据"""

    # CSV 输出临时文件前缀
    csv_prefix = SCRIPT_DIR / f"_baseline_{int(time.time())}"

    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(LOCUSTFILE),
        "--host", host,
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "--run-time", f"{run_time}s",
        "--csv", str(csv_prefix),
        "--csv-full-history",
        "--only-summary",
    ]

    print(f"[INFO] 启动 Locust 基线压测...")
    print(f"[INFO] 命令: {' '.join(cmd)}")
    print(f"[INFO] 目标: {host} | 用户: {users} | 速率: {spawn_rate}/s | 时长: {run_time}s")
    print("=" * 60)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=run_time + 60,  # 额外 60s 缓冲
            cwd=str(SCRIPT_DIR.parent.parent),  # 项目根目录
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
    except subprocess.TimeoutExpired:
        print("[WARN] Locust 执行超时，尝试读取已有 CSV 数据...")
    except FileNotFoundError:
        print("[ERROR] 未找到 locust 命令，请确认已安装: pip install locust")
        sys.exit(1)

    # 解析 CSV 统计结果
    stats = parse_csv_stats(csv_prefix)

    # 清理临时 CSV 文件
    cleanup_csv(csv_prefix)

    return stats


def parse_csv_stats(csv_prefix: Path) -> dict:
    """解析 Locust CSV 输出文件"""
    import csv

    stats_file = Path(f"{csv_prefix}_stats.csv")
    stats = {
        "total": {},
        "endpoints": [],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not stats_file.exists():
        print(f"[WARN] 未找到统计文件: {stats_file}")
        return stats

    with open(stats_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = {
                "name": row.get("Name", ""),
                "type": row.get("Type", ""),
                "requests": int(row.get("Request Count", 0) or 0),
                "failures": int(row.get("Failure Count", 0) or 0),
                "median": float(row.get("Median Response Time", 0) or 0),
                "p95": float(row.get("95%", 0) or 0),
                "p99": float(row.get("99%", 0) or 0),
                "avg": float(row.get("Average Response Time", 0) or 0),
                "max": float(row.get("Max Response Time", 0) or 0),
                "rps": float(row.get("Requests/s", 0) or 0),
            }

            if entry["name"] == "Aggregated":
                stats["total"] = entry
            else:
                stats["endpoints"].append(entry)

    return stats


def cleanup_csv(csv_prefix: Path):
    """清理 Locust 生成的临时 CSV 文件"""
    patterns = ["_stats.csv", "_failures.csv", "_stats_history.csv",
                "_exceptions.csv", "_failures.csv"]
    for suffix in patterns:
        f = Path(f"{csv_prefix}{suffix}")
        if f.exists():
            f.unlink()


def generate_report(stats: dict, args) -> str:
    """基于统计数据生成 Markdown 报告"""

    total = stats.get("total", {})
    endpoints = stats.get("endpoints", [])
    timestamp = stats.get("timestamp", "[未知]")

    # 计算错误率
    total_requests = total.get("requests", 0)
    total_failures = total.get("failures", 0)
    error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0

    # 构建各场景表格行
    endpoint_rows = []
    for ep in endpoints:
        ep_error_rate = (ep["failures"] / ep["requests"] * 100) if ep["requests"] > 0 else 0
        endpoint_rows.append(
            f"| {ep['type']} {ep['name']} | {ep['rps']:.1f} | {ep['failures']} | {ep_error_rate:.2f}% |"
        )

    # 构建响应时间表格
    def get_ep_metric(name_fragment: str, metric: str) -> str:
        for ep in endpoints:
            if name_fragment in ep["name"]:
                return f"{ep[metric]:.0f}"
        return "—"

    report = f"""# 基线压测报告 — {args.users} 用户

## 测试概要

| 项目 | 值 |
|------|-----|
| 测试日期 | {timestamp} |
| 测试工具 | Locust 2.x |
| 目标主机 | {args.host} |
| 并发用户数 | {args.users} |
| 加压速率 | {args.spawn_rate} users/s |
| 持续时间 | {args.run_time}s（稳定负载） |
| 测试脚本 | `tests/load/locustfile.py` |

## 压测场景

| 场景 | 权重 | 端点 |
|------|------|------|
| 登录 | 1 | POST /api/auth/login |
| 查询试算表 | 3 | GET /api/projects/{{pid}}/trial-balance |
| 查询底稿列表 | 2 | GET /api/projects/{{pid}}/workpapers |
| 编辑保存底稿 | 1 | GET + PUT /api/projects/{{pid}}/workpapers/{{wid}} |
| 穿透查询 | 2 | GET /api/projects/{{pid}}/drilldown?account_code=1001 |

---

## 响应时间（毫秒）

| 指标 | 全局 | 登录 | 查询试算表 | 查询底稿列表 | 穿透查询 |
|------|------|------|-----------|-------------|---------|
| P50 | {total.get('median', 0):.0f} | {get_ep_metric('login', 'median')} | {get_ep_metric('trial-balance', 'median')} | {get_ep_metric('workpapers', 'median')} | {get_ep_metric('drilldown', 'median')} |
| P95 | {total.get('p95', 0):.0f} | {get_ep_metric('login', 'p95')} | {get_ep_metric('trial-balance', 'p95')} | {get_ep_metric('workpapers', 'p95')} | {get_ep_metric('drilldown', 'p95')} |
| P99 | {total.get('p99', 0):.0f} | {get_ep_metric('login', 'p99')} | {get_ep_metric('trial-balance', 'p99')} | {get_ep_metric('workpapers', 'p99')} | {get_ep_metric('drilldown', 'p99')} |
| 最大值 | {total.get('max', 0):.0f} | {get_ep_metric('login', 'max')} | {get_ep_metric('trial-balance', 'max')} | {get_ep_metric('workpapers', 'max')} | {get_ep_metric('drilldown', 'max')} |
| 平均值 | {total.get('avg', 0):.0f} | {get_ep_metric('login', 'avg')} | {get_ep_metric('trial-balance', 'avg')} | {get_ep_metric('workpapers', 'avg')} | {get_ep_metric('drilldown', 'avg')} |

## 吞吐量与错误率

| 指标 | 值 |
|------|-----|
| 总请求数 | {total_requests} |
| 总失败数 | {total_failures} |
| 吞吐量 (RPS) | {total.get('rps', 0):.1f} |
| 错误率 (%) | {error_rate:.2f}% |

### 各场景 RPS 分布

| 场景 | RPS | 错误数 | 错误率 |
|------|-----|--------|--------|
{chr(10).join(endpoint_rows) if endpoint_rows else '| [无数据] | — | — | — |'}

---

## 资源使用率

| 指标 | 测试前 | 测试中峰值 | 测试后 |
|------|--------|-----------|--------|
| CPU 使用率 (%) | [待实测] | [待实测] | [待实测] |
| 内存使用率 (MB) | [待实测] | [待实测] | [待实测] |
| DB 连接数 (active) | [待实测] | [待实测] | [待实测] |
| DB 连接数 (idle) | [待实测] | [待实测] | [待实测] |
| Redis 连接数 | [待实测] | [待实测] | [待实测] |

> 注：资源使用率需在压测期间手动采集（见下方命令参考），或使用 `--monitor` 参数（待扩展）。

### 资源监控命令参考

```sql
-- PostgreSQL 连接数
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- 慢查询 Top 10
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
```

```bash
# CPU / 内存（Windows PowerShell）
Get-Process -Name python | Select-Object CPU, WorkingSet64

# Redis 连接数
redis-cli info clients
```

---

## 基线结论

### 达标判定

| 指标 | 目标 | 实测值 | 达标 |
|------|------|--------|------|
| P95 响应时间 | ≤ 2000ms | {total.get('p95', 0):.0f}ms | {'✅' if total.get('p95', 0) <= 2000 else '❌'} |
| P99 响应时间 | ≤ 5000ms | {total.get('p99', 0):.0f}ms | {'✅' if total.get('p99', 0) <= 5000 else '❌'} |
| 错误率 | < 0.1% | {error_rate:.2f}% | {'✅' if error_rate < 0.1 else '❌'} |
| RPS ({args.users} 用户) | 基线记录 | {total.get('rps', 0):.1f} | — |

### 后续行动

- [ ] 基于基线数据确定优化方向
- [ ] 执行 3.4 瓶颈优化（连接池/索引/缓存）
- [ ] 执行 3.5 目标压测（6000 用户）

---

## 执行方式

```bash
# 自动化执行（推荐）
python tests/load/run_baseline.py

# 手动执行
locust -f tests/load/locustfile.py --host={args.host} --headless -u {args.users} -r {args.spawn_rate} --run-time {args.run_time}s
```

---

*报告生成时间: {timestamp}*
"""
    return report


def main():
    args = parse_args()

    print("=" * 60)
    print("  审计平台基线压测 — Locust 自动化执行")
    print("=" * 60)
    print()

    # 检查 locustfile 存在
    if not LOCUSTFILE.exists():
        print(f"[ERROR] 未找到压测脚本: {LOCUSTFILE}")
        sys.exit(1)

    # 运行压测
    stats = run_locust(args.host, args.users, args.spawn_rate, args.run_time)

    # 生成报告
    if stats.get("total"):
        print()
        print("=" * 60)
        print("  生成基线报告...")
        print("=" * 60)

        report_content = generate_report(stats, args)
        output_path = Path(args.output)
        output_path.write_text(report_content, encoding="utf-8")
        print(f"[OK] 报告已输出: {output_path}")

        # 打印摘要
        total = stats["total"]
        total_requests = total.get("requests", 0)
        total_failures = total.get("failures", 0)
        error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0

        print()
        print("┌─────────────────────────────────────┐")
        print("│         基线压测结果摘要             │")
        print("├─────────────────────────────────────┤")
        print(f"│  总请求数:  {total_requests:<23} │")
        print(f"│  总失败数:  {total_failures:<23} │")
        print(f"│  错误率:    {error_rate:<22.2f}% │")
        print(f"│  RPS:       {total.get('rps', 0):<23.1f} │")
        print(f"│  P50:       {total.get('median', 0):<22.0f}ms │")
        print(f"│  P95:       {total.get('p95', 0):<22.0f}ms │")
        print(f"│  P99:       {total.get('p99', 0):<22.0f}ms │")
        print("└─────────────────────────────────────┘")
    else:
        print()
        print("[WARN] 未获取到统计数据，请检查:")
        print("  1. 后端服务是否已启动 (http://localhost:9980)")
        print("  2. Locust 是否正确安装 (pip install locust)")
        print("  3. 测试数据是否存在 (PROJECT_ID=1)")
        print()
        print("[INFO] 报告模板保留为占位状态，待实际执行后填充。")


if __name__ == "__main__":
    main()
