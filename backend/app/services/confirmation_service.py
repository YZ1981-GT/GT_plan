from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attachment_models import Attachment
from app.models.collaboration_models import (
    ConfirmationList, ConfirmationLetter, ConfirmationResult,
    ConfirmationSummary,
    ConfirmationType, ConfirmationStatusEnum, LetterFormat, ReplyStatus,
)


class ConfirmationService:
    @staticmethod
    def create_confirmation(
        db: Session,
        project_id: str,
        confirmation_type: str,
        description: str,
        counterparty_name: str,
        account_info: Optional[str] = None,
        balance: Optional[float] = None,
        balance_date=None,
        created_by: str = None,
    ) -> ConfirmationList:
        ct = ConfirmationType[confirmation_type.upper()] if confirmation_type.upper() in [e.name for e in ConfirmationType] else ConfirmationType.other
        c = ConfirmationList(
            id=uuid.uuid4(),
            project_id=project_id,
            confirmation_type=ct,
            description=description,
            counterparty_name=counterparty_name,
            account_info=account_info,
            balance=balance,
            balance_date=balance_date,
            status=ConfirmationStatusEnum.pending,
            created_by=created_by,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    @staticmethod
    def generate_letter(
        db: Session,
        confirmation_id: str,
        letter_content: str,
        letter_format: str = "standard",
        generated_by: Optional[str] = None,
    ) -> ConfirmationLetter:
        fmt = LetterFormat[letter_format.upper()] if letter_format.upper() in [e.name for e in LetterFormat] else LetterFormat.standard
        letter = ConfirmationLetter(
            id=uuid.uuid4(),
            confirmation_list_id=confirmation_id,
            letter_content=letter_content,
            letter_format=fmt,
            generated_by=generated_by,
            generated_at=datetime.now(timezone.utc),
            is_sent=False,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(letter)
        db.commit()
        db.refresh(letter)
        return letter

    @staticmethod
    def record_result(
        db: Session,
        confirmation_id: str,
        reply_status: str,
        confirmed_amount: Optional[float] = None,
        difference_amount: Optional[float] = None,
        difference_reason: Optional[str] = None,
        alternative_procedure: Optional[str] = None,
        alternative_conclusion: Optional[str] = None,
    ) -> ConfirmationResult:
        rs = ReplyStatus[reply_status.upper()] if reply_status.upper() in [e.name for e in ReplyStatus] else ReplyStatus.no_reply
        result = ConfirmationResult(
            id=uuid.uuid4(),
            confirmation_list_id=confirmation_id,
            reply_status=rs,
            confirmed_amount=confirmed_amount,
            difference_amount=difference_amount,
            difference_reason=difference_reason,
            needs_adjustment=(confirmed_amount is not None and difference_amount is not None and difference_amount != 0),
            alternative_procedure=alternative_procedure,
            alternative_conclusion=alternative_conclusion,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    @staticmethod
    def get_confirmations(db: Session, project_id: str) -> List[ConfirmationList]:
        return db.query(ConfirmationList).filter(
            ConfirmationList.project_id == project_id,
            ConfirmationList.is_deleted == False,  # noqa: E712
        ).all()

    @staticmethod
    def create_summary(
        db: Session,
        project_id: str,
        summary_date,
        created_by: str = None,
    ) -> ConfirmationSummary:
        # Auto-calculate from existing confirmations
        all_c = ConfirmationService.get_confirmations(db, project_id)
        total = len(all_c)
        sent = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.sent)
        replied = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.replied)
        matched = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.confirmed)
        mismatched = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.mismatched)
        not_replied = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.pending)
        returned = sum(1 for c in all_c if c.status == ConfirmationStatusEnum.cancelled)

        summary = ConfirmationSummary(
            id=uuid.uuid4(),
            project_id=project_id,
            summary_date=summary_date,
            total_count=total,
            sent_count=sent,
            replied_count=replied,
            matched_count=matched,
            mismatched_count=mismatched,
            not_replied_count=not_replied,
            returned_count=returned,
            created_by=created_by,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(summary)
        db.commit()
        db.refresh(summary)
        return summary



    @staticmethod
    def auto_extract_candidates(db: Session, project_id: str) -> List[dict]:
        """从试算表自动提取函证候选（简化：返回提示信息）"""
        # 实际应从 trial_balance 表提取银行、应收、应付科目
        return [
            {
                "suggestion_type": "bank",
                "description": "建议向银行发送询证函",
                "note": "请在余额表中添加银行科目后，系统将自动提取",
            },
            {
                "suggestion_type": "account_receivable",
                "description": "建议向主要客户发送询证函",
                "note": "请在余额表中添加应收账款科目后，系统将自动提取",
            },
        ]

    @staticmethod
    def approve_list(
        db: Session,
        confirmation_list_id: str,
        approved_by: str,
    ) -> dict:
        """审核函证清单"""
        c = db.query(ConfirmationList).filter(
            ConfirmationList.id == confirmation_list_id,
            ConfirmationList.is_deleted == False,
        ).first()
        if not c:
            raise ValueError("函证清单不存在")

        c.status = ConfirmationStatusEnum.sent
        c.sent_date = datetime.now(timezone.utc).date()
        c.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(c)

        return {
            "id": str(c.id),
            "status": c.status.value if hasattr(c.status, 'value') else str(c.status),
            "approved_by": approved_by,
            "sent_date": c.sent_date,
        }

    @staticmethod
    def generate_letters(
        db: Session,
        confirmation_list_id: str,
        format: str = "standard",
        generated_by: Optional[str] = None,
    ) -> ConfirmationLetter:
        """批量生成询证函（单条）"""
        # 生成标准函证内容
        c = db.query(ConfirmationList).filter(
            ConfirmationList.id == confirmation_list_id,
            ConfirmationList.is_deleted == False,
        ).first()
        if not c:
            raise ValueError("函证清单不存在")

        letter_content = f"""
致 {c.counterparty_name}：

本公司聘请的审计机构正在对本公司财务报表进行审计，需要向贵公司询证本公司与贵公司的往来款项余额。

请贵公司核对后，将本函直接回复至审计机构。

询证金额：{c.balance or '详见函证'}
截止日期：{c.balance_date or 'N/A'}
        """.strip()

        return ConfirmationService.generate_letter(
            db, confirmation_list_id, letter_content, format, generated_by
        )

    @staticmethod
    def update_summary(
        db: Session,
        confirmation_list_id: str,
    ) -> dict:
        """更新函证统计表"""
        c = db.query(ConfirmationList).filter(
            ConfirmationList.id == confirmation_list_id,
            ConfirmationList.is_deleted == False,
        ).first()
        if not c:
            raise ValueError("函证清单不存在")

        # 获取结果
        result = db.query(ConfirmationResult).filter(
            ConfirmationResult.confirmation_list_id == confirmation_list_id,
            ConfirmationResult.is_deleted == False,
        ).first()

        return {
            "confirmation_id": str(confirmation_list_id),
            "status": c.status.value if hasattr(c.status, 'value') else str(c.status),
            "reply_status": result.reply_status.value if result and hasattr(result.reply_status, 'value') else None,
            "difference_amount": result.difference_amount if result else None,
            "needs_adjustment": result.needs_adjustment if result else False,
        }

    @staticmethod
    def check_overdue(db: Session, project_id: str) -> List[dict]:
        """检查超30天未回函"""
        overdue_confirmations = db.query(ConfirmationList).filter(
            ConfirmationList.project_id == project_id,
            ConfirmationList.status == ConfirmationStatusEnum.sent,
            ConfirmationList.is_deleted == False,
        ).all()

        overdue = []
        for c in overdue_confirmations:
            if c.sent_date:
                days_since_sent = (datetime.now(timezone.utc).date() - c.sent_date).days
                if days_since_sent > 30:
                    overdue.append({
                        "confirmation_id": str(c.id),
                        "counterparty_name": c.counterparty_name,
                        "sent_date": c.sent_date,
                        "days_overdue": days_since_sent - 30,
                    })
        return overdue

    @staticmethod
    def upload_attachment(
        db: Session,
        result_id: str,
        file_data: bytes,
        filename: str,
        uploaded_by: Optional[str] = None,
    ) -> dict:
        """上传回函附件"""
        confirmation = db.query(ConfirmationList).filter(
            ConfirmationList.id == result_id,
            ConfirmationList.is_deleted == False,
        ).first()
        if not confirmation:
            raise ValueError("函证清单不存在")

        safe_name = Path(filename).name or "attachment.bin"
        suffix = Path(safe_name).suffix or ".bin"
        file_type = suffix.lstrip(".") or "unknown"
        paperless_document_id = None
        storage_type = "local"
        file_path = ""
        ocr_status = "pending"
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_data)
                temp_path = tmp.name

            use_paperless = (
                settings.ATTACHMENT_PRIMARY_STORAGE.lower() == "paperless"
                and bool(settings.PAPERLESS_URL and settings.PAPERLESS_TOKEN)
            )
            if use_paperless:
                try:
                    import httpx

                    with httpx.Client(timeout=settings.PAPERLESS_TIMEOUT) as client:
                        with open(temp_path, "rb") as f:
                            resp = client.post(
                                f"{settings.PAPERLESS_URL}/api/documents/post_document/",
                                files={"document": (safe_name, f)},
                                data={"title": safe_name, "document_type": "confirmation"},
                                headers={"Authorization": f"Token {settings.PAPERLESS_TOKEN}"},
                            )
                            if resp.status_code in (200, 201):
                                paperless_document_id = resp.json().get("id")
                except Exception:
                    paperless_document_id = None

            if paperless_document_id is not None:
                storage_type = "paperless"
                file_path = f"paperless://documents/{paperless_document_id}"
                ocr_status = "processing"
            else:
                if use_paperless and not settings.ATTACHMENT_FALLBACK_TO_LOCAL:
                    raise RuntimeError("Paperless-ngx 上传失败，且未启用本地回退存储")

                target_dir = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(confirmation.project_id) / "confirmation"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / safe_name
                counter = 1
                while target_path.exists():
                    target_path = target_dir / f"{Path(safe_name).stem}_{counter}{suffix}"
                    counter += 1
                target_path.write_bytes(file_data)
                file_path = target_path.as_posix()

            attachment = Attachment(
                id=uuid.uuid4(),
                project_id=confirmation.project_id,
                file_name=safe_name,
                file_path=file_path,
                file_type=file_type,
                file_size=len(file_data),
                attachment_type="confirmation",
                reference_id=confirmation.id,
                reference_type="confirmation_list",
                storage_type=storage_type,
                paperless_document_id=paperless_document_id,
                ocr_status=ocr_status,
                created_by=uploaded_by,
            )
            db.add(attachment)
            db.commit()
            db.refresh(attachment)

            return {
                "id": str(attachment.id),
                "file_name": attachment.file_name,
                "file_path": attachment.file_path,
                "storage_type": attachment.storage_type,
                "paperless_document_id": attachment.paperless_document_id,
            }
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
