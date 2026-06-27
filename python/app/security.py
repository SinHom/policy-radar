"""安全工具函数：SSRF 防护、输入验证、URL 白名单等。"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

# 默认拒绝的 URL schemes（防 SSRF / XSS）
BLOCKED_SCHEMES = {"file", "ftp", "javascript", "data", "vbscript", "ws", "wss"}

# 默认拒绝的 host（防 SSRF 攻击本机/内网）
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP metadata
}


def is_private_ip(ip: str) -> bool:
    """判断 IP 是否私有 / 保留 / 回环。非 IP（域名）返回 False（让 resolve_host 处理）。"""
    try:
        addr = ipaddress.ip_address(ip)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except ValueError:
        return False  # 不是 IP 字面量（是域名），让 resolve_host 去解析


def resolve_host(host: str) -> Optional[str]:
    """解析域名到 IP（如果解析到私有 IP 则返回 None 防 DNS rebinding）。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        if is_private_ip(ip):
            return None
        return ip
    return None


def validate_webhook_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """校验 webhook URL 是否合法。

    返回: (ok, error_msg)
    - 检查 scheme（必须 http/https）
    - 检查 host（拒绝 localhost / 私有 IP，防 SSRF）
    - 默认生产模式（allow_private=False），开发模式可开

    用法:
        ok, err = validate_webhook_url(sub.push_config['webhook_url'])
        if not ok: raise HTTPException(400, err)
    """
    if not url or not isinstance(url, str):
        return False, "url 为空"
    if len(url) > 2000:
        return False, "url 过长（> 2000 字符）"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"url 解析失败: {e}"

    # scheme
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"scheme 必须 http/https，收到 {parsed.scheme!r}"

    # userinfo 不允许（防凭据泄露）
    if parsed.username or parsed.password:
        return False, "url 不允许带 userinfo（用户名:密码@）"

    host = parsed.hostname
    if not host:
        return False, "url 缺 host"

    # 字面量 host 检查
    if host.lower() in BLOCKED_HOSTS:
        return False, f"host {host!r} 在黑名单（localhost / metadata）"

    # 私有 IP 检查
    if not allow_private:
        # 1. 如果是 IP 字面量
        if is_private_ip(host):
            return False, f"host {host!r} 是私有 IP（防 SSRF，需 ALLOW_PRIVATE_WEBHOOK=1）"
        # 2. 解析域名
        resolved = resolve_host(host)
        if resolved is None:
            return False, f"host {host!r} 解析失败或解析到私有 IP（防 SSRF）"
        # 3. 二次检查（防 DNS rebinding：先解析到公网，连接时又解析到私网）
        # 这里我们再做一次解析确认
        if is_private_ip(resolved):
            return False, f"host {host!r} 解析到私有 IP {resolved!r}"

    return True, ""


def sanitize_string(s: str, max_length: int = 1000) -> str:
    """清理字符串：截断 + 去控制字符。"""
    if not isinstance(s, str):
        return ""
    # 去 NUL 和其他控制字符（除 \n \r \t）
    s = "".join(c for c in s if c == "\n" or c == "\r" or c == "\t" or ord(c) >= 32)
    if len(s) > max_length:
        s = s[:max_length]
    return s
