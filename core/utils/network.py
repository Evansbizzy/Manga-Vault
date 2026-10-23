import ipaddress
import hashlib
import socket
from urllib.parse import urljoin, urlsplit

import requests
from django.core.cache import cache


def validate_public_http_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Only public HTTP(S) URLs are allowed')
    if parsed.username or parsed.password:
        raise ValueError('URLs with embedded credentials are not allowed')

    hostname = parsed.hostname.rstrip('.').lower()
    if hostname == 'localhost' or hostname.endswith('.localhost') or hostname.endswith('.local'):
        raise ValueError('Private network hosts are not allowed')

    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    cache_key = 'public-host-check:' + hashlib.sha256(f'{hostname}:{port}'.encode()).hexdigest()
    if cache.get(cache_key):
        return

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(hostname, port)
            }
        except (OSError, ValueError) as exc:
            raise ValueError('Could not resolve public host') from exc

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError('Private or non-public network hosts are not allowed')
    cache.set(cache_key, True, 60)


def safe_get(session, url, *, allow_redirects=True, max_redirects=5, **kwargs):
    current_url = url
    for redirect_count in range(max_redirects + 1):
        validate_public_http_url(current_url)
        response = session.get(current_url, allow_redirects=False, **kwargs)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response

        location = response.headers.get('Location')
        if not allow_redirects or not location:
            return response
        if redirect_count == max_redirects:
            response.close()
            raise requests.TooManyRedirects('Too many redirects')

        next_url = urljoin(current_url, location)
        response.close()
        current_url = next_url

    raise requests.TooManyRedirects('Too many redirects')
