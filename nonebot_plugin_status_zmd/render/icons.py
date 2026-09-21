"""内联 SVG 图标。

原版用内联 SVG 图标 + 深色方块承载，跨平台拿不到真实程序图标，所以按进程名
关键字映射到一组通用图标。
"""

from __future__ import annotations

import re

ICONS: dict[str, str] = {
    "default": '<rect x="4" y="4" width="16" height="16" rx="2"/>',
    "logo": '<path d="M4 4h16v10l-6 6H4V4Z"/><path d="M8 9h8M8 13h4"/>',
    "browser": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<path d="M3 9h18M6.5 6.5h.01"/>'
    ),
    "editor": '<path d="M9 7 4 12l5 5"/><path d="m15 7 5 5-5 5"/>',
    "code": (
        '<path d="M9 4c-2 0-2 2-2 4s-1 4-3 4c2 0 3 2 3 4s0 4 2 4"/>'
        '<path d="M15 4c2 0 2 2 2 4s1 4 3 4c-2 0-3 2-3 4s0 4-2 4"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="6" rx="8" ry="3"/>'
        '<path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/>'
        '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'
    ),
    "game": (
        '<path d="M6 7h12a4 4 0 0 1 4 4v4a4 4 0 0 1-7 2.6h-6A4 4 0 0 1 2 15v-4a4 4 0 0 1 4-4Z"/>'
        '<path d="M7 12h4M9 10v4M15 11h.01M18 13h.01"/>'
    ),
    "terminal": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<path d="m7 10 2.5 2.5L7 15"/><path d="M12.5 15H17"/>'
    ),
    "chat": '<path d="M4 5h16v11H9l-5 4V5Z"/>',
    "media": '<path d="M9 7.5v9l8-4.5-8-4.5Z"/>',
    "runtime": (
        '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/>'
        '<path d="M12 3v18M4 7.5l8 4.5 8-4.5"/>'
    ),
    "system": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>'
    ),
    "cpu": (
        '<rect x="7" y="7" width="10" height="10" rx="1"/>'
        '<path d="M4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3"/>'
    ),
    "memory": (
        '<rect x="3" y="8" width="18" height="8" rx="1"/>'
        '<path d="M7 12v2M11 12v2M15 12v2"/>'
    ),
    "disk": (
        '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/>'
        '<path d="M12 4v5.5"/>'
    ),
    "network": (
        '<circle cx="12" cy="5" r="2"/><circle cx="5" cy="18" r="2"/>'
        '<circle cx="19" cy="18" r="2"/><path d="M12 7v4M12 11 6 16M12 11l6 5"/>'
    ),
    "bot": (
        '<rect x="5" y="8" width="14" height="11" rx="2"/>'
        '<path d="M12 4v4M8.5 13h.01M15.5 13h.01M9.5 16.5h5"/>'
    ),
    "server": (
        '<rect x="3" y="4" width="18" height="6" rx="1"/>'
        '<rect x="3" y="14" width="18" height="6" rx="1"/>'
        '<path d="M7 7h.01M7 17h.01"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    "link": (
        '<path d="M9 15l6-6"/>'
        '<path d="M10.5 6.5 12 5a4 4 0 0 1 5.7 5.7l-1.5 1.5"/>'
        '<path d="M13.5 17.5 12 19a4 4 0 0 1-5.7-5.7l1.5-1.5"/>'
    ),
    "globals": (
        '<circle cx="12" cy="12" r="8"/><path d="M4 12h16"/>'
        '<path d="M12 4c2.4 2.4 3.6 5.1 3.6 8S14.4 17.6 12 20c-2.4-2.4-3.6-5.1-3.6-8S9.6 6.4 12 4Z"/>'
    ),
    "timer": ('<circle cx="12" cy="13" r="7"/><path d="M12 10v3l2 2M9 3h6"/>'),
}

#: 进程名关键字 -> 图标（顺序即优先级）
ICON_RULES: tuple[tuple[str, str], ...] = (
    (r"chrome|chromium|msedge|firefox|brave|opera|vivaldi|safari", "browser"),
    (r"code|idea|pycharm|webstorm|vim|emacs|sublime|notepad|zed|devenv", "editor"),
    (r"mysql|mariadb|postgres|redis|mongo|sqlite|clickhouse|etcd", "database"),
    (r"steam|epic|genshin|yuanshen|league|riot|game|battle", "game"),
    (r"bash|zsh|fish|sh$|pwsh|powershell|cmd|conhost|terminal|wt$|tmux", "terminal"),
    (r"qq|wechat|weixin|telegram|discord|slack|dingtalk|wxwork|feishu", "chat"),
    (r"python|pdm|uv$|pip|conda|jupyter", "runtime"),
    (
        r"node|npm|pnpm|yarn|bun|deno|java|dotnet|golang|go$|cargo|rustc|php|ruby",
        "code",
    ),
    (r"ffmpeg|vlc|mpv|spotify|music|player|obs", "media"),
    (
        r"nginx|httpd|apache|caddy|sshd|systemd|init$|kthread|containerd|dockerd",
        "server",
    ),
    (r"explorer|finder|dwm|lssrv|gnome|kde|xfce", "system"),
)


def proc_icon_key(name: str) -> str:
    """按进程名猜一个图标 key。"""
    lowered = name.lower()
    for pattern, key in ICON_RULES:
        if re.search(pattern, lowered):
            return key
    return "default"


def icon_svg(key: str, size: int = 20, *, stroke: float = 2.0) -> str:
    """渲染一个内联 SVG 图标（颜色跟随 currentColor）。

    类名用 ``svg-ic``，``ic`` 留给承载图标的深色圆圈（``.col-head .ic``）。
    """
    body = ICONS.get(key, ICONS["default"])
    return (
        f'<svg class="svg-ic" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="{stroke:g}" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{body}</svg>"
    )
