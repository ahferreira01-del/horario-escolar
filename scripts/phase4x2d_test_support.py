"""Helpers for isolated Phase 4X.2-D browser tests."""
import json
import os
import re
import shlex
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen


def assert_local_candidate_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return
    explicitly_allowed = os.environ.get("HI_BROWSER_LOCAL_TEST_HOST", "").lower()
    if not host.endswith(".invalid") or host != explicitly_allowed:
        raise RuntimeError("E2E só pode usar localhost ou o host .invalid explicitamente autorizado.")


def browser_launch_options() -> dict:
    options = {"headless": True}
    executable = os.environ.get("HI_CHROMIUM_EXECUTABLE")
    if executable:
        options["executable_path"] = executable
    args = shlex.split(os.environ.get("HI_CHROMIUM_ARGS", ""))
    if args:
        options["args"] = args
    return options


def invitation_url(page, recipient: str, base_url: str) -> str:
    """Read the real invitation from a loopback SMTP sink, or dev-only UI link."""
    sink_url = os.environ.get("HI_SMTP_SINK_HTTP_URL", "").strip()
    if sink_url:
        sink = urlsplit(sink_url)
        if sink.scheme != "http" or sink.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("A API do SMTP sink deve estar em loopback HTTP.")
        deadline = time.monotonic() + 25
        pattern = re.compile(r"https?://[A-Za-z0-9.-]+(?::[0-9]+)?/convite\?[^\s<>\"']+")
        observed_recipients = set()
        observed_to_headers = set()
        observed_links = set()
        while time.monotonic() < deadline:
            query = urlencode({"recipient": recipient})
            with urlopen(f"{sink_url}?{query}", timeout=3) as response:
                messages = json.loads(response.read().decode("utf-8")).get("messages", [])
            for message in reversed(messages):
                recipients = [str(value).lower() for value in message.get("recipients", [])]
                observed_recipients.update(recipients)
                observed_to_headers.update(
                    str(value).lower() for value in message.get("to", [])
                )
                if recipient.lower() not in recipients:
                    continue
                body = str(message.get("body") or message.get("text") or "")
                for candidate in re.findall(r"https?://[^\s<>\"']+", body):
                    parsed_candidate = urlsplit(candidate.rstrip(".,;"))
                    query_candidate = parse_qs(parsed_candidate.query)
                    observed_links.add(
                        f"{parsed_candidate.scheme}://{parsed_candidate.netloc}{parsed_candidate.path}"
                        f"; query_keys={sorted(query_candidate)}, "
                        f"token_count={len(query_candidate.get('token', []))}"
                    )
                match = pattern.search(body)
                if match:
                    link = match.group(0).rstrip(".,;")
                    actual, expected = urlsplit(link), urlsplit(base_url)
                    tokens = parse_qs(actual.query).get("token", [])
                    if len(tokens) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", tokens[0]):
                        continue
                    if (actual.scheme, actual.hostname, actual.port) != (
                        expected.scheme, expected.hostname, expected.port
                    ):
                        raise AssertionError("Convite recebido pelo SMTP sink aponta para outra origem.")
                    return link
            time.sleep(0.2)
        raise AssertionError(
            f"SMTP sink não recebeu convite para {recipient}; "
            f"RCPT observados={sorted(observed_recipients)}, "
            f"cabeçalhos To observados={sorted(observed_to_headers)}, "
            f"links observados (sem tokens)={sorted(observed_links)}."
        )

    link = page.locator(".code-link a").get_attribute("href")
    if not link:
        raise AssertionError("A UI não apresentou link de desenvolvimento e nenhum SMTP sink foi configurado.")
    actual, expected = urlsplit(link), urlsplit(base_url)
    if (actual.scheme, actual.hostname, actual.port) != (
        expected.scheme, expected.hostname, expected.port
    ):
        raise AssertionError("Link de desenvolvimento aponta para uma origem diferente da candidata.")
    return link
