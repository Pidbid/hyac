import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models.applications_model import (
    NotificationConfig,
)
from loguru import logger


class NotificationManager:
    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send_email(self, to_address: str, subject: str, body: str):
        """
        Sends a customized email notification.
        """
        if not self.config.email.enabled:
            logger.warning("Email notification is not enabled.")
            return

        email_config = self.config.email
        if not all(
            [
                email_config.smtpServer,
                email_config.port,
                email_config.username,
                email_config.password,
                email_config.fromAddress,
            ]
        ):
            logger.error("Email configuration is incomplete.")
            return

        msg = MIMEMultipart()
        msg["From"] = email_config.fromAddress
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP_SSL(email_config.smtpServer, email_config.port)
            server.login(email_config.username, email_config.password)
            server.send_message(msg)
            server.quit()
            logger.info(f"Email notification sent to {to_address}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def send_webhook(self, payload: dict):
        """
        Sends a webhook notification with a custom payload.
        """
        if not self.config.webhook.enabled:
            logger.warning("Webhook notification is not enabled.")
            return

        webhook_config = self.config.webhook
        if not webhook_config.url:
            logger.error("Webhook URL is not configured.")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=webhook_config.method, url=webhook_config.url, json=payload
                )
                response.raise_for_status()
                logger.info(f"Webhook notification sent to {webhook_config.url}")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to send webhook notification: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")

    async def send_wechat(self, payload: dict):
        """
        Sends a WeChat notification with a custom payload. (Not implemented yet)
        """
        if not self.config.wechat.enabled:
            logger.warning("WeChat notification is not enabled.")
            return

        logger.info(
            "WeChat notification is enabled, but the feature is not yet implemented."
        )
        # Placeholder for future implementation
        pass
