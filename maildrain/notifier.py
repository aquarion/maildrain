import json
import logging
import urllib.request
from typing import Protocol

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, message: str) -> None: ...


class NullNotifier:
    def send(self, message: str) -> None:
        pass


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send(self, message: str) -> None:
        payload = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            self._webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.warning("Slack notification failed: %s", e)


def build_notifier(webhook_url: str | None) -> Notifier:
    if webhook_url:
        return SlackNotifier(webhook_url)
    return NullNotifier()
