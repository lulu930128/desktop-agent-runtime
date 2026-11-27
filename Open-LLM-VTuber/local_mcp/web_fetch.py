"""Bounded public-web I/O for the existing kuro-web STDIO server only.

DNS is resolved at the network backend boundary. Only a validated numeric address
is passed to TCP; HTTP Host and TLS SNI/certificate checks retain the URL hostname.
No proxy, ambient authentication, cookies, retries, or hostname-connect fallback.
"""
from __future__ import annotations

import asyncio
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin

import certifi
import anyio
import httpcore
import httpx

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
MAX_CONCURRENT = 4
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


class FetchBlocked(ValueError):
    """Only fixed, non-sensitive reason codes may cross the tool boundary."""


def public_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        raise FetchBlocked("invalid_ip") from None
    # Explicit transition/special-use exclusions also cover Python 3.10's older
    # IANA classifications (notably 192.0.0/24 and IPv6 translation/tunnel ranges).
    special = ("192.0.0.0/24", "192.88.99.0/24") if ip.version == 4 else (
        "::/96", "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48",
        "100::/64", "2001::/23", "2002::/16", "3fff::/20", "5f00::/16",
    )
    if ("%" in value or not ip.is_global or ip.is_multicast or ip.is_reserved
            or any(ip in ipaddress.ip_network(net) for net in special)):
        raise FetchBlocked("non_public_ip")
    return ip.compressed


def validate_url(value: str) -> httpx.URL:
    if len(value) > 8192 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise FetchBlocked("invalid_url")
    try:
        url = httpx.URL(value)
        host = url.host.lower().rstrip(".")
        port = url.port
    except (ValueError, httpx.InvalidURL):
        raise FetchBlocked("invalid_url") from None
    if url.scheme not in {"http", "https"} or not host or url.userinfo:
        raise FetchBlocked("invalid_url_authority")
    if port not in (None, 80 if url.scheme == "http" else 443):
        raise FetchBlocked("non_standard_port")
    if (host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home", ".lan"))
            or "%" in host):
        raise FetchBlocked("private_hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or any(not part for part in host.split(".")):
            raise FetchBlocked("invalid_hostname") from None
    else:
        public_ip(host)
    return url.copy_with(fragment=None)


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if local_address is not None or socket_options:
            raise FetchBlocked("unsupported_connection_options")
        async def connect():
            try:
                ipaddress.ip_address(host)
            except ValueError:
                records = await asyncio.get_running_loop().getaddrinfo(
                    host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP,
                )
                if not records or len(records) > 32:
                    raise FetchBlocked("invalid_dns_answer")
                # Reject mixed public/private answers, not just the chosen address.
                addresses = [public_ip(row[4][0]) for row in records]
            else:
                addresses = [public_ip(host)]
            pinned = addresses[0]
            # AnyIO recognizes numeric literals and does not resolve the hostname
            # again. There is deliberately no retry against the original hostname.
            stream = await httpcore.AnyIOBackend().connect_tcp(pinned, port, timeout=timeout)
            try:
                peer = stream.get_extra_info("server_addr")
                if not peer or public_ip(peer[0]) != pinned or peer[1] != port:
                    raise FetchBlocked("peer_ip_mismatch")
            except BaseException:
                await stream.aclose()
                raise
            return stream
        with anyio.fail_after(min(timeout or 8.0, 8.0)):
            return await connect()

    async def connect_unix_socket(self, *args, **kwargs):
        raise FetchBlocked("unix_socket_blocked")


class WindowQuota:
    def __init__(self, limit: int, seconds: float = 60.0):
        self.limit, self.seconds = limit, seconds
        self.calls: deque[float] = deque()

    def take(self):
        now = time.monotonic()
        while self.calls and now - self.calls[0] >= self.seconds:
            self.calls.popleft()
        if len(self.calls) >= self.limit:
            raise FetchBlocked("request_quota_exhausted")
        self.calls.append(now)


@dataclass
class ResearchBudget:
    hops: int = 40
    fallback_queries: int = 2


budget: ContextVar[ResearchBudget | None] = ContextVar("web_budget", default=None)
_requests = WindowQuota(60)
_brave_requests = WindowQuota(2)
_slots = asyncio.Semaphore(MAX_CONCURRENT)


def bounded_research(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        token = budget.set(ResearchBudget())
        try:
            with anyio.fail_after(60.0):
                return await function(*args, **kwargs)
        except (TimeoutError, asyncio.TimeoutError):
            return "Research partial: operation_timeout; no completeness or freshness claim."
        finally:
            budget.reset(token)
    return wrapped


def safe_error(exc: Exception) -> str:
    if isinstance(exc, FetchBlocked):
        return str(exc)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpcore.TimeoutException)):
        return "fetch_timeout"
    return "fetch_unavailable"  # Never echo request URLs, headers, or provider errors.


@dataclass(frozen=True)
class FetchResponse:
    text: str
    final_url: str
    content_type: str


async def fetch_text(url: str, *, timeout: float = 20.0, params=None,
                     api_key: str | None = None) -> FetchResponse:
    async def run():
        current = validate_url(url)
        if params:
            current = current.copy_merge_params(params)
        validate_url(str(current))
        if api_key is not None and url != BRAVE_ENDPOINT:
            raise FetchBlocked("credential_target_blocked")
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity",
                   "Accept": "application/json" if api_key is not None else "text/html, application/xhtml+xml"}
        if api_key is not None:
            if not api_key or len(api_key) > 2048 or not api_key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in api_key):
                raise FetchBlocked("invalid_provider_configuration")
            headers["X-Subscription-Token"] = api_key
        seen: set[str] = set()
        async with _slots:
            for hop in range(MAX_REDIRECTS + 1):
                current = validate_url(str(current))
                if str(current) in seen:
                    raise FetchBlocked("redirect_loop")
                seen.add(str(current))
                active = budget.get()
                if active:
                    if active.hops <= 0:
                        raise FetchBlocked("operation_hop_quota_exhausted")
                    active.hops -= 1
                _requests.take()
                if api_key is not None:
                    _brave_requests.take()
                # Public httpcore API; no AsyncClient environment/proxy transport.
                # Explicit CA bundle also avoids SSL_CERT_FILE/DIR overrides.
                async with httpcore.AsyncConnectionPool(
                    ssl_context=ssl.create_default_context(cafile=certifi.where()),
                    network_backend=PublicNetworkBackend(), proxy=None,
                    max_connections=1, max_keepalive_connections=0, retries=0,
                ) as pool:
                    async with pool.stream("GET", str(current), headers=headers,
                                           extensions={"timeout": {key: 8.0 for key in ("connect", "read", "write", "pool")}}) as response:
                        fields = {}
                        for key, value in response.headers:
                            key = key.decode("ascii").lower()
                            if key in fields and key in {"content-type", "content-length", "content-encoding", "location"}:
                                raise FetchBlocked("ambiguous_response_headers")
                            fields[key] = value.decode("latin-1")
                        if response.status in {301, 302, 303, 307, 308}:
                            if api_key is not None:
                                raise FetchBlocked("provider_redirect_blocked")
                            if hop == MAX_REDIRECTS or not fields.get("location"):
                                raise FetchBlocked("redirect_limit")
                            target = validate_url(urljoin(str(current), fields["location"]))
                            if current.scheme == "https" and target.scheme != "https":
                                raise FetchBlocked("https_downgrade_blocked")
                            current = target
                            continue
                        if response.status != 200:
                            raise FetchBlocked("http_status_unavailable")
                        content_type = fields.get("content-type", "").split(";", 1)[0].strip().lower()
                        allowed = {"application/json"} if api_key is not None else HTML_TYPES
                        if content_type not in allowed:
                            raise FetchBlocked("unsupported_content_type")
                        if fields.get("content-encoding", "identity").strip().lower() != "identity":
                            raise FetchBlocked("compressed_content_blocked")
                        length = fields.get("content-length")
                        if length is not None and (not length.isdecimal() or int(length) > MAX_BYTES):
                            raise FetchBlocked("response_too_large")
                        body = bytearray()
                        async for chunk in response.aiter_stream():
                            if len(body) + len(chunk) > MAX_BYTES:
                                raise FetchBlocked("response_too_large")
                            body.extend(chunk)
                        # httpx decodes charset only; networking is exclusively above.
                        decoded = httpx.Response(200, content=bytes(body), headers={"content-type": fields["content-type"]}).text
                        return FetchResponse(decoded, str(current), content_type)
        raise FetchBlocked("redirect_limit")
    with anyio.fail_after(max(0.01, min(timeout, 20.0))):
        return await run()
