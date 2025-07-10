import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models.applications_model import (
    NotificationConfig,
    EmailNotification,
    WebhookNotification,
)
from loguru import logger


class NotificationManager:
    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send_notification(self, subject: str, message: str):
        """
        Sends a notification based on the configured methods.
        """
        if self.config.email.enabled:
            await self.send_email(subject, message)
        if self.config.webhook.enabled:
            await self.send_webhook(subject, message)
        if self.config.wechat.enabled:
            await self.send_wechat(subject, message)

    async def send_email(self, subject: str, message: str):
        """
        Sends an email notification.
        """
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
            logger.error(
                "Email notification is enabled, but configuration is incomplete."
            )
            return

        msg = MIMEMultipart()
        msg["From"] = email_config.fromAddress
        msg["To"] = ", ".join([email_config.fromAddress])  # Sending to self for now
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        try:
            server = smtplib.SMTP_SSL(email_config.smtpServer, email_config.port)
            server.login(email_config.username, email_config.password)
            server.send_message(msg)
            server.quit()
            logger.info(f"Email notification sent to {email_config.fromAddress}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def send_webhook(self, subject: str, message: str):
        """
        Sends a webhook notification.
        """
        webhook_config = self.config.webhook
        if not webhook_config.url:
            logger.error("Webhook notification is enabled, but URL is not configured.")
            return

        # Replace placeholders in the template
        payload_str = webhook_config.template.replace("{{subject}}", subject).replace(
            "{{message}}", message
        )
        try:
            payload = httpx.post(
                webhook_config.url,
                content=payload_str,
                headers={"Content-Type": "application/json"},
            ).json()
        except Exception as e:
            logger.error(f"Failed to decode webhook template JSON: {e}")
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

    async def send_wechat(self, subject: str, message: str):
        """
        Sends a WeChat notification. (Not implemented yet)
        """
        logger.info(
            "WeChat notification is enabled, but the feature is not yet implemented."
        )
        # Placeholder for future implementation
        pass
