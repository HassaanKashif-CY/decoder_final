import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class SlackSenderError(Exception):
    pass


def send_slack_message(text: str) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise SlackSenderError("SLACK_WEBHOOK_URL is not configured in Render.")

    parsed = urlparse(webhook_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"hooks.slack.com", "hooks.slack-gov.com"}
        or not parsed.path.startswith("/services/")
    ):
        raise SlackSenderError("SLACK_WEBHOOK_URL is not a valid Slack Incoming Webhook URL.")

    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            result = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or result.strip() != "ok":
                raise SlackSenderError(f"Slack rejected the message (HTTP {response.status}).")
    except HTTPError as exc:
        raise SlackSenderError(f"Slack returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise SlackSenderError("Could not connect to Slack. Check Render outbound connectivity.") from exc
    except TimeoutError as exc:
        raise SlackSenderError("Slack request timed out.") from exc
