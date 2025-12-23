"""
Comprehensive tests for universal proxy parser.

Run with: pytest tests/test_proxy_parser.py -v
"""

import pytest
from bot.utils.proxy_parser import (
    ProxyParser,
    ParsedProxy,
    ProxyProtocol,
    parse_proxy,
    parse_proxies,
    normalize_proxy,
)


class TestProxyParser:
    """Tests for ProxyParser class"""

    # ===== Positive test cases =====

    def test_parse_url_format_with_http_auth(self):
        """Test parsing http://user:pass@ip:port"""
        proxy = parse_proxy("http://user123:pass456@192.168.1.1:8080")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username == "user123"
        assert proxy.password == "pass456"
        assert proxy.protocol == ProxyProtocol.HTTP
        assert proxy.has_auth is True

    def test_parse_url_format_with_socks5_auth(self):
        """Test parsing socks5://user:pass@ip:port"""
        proxy = parse_proxy("socks5://admin:secret@10.0.0.1:1080")

        assert proxy is not None
        assert proxy.ip == "10.0.0.1"
        assert proxy.port == 1080
        assert proxy.username == "admin"
        assert proxy.password == "secret"
        assert proxy.protocol == ProxyProtocol.SOCKS5
        assert proxy.has_auth is True

    def test_parse_url_format_without_auth(self):
        """Test parsing http://ip:port"""
        proxy = parse_proxy("http://192.168.1.1:8080")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username is None
        assert proxy.password is None
        assert proxy.protocol == ProxyProtocol.HTTP
        assert proxy.has_auth is False

    def test_parse_user_at_host_format(self):
        """Test parsing user:pass@ip:port"""
        proxy = parse_proxy("user:pass@192.168.1.1:8080")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username == "user"
        assert proxy.password == "pass"
        assert proxy.has_auth is True

    def test_parse_host_at_user_format(self):
        """Test parsing ip:port@user:pass"""
        proxy = parse_proxy("192.168.1.1:8080@user:pass")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username == "user"
        assert proxy.password == "pass"
        assert proxy.has_auth is True

    def test_parse_colon_auth_format(self):
        """Test parsing ip:port:user:pass (current format)"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username == "user"
        assert proxy.password == "pass"
        assert proxy.has_auth is True

    def test_parse_no_auth_format(self):
        """Test parsing ip:port"""
        proxy = parse_proxy("192.168.1.1:8080")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080
        assert proxy.username is None
        assert proxy.password is None
        assert proxy.has_auth is False

    def test_parse_with_complex_password(self):
        """Test parsing proxy with special characters in password"""
        proxy = parse_proxy("http://user:p@ss!w0rd#123@192.168.1.1:8080")

        assert proxy is not None
        assert proxy.username == "user"
        assert proxy.password == "p@ss!w0rd#123"

    def test_parse_with_whitespace(self):
        """Test parsing proxy with leading/trailing whitespace"""
        proxy = parse_proxy("  192.168.1.1:8080:user:pass  ")

        assert proxy is not None
        assert proxy.ip == "192.168.1.1"
        assert proxy.port == 8080

    # ===== Edge cases =====

    def test_parse_edge_port_1(self):
        """Test parsing with minimum valid port (1)"""
        proxy = parse_proxy("192.168.1.1:1")

        assert proxy is not None
        assert proxy.port == 1

    def test_parse_edge_port_65535(self):
        """Test parsing with maximum valid port (65535)"""
        proxy = parse_proxy("192.168.1.1:65535")

        assert proxy is not None
        assert proxy.port == 65535

    def test_parse_edge_ip_0_0_0_0(self):
        """Test parsing with 0.0.0.0"""
        proxy = parse_proxy("0.0.0.0:8080")

        assert proxy is not None
        assert proxy.ip == "0.0.0.0"

    def test_parse_edge_ip_255_255_255_255(self):
        """Test parsing with 255.255.255.255"""
        proxy = parse_proxy("255.255.255.255:8080")

        assert proxy is not None
        assert proxy.ip == "255.255.255.255"

    # ===== Negative test cases =====

    def test_parse_empty_string(self):
        """Test parsing empty string"""
        proxy = parse_proxy("")
        assert proxy is None

    def test_parse_none(self):
        """Test parsing None"""
        proxy = parse_proxy(None)
        assert proxy is None

    def test_parse_whitespace_only(self):
        """Test parsing whitespace only"""
        proxy = parse_proxy("   ")
        assert proxy is None

    def test_parse_invalid_ip(self):
        """Test parsing with invalid IP"""
        proxy = parse_proxy("999.999.999.999:8080")
        assert proxy is None

    def test_parse_invalid_port_0(self):
        """Test parsing with port 0"""
        proxy = parse_proxy("192.168.1.1:0")
        assert proxy is None

    def test_parse_invalid_port_too_large(self):
        """Test parsing with port > 65535"""
        proxy = parse_proxy("192.168.1.1:99999")
        assert proxy is None

    def test_parse_no_port(self):
        """Test parsing IP without port"""
        proxy = parse_proxy("192.168.1.1")
        assert proxy is None

    def test_parse_invalid_format(self):
        """Test parsing completely invalid format"""
        proxy = parse_proxy("not-a-proxy")
        assert proxy is None

    def test_parse_hostname_instead_of_ip(self):
        """Test parsing hostname (not supported)"""
        proxy = parse_proxy("proxy.example.com:8080")
        assert proxy is None

    # ===== ParsedProxy methods =====

    def test_to_standard_format_with_auth(self):
        """Test conversion to standard format with auth"""
        proxy = parse_proxy("http://user:pass@192.168.1.1:8080")
        standard = proxy.to_standard_format()

        assert standard == "192.168.1.1:8080:user:pass"

    def test_to_standard_format_without_auth(self):
        """Test conversion to standard format without auth"""
        proxy = parse_proxy("192.168.1.1:8080")
        standard = proxy.to_standard_format()

        assert standard == "192.168.1.1:8080"

    def test_to_url_format_with_auth(self):
        """Test conversion to URL format with auth"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")
        url = proxy.to_url_format()

        assert url == "http://user:pass@192.168.1.1:8080"

    def test_to_url_format_with_socks5(self):
        """Test conversion to URL format with SOCKS5"""
        proxy = parse_proxy("socks5://user:pass@192.168.1.1:1080")
        url = proxy.to_url_format()

        assert url == "socks5://user:pass@192.168.1.1:1080"

    def test_to_url_format_override_protocol(self):
        """Test conversion to URL format with protocol override"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")
        url = proxy.to_url_format(ProxyProtocol.SOCKS5)

        assert url == "socks5://user:pass@192.168.1.1:8080"

    def test_to_at_format(self):
        """Test conversion to @ format"""
        proxy = parse_proxy("http://user:pass@192.168.1.1:8080")
        at_format = proxy.to_at_format()

        assert at_format == "192.168.1.1:8080@user:pass"

    def test_to_user_at_host_format(self):
        """Test conversion to user@host format"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")
        user_at_host = proxy.to_user_at_host_format()

        assert user_at_host == "user:pass@192.168.1.1:8080"

    def test_host_port_property(self):
        """Test host_port property"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")

        assert proxy.host_port == "192.168.1.1:8080"

    def test_auth_string_property_with_auth(self):
        """Test auth_string property with auth"""
        proxy = parse_proxy("192.168.1.1:8080:user:pass")

        assert proxy.auth_string == "user:pass"

    def test_auth_string_property_without_auth(self):
        """Test auth_string property without auth"""
        proxy = parse_proxy("192.168.1.1:8080")

        assert proxy.auth_string == ""

    # ===== Batch parsing =====

    def test_parse_list_all_valid(self):
        """Test parsing list of all valid proxies"""
        proxies = [
            "http://user:pass@192.168.1.1:8080",
            "socks5://admin:secret@10.0.0.1:1080",
            "192.168.1.2:3128",
        ]

        parsed, failed = parse_proxies(proxies)

        assert len(parsed) == 3
        assert len(failed) == 0

    def test_parse_list_mixed(self):
        """Test parsing list with both valid and invalid proxies"""
        proxies = [
            "http://user:pass@192.168.1.1:8080",
            "invalid-proxy",
            "192.168.1.2:3128",
            "999.999.999.999:8080",
        ]

        parsed, failed = parse_proxies(proxies)

        assert len(parsed) == 2
        assert len(failed) == 2
        assert "invalid-proxy" in failed
        assert "999.999.999.999:8080" in failed

    def test_parse_list_empty(self):
        """Test parsing empty list"""
        parsed, failed = parse_proxies([])

        assert len(parsed) == 0
        assert len(failed) == 0

    def test_parse_list_with_empty_strings(self):
        """Test parsing list with empty strings"""
        proxies = [
            "192.168.1.1:8080",
            "",
            "   ",
            "192.168.1.2:3128",
        ]

        parsed, failed = parse_proxies(proxies)

        assert len(parsed) == 2
        assert len(failed) == 0  # Empty strings are skipped

    # ===== Normalize function =====

    def test_normalize_to_standard(self):
        """Test normalize to standard format"""
        result = normalize_proxy("http://user:pass@192.168.1.1:8080", "standard")

        assert result == "192.168.1.1:8080:user:pass"

    def test_normalize_to_url(self):
        """Test normalize to URL format"""
        result = normalize_proxy("192.168.1.1:8080:user:pass", "url")

        assert result == "http://user:pass@192.168.1.1:8080"

    def test_normalize_to_at(self):
        """Test normalize to @ format"""
        result = normalize_proxy("user:pass@192.168.1.1:8080", "at")

        assert result == "192.168.1.1:8080@user:pass"

    def test_normalize_invalid_proxy(self):
        """Test normalize with invalid proxy"""
        result = normalize_proxy("invalid-proxy", "standard")

        assert result is None

    # ===== Real-world examples =====

    def test_real_world_examples(self):
        """Test parsing real-world proxy examples"""
        examples = [
            ("http://user123:pass456@192.168.1.1:8080", "192.168.1.1", 8080, "user123", "pass456"),
            ("socks5://admin:secret@10.0.0.1:1080", "10.0.0.1", 1080, "admin", "secret"),
            ("192.168.1.1:8080:user:pass", "192.168.1.1", 8080, "user", "pass"),
            ("192.168.1.1:8080@user:pass", "192.168.1.1", 8080, "user", "pass"),
            ("user:pass@192.168.1.1:8080", "192.168.1.1", 8080, "user", "pass"),
            ("192.168.1.1:8080", "192.168.1.1", 8080, None, None),
        ]

        for proxy_str, expected_ip, expected_port, expected_user, expected_pass in examples:
            proxy = parse_proxy(proxy_str)

            assert proxy is not None, f"Failed to parse: {proxy_str}"
            assert proxy.ip == expected_ip
            assert proxy.port == expected_port
            assert proxy.username == expected_user
            assert proxy.password == expected_pass

    def test_round_trip_conversion(self):
        """Test round-trip conversion: parse -> normalize -> parse"""
        original = "http://user:pass@192.168.1.1:8080"

        # Parse original
        proxy1 = parse_proxy(original)

        # Convert to standard format
        standard = proxy1.to_standard_format()

        # Parse standard format
        proxy2 = parse_proxy(standard)

        # Should have same data
        assert proxy1.ip == proxy2.ip
        assert proxy1.port == proxy2.port
        assert proxy1.username == proxy2.username
        assert proxy1.password == proxy2.password

    def test_format_conversion_chain(self):
        """Test conversion between all formats"""
        original = "192.168.1.1:8080:user:pass"

        proxy = parse_proxy(original)

        # Convert to all formats
        standard = proxy.to_standard_format()
        url = proxy.to_url_format()
        at_format = proxy.to_at_format()
        user_at_host = proxy.to_user_at_host_format()

        # Parse all formats back
        proxy_standard = parse_proxy(standard)
        proxy_url = parse_proxy(url)
        proxy_at = parse_proxy(at_format)
        proxy_user_at_host = parse_proxy(user_at_host)

        # All should have same data
        proxies = [proxy_standard, proxy_url, proxy_at, proxy_user_at_host]
        for p in proxies:
            assert p.ip == "192.168.1.1"
            assert p.port == 8080
            assert p.username == "user"
            assert p.password == "pass"


class TestProxyParserIntegration:
    """Integration tests for proxy parser"""

    def test_batch_processing_performance(self):
        """Test batch processing of many proxies"""
        # Generate 100 proxies
        proxies = [f"192.168.1.{i}:8080:user{i}:pass{i}" for i in range(1, 101)]

        parsed, failed = parse_proxies(proxies)

        assert len(parsed) == 100
        assert len(failed) == 0

    def test_mixed_formats_batch(self):
        """Test batch processing with mixed formats"""
        proxies = [
            "http://user1:pass1@192.168.1.1:8080",
            "socks5://user2:pass2@192.168.1.2:1080",
            "user3:pass3@192.168.1.3:3128",
            "192.168.1.4:8080@user4:pass4",
            "192.168.1.5:8080:user5:pass5",
            "192.168.1.6:8080",
        ]

        parsed, failed = parse_proxies(proxies)

        assert len(parsed) == 6
        assert len(failed) == 0

        # Check protocols were detected correctly
        assert parsed[0].protocol == ProxyProtocol.HTTP
        assert parsed[1].protocol == ProxyProtocol.SOCKS5

    def test_normalization_consistency(self):
        """Test that normalization is consistent across formats"""
        formats = [
            "http://user:pass@192.168.1.1:8080",
            "user:pass@192.168.1.1:8080",
            "192.168.1.1:8080@user:pass",
            "192.168.1.1:8080:user:pass",
        ]

        # All should normalize to same standard format
        normalized = [normalize_proxy(fmt, "standard") for fmt in formats]

        assert all(n == "192.168.1.1:8080:user:pass" for n in normalized)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
