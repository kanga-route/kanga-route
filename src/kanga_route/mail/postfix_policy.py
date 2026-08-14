"""Fail-open Postfix access-policy service backed only by cached evidence."""

import logging
import os
import socketserver
from typing import Mapping

from kanga_route.application.mail_advisory import (
    AdviceAction,
    AdviceSource,
    MailAdvisoryService,
)
from kanga_route.cache.dynamodb import DynamoDBCacheStore
from kanga_route.models import VerificationStatus

logger = logging.getLogger(__name__)
VALID_MODES = {"observe", "enforce-cached-invalid"}


def parse_policy_request(lines: list[str]) -> dict[str, str]:
    """Parse one bounded Postfix key=value policy request."""
    attributes: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key:
            attributes[key] = value
    return attributes


def policy_action(
    advisory_service: MailAdvisoryService,
    attributes: Mapping[str, str],
    mode: str = "observe",
) -> str:
    """Return a Postfix action; every uncertainty resolves to DUNNO."""
    if mode not in VALID_MODES:
        raise ValueError(f"POSTFIX_POLICY_MODE must be one of {sorted(VALID_MODES)}")
    recipient = attributes.get("recipient", "")
    try:
        outcome = advisory_service.advise([recipient])
    except Exception:
        return "DUNNO"
    if not outcome.recipients:
        return "DUNNO"

    advice = outcome.recipients[0]
    cached_invalid = (
        advice.action == AdviceAction.WARN
        and advice.source == AdviceSource.CACHE
        and advice.result is not None
        and advice.result.status == VerificationStatus.INVALID
    )
    if mode == "enforce-cached-invalid" and cached_invalid:
        return "REJECT recipient failed a cached Kanga-Route verification"
    if cached_invalid:
        logger.warning("Cached-invalid recipient observed; message allowed")
    return "DUNNO"


class PostfixPolicyHandler(socketserver.StreamRequestHandler):
    """Serve repeated Postfix policy requests over one connection."""

    max_line_bytes = 4_096
    max_request_lines = 64

    def handle(self) -> None:
        while True:
            lines = []
            for _ in range(self.max_request_lines):
                raw = self.rfile.readline(self.max_line_bytes + 1)
                if not raw:
                    return
                if len(raw) > self.max_line_bytes:
                    self._respond("DUNNO")
                    return
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    break
                lines.append(line)
            else:
                self._respond("DUNNO")
                return

            try:
                attributes = parse_policy_request(lines)
                action = policy_action(
                    self.server.advisory_service,
                    attributes,
                    self.server.policy_mode,
                )
            except Exception:
                logger.exception("Policy request failed open")
                action = "DUNNO"
            self._respond(action)

    def _respond(self, action: str) -> None:
        self.wfile.write(f"action={action}\n\n".encode("utf-8"))
        self.wfile.flush()


class PostfixPolicyServer(socketserver.ThreadingTCPServer):
    """Threaded policy server carrying immutable service configuration."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, advisory_service, policy_mode):
        self.advisory_service = advisory_service
        self.policy_mode = policy_mode
        super().__init__(server_address, PostfixPolicyHandler)


def main() -> None:
    """Run the optional policy service; cache failures remain fail-open."""
    logging.basicConfig(
        level=os.getenv("POSTFIX_POLICY_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    host = os.getenv("POSTFIX_POLICY_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("POSTFIX_POLICY_PORT", "10040"))
    mode = os.getenv("POSTFIX_POLICY_MODE", "observe").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"POSTFIX_POLICY_MODE must be one of {sorted(VALID_MODES)}")

    advisory_service = MailAdvisoryService(DynamoDBCacheStore())
    with PostfixPolicyServer((host, port), advisory_service, mode) as server:
        logger.info("Postfix policy service listening on %s:%s (%s)", host, port, mode)
        server.serve_forever()


if __name__ == "__main__":
    main()
