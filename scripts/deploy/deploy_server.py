# -*- coding: utf-8 -*-
"""把 dev1.0（或指定分支）部署到服务器。在本机 Windows 仓库根执行。

三个目标，部署方式各不相同，脚本按 ``--target`` 自动区分：

* ``prod``      60.205.170.122  docker：代码同步到 /www/wwwroot/gt-dev10 → 服务器上构建后端镜像 →
                试导入通过后替换 audit-backend 容器；前端在本机构建，替换 frontend-dist（宝塔 nginx）。
* ``test``      182.92.234.38   systemd：git bundle 传代码 → /opt/gt-new-plan 切到新提交 → 依赖有变才
                pip install → 试导入通过后重启 gt-backend；前端在本机构建，替换 audit-platform/frontend/dist。
* ``intranet``  应用 192.168.80.75 + 数据库 192.168.80.74，docker compose（项目 gt-audit）：数据库在 74 上备份；
                git bundle 传代码到 75 的 /opt/gt-audit/app_dev10，保留服务器本地的 Dockerfile 改动（国内镜像源）；
                在 75 上构建后端和前端镜像 → 后端试导入通过后替换两个容器。

流程：本机检查 → 构建前端（intranet 在服务器上构建）→ 连服务器预检 → 确认 → 备份（数据库 / 代码 /
镜像或 git 标签 / 旧前端）→ 上传 → 部署 → 等健康 → 检查迁移、站点、在线编辑契约 → 写 ROLLBACK.txt。
数据库迁移由后端启动时自动执行。

用法（PowerShell，仓库根；密码从环境变量读，没设就交互输入，不写进任何文件）::

    git switch dev1.0; git pull                                  # 本机先切到要部署的提交
    .venv\\Scripts\\python.exe scripts\\deploy\\deploy_server.py --target prod --check   # 只读预检
    .venv\\Scripts\\python.exe scripts\\deploy\\deploy_server.py --target prod           # 部署
    .venv\\Scripts\\python.exe scripts\\deploy\\deploy_server.py --target prod --post-only --provision-contracts --republish-stale

密码环境变量（可选）：``GT_DEPLOY_PW_PROD`` / ``GT_DEPLOY_PW_TEST`` / ``GT_DEPLOY_PW_INTRANET``（75）/
``GT_DEPLOY_PW_INTRANET_DB``（74），都没设时用 ``GT_DEPLOY_PW``，再没有就提示输入。

``--provision-contracts``  补发在线编辑契约（只新增定义，不动业务数据）。
``--republish-stale``      已发布在线编辑版本但用的是旧定义包的底稿，按模板重发一代（业务数据保留）。
两者默认只检查并列出结果，加参数才写库（``--post-only`` 写库前会先备份数据库）。
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "audit-platform" / "frontend"
SYNC_DIRS = ("backend", "audit-platform/frontend/src", "audit-platform/frontend/scripts", "docs", ".kiro")
GENERATED_FRONTEND_FILES = {"audit-platform/frontend/src/components.d.ts", "audit-platform/frontend/src/auto-imports.d.ts"}
PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
#: intranet 服务器上未提交仓库的本地改动（国内镜像源 / 去掉旧构建器不支持的阶段），每次部署后重新套上
INTRANET_LOCAL_FILES = ("backend/Dockerfile", "audit-platform/frontend/Dockerfile")


@dataclass(frozen=True)
class Target:
    name: str
    host: str
    kind: str                     # docker | systemd | compose_git
    root: str                     # 代码目录（compose_git 是 git 仓库目录）
    backup_base: str
    site_url: str                 # 在服务器本机访问站点首页的地址
    site_host: str = ""           # 访问站点时带的 Host 头（空 = 不带）
    frontend_dir: str = ""        # 本机构建的前端放到哪（compose_git 为空：前端在镜像里）
    backend_container: str = ""   # 空 = 不在容器里（systemd）
    db_host: str = ""             # 空 = 与应用同机
    db_container: str = ""        # 空 = 本机直装的 PostgreSQL
    db_backup_base: str = ""
    compose: str = ""             # docker compose 命令前缀（在 compose_dir 下执行）
    compose_dir: str = ""
    images: tuple[str, ...] = ()  # 部署前打 pre-<ts> 标签的镜像
    health_url: str = "http://127.0.0.1:9980/api/health"
    #: 前端改为「本机构建 + 服务器上只打 nginx 小镜像」时填这两个：镜像名、OnlyOffice 地址
    prebuilt_frontend_image: str = ""
    frontend_onlyoffice_url: str = ""


TARGETS = {
    "prod": Target(
        "prod", "60.205.170.122", "docker", "/www/wwwroot/gt-dev10", "/www/backup", "https://127.0.0.1/",
        site_host="www.gt.qccz.com.cn", frontend_dir="/www/wwwroot/gt-dev10/frontend-dist",
        backend_container="audit-backend", db_container="audit-postgres",
        compose="docker compose -p deploy -f deploy/docker-compose.prod.yml --env-file .env",
        compose_dir="/www/wwwroot/gt-dev10", images=("deploy-backend:dev10",)),
    "test": Target(
        "test", "182.92.234.38", "systemd", "/opt/gt-new-plan", "/opt", "https://127.0.0.1/",
        site_host="gt-test.qccz.com.cn", frontend_dir="/opt/gt-new-plan/audit-platform/frontend/dist"),
    "intranet": Target(
        "intranet", "192.168.80.75", "compose_git", "/opt/gt-audit/app_dev10", "/opt/gt-audit/backup",
        # 这台机器上用 127.0.0.1 访问 docker 映射端口会挂住，必须用本机 IP
        "http://192.168.80.75/", backend_container="gt-plan", db_host="192.168.80.74", db_container="audit-postgres",
        db_backup_base="/opt/gt-audit/backups",
        compose="DOCKER_BUILDKIT=0 docker compose -p gt-audit -f app-compose.dev10.yml --env-file .env",
        compose_dir="/opt/gt-audit", images=("gt_plan-backend:dev10", "gt-plan-frontend:dev10"),
        health_url="http://192.168.80.75:9980/api/health",
        # 前端不再在服务器上编译（装 npm 依赖 + 编译要 40 分钟以上），改本机构建后只打 nginx 小镜像
        prebuilt_frontend_image="gt-plan-frontend:dev10",
        frontend_onlyoffice_url="http://192.168.80.75:8080"),
}

#: 服务器上用 python3 发 HTTP（有的机器没装 curl；不走代理、不校验证书，只在服务器本机访问）
HTTP_PROBE = r'''import sys,ssl,urllib.request,urllib.error
url,host=sys.argv[1],sys.argv[2]
op=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
req=urllib.request.Request(url,headers={"Host":host} if host else {})
try:
    r=op.open(req,timeout=20); code=r.status; body=r.read()
except urllib.error.HTTPError as e:
    code=e.code; body=e.read()
except Exception:
    print("000"); sys.exit(0)
print(code); sys.stdout.write(body.decode("utf-8","replace"))'''


class DeployError(RuntimeError):
    pass


def say(msg: str) -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    say(f"\n==== {msg}")


# ─── 本机 ─────────────────────────────────────────────────────────────────────

def local(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    p = subprocess.run(list(args), cwd=cwd, capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise DeployError(f"本机命令失败（{' '.join(args)}）：{p.stderr.decode('utf-8', 'replace')[-1500:]}")
    return out


def git(*args: str, check: bool = True) -> str:
    return local("git", "-c", "core.quotepath=false", *args, check=check).strip()


def local_checks(ref: str, need_frontend: bool) -> tuple[str, str]:
    step("本机检查")
    if subprocess.run(["git", "fetch", "origin"], cwd=ROOT, capture_output=True).returncode != 0:
        say("⚠ git fetch origin 失败（网络？），按本机已有的远端数据继续")
    sha = git("rev-parse", f"{ref}^{{commit}}")
    full_ref = git("rev-parse", "--symbolic-full-name", ref)
    if not full_ref:
        raise DeployError(f"--ref 必须是分支名（如 origin/dev1.0），不能是提交号：{ref}")
    say(f"部署提交：{sha[:9]} {git('log', '-1', '--format=%ad %s', '--date=format:%m-%d %H:%M', sha)}（{full_ref}）")
    if need_frontend:
        head = git("rev-parse", "HEAD")
        if head != sha:
            raise DeployError(f"本机当前提交 {head[:9]} 不是要部署的 {sha[:9]}；前端要从工作区构建，请先 "
                              "`git switch dev1.0; git pull` 让两者一致")
        status = local("git", "-c", "core.quotepath=false", "status", "--porcelain", "--", "audit-platform/frontend")
        dirty = [line[3:] for line in status.splitlines() if line.strip()]
        dirty = [p for p in dirty if p not in GENERATED_FRONTEND_FILES]
        if dirty:
            raise DeployError("前端目录有未提交改动，构建结果会和提交不一致：\n  " + "\n  ".join(dirty[:20]))
    names = git("ls-tree", "--name-only", f"{sha}:backend/migrations/").split()
    for prefix in ("V", "R"):
        seen: dict[int, list[str]] = {}
        for n in names:
            m = re.match(rf"{prefix}(\d+)__", n)
            if m:
                seen.setdefault(int(m.group(1)), []).append(n)
        dup = {k: v for k, v in seen.items() if len(v) > 1}
        if dup:
            raise DeployError(f"迁移编号重复，部署后启动必失败：{dup}")
    top = max(int(n[1:].split("__", 1)[0]) for n in names if re.match(r"V\d+__", n))
    say(f"迁移文件无重复编号；最高 V{top}")
    return sha, full_ref


def build_frontend(work: Path, onlyoffice_url: str | None = None) -> Path:
    """本机构建前端。onlyoffice_url 非空时写入临时 env 文件（内网镜像构建时用的是服务器上的
    .env.production，本机构建要显式给同一个值，否则在线编辑加载不到 OnlyOffice）。"""
    step("构建前端（约 4~6 分钟）" + (f"，OnlyOffice 地址 {onlyoffice_url}" if onlyoffice_url else ""))
    dist = work / "dist"
    log = work / "frontend-build.log"
    env = dict(os.environ)
    if onlyoffice_url:
        env["VITE_ONLYOFFICE_URL"] = onlyoffice_url
    with log.open("wb") as fh:
        p = subprocess.run(["node", "--max-old-space-size=16384", "node_modules/vite/bin/vite.js", "build", "--mode", "production",
                            "--outDir", str(dist), "--emptyOutDir"], cwd=FRONTEND, env=env, stdout=fh, stderr=subprocess.STDOUT)
    if p.returncode != 0 or not (dist / "index.html").is_file():
        raise DeployError(f"前端构建失败，见 {log}")
    if onlyoffice_url:
        hit = any(onlyoffice_url.encode() in f.read_bytes() for f in (dist / "assets").glob("*.js"))
        if not hit:
            raise DeployError(f"构建产物里找不到 OnlyOffice 地址 {onlyoffice_url}，在线编辑会加载不到")
        say(f"已确认产物里带 OnlyOffice 地址 {onlyoffice_url}")
    p = subprocess.run(["node", "scripts/check-chunk-cycles.mjs", "--strict", "--dir", str(dist)], cwd=FRONTEND, capture_output=True)
    if p.returncode != 0:
        raise DeployError("分包循环检查失败（生产会白屏）：" + p.stdout.decode("utf-8", "replace")[-1500:])
    subprocess.run(["git", "restore", "--", *sorted(GENERATED_FRONTEND_FILES)], cwd=ROOT, capture_output=True)
    tgz = work / "dist.tgz"
    with tarfile.open(tgz, "w:gz") as tar:
        for child in dist.iterdir():
            tar.add(child, arcname=child.name)
    say(f"前端构建成功，{tgz.stat().st_size / 1e6:.1f} MB")
    return tgz


# ─── 服务器 ───────────────────────────────────────────────────────────────────

class Remote:
    def __init__(self, host: str, password: str) -> None:
        import paramiko

        self.host = host
        self.cli = paramiko.SSHClient()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.cli.connect(host, username="root", password=password, timeout=30, banner_timeout=30,
                             auth_timeout=30, look_for_keys=False, allow_agent=False)
        except Exception as e:  # noqa: BLE001
            raise DeployError(f"连不上 {host}：{type(e).__name__} {e}") from e

    def run(self, cmd: str, timeout: int = 600, check: bool = True) -> str:
        _, out, err = self.cli.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        if check and rc != 0:
            raise DeployError(f"{self.host} 命令失败（rc={rc}）：{cmd[:200]}\n{(e or o)[-2000:]}")
        return o.strip()

    def run_long(self, cmd: str, log: str, label: str, timeout_s: int = 3600) -> None:
        """后台执行并轮询，避免 SSH 长连接中断让命令半途而废。"""
        wrapped = f"({cmd}) > {log} 2>&1; echo EXIT=$? >> {log}"
        self.run(f"nohup sh -c {shlex.quote(wrapped)} > /dev/null 2>&1 &")
        start = time.time()
        while time.time() - start < timeout_s:
            time.sleep(15)
            m = re.search(r"EXIT=(\d+)", self.run(f"grep -o 'EXIT=[0-9]*' {log} 2>/dev/null || true", check=False))
            if m:
                if m.group(1) != "0":
                    raise DeployError(f"{label}失败，{self.host} 日志 {log}：\n" + self.run(f"tail -n 30 {log}", check=False))
                say(f"  {label}完成（{int(time.time() - start)} 秒）")
                return
            tail = self.run(f"tail -n 1 {log} 2>/dev/null || true", check=False)
            say(f"  {label}进行中 {int(time.time() - start)}s：{tail[-100:]}")
        raise DeployError(f"{label}超时，{self.host} 日志 {log}")

    def put(self, local_path: Path, remote_path: str) -> None:
        sftp = self.cli.open_sftp()
        last = [-20]

        def progress(done: int, total: int) -> None:
            pct = done * 100 // max(total, 1)
            if pct >= last[0] + 20:
                last[0] = pct
                say(f"  上传 {local_path.name} {pct}%")

        sftp.put(str(local_path), remote_path, callback=progress)
        if sftp.stat(remote_path).st_size != local_path.stat().st_size:
            raise DeployError(f"上传后大小不一致：{remote_path}")
        sftp.close()

    def http(self, url: str, host_header: str = "") -> tuple[str, str]:
        out = self.run(f"python3 -c {shlex.quote(HTTP_PROBE)} {shlex.quote(url)} {shlex.quote(host_header)}",
                       timeout=60, check=False)
        code, _, body = out.partition("\n")
        return code.strip(), body


@dataclass
class Ctx:
    t: Target
    app: Remote
    db: Remote

    def psql(self, sql: str) -> str:
        q = shlex.quote(sql)
        if self.t.db_container:
            return self.db.run(f"docker exec {self.t.db_container} psql -U postgres -d audit_platform -At -F '|' -c {q}")
        return self.db.run(f"sudo -u postgres psql -d audit_platform -At -F '|' -c {q}")

    def backend_python(self, args: str, timeout: int = 1800) -> str:
        """在后端运行环境里执行 backend/ 下的脚本（docker 进容器，systemd 用 venv）。"""
        if self.t.backend_container:
            return self.app.run(f"docker exec -e PYTHONIOENCODING=utf-8 {self.t.backend_container} python {args}",
                                timeout=timeout, check=False)
        return self.app.run(f"cd {self.t.root}/backend && PYTHONIOENCODING=utf-8 ../.venv/bin/python {args}",
                            timeout=timeout, check=False)

    def health(self) -> dict | None:
        code, body = self.app.http(self.t.health_url)
        try:
            return json.loads(body).get("data") or {} if code == "200" else None
        except ValueError:
            return None

    def deployed_version(self) -> str:
        if self.t.kind == "docker":
            return self.app.run(f"cat {self.t.root}/DEPLOYED_VERSION 2>/dev/null || echo 未记录", check=False)
        return self.app.run(f"cd {self.t.root} && git log -1 --format='%h %ad %s' --date=format:'%m-%d %H:%M'", check=False)


def summarize_health(h: dict | None) -> str:
    if h is None:
        return "不可访问"
    mig = h.get("migration") or {}
    drift = h.get("schema_drift") or {}
    fails = [f.get("version") if isinstance(f, dict) else f for f in (mig.get("failures") or [])]
    return (f"{h.get('status')}；迁移 已执行 {mig.get('applied_count')} / 待执行 {mig.get('pending_versions')} / 失败 {fails}；"
            f"严重漂移 {drift.get('critical_count')}")


def check_disk(r: Remote, label: str) -> None:
    free = int(r.run("df -Pk / | tail -1 | awk '{print $4}'"))
    say(f"{label}磁盘剩余：{free / 1024 / 1024:.1f} GB")
    if free < 5 * 1024 * 1024:
        raise DeployError(f"{label}磁盘剩余不足 5 GB，先清理再部署")


def preflight(c: Ctx) -> None:
    t = c.t
    step(f"服务器预检 {t.name} {t.host}" + (f" / 数据库 {t.db_host}" if t.db_host else ""))
    say("当前版本：" + c.deployed_version())
    say("健康：" + summarize_health(c.health()))
    check_disk(c.app, "应用服务器" if t.db_host else "")
    if t.db_host:
        check_disk(c.db, "数据库服务器")
    if t.kind == "systemd":
        say("gt-backend：" + c.app.run("systemctl is-active gt-backend", check=False))
    else:
        say(c.app.run("docker ps --format '{{.Names}} {{.Status}}' | grep -E 'audit-|gt-plan' || true", check=False))
    if t.db_host:
        say("数据库：" + c.db.run(f"docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' | grep {t.db_container} || true",
                                check=False))
    if t.kind == "compose_git":
        local_mods = c.app.run(f"cd {t.root} && git status --short", check=False)
        say("服务器本地改动（部署后会保留 Dockerfile 的改动）：\n  " + (local_mods.replace("\n", "\n  ") or "无"))


def backup_db(c: Ctx, ts: str) -> str:
    """备份数据库，返回备份文件路径（在数据库所在机器上）。"""
    t = c.t
    if t.db_host:
        bdir = f"{t.db_backup_base}/gt-deploy-{ts}"
    elif t.kind == "docker":
        bdir = f"{t.backup_base}/gt-deploy-{ts}"
    else:
        bdir = f"{t.backup_base}/gt-backup-{ts}"
    dump = f"{bdir}/db-before.dump"
    c.db.run(f"mkdir -p {bdir}")
    if t.db_container:
        c.db.run_long(f"docker exec {t.db_container} pg_dump -U postgres -d audit_platform -Fc -Z 6 > {dump}",
                      f"{bdir}/pg_dump.log", "数据库备份")
        n = c.db.run(f"docker exec -i {t.db_container} pg_restore --list < {dump} | grep -c 'TABLE DATA'")
    else:
        c.db.run_long(f"sudo -u postgres pg_dump -d audit_platform -Fc -Z 6 > {dump}", f"{bdir}/pg_dump.log", "数据库备份")
        n = c.db.run(f"pg_restore --list {dump} | grep -c 'TABLE DATA'")
    if int(n or 0) == 0:
        raise DeployError(f"数据库备份读不出任何表：{c.db.host}:{dump}")
    say(f"数据库备份 {c.db.host}:{dump}（{c.db.run(f'du -sh {dump} | cut -f1')}，可读出 {n} 张表）")
    return dump


def backup(c: Ctx, bdir: str, ts: str) -> str:
    step(f"备份到 {bdir}")
    t = c.t
    c.app.run(f"mkdir -p {bdir}")
    dump = backup_db(c, ts)
    for image in t.images:
        c.app.run(f"docker tag {image} {image.split(':')[0]}:pre-{ts}")
    if t.kind == "docker":
        c.app.run(f"cd {t.root} && tar --exclude='audit-platform/frontend/node_modules' --exclude='storage' "
                  f"--exclude='*/__pycache__' -czf {bdir}/code-before.tgz backend audit-platform docs .kiro deploy frontend-dist .env",
                  timeout=1800)
        say("代码已打包 code-before.tgz")
    else:
        c.app.run(f"cd {t.root} && git tag -f deploy-backup-{ts} HEAD")
        say(f"代码标签 deploy-backup-{ts}")
    if t.kind == "systemd":
        c.app.run(f"test -d {t.frontend_dir} && cp -a {t.frontend_dir} {bdir}/dist-before || true")
    if t.kind == "compose_git":
        c.app.run(f"cd {t.root} && git diff -- {' '.join(INTRANET_LOCAL_FILES)} > {bdir}/local-dockerfiles.patch")
        c.app.run(f"cd {t.compose_dir} && cp -a app-compose.dev10.yml .env {bdir}/")
        say("服务器本地 Dockerfile 改动已存为 local-dockerfiles.patch")
    if t.images:
        say("镜像已标 " + "、".join(f"{i.split(':')[0]}:pre-{ts}" for i in t.images))
    return dump


def wait_healthy(c: Ctx, minutes: int = 12) -> dict:
    step("等待后端就绪（启动时会执行数据库迁移）")
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(10)
        h = c.health()
        if h is not None:
            say("后端已就绪：" + summarize_health(h))
            return h
        say("  等待中")
    raise DeployError("后端 12 分钟内没有就绪；看日志：" + (
        f"docker logs --tail 200 {c.t.backend_container}" if c.t.backend_container else "journalctl -u gt-backend -n 200"))


def python_pkgs(text: str) -> set[str]:
    names = set()
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip().lower().replace("_", "-"))
    return names


def import_check_container(c: Ctx, ts: str) -> None:
    t = c.t
    out = c.app.run(f"cd {t.compose_dir} && {t.compose} run --rm --no-deps -T --entrypoint python backend "
                    f"-c \"import app.main; print('IMPORT_OK')\" 2>&1 | tail -5", timeout=900, check=False)
    if "IMPORT_OK" not in out:
        for image in t.images:
            c.app.run(f"docker tag {image.split(':')[0]}:pre-{ts} {image}", check=False)
        raise DeployError("新镜像导入后端失败，容器未替换，镜像标签已还原为部署前版本：\n" + out[-1500:])
    say("新镜像试导入通过")


def deploy_prod(c: Ctx, work: Path, sha: str, ref: str, bdir: str, yes: bool, ts: str) -> None:
    t, r = c.t, c.app
    step("打包并上传代码")
    code = work / "code.tgz"
    git("archive", "--format=tar.gz", "-o", str(code), sha, *SYNC_DIRS)
    r.put(code, f"{bdir}/code.tgz")
    r.put(work / "dist.tgz", f"{bdir}/dist.tgz")
    r.run(f"rm -rf {bdir}/stage && mkdir -p {bdir}/stage && tar -xzf {bdir}/code.tgz -C {bdir}/stage", timeout=1800)

    step("检查依赖与文件删除")
    new_req = python_pkgs(r.run(f"cat {bdir}/stage/backend/requirements.txt"))
    old_req = python_pkgs(r.run(f"cat {t.root}/backend/requirements.txt", check=False))
    prod_req = python_pkgs(r.run(f"cat {t.root}/backend/requirements.prod.txt"))
    added = sorted((new_req - old_req) - prod_req)
    if added:
        say(f"⚠ requirements.txt 新增了 {added}，正式环境用的是服务器上的 requirements.prod.txt，没有这些包。"
            "如果后端用得到，镜像试导入会失败并停在替换容器之前；届时把包加进 requirements.prod.txt 再部署。")
    deleted = []
    for d in SYNC_DIRS:
        if d == ".kiro":
            continue
        out = r.run(f"cd {t.root} && rsync -a --delete --dry-run --itemize-changes --exclude='__pycache__/' "
                    f"--exclude='requirements.prod.txt' {bdir}/stage/{d}/ {d}/ | grep '^\\*deleting' || true", check=False)
        deleted += [f"{d}/{line.split(None, 1)[1]}" for line in out.splitlines()
                    if line.strip() and not line.rstrip().endswith("/")]
    if deleted:
        say(f"新代码里已删除、同步时会从服务器删掉的文件 {len(deleted)} 个（部署前的代码已备份在 code-before.tgz）：")
        for p in deleted[:40]:
            say("  " + p)
        if not yes and input("继续？输入 y 确认：").strip().lower() != "y":
            raise DeployError("已取消（服务器还没有任何改动，备份目录可删）")

    step("同步代码")
    for d in SYNC_DIRS:
        r.run(f"cd {t.root} && rsync -a --delete --exclude='__pycache__/' --exclude='requirements.prod.txt' "
              f"{bdir}/stage/{d}/ {d}/", timeout=1800)

    step("构建后端镜像（约 2~5 分钟）")
    r.run_long(f"cd {t.compose_dir} && {t.compose} build backend", f"{bdir}/image-build.log", "镜像构建", 3600)
    import_check_container(c, ts)
    step("替换后端容器")
    r.run(f"cd {t.compose_dir} && {t.compose} up -d --no-deps backend", timeout=600)
    r.run(f"echo {shlex.quote(f'{sha[:9]} {ref} {ts}')} > {t.root}/DEPLOYED_VERSION")


def push_git_bundle(c: Ctx, work: Path, sha: str, ref: str, bdir: str) -> bool:
    """把提交以 git bundle 传上去并 fetch；服务器已是该提交时返回 False。"""
    t, r = c.t, c.app
    step("打包并上传代码")
    base = r.run(f"cd {t.root} && git rev-parse HEAD")
    if base == sha:
        say("服务器代码已是该提交，跳过代码更新")
        return False
    bundle = work / "code.bundle"
    args = ["bundle", "create", str(bundle), ref]
    shallow = r.run(f"cd {t.root} && git rev-parse --is-shallow-repository", check=False) == "true"
    known = subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=ROOT, capture_output=True).returncode == 0
    if shallow:
        # 浅克隆只有少数提交，增量 bundle 依赖的历史提交它没有 ⇒ 发全量历史并顺带补全（之后就能增量）
        say("服务器仓库是浅克隆，打全量 bundle（一次性，较大）并补全历史")
    elif known:
        args.append(f"^{base}")
    else:
        say(f"⚠ 本机没有服务器当前提交 {base[:9]}，打全量 bundle（较大）")
    git(*args)
    say(f"代码包 {bundle.stat().st_size / 1e6:.1f} MB")
    r.put(bundle, f"{bdir}/code.bundle")
    verify = r.run(f"cd {t.root} && git bundle verify {bdir}/code.bundle 2>&1; echo rc=$?", check=False, timeout=900)
    if not verify.rstrip().endswith("rc=0"):
        raise DeployError("服务器上校验代码包失败（缺少依赖的提交），代码未改动：\n" + verify[-1200:])
    r.run(f"cd {t.root} && git fetch {bdir}/code.bundle +{ref}:refs/remotes/bundle/deploy", timeout=1800)
    if shallow:
        # 从 bundle 取全量历史不会自动去掉 shallow 标记；历史完整（fsck 通过）才去掉，否则放回
        out = r.run(f"cd {t.root} && mv .git/shallow {bdir}/git-shallow.bak && git fsck --connectivity-only --no-dangling "
                    f"> {bdir}/fsck.log 2>&1; echo rc=$?", check=False, timeout=1800)
        if not out.rstrip().endswith("rc=0"):
            r.run(f"cd {t.root} && cp {bdir}/git-shallow.bak .git/shallow", check=False)
            raise DeployError(f"补全历史后校验不通过，已恢复浅克隆标记，代码未改动；见 {bdir}/fsck.log")
        say("服务器仓库历史已补全（不再是浅克隆，下次部署走增量）")
    return True


def checkout(c: Ctx, sha: str) -> None:
    t, r = c.t, c.app
    r.run(f"cd {t.root} && git checkout -f -B dev1.0 refs/remotes/bundle/deploy", timeout=900)
    now = r.run(f"cd {t.root} && git rev-parse HEAD")
    if now != sha:
        raise DeployError(f"切换后服务器提交是 {now[:9]}，不是 {sha[:9]}")


def deploy_test(c: Ctx, work: Path, sha: str, ref: str, bdir: str, ts: str) -> None:
    t, r = c.t, c.app
    changed = push_git_bundle(c, work, sha, ref, bdir)
    r.put(work / "dist.tgz", f"{bdir}/dist.tgz")
    if not changed:
        return
    step("切换代码")
    req_before = r.run(f"cd {t.root} && sha256sum backend/requirements.txt | cut -c1-64")
    checkout(c, sha)
    if r.run(f"cd {t.root} && sha256sum backend/requirements.txt | cut -c1-64") != req_before:
        r.run_long(f"{t.root}/.venv/bin/pip install -r {t.root}/backend/requirements.txt -i {PIP_INDEX}",
                   f"{bdir}/pip.log", "安装依赖", 1800)
    out = c.backend_python("-c \"import app.main; print('IMPORT_OK')\" 2>&1 | tail -5", timeout=900)
    if "IMPORT_OK" not in out:
        r.run(f"cd {t.root} && git checkout -f -B dev1.0 deploy-backup-{ts}", check=False)
        raise DeployError("新代码导入后端失败，代码已切回部署前版本，服务未重启：\n" + out[-1500:])
    say("新代码试导入通过")
    step("重启后端")
    r.run("systemctl restart gt-backend")


def deploy_intranet(c: Ctx, work: Path, sha: str, ref: str, bdir: str, ts: str) -> None:
    t, r = c.t, c.app
    if not push_git_bundle(c, work, sha, ref, bdir):
        say("代码未变，仍会重新构建镜像")
    else:
        step("切换代码并保留服务器本地 Dockerfile 改动")
        checkout(c, sha)
        patch = f"{bdir}/local-dockerfiles.patch"
        if r.run(f"test -s {patch} && echo yes || echo no") == "yes":
            out = r.run(f"cd {t.root} && git apply --3way {patch} 2>&1; echo rc=$?", check=False)
            if not out.rstrip().endswith("rc=0"):
                r.run(f"cd {t.root} && git checkout -f -B dev1.0 deploy-backup-{ts} && git apply {patch}", check=False)
                raise DeployError("新代码的 Dockerfile 和服务器本地改动冲突，已切回部署前代码（本地改动已还原）。"
                                  f"需要手工合并 {patch} 后再部署：\n" + out[-1500:])
            say("本地 Dockerfile 改动已重新套上：" + r.run(f"cd {t.root} && git status --short -- {' '.join(INTRANET_LOCAL_FILES)}"))

    step("构建后端镜像（约 2~5 分钟）")
    r.run_long(f"cd {t.compose_dir} && {t.compose} build backend", f"{bdir}/image-build.log", "镜像构建", 5400)
    build_prebuilt_frontend_image(c, bdir, ts)
    import_check_container(c, ts)
    step("替换后端和前端容器")
    r.run(f"cd {t.compose_dir} && {t.compose} up -d --no-deps backend frontend", timeout=900)


#: 服务器上临时拼前端镜像用的 Dockerfile：只复制本机构建好的产物，不装依赖、不编译
PREBUILT_FRONTEND_DOCKERFILE = """FROM nginx:1.27-alpine
ENV GT_BACKEND_HOST=backend \\
    GT_BACKEND_PORT=9980 \\
    NGINX_ENVSUBST_FILTER=^GT_
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \\
  CMD wget -q -O /dev/null http://127.0.0.1/frontend-health || exit 1
"""


def build_prebuilt_frontend_image(c: Ctx, bdir: str, ts: str) -> None:
    """用本机构建好的 dist 在服务器上拼一个 nginx 镜像（几十秒），替代在服务器上编译前端。"""
    t, r = c.t, c.app
    step(f"打前端镜像 {t.prebuilt_frontend_image}（用本机构建好的产物，几十秒）")
    ctx = f"{bdir}/fe-image"
    r.run(f"rm -rf {ctx} && mkdir -p {ctx}/dist")
    r.run(f"tar -xzf {bdir}/dist.tgz -C {ctx}/dist && test -f {ctx}/dist/index.html")
    tpl = f"{t.root}/audit-platform/frontend/docker/default.conf.template"
    if r.run(f"test -f {tpl} && echo yes || echo no") != "yes":
        raise DeployError(f"服务器上找不到 nginx 模板 {tpl}，无法拼前端镜像")
    r.run(f"cp {tpl} {ctx}/default.conf.template")
    r.run(f"cat > {ctx}/Dockerfile << 'GT_EOF'\n{PREBUILT_FRONTEND_DOCKERFILE}GT_EOF")
    r.run_long(f"cd {ctx} && DOCKER_BUILDKIT=0 docker build -t {t.prebuilt_frontend_image} .",
               f"{bdir}/fe-image-build.log", "前端镜像", 900)
    created = r.run(f"docker image inspect {t.prebuilt_frontend_image} --format '{{{{.Created}}}}'", check=False)
    say(f"前端镜像已更新：{created}")


def swap_frontend(c: Ctx, bdir: str, ts: str) -> None:
    t, r = c.t, c.app
    if t.frontend_dir:
        step("替换前端")
        fd = t.frontend_dir
        r.run(f"rm -rf {fd}.new && mkdir -p {fd}.new && tar -xzf {bdir}/dist.tgz -C {fd}.new && test -f {fd}.new/index.html")
        if t.kind == "docker":
            r.run(f"mv {fd} {fd}.bak-{ts} && mv {fd}.new {fd}")
        else:
            r.run(f"rm -rf {fd} && mv {fd}.new {fd}")
        r.run(f"find {fd} -type d -exec chmod 755 {{}} + && find {fd} -type f -exec chmod 644 {{}} +")
    code, _ = r.http(t.site_url, t.site_host)
    say(f"站点首页 {t.site_host or t.host} → HTTP {code}")


def write_rollback(c: Ctx, bdir: str, ts: str, dump: str) -> None:
    t = c.t
    db_restore = (f"docker exec -i {t.db_container} pg_restore -U postgres -d audit_platform --clean --if-exists < {dump}"
                  if t.db_container else f"sudo -u postgres pg_restore -d audit_platform --clean --if-exists {dump}")
    db_where = f"（在数据库服务器 {t.db_host} 上执行）" if t.db_host else ""
    tags = "\n".join(f"docker tag {i.split(':')[0]}:pre-{ts} {i}" for i in t.images)
    if t.kind == "docker":
        body = f"""cd {t.root}
{tags}
{t.compose} up -d --no-deps backend
rm -rf frontend-dist && mv frontend-dist.bak-{ts} frontend-dist
# 代码目录（只影响下次构建）：tar -xzf {bdir}/code-before.tgz -C {t.root}"""
    elif t.kind == "systemd":
        body = f"""cd {t.root} && git checkout -f -B dev1.0 deploy-backup-{ts}
rm -rf {t.frontend_dir} && cp -a {bdir}/dist-before {t.frontend_dir}
systemctl restart gt-backend"""
    else:
        body = f"""cd {t.compose_dir}
{tags}
{t.compose} up -d --no-deps backend frontend
# 代码目录（只影响下次构建）：
cd {t.root} && git checkout -f -B dev1.0 deploy-backup-{ts} && git apply {bdir}/local-dockerfiles.patch"""
    text = (f"# 回退到部署前（{ts}）\n{body}\n# 数据库{db_where}（会丢掉部署后写入的数据，只在新迁移出问题时用）：\n"
            f"#   {db_restore}\n")
    c.app.run(f"cat > {bdir}/ROLLBACK.txt << 'GT_EOF'\n{text}GT_EOF")
    step(f"回退方法（已写入 {t.host}:{bdir}/ROLLBACK.txt）")
    say(text)


def post_checks(c: Ctx, provision: bool, republish: bool) -> None:
    step("迁移检查")
    h = c.health() or {}
    say(summarize_health(h))
    for f in (h.get("migration") or {}).get("failures") or []:
        msg = json.dumps(f, ensure_ascii=False)
        say("  失败：" + msg[:300])
        if "concurrent prebuild" in msg:
            say("  ⇒ 大表索引要先在线建好：在后端环境里执行 "
                "python scripts/ops/build_ledger_query_indexes.py --apply --confirm BUILD_LEDGER_INDEXES，再重启后端")

    step("在线编辑契约检查")
    tool = "scripts/fix/fix_task76_provision_projection_definitions.py"
    jpath = "/tmp/gt_deploy_contract_check.json"
    c.backend_python(f"{tool} --check --json {jpath} > /dev/null 2>&1")
    reader = f"docker exec {c.t.backend_container} cat {jpath}" if c.t.backend_container else f"cat {jpath}"
    try:
        report = json.loads(c.app.run(reader, check=False))
    except ValueError:
        say(f"契约检查没有产出报告，跳过（可手工运行 {tool} --check）")
        return
    bundle_of: dict[str, str] = {}
    pending = []
    for e in report.get("entries", []):
        eid = (e.get("target") or {}).get("entry_id")
        digest = (e.get("digests") or {}).get("bundle")
        if eid and digest:
            bundle_of[eid] = digest
        if e.get("would_create"):
            pending.append(eid)
    say(f"需要补发契约的底稿 {len(pending)} 个" + (f"：{', '.join(pending)}" if pending else ""))
    if pending and provision:
        for eid in pending:
            out = c.backend_python(f"{tool} --apply --entry {shlex.quote(eid)} > /dev/null 2>&1; echo rc=$?")
            say(f"  补发 {eid}：{'成功' if out.strip().endswith('rc=0') else '失败 ' + out[-200:]}")
    elif pending:
        say("  加 --post-only --provision-contracts 再运行一次即可补发（只新增定义，不动业务数据）")

    step("已发布在线编辑版本的底稿")
    rows = c.psql("SELECT s.wp_id, s.entry_id, r.definition_bundle_sha256, wi.wp_code "
                  "FROM working_paper_sync_entry_state s JOIN working_paper_content_representation r ON r.id = s.current_representation_id "
                  "JOIN working_paper wp ON wp.id = s.wp_id JOIN projects p ON p.id = wp.project_id "
                  "LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id WHERE wp.is_deleted = false AND p.is_deleted = false")
    stale = []
    for line in rows.splitlines():
        wp_id, eid, digest, code = (line.split("|") + [""] * 4)[:4]
        if eid in bundle_of and digest.strip() != bundle_of[eid]:
            stale.append((wp_id, eid, code))
    say(f"用旧定义包、需要重发的底稿 {len(stale)} 份（已删项目的不算）")
    for wp_id, eid, code in stale:
        if republish:
            out = c.backend_python(f"scripts/fix/republish_entry_from_template.py --wp-id {wp_id} --entry-id {shlex.quote(eid)} "
                                   f"--apply 2>&1 | grep -o '\"status\": \"[a-z_]*\"' | tail -1")
            say(f"  重发 {code} {wp_id[:8]}：{out or '无输出'}")
        else:
            say(f"  {code} {wp_id[:8]} {eid}")
    if stale and not republish:
        say("  加 --post-only --republish-stale 再运行一次即可重发（业务数据保留，有人正在在线编辑的会被跳过）")


def password_for(t: Target, host: str, role: str) -> str:
    key = f"GT_DEPLOY_PW_{t.name.upper()}" + ("_DB" if role == "db" else "")
    return os.environ.get(key) or os.environ.get("GT_DEPLOY_PW") or getpass.getpass(f"{host} root 密码：")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="部署 dev1.0 到服务器")
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--ref", default="origin/dev1.0", help="要部署的分支（默认 origin/dev1.0）")
    ap.add_argument("--check", action="store_true", help="只做本机检查与服务器只读预检，不改任何东西")
    ap.add_argument("--post-only", action="store_true", help="不部署，只做部署后的迁移 / 契约检查")
    ap.add_argument("--provision-contracts", action="store_true", help="补发在线编辑契约")
    ap.add_argument("--republish-stale", action="store_true", help="重发用旧定义包的在线编辑版本")
    ap.add_argument("--yes", action="store_true", help="跳过确认提示")
    a = ap.parse_args()
    t = TARGETS[a.target]
    need_frontend = bool(t.frontend_dir) or bool(t.prebuilt_frontend_image)
    try:
        if not a.post_only:
            sha, full_ref = local_checks(a.ref, need_frontend)
        app = Remote(t.host, password_for(t, t.host, "app"))
        db = Remote(t.db_host, password_for(t, t.db_host, "db")) if t.db_host else app
        c = Ctx(t, app, db)
        preflight(c)
        if a.check:
            say("\n只读预检完成，没有改动任何东西。")
            return 0
        if a.post_only:
            if a.provision_contracts or a.republish_stale:
                step("写库前先备份数据库")
                backup_db(c, datetime.now().strftime("%Y%m%d-%H%M%S"))
            post_checks(c, a.provision_contracts, a.republish_stale)
            return 0
        if not a.yes:
            ok = input(f"\n将把 {sha[:9]} 部署到 {t.name}（{t.host}），会短暂中断服务。输入 {t.name} 确认：").strip()
            if ok != t.name:
                raise DeployError("已取消")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        work = ROOT / f"tmp_deploy_{t.name}_{ts}"
        work.mkdir(parents=True)
        if need_frontend:
            build_frontend(work, t.frontend_onlyoffice_url or None)
        bdir = f"{t.backup_base}/gt-deploy-{ts}" if t.kind != "systemd" else f"{t.backup_base}/gt-backup-{ts}"
        dump = backup(c, bdir, ts)
        if t.kind == "docker":
            deploy_prod(c, work, sha, full_ref, bdir, a.yes, ts)
        elif t.kind == "systemd":
            deploy_test(c, work, sha, full_ref, bdir, ts)
        else:
            deploy_intranet(c, work, sha, full_ref, bdir, ts)
        wait_healthy(c)
        swap_frontend(c, bdir, ts)
        app.run(f"rm -rf {bdir}/stage", check=False)
        post_checks(c, a.provision_contracts, a.republish_stale)
        write_rollback(c, bdir, ts, dump)
        say(f"\n部署完成：{t.name} 现在是 {sha[:9]}。本机临时目录 {work.name} 可以删除。")
        return 0
    except DeployError as e:
        say(f"\n✗ {e}")
        return 1
    except KeyboardInterrupt:
        say("\n✗ 已中断。若中断发生在备份之后，看服务器备份目录的状态再决定是否回退。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
