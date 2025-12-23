"""
Universal proxy parser supporting multiple formats.

Supported formats:
1. http://login:password@ip:port
2. socks5://login:password@ip:port
3. ip:port:login:password
4. ip:port@login:password
5. login:password@ip:port
6. ip:port (no auth)

Examples:
    >>> from bot.utils.proxy_parser import parse_proxy
    >>> proxy = parse_proxy("http://user:pass@192.168.1.1:8080")
    >>> proxy.ip
    '192.168.1.1'
    >>> proxy.to_standard_format()
    '192.168.1.1:8080:user:pass'
"""

import re
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class ProxyProtocol(str, Enum):
    """Proxy protocol types"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    UNKNOWN = "unknown"


@dataclass
class ParsedProxy:
    """
    Structured representation of parsed proxy.

    Attributes:
        ip: IP address
        port: Port number
        username: Optional username for authentication
        password: Optional password for authentication
        protocol: Proxy protocol (http/socks5)
        original: Original proxy string
    """
    ip: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    original: str = ""

    @property
    def has_auth(self) -> bool:
        """Check if proxy has authentication"""
        return bool(self.username and self.password)

    @property
    def host_port(self) -> str:
        """Get IP:PORT string"""
        return f"{self.ip}:{self.port}"

    @property
    def auth_string(self) -> str:
        """Get username:password string or empty"""
        if self.has_auth:
            return f"{self.username}:{self.password}"
        return ""

    def to_standard_format(self) -> str:
        """
        Convert to standard format: ip:port:user:pass
        This is the format stored in Google Sheets.
        """
        if self.has_auth:
            return f"{self.ip}:{self.port}:{self.username}:{self.password}"
        return f"{self.ip}:{self.port}"

    def to_url_format(self, protocol: Optional[ProxyProtocol] = None) -> str:
        """
        Convert to URL format: protocol://[user:pass@]ip:port

        Args:
            protocol: Override protocol (default: use detected protocol)
        """
        proto = protocol or self.protocol

        if self.has_auth:
            return f"{proto.value}://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{proto.value}://{self.ip}:{self.port}"

    def to_at_format(self) -> str:
        """Convert to @ format: ip:port@user:pass"""
        if self.has_auth:
            return f"{self.ip}:{self.port}@{self.username}:{self.password}"
        return f"{self.ip}:{self.port}"

    def to_user_at_host_format(self) -> str:
        """Convert to user@host format: user:pass@ip:port"""
        if self.has_auth:
            return f"{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{self.ip}:{self.port}"


class ProxyParser:
    """Universal proxy parser supporting multiple formats"""

    # Regex patterns for different formats
    # Format 1a: protocol://user:pass@ip:port (standard URL format)
    PATTERN_URL_USER_AT_HOST = re.compile(
        r'^(?P<protocol>https?|socks5?)://'
        r'(?P<username>[^:@]+):(?P<password>[^@]+)@'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    # Format 1b: protocol://ip:port@user:pass (alternative URL format)
    # Example: socks5://185.78.79.140:64139@69uH6AKw:px4dCDvn
    PATTERN_URL_HOST_AT_USER = re.compile(
        r'^(?P<protocol>https?|socks5?)://'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})@'
        r'(?P<username>[^:@]+):(?P<password>.+)$'
    )

    # Format 1c: protocol://ip:port (no auth)
    PATTERN_URL_NO_AUTH = re.compile(
        r'^(?P<protocol>https?|socks5?)://'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    # Format 2: user:pass@ip:port
    PATTERN_USER_AT_HOST = re.compile(
        r'^(?P<username>[^:@]+):(?P<password>[^@]+)@'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    # Format 3: ip:port@user:pass
    PATTERN_HOST_AT_USER = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})@'
        r'(?P<username>[^:@]+):(?P<password>.+)$'
    )

    # Format 4: ip:port:user:pass (current format)
    PATTERN_COLON_AUTH = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})'
        r':(?P<username>[^:]+)'
        r':(?P<password>.+)$'
    )

    # Format 5: ip:port (no auth)
    PATTERN_NO_AUTH = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    @classmethod
    def parse(cls, proxy_string: str) -> Optional[ParsedProxy]:
        """
        Parse proxy string in any supported format.

        Args:
            proxy_string: Proxy string to parse

        Returns:
            ParsedProxy object or None if parsing failed

        Examples:
            >>> parser = ProxyParser()
            >>> proxy = parser.parse("http://user:pass@192.168.1.1:8080")
            >>> proxy.ip
            '192.168.1.1'
            >>> proxy.username
            'user'
        """
        if not proxy_string:
            return None

        proxy_string = proxy_string.strip()

        # Try URL formats first (most specific - have protocol prefix)
        # 1a: protocol://user:pass@ip:port
        match = cls.PATTERN_URL_USER_AT_HOST.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # 1b: protocol://ip:port@user:pass (e.g., socks5://185.78.79.140:64139@69uH6AKw:px4dCDvn)
        match = cls.PATTERN_URL_HOST_AT_USER.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # 1c: protocol://ip:port (no auth)
        match = cls.PATTERN_URL_NO_AUTH.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try user:pass@ip:port (without protocol)
        match = cls.PATTERN_USER_AT_HOST.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port@user:pass (without protocol)
        match = cls.PATTERN_HOST_AT_USER.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port:user:pass (current format)
        match = cls.PATTERN_COLON_AUTH.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port (no auth)
        match = cls.PATTERN_NO_AUTH.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        return None

    @classmethod
    def _create_from_match(cls, match: re.Match, original: str) -> Optional[ParsedProxy]:
        """Create ParsedProxy from regex match"""
        data = match.groupdict()

        # Validate port
        port = int(data['port'])
        if not (1 <= port <= 65535):
            return None

        # Validate IP (basic check)
        ip_parts = data['ip'].split('.')
        if any(int(part) > 255 for part in ip_parts):
            return None

        # Detect protocol
        protocol = ProxyProtocol.HTTP
        if 'protocol' in data and data['protocol']:
            proto_str = data['protocol'].lower()
            if 'socks' in proto_str:
                protocol = ProxyProtocol.SOCKS5
            elif proto_str == 'https':
                protocol = ProxyProtocol.HTTPS

        return ParsedProxy(
            ip=data['ip'],
            port=port,
            username=data.get('username'),
            password=data.get('password'),
            protocol=protocol,
            original=original
        )

    @classmethod
    def parse_list(cls, proxy_strings: list[str]) -> tuple[list[ParsedProxy], list[str]]:
        """
        Parse list of proxy strings.

        Args:
            proxy_strings: List of proxy strings

        Returns:
            Tuple of (successfully_parsed, failed_strings)
        """
        parsed = []
        failed = []

        for proxy_str in proxy_strings:
            proxy_str = proxy_str.strip()
            if not proxy_str:
                continue

            result = cls.parse(proxy_str)
            if result:
                parsed.append(result)
            else:
                failed.append(proxy_str)

        return parsed, failed

    @classmethod
    def normalize(cls, proxy_string: str, output_format: str = 'standard') -> Optional[str]:
        """
        Normalize proxy string to specified format.

        Args:
            proxy_string: Input proxy string
            output_format: Output format ('standard', 'url', 'at', 'user_at_host')

        Returns:
            Normalized proxy string or None if parsing failed
        """
        parsed = cls.parse(proxy_string)
        if not parsed:
            return None

        if output_format == 'standard':
            return parsed.to_standard_format()
        elif output_format == 'url':
            return parsed.to_url_format()
        elif output_format == 'at':
            return parsed.to_at_format()
        elif output_format == 'user_at_host':
            return parsed.to_user_at_host_format()

        return None


# Convenience functions
def parse_proxy(proxy_string: str) -> Optional[ParsedProxy]:
    """Convenience function to parse single proxy"""
    return ProxyParser.parse(proxy_string)


def parse_proxies(proxy_strings: list[str]) -> tuple[list[ParsedProxy], list[str]]:
    """Convenience function to parse multiple proxies"""
    return ProxyParser.parse_list(proxy_strings)


def normalize_proxy(proxy_string: str, output_format: str = 'standard') -> Optional[str]:
    """Convenience function to normalize proxy format"""
    return ProxyParser.normalize(proxy_string, output_format)
