"""Slack integration: notifications (Web API) + button clicks over Socket Mode (no public URL needed).

If tokens are missing, NullNotifier is used and approval happens in the dashboard/API instead.
Slack being down never blocks the incident workflow — failures are logged and skipped.
"""
import logging
from typing import Callable

from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from app.services.slack_messages import ACTION_IDS, finished_text, pending_blocks

logger = logging.getLogger("opsmind.slack")

DecideFn = Callable[[str, str, str], None]  # (incident_id, decision, operator)


class NullNotifier:
    is_enabled = False

    def incident_pending(self, incident: dict) -> None:
        logger.info("slack disabled; approve in dashboard", extra={"event": "slack_skipped", "incident_id": incident["id"]})

    def incident_finished(self, incident: dict) -> None:
        pass


class SlackNotifier:
    is_enabled = True

    def __init__(self, client: WebClient, channel: str, dashboard_url: str) -> None:
        self._client, self._channel, self._dashboard_url = client, channel, dashboard_url
        self._threads: dict[str, str] = {}  # incident_id → message ts

    def _safely(self, action: str, fn: Callable[[], dict]) -> dict | None:
        try:
            return fn()
        except (SlackApiError, OSError) as exc:
            logger.warning("slack call failed", extra={"event": "slack_error", "action": action, "error": str(exc)})
            return None

    def incident_pending(self, incident: dict) -> None:
        blocks = pending_blocks(incident, self._dashboard_url)
        text = f"🚨 {incident['id']} needs a decision"
        response = self._safely("post", lambda: self._client.chat_postMessage(channel=self._channel, text=text, blocks=blocks))
        if response:
            self._threads[incident["id"]] = response["ts"]

    def incident_finished(self, incident: dict) -> None:
        ts = self._threads.get(incident["id"])
        self._safely("reply", lambda: self._client.chat_postMessage(
            channel=self._channel, text=finished_text(incident), thread_ts=ts, reply_broadcast=bool(ts)))

    def acknowledge(self, incident_id: str, text: str) -> None:
        ts = self._threads.get(incident_id)
        self._safely("ack", lambda: self._client.chat_postMessage(channel=self._channel, text=text, thread_ts=ts))


def handle_interaction(payload: dict, decide: DecideFn, notify: Callable[[str, str], None]) -> None:
    for action in payload.get("actions", []):
        decision = ACTION_IDS.get(action.get("action_id"))
        if decision is None:
            continue  # e.g. the Edit button is a plain link to the dashboard
        user = payload.get("user", {})
        operator = user.get("username") or user.get("name") or user.get("id", "slack-user")
        incident_id = action["value"]
        try:
            decide(incident_id, decision, operator)
            notify(incident_id, f"👤 {operator} chose *{decision}* for {incident_id}.")
        except Exception as exc:  # noqa: BLE001 — report back to the channel rather than crash the socket
            notify(incident_id, f"⚠️ Could not apply {decision} to {incident_id}: {exc}")


def start_socket_mode(app_token: str, client: WebClient, decide: DecideFn, notifier: SlackNotifier) -> SocketModeClient:
    socket = SocketModeClient(app_token=app_token, web_client=client)

    def listener(sock: SocketModeClient, request: SocketModeRequest) -> None:
        sock.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
        if request.type == "interactive":
            handle_interaction(request.payload, decide, notifier.acknowledge)

    socket.socket_mode_request_listeners.append(listener)
    socket.connect()
    logger.info("slack socket mode connected", extra={"event": "slack_connected"})
    return socket
