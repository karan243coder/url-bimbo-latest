# BIMBO v4.0 — Anime Progress UI (Memory-Efficient for 512MB Koyeb)
# ================================================================
# - Header: random from sticker/NekoArt_*_*/
# - Task: random from sticker/Ufhjbdsvb-*/
# - Memory: ONE image at a time, immediate cleanup
# - Fallback: text dashboard if PIL fails
# ================================================================

import os
import glob
import random
import logging
import time
import gc
from pathlib import Path

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD_WIDTH = 480
TASK_HEIGHT = 220
HEADER_HEIGHT = 280
PADDING = 15

# Cache: max 4 images to save RAM on 512MB
_image_cache = {}  # path -> PIL.Image (max 4)
_MAX_CACHE = 4

# Folder paths (resolved once)
_NEKO_DIR = None
_UFH_DIR = None


def _resolve_dirs():
    global _NEKO_DIR, _UFH_DIR
    if _NEKO_DIR is None:
        for d in glob.glob(os.path.join(BASE_DIR, "sticker", "NekoArt_*")):
            if os.path.isdir(d):
                _NEKO_DIR = d
                break
    if _UFH_DIR is None:
        for d in glob.glob(os.path.join(BASE_DIR, "sticker", "Ufhjbdsvb-*")):
            if os.path.isdir(d):
                _UFH_DIR = d
                break


def _get_image_files(folder):
    """Get list of image files (webp/png/jpg) in folder"""
    if not folder or not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(('.webp', '.png', '.jpg', '.jpeg'))
        and not f.startswith('.')
    ]


def _evict_cache():
    """Keep cache small for 512MB RAM"""
    while len(_image_cache) > _MAX_CACHE:
        _image_cache.pop(next(iter(_image_cache)), None)


def _load_image(path):
    """Load image with cache, memory-efficient"""
    if path in _image_cache:
        return _image_cache[path]
    
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()  # Force load so we can close the file
        
        # Auto-orient
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        
        _evict_cache()
        _image_cache[path] = img
        return img
    except Exception as e:
        logger.debug(f"Image load failed: {e}")
        return None


def _get_random_neko():
    """Get random header image from NekoArt folder"""
    _resolve_dirs()
    files = _get_image_files(_NEKO_DIR)
    if not files:
        return None
    return random.choice(files)


def _get_random_ufh():
    """Get random task image from Ufhjbdsvb folder"""
    _resolve_dirs()
    files = _get_image_files(_UFH_DIR)
    if not files:
        return None
    return random.choice(files)


def _draw_rounded_rect(draw, xy, radius, fill):
    """Draw rounded rectangle"""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + radius*2, y0 + radius*2], 180, 270, fill=fill)
    draw.pieslice([x1 - radius*2, y0, x1, y0 + radius*2], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - radius*2, x0 + radius*2, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - radius*2, y1 - radius*2, x1, y1], 0, 90, fill=fill)


def _text_size(draw, text, font):
    """Get text size"""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return len(text) * 7, 14


def _fit_text(draw, text, font, max_width):
    """Truncate text to fit width"""
    if not text:
        return ""
    w, _ = _text_size(draw, text, font)
    if w <= max_width:
        return text
    while len(text) > 3:
        text = text[:-4] + "..."
        w, _ = _text_size(draw, text, font)
        if w <= max_width:
            return text
    return text[:10] + "..."


def _draw_progress_bar(draw, x, y, width, height, percentage, color="#4FC3F7"):
    """Draw a colored progress bar"""
    percentage = max(0, min(100, percentage))
    # Background
    draw.rounded_rectangle([x, y, x + width, y + height], radius=height//2, fill="#1A1A2E")
    # Fill
    fill_width = int(width * percentage / 100)
    if fill_width > 0:
        draw.rounded_rectangle([x, y, x + fill_width, y + height], radius=height//2, fill=color)


def _generate_font(size):
    """Get a font, fallback to default"""
    try:
        from PIL import ImageFont
        # Try common font paths
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf"),
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                return ImageFont.truetype(fp, size)
        return ImageFont.load_default()
    except Exception:
        try:
            from PIL import ImageFont
            return ImageFont.load_default()
        except Exception:
            return None


async def generate_anime_progress_card(user_id, tasks, stats, system_stats):
    """
    Generate a beautiful anime progress card image.
    
    Args:
        user_id: Telegram user ID
        tasks: list of task dicts from display_progress
        stats: pipeline stats dict
        system_stats: system health dict
    
    Returns:
        Path to generated image file, or None if failed
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.debug("PIL not available for anime UI")
        return None

    try:
        # ── Calculate dimensions ──
        active_tasks = tasks[:4]
        num_tasks = len(active_tasks)
        if num_tasks == 0:
            return None
        
        img_height = HEADER_HEIGHT + (num_tasks * TASK_HEIGHT) + 200  # extra for queue + health
        img_width = CARD_WIDTH

        # ── Create base image ──
        img = Image.new('RGB', (img_width, img_height), '#0D1117')
        draw = ImageDraw.Draw(img)

        # ─ Draw header with anime ──
        header_path = _get_random_neko()
        header_img = _load_image(header_path) if header_path else None
        
        # Dark header background
        _draw_rounded_rect(draw, [10, 10, img_width - 10, HEADER_HEIGHT], 12, '#161B22')
        
        if header_img:
            # Resize to fit header (100x100 circle area on left)
            h_size = 90
            header_resized = header_img.resize((h_size, h_size), Image.LANCZOS)
            # Paste with slight offset
            img.paste(header_resized, (25, 25), header_resized if header_resized.mode == 'RGBA' else None)
        
        # Header text
        font_title = _generate_font(20)
        font_sub = _generate_font(14)
        
        draw.text((130, 30), "⚡ BIMBO LIVE", fill='#58A6FF', font=font_title)
        active_now = len([t for t in active_tasks if t.get('status') not in ('queued', 'waiting')])
        draw.text((130, 58), f"• {active_now} active", fill='#8B949E', font=font_sub)

        # ── Draw task cards ──
        y_offset = HEADER_HEIGHT + 10
        
        for idx, task in enumerate(active_tasks):
            card_y = y_offset + (idx * TASK_HEIGHT)
            
            # Card background
            _draw_rounded_rect(draw, [10, card_y, img_width - 10, card_y + TASK_HEIGHT - 10], 10, '#161B22')
            
            # Task anime image
            task_path = _get_random_ufh()
            task_img = _load_image(task_path) if task_path else None
            
            img_size = 80
            if task_img:
                task_resized = task_img.resize((img_size, img_size), Image.LANCZOS)
                img.paste(task_resized, (25, card_y + 20), task_resized if task_resized.mode == 'RGBA' else None)
            
            # Task info
            is_upload = task.get('task_type') == 'upload'
            icon = '⬆️' if is_upload else '⬇️'
            stage = 'UPLOAD' if is_upload else 'DOWNLOAD'
            name = str(task.get('filename', 'Unknown'))[:28]
            pct = max(0.0, min(100.0, float(task.get('percentage', 0))))
            
            # Stage label
            stage_color = '#BC8CFF' if is_upload else '#4FC3F7'
            font_stage = _generate_font(13)
            draw.text((115, card_y + 18), f"{icon} {idx+1} · {stage}", fill=stage_color, font=font_stage)
            
            # Filename
            font_name = _generate_font(15)
            draw.text((115, card_y + 38), name, fill='#E6EDF3', font=font_name)
            
            # Progress bar
            bar_color = '#BC8CFF' if is_upload else '#4FC3F7'
            _draw_progress_bar(draw, 115, card_y + 65, 260, 16, pct, bar_color)
            
            # Percentage
            font_pct = _generate_font(18)
            pct_text = f"{pct:.1f}%"
            draw.text((380, card_y + 60), pct_text, fill='#E6EDF3', font=font_pct)
            
            # Stats
            font_small = _generate_font(12)
            done = task.get('downloaded', 0)
            total = task.get('total_size', 0)
            
            def _fmt(b):
                if b <= 0: return '0B'
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if b < 1024: return f"{b:.1f}{unit}"
                    b /= 1024
                return f"{b:.1f}TB"
            
            speed = task.get('avg_speed', 0)
            eta = task.get('eta', 0)
            elapsed = task.get('elapsed', 0)
            
            info_y = card_y + 90
            draw.text((115, info_y), f"📦 {_fmt(done)} / {_fmt(total)}", fill='#8B949E', font=font_small)
            draw.text((115, info_y + 18), f"⚡ {_fmt(speed)}/s", fill='#8B949E', font=font_small)
            draw.text((250, info_y), f"⏱ {_fmt(eta * speed) if speed > 0 and eta > 0 else '?'} left", fill='#8B949E', font=font_small)
            draw.text((250, info_y + 18), f"🕒 {_fmt(elapsed)}", fill='#8B949E', font=font_small)
            
            # Engine badge
            engine = task.get('engine', 'unknown')
            engine_colors = {
                'aria2': '#3FB950', 'yt-dlp': '#58A6FF', 'pyrogram': '#BC8CFF',
                'libtorrent': '#F0883E', 'ffmpeg': '#F85149', 'unknown': '#8B949E'
            }
            eng_color = engine_colors.get(engine, '#8B949E')
            status = task.get('status', 'unknown').upper()
            draw.text((115, card_y + TASK_HEIGHT - 40), f"{engine} • {status}", fill=eng_color, font=font_small)

        # ── Pipeline Queue section ──
        queue_y = y_offset + (num_tasks * TASK_HEIGHT) + 10
        _draw_rounded_rect(draw, [10, queue_y, img_width - 10, queue_y + 75], 10, '#161B22')
        
        font_section = _generate_font(14)
        font_q = _generate_font(12)
        
        draw.text((25, queue_y + 10), "🧭 PIPELINE QUEUE", fill='#58A6FF', font=font_section)
        
        dl_active = stats.get('download_active', 0)
        dl_limit = stats.get('download_limit', 2)
        dl_wait = stats.get('download_waiting', 0)
        ul_active = stats.get('upload_active', 0)
        ul_limit = stats.get('upload_limit', 2)
        ul_wait = stats.get('upload_waiting', 0)
        bulk = stats.get('bulk_pending', 0)
        mine = stats.get('total_pending', 0)
        
        draw.text((25, queue_y + 32), f"⬇️ DL {dl_active}/{dl_limit} • wait {dl_wait}", fill='#8B949E', font=font_q)
        draw.text((25, queue_y + 50), f"⬆️ UL {ul_active}/{ul_limit} • wait {ul_wait}", fill='#8B949E', font=font_q)
        draw.text((250, queue_y + 32), f"📚 Bulk {bulk}", fill='#8B949E', font=font_q)
        draw.text((250, queue_y + 50), f" Yours {mine}", fill='#8B949E', font=font_q)

        # ── System Health section ──
        health_y = queue_y + 85
        _draw_rounded_rect(draw, [10, health_y, img_width - 10, health_y + 75], 10, '#161B22')
        
        draw.text((25, health_y + 10), "🖥️ SYSTEM HEALTH", fill='#58A6FF', font=font_section)
        
        cpu = system_stats.get('cpu', 0)
        ram = system_stats.get('ram', 0)
        disk_free = system_stats.get('disk_free', 0)
        dl_speed = system_stats.get('total_dl_speed', 0)
        ul_speed = system_stats.get('total_ul_speed', 0)
        
        def _fmt_speed(b):
            if b <= 0: return '0B/s'
            for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
                if b < 1024: return f"{b:.1f}{unit}"
                b /= 1024
            return f"{b:.1f}TB/s"
        
        def _fmt_disk(b):
            if b <= 0: return '0B'
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if b < 1024: return f"{b:.1f}{unit}"
                b /= 1024
            return f"{b:.1f}TB"
        
        cpu_color = '#3FB950' if cpu < 70 else '#F0883E' if cpu < 90 else '#F85149'
        ram_color = '#3FB950' if ram < 70 else '#F0883E' if ram < 85 else '#F85149'
        
        draw.text((25, health_y + 32), f"CPU", fill='#8B949E', font=font_q)
        draw.text((60, health_y + 32), f"{cpu:.0f}%", fill=cpu_color, font=font_q)
        draw.text((115, health_y + 32), f"RAM", fill='#8B949E', font=font_q)
        draw.text((150, health_y + 32), f"{ram:.0f}%", fill=ram_color, font=font_q)
        draw.text((210, health_y + 32), f"Free {_fmt_disk(disk_free)}", fill='#8B949E', font=font_q)
        
        draw.text((25, health_y + 50), f"Net ️ {_fmt_speed(dl_speed)}", fill='#8B949E', font=font_q)
        draw.text((180, health_y + 50), f"⬆️ {_fmt_speed(ul_speed)}", fill='#8B949E', font=font_q)

        # Warnings
        warnings = []
        if ram >= 85: warnings.append('High RAM')
        if disk_free and disk_free < 2 * 1024**3: warnings.append('Low disk')
        if cpu >= 90: warnings.append('High CPU')
        if warnings:
            draw.text((25, health_y + 68), f"⚠️ {' • '.join(warnings)}", fill='#F0883E', font=font_q)

        # ── Save to temp file ──
        temp_dir = os.path.join(BASE_DIR, "data", "anime_cards")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"card_{user_id}_{int(time.time() * 1000)}.png")
        
        img.save(out_path, 'PNG', optimize=True)
        
        # ── CRITICAL: Free memory immediately ──
        del img
        del draw
        gc.collect()
        
        logger.info(f"✅ Anime card generated: {out_path}")
        return out_path

    except Exception as e:
        logger.error(f"Anime card generation failed: {e}", exc_info=True)
        return None


async def send_anime_progress(client, chat_id, text, caption=None, reply_to=None):
    """
    Generate and send anime progress card.
    Falls back to text if image generation fails.
    """
    try:
        from helper_funcs.display_progress import get_user_active_tasks, get_user_all_tasks
        
        active = get_user_active_tasks(chat_id)
        all_t = get_user_all_tasks(chat_id)
        
        if not active:
            return None
        
        try:
            from plugins.media_pipeline import get_pipeline_stats
            mine = get_pipeline_stats(chat_id)
            global_q = get_pipeline_stats()
        except Exception:
            mine = global_q = {
                'download_active': 0, 'download_waiting': 0, 'download_limit': 2,
                'upload_active': 0, 'upload_waiting': 0, 'upload_limit': 2,
                'bulk_pending': 0, 'interactive': 0, 'total_pending': 0,
            }
        
        from helper_funcs.display_progress import get_system_stats_advanced
        sys_stats = get_system_stats_advanced()
        
        # Generate image
        img_path = await generate_anime_progress_card(chat_id, active, global_q, sys_stats)
        
        if img_path and os.path.exists(img_path):
            try:
                if caption is None:
                    caption = text  # Use text as caption below image
                
                sent = await client.send_photo(
                    chat_id=chat_id,
                    photo=img_path,
                    caption=caption[:1000] if caption else None,
                    reply_to_message_id=reply_to
                )
                # Delete temp image after sending
                try:
                    os.remove(img_path)
                except Exception:
                    pass
                return sent
            except Exception as e:
                logger.debug(f"send_photo failed: {e}")
                try:
                    os.remove(img_path)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Anime UI failed: {e}")
    
    return None
