"""Cookie-less TeraBox resolver/download backend.

The bot does not keep a TeraBox account, cookie, or session.  It asks one or more
configured resolver APIs for a short-lived direct URL, then downloads that URL.
Resolvers are third-party services and may rate-limit or go offline, so more than
one endpoint can be configured through BIMBO_TERABOX_RESOLVERS.
"""
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, unquote

import requests

logger = logging.getLogger(__name__)

# Comma-separated resolver endpoints. Every endpoint must accept ?url=<share-url>
# and return JSON containing success plus filename/size and a direct URL or qualities.
DEFAULT_RESOLVERS = "https://terabox-api.mn-bots.workers.dev/download"

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "1024tera.com", "1024terabox.com",
    "terasharefile.com", "terashare.net", "terabox.app", "teraboxlink.com",
    "teraboxshare.com", "terafileshare.com", "mirrobox.com", "nephobox.com",
    "4funbox.com", "momerybox.com", "tibibox.com", "freeterabox.com",
    "terafile.co", "dubox.com", "terabox.hn", "terabox.club", "terabox.fun",
    "terabox.news", "terabox.site", "terabox.online", "terabox.space",
    "terabox.tech", "terabox.work", "terabox.world", "terabox.xyz",
]


def is_terabox(url: str) -> bool:
    """Return True only for a recognised TeraBox host (not a lookalike host)."""
    try:
        host = (urlparse(url).hostname or "").lower()
        return any(host == domain or host.endswith("." + domain) for domain in TERABOX_DOMAINS)
    except Exception:
        return False


def _resolvers():
    raw = os.getenv("BIMBO_TERABOX_RESOLVERS", DEFAULT_RESOLVERS)
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _quality_url(data: Dict[str, Any]) -> str:
    """Choose the highest numeric quality returned by a resolver."""
    qualities = data.get("qualities") or {}
    candidates = []

    if isinstance(qualities, dict):
        for label, value in qualities.items():
            if isinstance(value, dict):
                value = value.get("url") or value.get("download_url")
            if not isinstance(value, str) or not value:
                continue
            match = re.search(r"(\d{3,4})", str(label))
            candidates.append((int(match.group(1)) if match else -1, value))
    elif isinstance(qualities, list):
        for item in qualities:
            if not isinstance(item, dict):
                continue
            value = item.get("url") or item.get("download_url")
            label = item.get("quality") or item.get("label") or item.get("height") or ""
            if isinstance(value, str) and value:
                match = re.search(r"(\d{3,4})", str(label))
                candidates.append((int(match.group(1)) if match else -1, value))

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    # Some APIs declare a best quality separately.
    best = data.get("best_quality")
    if isinstance(qualities, dict) and best in qualities:
        value = qualities[best]
        if isinstance(value, dict):
            value = value.get("url") or value.get("download_url")
        if isinstance(value, str):
            return value

    # Direct download is normally the original shared file.
    for key in ("direct_download_url", "download_url", "download_link", "media_url", "url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return ""


def _normalise_response(data: Dict[str, Any], share_url: str, resolver: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("resolver returned invalid JSON")
    if data.get("success") is False:
        raise ValueError(str(data.get("message") or data.get("error") or "resolver rejected this link"))

    download_url = _quality_url(data)
    if not download_url:
        raise ValueError("resolver returned no direct/quality URL")

    name = data.get("filename") or data.get("file_name") or data.get("name") or "terabox_file"
    size = _as_int(data.get("size") or data.get("file_size") or data.get("size_bytes"))
    thumb = data.get("thumbnail") or data.get("thumb") or ""
    qualities = data.get("qualities") or {}

    # Keep both schemas because youtube_dl_echo.py and the callback use different keys.
    return {
        "success": True,
        "file_name": str(name),
        "file_size": size,
        "download_link": download_url,
        "thumbnail": thumb,
        "title": str(name),
        "size": size,
        "download_url": download_url,
        "direct_url": download_url,
        "share_url": share_url,
        "headers": {},
        "qualities": qualities,
        "resolver": resolver,
    }


def extract_terabox_info(url: str) -> Optional[Dict[str, Any]]:
    """Resolve a public share URL without storing any TeraBox cookie/session."""
    if not is_terabox(url):
        return {"error": "Unsupported TeraBox URL", "error_type": "invalid_url"}

    errors = []
    for resolver in _resolvers():
        try:
            response = requests.get(
                resolver,
                params={"url": url},
                timeout=(10, 35),
                headers={"Accept": "application/json", "User-Agent": "BIMBO-URL-Bot/1.0"},
            )
            response.raise_for_status()
            info = _normalise_response(response.json(), url, resolver)
            logger.info("TeraBox resolved via %s: %s", resolver, info["file_name"])
            return info
        except (requests.RequestException, ValueError) as exc:
            logger.warning("TeraBox resolver failed (%s): %s", resolver, exc)
            errors.append(f"{urlparse(resolver).netloc or resolver}: {exc}")

    detail = "; ".join(errors[:2]) or "No resolver configured"
    return {
        "error": f"All cookie-less resolvers are unavailable. {detail}",
        "error_type": "resolver_unavailable",
    }


def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "terabox_file")
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(". ") or "terabox_file"


def _download_hls(url: str, output_path: str) -> Optional[str]:
    """yt-dlp is used only for an HLS URL returned by a resolver."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-playlist", "--retries", "3", "-o", output_path, url],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=7200,
            check=False,
        )
        if result.returncode:
            logger.error("TeraBox HLS download failed: %s", result.stdout[-1000:])
            return None
        # yt-dlp may change the extension; return the newest matching file.
        parent = Path(output_path).parent
        stem = Path(output_path).stem
        matches = sorted(parent.glob(stem + "*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(matches[0]) if matches else None
    except Exception as exc:
        logger.error("TeraBox HLS downloader error: %s", exc)
        return None


def download_terabox_file(_unused_instance, file_info: Dict[str, Any], download_dir: str) -> Optional[str]:
    """Download the direct URL resolved above; no TeraBox authentication is used."""
    direct_url = file_info.get("download_link") or file_info.get("download_url")
    if not direct_url:
        logger.error("TeraBox file info contains no download URL")
        return None

    os.makedirs(download_dir, exist_ok=True)
    filename = _safe_filename(file_info.get("file_name") or file_info.get("title") or "terabox_file")
    output_path = os.path.join(download_dir, filename)

    if ".m3u8" in direct_url.lower():
        return _download_hls(direct_url, output_path)

    temp_path = output_path + ".part"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Referer": "https://www.1024tera.com/",
    }
    try:
        with requests.get(direct_url, stream=True, headers=headers, timeout=(15, 600), allow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise RuntimeError("resolver URL returned an HTML page instead of a file")
            with open(temp_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise RuntimeError("empty file received from resolver URL")
        os.replace(temp_path, output_path)
        logger.info("TeraBox download complete: %s", output_path)
        return output_path
    except Exception as exc:
        logger.error("TeraBox direct download failed: %s", exc, exc_info=True)
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return None


# Compatibility alias used by youtube_dl_echo.py
extract = extract_terabox_info
