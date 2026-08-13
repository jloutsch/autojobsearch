"""Shared cleaning for third-party text before it reaches a renderer or a prompt.

Everything a source module returns — titles, companies, locations, descriptions,
URLs — is attacker-controllable in principle. These helpers live in one module so
the same rule applies everywhere the data surfaces; a copy per call site drifts.
"""

import re
from urllib.parse import quote_plus

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


def company_search_url(name: str) -> str:
    """Build a web-search URL for a company name.

    No job source supplies an employer's website, so the company name is the only
    thing available to link on. The name is percent-encoded into a fixed origin:
    encoding is what stops a name containing a quote from terminating the href it
    is placed into, which HTML-escaping alone cannot do once the attribute
    boundary is already broken.

    Returns "" for an empty name so callers can render plain text — do not pass
    that through safe_url(), which turns "" into "#".
    """
    cleaned = str(name or "").strip()
    if not cleaned:
        return ""
    return "https://www.google.com/search?q=" + quote_plus(cleaned)
