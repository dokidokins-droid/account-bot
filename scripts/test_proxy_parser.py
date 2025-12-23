"""
Simple test script for proxy parser without pytest dependency.

Run: python scripts/test_proxy_parser.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bot.utils.proxy_parser import parse_proxy, parse_proxies, normalize_proxy, ProxyProtocol


def test_all_formats():
    """Test parsing all supported formats"""
    print("=" * 60)
    print("Testing all supported proxy formats")
    print("=" * 60)

    test_cases = [
        ("http://user:pass@192.168.1.1:8080", "URL with HTTP auth"),
        ("socks5://admin:secret@10.0.0.1:1080", "URL with SOCKS5 auth"),
        ("user:pass@192.168.1.1:8080", "user:pass@ip:port"),
        ("192.168.1.1:8080@user:pass", "ip:port@user:pass"),
        ("192.168.1.1:8080:user:pass", "ip:port:user:pass (current)"),
        ("192.168.1.1:8080", "ip:port (no auth)"),
        ("http://192.168.1.1:8080", "URL without auth"),
    ]

    success = 0
    failed = 0

    for proxy_str, description in test_cases:
        proxy = parse_proxy(proxy_str)

        if proxy:
            print(f"\n[OK] {description}")
            print(f"  Input:    {proxy_str}")
            print(f"  IP:       {proxy.ip}")
            print(f"  Port:     {proxy.port}")
            print(f"  Username: {proxy.username or 'N/A'}")
            print(f"  Password: {proxy.password or 'N/A'}")
            print(f"  Protocol: {proxy.protocol.value}")
            success += 1
        else:
            print(f"\n[FAIL] {description}")
            print(f"  Input: {proxy_str}")
            print(f"  ERROR: Failed to parse")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {success} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


def test_format_conversions():
    """Test format conversions"""
    print("\n" + "=" * 60)
    print("Testing format conversions")
    print("=" * 60)

    original = "192.168.1.1:8080:user:pass"
    proxy = parse_proxy(original)

    if not proxy:
        print("[FAIL] Failed to parse original format")
        return False

    conversions = [
        ("Standard", proxy.to_standard_format(), "192.168.1.1:8080:user:pass"),
        ("URL", proxy.to_url_format(), "http://user:pass@192.168.1.1:8080"),
        ("@ format", proxy.to_at_format(), "192.168.1.1:8080@user:pass"),
        ("user@host", proxy.to_user_at_host_format(), "user:pass@192.168.1.1:8080"),
    ]

    all_ok = True
    for name, result, expected in conversions:
        if result == expected:
            print(f"[OK] {name:15} {result}")
        else:
            print(f"[FAIL] {name:15} Expected: {expected}, Got: {result}")
            all_ok = False

    return all_ok


def test_batch_parsing():
    """Test batch parsing"""
    print("\n" + "=" * 60)
    print("Testing batch parsing")
    print("=" * 60)

    proxies = [
        "http://user1:pass1@192.168.1.1:8080",
        "socks5://user2:pass2@10.0.0.1:1080",
        "invalid-proxy",
        "192.168.1.2:3128",
        "999.999.999.999:8080",  # Invalid IP
        "user3:pass3@192.168.1.3:8080",
    ]

    parsed, failed = parse_proxies(proxies)

    print(f"\nTotal input:  {len(proxies)}")
    print(f"Parsed:       {len(parsed)}")
    print(f"Failed:       {len(failed)}")

    print("\nParsed proxies:")
    for p in parsed:
        print(f"  - {p.ip}:{p.port} (auth: {p.has_auth})")

    print("\nFailed proxies:")
    for f in failed:
        print(f"  - {f}")

    expected_parsed = 4
    expected_failed = 2

    if len(parsed) == expected_parsed and len(failed) == expected_failed:
        print(f"\n[OK] Batch parsing OK")
        return True
    else:
        print(f"\n[FAIL] Batch parsing FAILED")
        print(f"  Expected: {expected_parsed} parsed, {expected_failed} failed")
        print(f"  Got:      {len(parsed)} parsed, {len(failed)} failed")
        return False


def test_invalid_formats():
    """Test invalid formats return None"""
    print("\n" + "=" * 60)
    print("Testing invalid formats (should fail)")
    print("=" * 60)

    invalid_cases = [
        ("", "Empty string"),
        ("   ", "Whitespace only"),
        ("not-a-proxy", "Invalid format"),
        ("192.168.1.1", "Missing port"),
        ("192.168.1.1:99999", "Port too large"),
        ("999.999.999.999:8080", "Invalid IP"),
        ("proxy.example.com:8080", "Hostname (not supported)"),
    ]

    all_ok = True
    for proxy_str, description in invalid_cases:
        proxy = parse_proxy(proxy_str)

        if proxy is None:
            print(f"[OK] {description:30} -> None (as expected)")
        else:
            print(f"[FAIL] {description:30} -> Parsed (should be None!)")
            all_ok = False

    return all_ok


def test_edge_cases():
    """Test edge cases"""
    print("\n" + "=" * 60)
    print("Testing edge cases")
    print("=" * 60)

    edge_cases = [
        ("192.168.1.1:1", "Minimum port (1)"),
        ("192.168.1.1:65535", "Maximum port (65535)"),
        ("0.0.0.0:8080", "IP 0.0.0.0"),
        ("255.255.255.255:8080", "IP 255.255.255.255"),
        ("192.168.1.1:8080:user:p@ss!w0rd#123", "Special chars in password (colon format)"),
        ("  192.168.1.1:8080:user:pass  ", "Leading/trailing whitespace"),
    ]

    all_ok = True
    for proxy_str, description in edge_cases:
        proxy = parse_proxy(proxy_str)

        if proxy:
            print(f"[OK] {description:40} -> {proxy.ip}:{proxy.port}")
        else:
            print(f"[FAIL] {description:40} -> Failed to parse")
            all_ok = False

    return all_ok


def test_normalization():
    """Test normalization function"""
    print("\n" + "=" * 60)
    print("Testing normalization")
    print("=" * 60)

    tests = [
        ("http://user:pass@192.168.1.1:8080", "standard", "192.168.1.1:8080:user:pass"),
        ("192.168.1.1:8080:user:pass", "url", "http://user:pass@192.168.1.1:8080"),
        ("user:pass@192.168.1.1:8080", "at", "192.168.1.1:8080@user:pass"),
    ]

    all_ok = True
    for input_str, output_format, expected in tests:
        result = normalize_proxy(input_str, output_format)

        if result == expected:
            print(f"[OK] {output_format:10} {input_str[:30]:30} -> {result}")
        else:
            print(f"[FAIL] {output_format:10} Expected: {expected}, Got: {result}")
            all_ok = False

    return all_ok


def test_real_world_examples():
    """Test real-world proxy examples"""
    print("\n" + "=" * 60)
    print("Testing real-world examples")
    print("=" * 60)

    examples = [
        "http://user123:pass456@192.168.1.1:8080",
        "socks5://admin:secret@10.0.0.1:1080",
        "192.168.1.1:8080:user:pass",
        "192.168.1.1:8080@user:pass",
        "user:pass@192.168.1.1:8080",
        "192.168.1.1:8080",
    ]

    parsed, failed = parse_proxies(examples)

    print(f"\nParsed {len(parsed)}/{len(examples)} real-world examples")

    all_ok = len(parsed) == len(examples) and len(failed) == 0

    if all_ok:
        print("[OK] All real-world examples parsed successfully")
    else:
        print("[FAIL] Some real-world examples failed to parse")

    return all_ok


def main():
    """Run all tests"""
    print("\n")
    print("=" * 60)
    print(" " * 10 + "PROXY PARSER TEST SUITE")
    print("=" * 60)

    tests = [
        ("All Formats", test_all_formats),
        ("Format Conversions", test_format_conversions),
        ("Batch Parsing", test_batch_parsing),
        ("Invalid Formats", test_invalid_formats),
        ("Edge Cases", test_edge_cases),
        ("Normalization", test_normalization),
        ("Real-World Examples", test_real_world_examples),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[FAIL] {name} CRASHED: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[OK] PASSED" if result else "[FAIL] FAILED"
        print(f"{status:10} {name}")

    print("\n" + "=" * 60)
    print(f"Total: {passed}/{total} test suites passed")
    print("=" * 60)

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[FAILED] {total - passed} test suite(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
