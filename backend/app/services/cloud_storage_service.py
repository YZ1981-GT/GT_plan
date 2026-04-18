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
from datetime import datetime
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

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))


class CloudStorageService:
    """云端存储服务"""

    async def upload_project_archive(
        self,
        project_id: UUID,
        project_name: str,
        year: int,
    ) -> dict[str, Any]:
        """将项目底稿归档推送到云端

        目录结构：{base}/{year}/{project_name}_{project_id[:8]}/
        """
        local_dir = STORAGE_ROOT / "projects" / str(project_id)
        if not local_dir.exists():
            raise ValueError(f"项目本地目录不存在: {local_dir}")

        # 统计本地文件
        files = list(local_dir.rglob("*"))
        file_list = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in file_list)

        remote_prefix = f"{year}/{project_name}_{str(project_id)[:8]}"

        logger.info(
            "cloud_upload: project=%s files=%d size=%.1fMB type=%s",
            project_id, len(file_list), total_size / 1024 / 1024, CLOUD_STORAGE_TYPE,
        )

        if CLOUD_STORAGE_TYPE == "sftp":
            result = await self._upload_sftp(local_dir, remote_prefix, file_list)
        elif CLOUD_STORAGE_TYPE == "s3":
            result = await self._upload_s3(local_dir, remote_prefix, file_list)
        elif CLOUD_STORAGE_TYPE == "smb":
            result = await self._upload_smb(local_dir, remote_prefix, file_list)
        else:
            result = await self._upload_local(local_dir, remote_prefix, file_list)

        result.update({
            "project_id": str(project_id),
            "remote_prefix": remote_prefix,
            "file_count": len(file_list),
            "total_size": total_size,
            "storage_type": CLOUD_STORAGE_TYPE,
            "uploaded_at": datetime.utcnow().isoformat(),
        })
        return result

    async def _upload_local(self, local_dir: Path, remote_prefix: str, files: list) -> dict:
        """本地目录复制（测试/开发用）"""
        dest = Path(CLOUD_LOCAL_PATH) / remote_prefix
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for f in files:
            rel = f.relative_to(local_dir)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied += 1
        return {"status": "success", "method": "local_copy", "copied": copied}

    async def _upload_sftp(self, local_dir: Path, remote_prefix: str, files: list) -> dict:
        """SFTP 上传到内部服务器"""
        try:
            import paramiko
        except ImportError:
            logger.warning("paramiko not installed, falling back to local copy")
            return await self._upload_local(local_dir, remote_prefix, files)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs: dict[str, Any] = {
                "hostname": CLOUD_SFTP_HOST,
                "port": CLOUD_SFTP_PORT,
                "username": CLOUD_SFTP_USER,
            }
            if CLOUD_SFTP_KEY_PATH:
                connect_kwargs["key_filename"] = CLOUD_SFTP_KEY_PATH
            elif CLOUD_SFTP_PASSWORD:
                connect_kwargs["password"] = CLOUD_SFTP_PASSWORD

            ssh.connect(**connect_kwargs)
            sftp = ssh.open_sftp()

            remote_base = f"{CLOUD_SFTP_BASE_PATH}/{remote_prefix}"
            uploaded = 0
            for f in files:
                rel = str(f.relative_to(local_dir)).replace("\\", "/")
                remote_path = f"{remote_base}/{rel}"
                # 创建远程目录
                remote_dir = "/".join(remote_path.split("/")[:-1])
                try:
                    sftp.stat(remote_dir)
                except FileNotFoundError:
                    self._sftp_makedirs(sftp, remote_dir)
                sftp.put(str(f), remote_path)
                uploaded += 1

            sftp.close()
            return {"status": "success", "method": "sftp", "uploaded": uploaded,
                    "host": CLOUD_SFTP_HOST}
        except Exception as e:
            logger.error("SFTP upload failed: %s", e)
            return {"status": "failed", "method": "sftp", "error": str(e)}
        finally:
            ssh.close()

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

    async def _upload_s3(self, local_dir: Path, remote_prefix: str, files: list) -> dict:
        """S3 兼容协议上传（MinIO / 阿里云 OSS）"""
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            logger.warning("boto3 not installed, falling back to local copy")
            return await self._upload_local(local_dir, remote_prefix, files)

        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=CLOUD_S3_ENDPOINT,
                aws_access_key_id=CLOUD_S3_ACCESS_KEY,
                aws_secret_access_key=CLOUD_S3_SECRET_KEY,
                region_name=CLOUD_S3_REGION or None,
                config=BotoConfig(signature_version="s3v4"),
            )
            uploaded = 0
            for f in files:
                rel = str(f.relative_to(local_dir)).replace("\\", "/")
                key = f"{remote_prefix}/{rel}"
                s3.upload_file(str(f), CLOUD_S3_BUCKET, key)
                uploaded += 1
            return {"status": "success", "method": "s3", "uploaded": uploaded,
                    "bucket": CLOUD_S3_BUCKET}
        except Exception as e:
            logger.error("S3 upload failed: %s", e)
            return {"status": "failed", "method": "s3", "error": str(e)}

    async def _upload_smb(self, local_dir: Path, remote_prefix: str, files: list) -> dict:
        """SMB/CIFS 共享文件夹复制"""
        dest = Path(CLOUD_SMB_SERVER) / remote_prefix
        try:
            dest.mkdir(parents=True, exist_ok=True)
            copied = 0
            for f in files:
                rel = f.relative_to(local_dir)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                copied += 1
            return {"status": "success", "method": "smb", "copied": copied}
        except Exception as e:
            logger.error("SMB copy failed: %s", e)
            return {"status": "failed", "method": "smb", "error": str(e)}

    async def cleanup_local_after_archive(
        self, project_id: UUID, keep_metadata: bool = True,
    ) -> dict:
        """归档推送成功后清理本地文件（可选）"""
        local_dir = STORAGE_ROOT / "projects" / str(project_id)
        if not local_dir.exists():
            return {"status": "skipped", "reason": "目录不存在"}

        if keep_metadata:
            # 只删除底稿文件，保留目录结构
            removed = 0
            for f in local_dir.rglob("*"):
                if f.is_file() and f.suffix in (".xlsx", ".xls", ".docx", ".doc", ".pdf"):
                    f.unlink()
                    removed += 1
            return {"status": "success", "removed_files": removed, "kept_metadata": True}
        else:
            shutil.rmtree(local_dir)
            return {"status": "success", "removed_dir": str(local_dir)}
