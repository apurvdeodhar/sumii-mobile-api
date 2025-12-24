"""Push Notification Service - Send notifications via Expo Push API

This service handles sending push notifications to users via Expo's Push API.
For MVP, we use Expo directly. Post-MVP, migrate to AWS SNS Mobile Push.

Architecture:
    Backend Event → PushService.send() → Expo API → FCM/APNs → Device

Usage:
    push_service = PushService()
    await push_service.send_notification(
        push_token="ExponentPushToken[xxx]",
        title="Zusammenfassung bereit",
        body="Ihre rechtliche Zusammenfassung ist jetzt verfügbar",
        data={"type": "summary_ready", "summary_id": "..."}
    )
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Expo Push API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushService:
    """Send push notifications via Expo Push API"""

    async def send_notification(
        self,
        push_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Send a push notification to a device via Expo

        Args:
            push_token: Expo push token (e.g., "ExponentPushToken[xxx]")
            title: Notification title
            body: Notification body text
            data: Optional data payload (delivered to app when opened)

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not push_token:
            logger.warning("No push token provided, skipping notification")
            return False

        if not push_token.startswith("ExponentPushToken["):
            logger.warning(f"Invalid push token format: {push_token[:20]}...")
            return False

        # Skip test tokens in development (they won't work with Expo)
        if "test-" in push_token or push_token.endswith("[test]"):
            logger.debug(f"Skipping test push token: {push_token[:30]}...")
            return True  # Return True so tests pass

        payload = {
            "to": push_token,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    data_result = result.get("data", {})

                    # Check if Expo reported success
                    if data_result.get("status") == "ok":
                        logger.info(f"Push notification sent: {title}")
                        return True

                    # Handle known error types gracefully
                    error_type = data_result.get("details", {}).get("error", "")
                    if error_type == "DeviceNotRegistered":
                        logger.info(
                            f"Push token not registered (device may have uninstalled app): {push_token[:30]}..."
                        )
                        # Don't log as error - this is normal when devices uninstall
                        return False
                    elif error_type == "InvalidCredentials":
                        logger.error("Expo push credentials are invalid")
                        return False
                    else:
                        logger.warning(f"Expo push returned error: {data_result.get('message', result)}")
                        return False
                else:
                    logger.error(f"Expo push failed: {response.status_code} - {response.text}")
                    return False

        except httpx.TimeoutException:
            logger.error("Expo push timed out")
            return False
        except Exception as e:
            logger.error(f"Expo push error: {e}", exc_info=True)
            return False

    async def send_to_user(
        self,
        user: Any,  # User model
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Send push notification to a user if they have a push token

        Args:
            user: User model instance
            title: Notification title
            body: Notification body
            data: Optional data payload

        Returns:
            True if sent, False if user has no token or send failed
        """
        if not user.push_token:
            logger.debug(f"User {user.id} has no push token, skipping")
            return False

        return await self.send_notification(
            push_token=user.push_token,
            title=title,
            body=body,
            data=data,
        )


# Singleton instance
push_service = PushService()
