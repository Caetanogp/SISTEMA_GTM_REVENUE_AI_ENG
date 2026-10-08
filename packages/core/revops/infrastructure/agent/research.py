"""Bounded, allowlisted public-page research for SPEC-010."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from revops.application.ports import (
    CompanyResearcher,
    ExternalResearchError,
    ResearchPage,
    TrustedRunContext,
)
from revops.domain.entities.account import Account

MAX_PAGES = 3
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TEXT_CHARACTERS = 12_000
MAX_ATTEMPTS = 2


class ResearchPolicyError(ExternalResearchError):
    """A sanitized refusal to access an unauthorized or unsafe source."""

    def __init__(self, message: str) -> None:
        super().__init__("research_policy_refused")
        self.message = message


class ResearchFetchError(ExternalResearchError):
    """A sanitized bounded transport or response failure."""

    def __init__(self, message: str) -> None:
        super().__init__("research_source_unavailable", retryable=True)
        self.message = message


@dataclass(frozen=True, slots=True)
class AuthorizedCompanyPage:
    host: str
    path_prefix: str
    url: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or parsed.port not in (None, 443):
            raise ResearchPolicyError("research source must use HTTPS on port 443")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ResearchPolicyError("research source cannot contain credentials or query data")
        if parsed.hostname != self.host.casefold():
            raise ResearchPolicyError("research source host does not match authorization")
        if not self.path_prefix.startswith("/"):
            raise ResearchPolicyError("research source path prefix must start with '/'")
        if not parsed.path.startswith(self.path_prefix):
            raise ResearchPolicyError("research source path is outside the authorized prefix")


@dataclass(frozen=True, slots=True)
class ResearchSourcePolicy:
    """Deployment-owned source allowlist; an account domain never creates permission."""

    pages: tuple[AuthorizedCompanyPage, ...] = ()

    def pages_for(self, account: Account) -> tuple[AuthorizedCompanyPage, ...]:
        host = str(account.domain).casefold()
        return tuple(page for page in self.pages if page.host.casefold() == host)[:MAX_PAGES]


class AddressResolver(Protocol):
    def __call__(self, host: str, port: int) -> Sequence[str]: ...


def resolve_global_addresses(host: str, port: int) -> tuple[str, ...]:
    """Resolve and retain only globally routable addresses for one connection attempt."""
    addresses: list[str] = []
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        candidate = str(sockaddr[0])
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError as exc:
            raise ResearchPolicyError("research DNS returned an invalid address") from exc
        if not parsed.is_global or parsed.is_private or parsed.is_loopback or parsed.is_link_local:
            raise ResearchPolicyError("research destination is not globally routable")
        if family in (socket.AF_INET, socket.AF_INET6) and candidate not in addresses:
            addresses.append(candidate)
    if not addresses:
        raise ResearchPolicyError("research host has no globally routable address")
    return tuple(addresses)


class PageFetcher(Protocol):
    async def fetch(self, page: AuthorizedCompanyPage) -> ResearchPage: ...


class HttpxPageFetcher:
    """Fetch one authorized page while pinning the validated connection address."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolve: AddressResolver = resolve_global_addresses,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._resolve = resolve
        self._now = now

    async def fetch(self, page: AuthorizedCompanyPage) -> ResearchPage:
        parsed = urlsplit(page.url)
        host = parsed.hostname
        if host is None:
            raise ResearchPolicyError("research source has no host")
        addresses = self._resolve(host, 443)
        address = addresses[0]
        literal_host = f"[{address}]" if ":" in address else address
        target = f"https://{literal_host}{parsed.path or '/'}"
        headers = {"Host": host}
        extensions = {"sni_hostname": host}
        owned = self._client is None
        client = self._client or httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(8.0),
        )
        try:
            async with client.stream(
                "GET", target, headers=headers, extensions=extensions
            ) as response:
                if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                    raise ResearchPolicyError("research redirects are disabled")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ResearchFetchError("research source temporarily unavailable")
                if response.status_code >= 400:
                    raise ResearchFetchError("research source refused the request")
                media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if media_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                    raise ResearchPolicyError(
                        "research source returned an unsupported content type"
                    )
                body = await _read_bounded(response)
        except httpx.TimeoutException as exc:
            raise ResearchFetchError("research source timed out") from exc
        except httpx.RequestError as exc:
            raise ResearchFetchError("research source request failed") from exc
        finally:
            if owned:
                await client.aclose()
        content_hash = sha256(body).hexdigest()
        text = _extract_text(body, media_type)
        if not text:
            raise ResearchFetchError("research source contained no usable text")
        return ResearchPage(
            source_id=f"{host}{parsed.path or '/'}",
            url=page.url,
            retrieved_at=self._now(),
            content_hash=content_hash,
            text=text,
        )


@dataclass(frozen=True, slots=True)
class BoundedCompanyResearcher(CompanyResearcher):
    policy: ResearchSourcePolicy
    fetcher: PageFetcher

    async def research(
        self, *, context: TrustedRunContext, account: Account, objective: str
    ) -> Sequence[ResearchPage]:
        del context, objective
        pages = self.policy.pages_for(account)
        if not pages:
            raise ResearchPolicyError("no authorized research page is configured")
        results: list[ResearchPage] = []
        for page in pages:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    results.append(await self.fetcher.fetch(page))
                    break
                except ResearchFetchError:
                    if attempt + 1 == MAX_ATTEMPTS:
                        raise
        return tuple(results)


async def _read_bounded(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ResearchPolicyError("research response exceeds the size limit")
        chunks.append(chunk)
    return b"".join(chunks)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _extract_text(body: bytes, media_type: str) -> str:
    decoded = body.decode("utf-8", errors="replace")
    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = _TextExtractor()
        parser.feed(decoded)
        decoded = " ".join(parser.parts)
    return " ".join(decoded.split())[:MAX_TEXT_CHARACTERS]
