"""Shared cleaning for third-party text before it reaches a renderer or a prompt.

Everything a source module returns — titles, companies, locations, descriptions,
URLs — is attacker-controllable in principle. These helpers live in one module so
the same rule applies everywhere the data surfaces; a copy per call site drifts.
"""

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x20]")
_HTTP_SCHEME = re.compile(r"(?i)^https?://")


def safe_url(raw: str) -> str:
    """Return the URL if it is an http(s) link, otherwise '#'.

    Escaping is not enough on its own: a "javascript:..." URL contains no
    HTML-escapable characters, so it survives html.escape() intact and executes
    against whatever origin rendered it. Scheme allowlisting is the control that
    actually stops it.
    """
    candidate = _CONTROL_CHARS.sub("", str(raw or ""))
    return candidate if _HTTP_SCHEME.match(candidate) else "#"
