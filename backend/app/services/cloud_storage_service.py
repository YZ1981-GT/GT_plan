"""云端存储服务 — 归档推送到事务所内部服务器

三阶段存储架构：
  1. 项目进行中 → 本地磁盘 storage/projects/{id}/workpapers/
  2. 日常使用中 → Paperless-ngx 存 OCR 文本+元数据（不存文件）
  3. 项目归档时 → 推送到内部服务器，本地可选清理

支持的传输方式（通过 CLOUD_STORAGE_TYPE 配置切换）：
  - sftp: SFTP 传输到内部文件服务器（默认）
  - s3: S3 兼容协议（MinIO / 阿里云 OSS / 内部对象存储）
  - smb: Windows 共享文件夹（SMB/CIFS）
  - local: 本地目录复制（测试用）
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# ── 配置（从环境变量读取，预留地址） ─────────────────────

CLOUD_STORAGE_TYPE = os.environ.get("CLOUD_STORAGE_TYPE", "local")

# SFTP 配置（事务所内部服务器）
CLOUD_SFTP_HOST = os.environ.get("CLOUD_SFTP_HOST", "192.168.1.100")  # 预留地址
CLOUD_SFTP_PORT = int(os.environ.get("CLOUD_SFTP_PORT", "22"))
CLOUD_SFTP_USER = os.environ.get("CLOUD_SFTP_USER", "audit_archive")
CLOUD_SFTP_PASSWORD = os.environ.get("CLOUD_SFTP_PASSWORD", "")
CLOUD_SFTP_KEY_PATH = os.environ.get("CLOUD_SFTP_KEY_PATH", "")
CLOUD_SFTP_BASE_PATH = os.environ.get("CLOUD_SFTP_BASE_PATH", "/archive/audit")

# S3 兼容配置（MinIO / 阿里云 OSS / 内部对象存储）
CLOUD_S3_ENDPOINT = os.environ.get("CLOUD_S3_ENDPOINT", "http://192.168.1.100:9000")
CLOUD_S3_ACCESS_KEY = os.environ.get("CLOUD_S3_ACCESS_KEY", "")
CLOUD_S3_SECRET_KEY = os.environ.get("CLOUD_S3_SECRET_KEY", "")
CLOUD_S3_BUCKET = os.environ.get("CLOUD_S3_BUCKET", "audit-archive")
CLOUD_S3_REGION = os.environ.get("CLOUD_S3_REGION", "")

# SMB 配置（Windows 共享）
CLOUD_SMB_SERVER = os.environ.get("CLOUD_SMB_SERVER", "\\\\192.168.1.100\\archive")
CLOUD_SMB_USER = os.environ.get("CLOUD_SMB_USER", "")
CLOUD_SMB_PASSWORD = os.environ.get("CLOUD_SMB_PASSWORD", "")

# 本地目录（测试用）
CLOUD_LOCAL_PATH = os.environ.get("CLOUD_LOCAL_PATH", "archive_cloud")

# 是否启用上传时双写（默认开启，有云端服务器时自动同步）
CLOUD_SYNC_ON_UPLOAD = os.environ.get("CLOUD_SYNC_ON_UPLOAD", "true").lower() == "true"


class CloudStorageService:
    """云端存储服务"""

    async def sync_single_file(
        self,
        project_id: UUID,
        project_name: str,
        year: int,
        local_file: Path,
        relative_path: str,
    ) -> dict[str, Any]:
        """上传时同步单个文件到云端（双写模式）

        在底稿上传/WOPI保存时调用，不阻塞主流程（失败只记日志不报错）。
        """
        if not CLOUD_SYNC_ON_UPLOAD:
            return {"status": "disabled"}

        remote_prefix = f"{year}/{project_name}_{str(project_id)[:8]}"
        remote_key = f"{remote_prefix}/{relative_path}"

        try:
            if CLOUD_STORAGE_TYPE == "sftp":
                return await self._sync_file_sftp(local_file, remote_key)
            elif CLOUD_STORAGE_TYPE == "s3":
                return await self._sync_file_s3(local_file, remote_key)
            elif CLOUD_STORAGE_TYPE == "smb":
                return await self._sync_file_smb(local_file, remote_key)
            else:
                return await self._sync_file_local(local_file, remote_key)
        except Exception as e:
            logger.warning("cloud sync failed (non-blocking): %s", e)
            return {"status": "failed", "error": str(e)}

    async def _sync_file_local(self, local_file: Path, remote_key: str) -> dict:
        dest = Path(CLOUD_LOCAL_PATH) / remote_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_file, dest)
        return {"status": "success", "method": "local", "remote_key": remote_key}

    async def _sync_file_sftp(self, local_file: Path, remote_key: str) -> dict:
        try:
            import paramiko
        except ImportError:
            return await self._sync_file_local(local_file, remote_key)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            kw: dict[str, Any] = {"hostname": CLOUD_SFTP_HOST, "port": CLOUD_SFTP_PORT, "username": CLOUD_SFTP_USER}
            if CLOUD_SFTP_KEY_PATH:
                kw["key_filename"] = CLOUD_SFTP_KEY_PATH
            elif CLOUD_SFTP_PASSWORD:
                kw["password"] = CLOUD_SFTP_PASSWORD
            ssh.connect(**kw)
            sftp = ssh.open_sftp()
            remote_path = f"{CLOUD_SFTP_BASE_PATH}/{remote_key}"
            remote_dir = "/".join(remote_path.split("/")[:-1])
            self._sftp_makedirs(sftp, remote_dir)
            sftp.put(str(local_file), remote_path)
            sftp.close()
            return {"status": "success", "method": "sftp", "remote_key": remote_key}
        finally:
            ssh.close()

    async def _sync_file_s3(self, local_file: Path, remote_key: str) -> dict:
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            return await self._sync_file_local(local_file, remote_key)
        s3 = boto3.client("s3", endpoint_url=CLOUD_S3_ENDPOINT,
                          aws_access_key_id=CLOUD_S3_ACCESS_KEY,
                          aws_secret_access_key=CLOUD_S3_SECRET_KEY,
                          region_name=CLOUD_S3_REGION or None,
                          config=BotoConfig(signature_version="s3v4"))
        s3.upload_file(str(local_file), CLOUD_S3_BUCKET, remote_key)
        return {"status": "success", "method": "s3", "remote_key": remote_key}

    async def _sync_file_smb(self, local_file: Path, remote_key: str) -> dict:
        dest = Path(CLOUD_SMB_SERVER) / remote_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_file, dest)
        return {"status": "success", "method": "smb", "remote_key": remote_key}

    def get_cloud_url(self, project_id: UUID, project_name: str, year: int, relative_path: str) -> str | None:
        """获取云端文件的访问 URL（供其他用户直接打开原始文档）"""
        remote_prefix = f"{year}/{project_name}_{str(project_id)[:8]}"
        remote_key = f"{remote_prefix}/{relative_path}"

        if CLOUD_STORAGE_TYPE == "s3":
            return f"{CLOUD_S3_ENDPOINT}/{CLOUD_S3_BUCKET}/{remote_key}"
        elif CLOUD_STORAGE_TYPE == "smb":
            return f"{CLOUD_SMB_SERVER}/{remote_key}"
        elif CLOUD_STORAGE_TYPE == "sftp":
            return f"sftp://{CLOUD_SFTP_HOST}{CLOUD_SFTP_BASE_PATH}/{remote_key}"
        else:
            return f"file:///{CLOUD_LOCAL_PATH}/{remote_key}"

    async def upload_archive_package(
        self,
        project_id: UUID,
        project_name: str,
        year: int,
        package_path: Path,
    ) -> dict[str, Any]:
        """上传归档包（spec attachment-archive-and-a-class-evidence ADR-AE-05）：任何失败都抛错。

        目录：``{base}/{year}/{项目名}_{project_id[:8]}/archive/{包文件名}``（与上传双写同一前缀）。
        配置了 sftp / s3 却没装对应库 ⇒ 直接报错（``_sync_file_*`` 缺库时会退回本地复制，归档不接受这种假成功）。
        """
        if not package_path.is_file():
            raise FileNotFoundError(f"归档包文件不存在：{package_path.name}")
        safe_project = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in (project_name or "unknown")).strip()
        remote_key = f"{year}/{safe_project or 'unknown'}_{str(project_id)[:8]}/archive/{package_path.name}"
        required = {"sftp": "paramiko", "s3": "boto3"}.get(CLOUD_STORAGE_TYPE)
        if required:
            import importlib.util

            if importlib.util.find_spec(required) is None:
                raise RuntimeError(f"云端存储类型为 {CLOUD_STORAGE_TYPE}，但服务器未安装 {required}，无法推送归档包")
        if CLOUD_STORAGE_TYPE == "sftp":
            result = await self._sync_file_sftp(package_path, remote_key)
        elif CLOUD_STORAGE_TYPE == "s3":
            result = await self._sync_file_s3(package_path, remote_key)
        elif CLOUD_STORAGE_TYPE == "smb":
            result = await self._sync_file_smb(package_path, remote_key)
        else:
            result = await self._sync_file_local(package_path, remote_key)
        if (result or {}).get("status") != "success":
            raise RuntimeError(f"归档包上传失败：{(result or {}).get('error') or result}")
        logger.info("archive_package_pushed: project=%s key=%s method=%s",
                    project_id, remote_key, result.get("method"))
        return {**result, "uploaded_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def _sftp_makedirs(sftp, remote_dir: str):
        """递归创建 SFTP 远程目录"""
        dirs = remote_dir.split("/")
        current = ""
        for d in dirs:
            if not d:
                current = "/"
                continue
            current = f"{current}/{d}" if current != "/" else f"/{d}"
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)
