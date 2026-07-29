# BIMBO v4.0 — PREMIUM Anime Progress UI (Mobile-First, Dark Theme)
# ================================================================
# Features:
# - Mobile-optimized (480x820)
# - Circular progress in header
# - Anime thumbnails per task (different random per task)
# - Colored progress bars (blue=download, purple=upload)
# - Dark premium theme
# - Pipeline queue with icons
# - System health with mini bars
# - Memory-efficient for 512MB RAM
# ================================================================

import os
import glob
import random
import logging
import time
import gc
import math
from pathlib import Path

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mobile screen dimensions
CARD_WIDTH = 480
CARD_HEIGHT = 820

# Task card dimensions
TASK_CARD_HEIGHT = 180
TASK_THUMB_SIZE = 70

# Header dimensions
HEADER_HEIGHT = 140

# Cache
_image_cache = {}
_MAX_CACHE = 4

# Folder paths
_NEKO_DIR = None
_UFH_DIR = None

# Task image tracking: user_id -> set of used image paths (to avoid repeats)
_user_used_images = {}


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
    if not folder or not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(('.webp', '.png', '.jpg', '.jpeg'))
        and not f.startswith('.')
    ]


def _get_random_unique(user_id, folder_files, cache_key="task"):
    """Get random image, avoiding recently used ones for this user"""
    if not folder_files:
        return None
    
    # Get used images for this user
    used = _user_used_images.get(user_id, set())
    
    # Filter out used images
    available = [f for f in folder_files if f not in used]
    
    # If all used, reset
    if not available:
        used.clear()
        available = folder_files
    
    # Pick random
    chosen = random.choice(available)
    
    # Track usage (max 10 per user to save memory)
    if user_id not in _user_used_images:
        _user_used_images[user_id] = set()
    _user_used_images[user_id].add(chosen)
    if len(_user_used_images[user_id]) > 10:
        # Remove oldest
        _user_used_images[user_id] = set(list(_user_used_images[user_id])[-5:])
    
    return chosen


def _evict_cache():
    while len(_image_cache) > _MAX_CACHE:
        _image_cache.pop(next(iter(_image_cache)), None)


def _load_image(path):
    if path in _image_cache:
        return _image_cache[path]
    
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()
        
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


def _draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + radius*2, y0 + radius*2], 180, 270, fill=fill)
    draw.pieslice([x1 - radius*2, y0, x1, y0 + radius*2], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - radius*2, x0 + radius*2, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - radius*2, y1 - radius*2, x1, y1], 0, 90, fill=fill)


def _draw_circular_progress(draw, cx, cy, radius, percentage, color="#4FC3F7"):
    """Draw circular progress indicator"""
    # Background circle
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], outline="#2A2A3E", width=4)
    
    # Progress arc
    if percentage > 0:
        start_angle = -90
        end_angle = -90 + (360 * percentage / 100)
        
        # Draw arc using polygon approximation
        points = []
        for angle_deg in range(int(start_angle), int(end_angle) + 1, 5):
            angle_rad = math.radians(angle_deg)
            x = cx + radius * math.cos(angle_rad)
            y = cy + radius * math.sin(angle_rad)
            points.append((x, y))
        
        if points:
            draw.line(points, fill=color, width=6)


def _draw_progress_bar(draw, x, y, width, height, percentage, color="#4FC3F7"):
    percentage = max(0, min(100, percentage))
    # Background
    _draw_rounded_rect(draw, [x, y, x + width, y + height], height//2, "#1A1A2E")
    # Fill
    fill_width = max(0, int(width * percentage / 100))
    if fill_width > 0:
        _draw_rounded_rect(draw, [x, y, x + fill_width, y + height], height//2, color)


def _draw_mini_bar(draw, x, y, width, height, percentage, color="#4FC3F7"):
    """Tiny bar for system stats"""
    draw.rectangle([x, y, x + width, y + height], fill="#1A1A2E")
    fill_w = max(0, int(width * percentage / 100))
    if fill_w > 0:
        draw.rectangle([x, y, x + fill_w, y + height], fill=color)


def _fit_text(draw, text, font, max_width):
    if not text:
        return ""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
    except Exception:
        w = len(text) * 7
    
    if w <= max_width:
        return text
    while len(text) > 3:
        text = text[:-4] + "..."
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(text) * 7
        if w <= max_width:
            return text
    return text[:10] + "..."


def _generate_font(size, bold=False):
    try:
        from PIL import ImageFont
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                return ImageFont.truetype(fp, size)
        return ImageFont.load_default()
    except Exception:
        return None


def _fmt_size(b):
    if b <= 0: return '0B'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024: return f"{b:.2f}{unit}"
        b /= 1024
    return f"{b:.2f}TB"


def _fmt_speed(b):
    if b <= 0: return '0B/s'
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if b < 1024: return f"{b:.2f}{unit}"
        b /= 1024
    return f"{b:.2f}TB/s"


def _fmt_time(seconds):
    if seconds <= 0 or seconds > 86400:
        return '?s'
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}s'
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f'{minutes}m {secs}s'
    hours = minutes // 60
    mins = minutes % 60
    return f'{hours}h {mins}m'


async def generate_anime_progress_card(user_id, tasks, stats, system_stats):
    """
    Generate premium mobile-first anime progress card.
    
    Layout:
    - Header: Live Status + Circular Progress + Active Tasks
    - Task Cards: Anime thumb + Progress + Stats
    - Pipeline Queue
    - System Health
    
    Returns: Path to generated image or None
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    try:
        active_tasks = tasks[:4]
        num_tasks = len(active_tasks)
        if num_tasks == 0:
            return None
        
        # Calculate height
        img_height = HEADER_HEIGHT + (num_tasks * (TASK_CARD_HEIGHT + 10)) + 120
        img_height = min(img_height, CARD_HEIGHT)
        
        # Create base image with dark gradient
        img = Image.new('RGB', (CARD_WIDTH, img_height), '#0A0E1A')
        draw = ImageDraw.Draw(img)
        
        # Background gradient effect
        for y in range(img_height):
            intensity = int(10 + (y / img_height) * 15)
            draw.line([(0, y), (CARD_WIDTH, y)], fill=(intensity, intensity, intensity + 10))

        # ── HEADER SECTION ──
        header_y = 10
        _draw_rounded_rect(draw, [10, header_y, CARD_WIDTH - 10, header_y + HEADER_HEIGHT], 12, '#1A1F2E')
        
        # Header title
        font_title = _generate_font(18, bold=True)
        font_sub = _generate_font(13)
        
        draw.text((20, header_y + 15), "⚡ BIMBO LIVE ⚡", fill='#4FC3F7', font=font_title)
        
        # Live status indicator
        draw.ellipse([20, header_y + 45, 30, header_y + 55], fill='#4CAF50')
        draw.text((35, header_y + 43), "LIVE STATUS", fill='#4CAF50', font=font_sub)
        
        # Active tasks count
        active_now = len([t for t in active_tasks if t.get('status') not in ('queued', 'waiting')])
        draw.text((CARD_WIDTH - 120, header_y + 43), f"+ {active_now} Active Tasks", fill='#4FC3F7', font=font_sub)
        
        # Circular progress in center
        overall_pct = 0
        if active_tasks:
            pcts = [t.get('percentage', 0) for t in active_tasks]
            overall_pct = sum(pcts) / len(pcts)
        
        cx = CARD_WIDTH // 2
        cy = header_y + 90
        radius = 35
        _draw_circular_progress(draw, cx, cy, radius, overall_pct, '#BC8CFF')
        
        # Percentage text in center
        font_pct = _generate_font(20, bold=True)
        pct_text = f"{overall_pct:.1f}%"
        bbox = draw.textbbox((0, 0), pct_text, font=font_pct)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw//2, cy - 12), pct_text, fill='#FFFFFF', font=font_pct)
        
        font_small = _generate_font(10)
        sub_text = "OVERALL"
        bbox = draw.textbbox((0, 0), sub_text, font=font_small)
        sw = bbox[2] - bbox[0]
        draw.text((cx - sw//2, cy + 15), sub_text, fill='#8B949E', font=font_small)

        # ── TASK CARDS ──
        y_offset = header_y + HEADER_HEIGHT + 10
        
        # Get folder files once
        _resolve_dirs()
        neko_files = _get_image_files(_NEKO_DIR)
        ufh_files = _get_image_files(_UFH_DIR)
        
        for idx, task in enumerate(active_tasks):
            card_y = y_offset + (idx * (TASK_CARD_HEIGHT + 10))
            if card_y + TASK_CARD_HEIGHT > img_height - 20:
                break
            
            # Card background with border
            _draw_rounded_rect(draw, [10, card_y, CARD_WIDTH - 10, card_y + TASK_CARD_HEIGHT], 10, '#161B22')
            draw.rectangle([10, card_y, CARD_WIDTH - 10, card_y + 2], fill='#4FC3F7' if task.get('task_type') != 'upload' else '#BC8CFF')
            
            # Task thumbnail (random unique per task)
            thumb_path = _get_random_unique(user_id, ufh_files, "task")
            thumb_img = _load_image(thumb_path) if thumb_path else None
            
            thumb_x = 20
            thumb_y = card_y + 20
            if thumb_img:
                thumb_resized = thumb_img.resize((TASK_THUMB_SIZE, TASK_THUMB_SIZE), Image.LANCZOS)
                # Paste with rounded corners effect (simple rectangle for now)
                img.paste(thumb_resized, (thumb_x, thumb_y), thumb_resized if thumb_resized.mode == 'RGBA' else None)
            
            # Task info
            is_upload = task.get('task_type') == 'upload'
            icon = '⬆️' if is_upload else '⬇️'
            stage = 'UPLOAD' if is_upload else 'DOWNLOAD'
            stage_color = '#BC8CFF' if is_upload else '#4FC3F7'
            
            name = str(task.get('filename', 'Unknown'))[:30]
            pct = max(0.0, min(100.0, float(task.get('percentage', 0))))
            
            # Stage label with number
            font_stage = _generate_font(14, bold=True)
            draw.text((thumb_x + TASK_THUMB_SIZE + 15, card_y + 15), f"{icon} {idx+1} · {stage}", fill=stage_color, font=font_stage)
            
            # Filename
            font_name = _generate_font(16, bold=True)
            name_text = _fit_text(draw, name, font_name, 280)
            draw.text((thumb_x + TASK_THUMB_SIZE + 15, card_y + 38), name_text, fill='#E6EDF3', font=font_name)
            
            # Percentage
            font_pct_large = _generate_font(18, bold=True)
            draw.text((CARD_WIDTH - 80, card_y + 38), f"{pct:.1f}%", fill='#E6EDF3', font=font_pct_large)
            
            # Progress bar
            bar_color = '#BC8CFF' if is_upload else '#4FC3F7'
            _draw_progress_bar(draw, thumb_x + TASK_THUMB_SIZE + 15, card_y + 65, 280, 12, pct, bar_color)
            
            # Stats
            font_stats = _generate_font(11)
            done = task.get('downloaded', 0)
            total = task.get('total_size', 0)
            speed = task.get('avg_speed', 0)
            eta = task.get('eta', 0)
            elapsed = task.get('elapsed', 0)
            
            stats_y = card_y + 85
            draw.text((thumb_x + TASK_THUMB_SIZE + 15, stats_y), f"📦 {_fmt_size(done)} / {_fmt_size(total)}", fill='#8B949E', font=font_stats)
            draw.text((250, stats_y), f"⚡ {_fmt_speed(speed)}", fill='#8B949E', font=font_stats)
            
            stats_y2 = card_y + 105
            draw.text((thumb_x + TASK_THUMB_SIZE + 15, stats_y2), f"⏱ {_fmt_time(eta)} left", fill='#8B949E', font=font_stats)
            draw.text((200, stats_y2), f"🕒 {_fmt_time(elapsed)}", fill='#8B949E', font=font_stats)
            draw.text((310, stats_y2), f"📁 File", fill='#8B949E', font=font_stats)
            
            # Engine badge
            engine = task.get('engine', 'unknown')
            engine_colors = {
                'aria2': '#3FB950', 'yt-dlp': '#58A6FF', 'pyrogram': '#BC8CFF',
                'libtorrent': '#F0883E', 'ffmpeg': '#F85149', 'unknown': '#8B949E'
            }
            eng_color = engine_colors.get(engine, '#8B949E')
            status = task.get('status', 'unknown').upper()
            
            badge_y = card_y + TASK_CARD_HEIGHT - 30
            _draw_rounded_rect(draw, [thumb_x + TASK_THUMB_SIZE + 15, badge_y, thumb_x + TASK_THUMB_SIZE + 80, badge_y + 20], 5, '#2A2A3E')
            draw.text((thumb_x + TASK_THUMB_SIZE + 20, badge_y + 4), engine, fill=eng_color, font=font_stats)
            
            _draw_rounded_rect(draw, [CARD_WIDTH - 120, badge_y, CARD_WIDTH - 20, badge_y + 20], 5, '#2A2A3E')
            draw.text((CARD_WIDTH - 115, badge_y + 4), status, fill=eng_color, font=font_stats)

        # ── PIPELINE QUEUE SECTION ──
        queue_y = y_offset + (num_tasks * (TASK_CARD_HEIGHT + 10)) + 10
        if queue_y + 100 <= img_height:
            _draw_rounded_rect(draw, [10, queue_y, CARD_WIDTH - 10, queue_y + 90], 10, '#161B22')
            
            font_section = _generate_font(13, bold=True)
            font_q = _generate_font(11)
            
            draw.text((20, queue_y + 10), "🧭 PIPELINE QUEUE", fill='#58A6FF', font=font_section)
            
            dl_active = stats.get('download_active', 0)
            dl_limit = stats.get('download_limit', 2)
            dl_wait = stats.get('download_waiting', 0)
            ul_active = stats.get('upload_active', 0)
            ul_limit = stats.get('upload_limit', 2)
            ul_wait = stats.get('upload_waiting', 0)
            bulk = stats.get('bulk_pending', 0)
            mine = stats.get('total_pending', 0)
            priority = stats.get('interactive', 0)
            
            q_y = queue_y + 30
            draw.text((20, q_y), "⬇️", fill='#4FC3F7', font=font_q)
            draw.text((40, q_y), f"DL {dl_active}/{dl_limit}", fill='#E6EDF3', font=font_q)
            draw.text((140, q_y), f"wait {dl_wait}", fill='#8B949E', font=font_q)
            
            draw.text((20, q_y + 18), "⬆️", fill='#BC8CFF', font=font_q)
            draw.text((40, q_y + 18), f"UL {ul_active}/{ul_limit}", fill='#E6EDF3', font=font_q)
            draw.text((140, q_y + 18), f"wait {ul_wait}", fill='#8B949E', font=font_q)
            
            draw.text((20, q_y + 36), "📚", fill='#F0883E', font=font_q)
            draw.text((40, q_y + 36), f"Bulk {bulk}", fill='#E6EDF3', font=font_q)
            draw.text((140, q_y + 36), f"Yours {mine}", fill='#8B949E', font=font_q)
            
            draw.text((20, q_y + 54), "🚀", fill='#F85149', font=font_q)
            draw.text((40, q_y + 54), f"Priority {priority}", fill='#E6EDF3', font=font_q)

            # ── SYSTEM HEALTH SECTION ──
            health_y = queue_y + 100
            if health_y + 80 <= img_height:
                _draw_rounded_rect(draw, [10, health_y, CARD_WIDTH - 10, health_y + 75], 10, '#161B22')
                
                draw.text((20, health_y + 10), "️ SYSTEM HEALTH", fill='#58A6FF', font=font_section)
                
                cpu = system_stats.get('cpu', 0)
                ram = system_stats.get('ram', 0)
                disk_free = system_stats.get('disk_free', 0)
                dl_speed = system_stats.get('total_dl_speed', 0)
                ul_speed = system_stats.get('total_ul_speed', 0)
                
                cpu_color = '#3FB950' if cpu < 70 else '#F0883E' if cpu < 90 else '#F85149'
                ram_color = '#3FB950' if ram < 70 else '#F0883E' if ram < 85 else '#F85149'
                
                h_y = health_y + 30
                draw.text((20, h_y), "CPU", fill='#8B949E', font=font_q)
                draw.text((50, h_y), f"{cpu:.0f}%", fill=cpu_color, font=font_q)
                _draw_mini_bar(draw, 90, h_y + 5, 50, 6, cpu, cpu_color)
                
                draw.text((160, h_y), "RAM", fill='#8B949E', font=font_q)
                draw.text((190, h_y), f"{ram:.0f}%", fill=ram_color, font=font_q)
                _draw_mini_bar(draw, 230, h_y + 5, 50, 6, ram, ram_color)
                
                draw.text((300, h_y), "FREE", fill='#8B949E', font=font_q)
                draw.text((335, h_y), _fmt_size(disk_free), fill='#E6EDF3', font=font_q)
                
                h_y2 = health_y + 50
                draw.text((20, h_y2), "NET", fill='#8B949E', font=font_q)
                draw.text((50, h_y2), f"↓{_fmt_speed(dl_speed)}", fill='#4FC3F7', font=font_q)
                draw.text((160, h_y2), f"↑{_fmt_speed(ul_speed)}", fill='#BC8CFF', font=font_q)
                
                # Warnings
                warnings = []
                if ram >= 85: warnings.append('High RAM')
                if disk_free and disk_free < 2 * 1024**3: warnings.append('Low disk')
                if cpu >= 90: warnings.append('High CPU')
                if warnings:
                    draw.text((20, h_y2 + 18), f"⚠️ {' • '.join(warnings)}", fill='#F0883E', font=font_q)

        # ── Save to temp file ─
        temp_dir = os.path.join(BASE_DIR, "data", "anime_cards")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"card_{user_id}_{int(time.time() * 1000)}.png")
        
        img.save(out_path, 'PNG', optimize=True, quality=85)
        
        # ── CRITICAL: Free memory immediately ──
        del img
        del draw
        gc.collect()
        
        logger.info(f"✅ Premium anime card generated: {out_path}")
        return out_path

    except Exception as e:
        logger.error(f"Premium card generation failed: {e}", exc_info=True)
        return None


async def send_anime_progress(client, chat_id, text, caption=None, reply_to=None):
    """
    Generate and send premium anime progress card.
    Falls back to text if image generation fails.
    """
    try:
        from helper_funcs.display_progress import get_user_active_tasks, get_user_all_tasks
        
        active = get_user_active_tasks(chat_id)
        
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
