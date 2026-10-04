import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_HTML_BYTES = 192 * 1024
MAX_REDIRECTS = 3


def normalized_url(value: str, *, require_https: bool = False) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        if require_https and parsed.scheme != 'https':
            return None
        if parsed.port not in (None, 80, 443):
            return None
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:
                return None
        except ValueError:
            pass
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))
    except ValueError:
        return None


async def require_public_host(url: str):
    parsed = urlsplit(url)
    try:
        records = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        addresses = {record[4][0] for record in records}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError
    except (OSError, ValueError):
        raise ValueError('unavailable preview host') from None


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == 'meta':
            key = (attributes.get('property') or attributes.get('name') or '').lower()
            if key in ('og:title', 'twitter:title', 'og:description', 'twitter:description', 'description', 'og:image', 'twitter:image') and key not in self.meta:
                self.meta[key] = attributes.get('content', '')
        elif tag.lower() == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)


def compact(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    result = ' '.join(value.split())[:limit]
    return result or None


def parse_preview(html: bytes, final_url: str) -> dict[str, str | None]:
    parser = MetadataParser()
    parser.feed(html.decode('utf-8', errors='replace'))
    title = compact(parser.meta.get('og:title') or parser.meta.get('twitter:title') or ''.join(parser.title_parts), 180)
    description = compact(parser.meta.get('og:description') or parser.meta.get('twitter:description') or parser.meta.get('description'), 360)
    raw_image = parser.meta.get('og:image') or parser.meta.get('twitter:image')
    image = normalized_url(urljoin(final_url, raw_image), require_https=True) if raw_image else None
    return {'url': final_url, 'title': title, 'description': description, 'image': image}


class LinkPreviewer:
    """Fetches one small public HTML response for display only; never writes files or caches."""

    async def get(self, raw_url: str) -> dict[str, str | None] | None:
        current = normalized_url(raw_url)
        if not current:
            return None
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False, headers={'User-Agent': 'TelegramReader/1.0 preview', 'Accept': 'text/html,application/xhtml+xml'}) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    await require_public_host(current)
                    async with client.stream('GET', current) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get('location')
                            current = normalized_url(urljoin(current, location or '')) if location else None
                            if not current:
                                return None
                            continue
                        if response.status_code != 200 or 'html' not in response.headers.get('content-type', '').lower():
                            return None
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > MAX_HTML_BYTES:
                                return None
                        preview = parse_preview(bytes(chunks), str(response.url))
                        if not preview['title'] and not preview['description'] and not preview['image']:
                            return None
                        return preview
        except (httpx.HTTPError, ValueError, UnicodeError):
            return None
        return None
