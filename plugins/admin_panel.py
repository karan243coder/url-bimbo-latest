import os
import json
import random
from datetime import datetime
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import BIMBO_OWNER_ID, BIMBO_DATABASE_URL
from plugins.premium import premium_manager
from database.access import bimbo
import logging

logger = logging.getLogger(__name__)

ADMIN_DATA_FILE = "admin_data.json"

def load_admin_data():
    try:
        if os.path.exists(ADMIN_DATA_FILE):
            with open(ADMIN_DATA_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Load admin data error: {e}")
    
    return {
        'channels': [],
        'banned_users': [],
        'custom_messages': {},
        'settings': {
            'force_sub': False,
            'maintenance_mode': False
        },
        'images': {
            'progress': [],
            'start': '',
            'local_folder': 'images/'
        }
    }

def save_admin_data(data):
    try:
        with open(ADMIN_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save admin data error: {e}")

admin_data = load_admin_data()

# ── Image helper functions ──
def get_progress_images():
    """Get progress images from admin data"""
    return admin_data.get('images', {}).get('progress', [])

def set_progress_images(images_list):
    """Set progress images"""
    if 'images' not in admin_data:
        admin_data['images'] = {}
    admin_data['images']['progress'] = images_list
    save_admin_data(admin_data)

def get_start_pic():
    """Get start pic from admin data"""
    return admin_data.get('images', {}).get('start', '')

def set_start_pic(url):
    """Set start pic"""
    if 'images' not in admin_data:
        admin_data['images'] = {}
    admin_data['images']['start'] = url
    save_admin_data(admin_data)

def get_image_folder():
    """Get local image folder path"""
    return admin_data.get('images', {}).get('local_folder', 'images/')

def set_image_folder(path):
    """Set local image folder"""
    if 'images' not in admin_data:
        admin_data['images'] = {}
    admin_data['images']['local_folder'] = path
    save_admin_data(admin_data)

def get_random_progress_image():
    """Get a random progress image from links or local folder"""
    images = get_progress_images()
    folder = get_image_folder()
    
    # Collect all sources
    all_sources = list(images)
    
    # Check local folder
    if folder and os.path.isdir(folder):
        try:
            files = [f for f in os.listdir(folder) 
                     if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) 
                     and not f.startswith('.')]
            if files:
                # Add full paths
                all_sources.extend([os.path.join(folder, f) for f in files])
        except Exception:
            pass
    
    if not all_sources:
        return None
    
    return random.choice(all_sources)

@Client.on_message(filters.command("admin") & filters.user(BIMBO_OWNER_ID))
async def admin_panel(client: Client, message: Message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(" Channels", callback_data="admin_channels"),
            InlineKeyboardButton(" Ban Users", callback_data="admin_ban")
        ],
        [
            InlineKeyboardButton(" Statistics", callback_data="admin_stats"),
            InlineKeyboardButton(" Settings", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton(" Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton(" Database", callback_data="admin_database")
        ],
        [
            InlineKeyboardButton(" Premium Users", callback_data="admin_premium"),
            InlineKeyboardButton(" Premium List", callback_data="admin_premium_list")
        ],
        [
            InlineKeyboardButton(" Images", callback_data="admin_images")
        ]
    ])
    
    await message.reply_text(
        " **Admin Panel**\n\n"
        "Welcome to the admin control center.\n"
        "Choose an option below:",
        reply_markup=buttons
    )

@Client.on_callback_query(filters.regex("^admin_"))
async def admin_callback(client: Client, callback_query):
    data = callback_query.data
    
    if data == "admin_channels":
        await show_channels(callback_query)
    elif data == "admin_ban":
        await show_ban_panel(callback_query)
    elif data == "admin_stats":
        await show_stats(callback_query)
    elif data == "admin_settings":
        await show_settings(callback_query)
    elif data == "admin_broadcast":
        await callback_query.answer("Use /broadcast command", show_alert=True)
    elif data == "admin_database":
        await show_database(callback_query)
    elif data == "admin_premium":
        await show_premium_panel(callback_query)
    elif data == "admin_premium_list":
        await show_premium_list(callback_query)
    elif data == "admin_images":
        await show_images_panel(callback_query)
    elif data == "admin_back":
        await show_admin_panel(callback_query)

async def show_admin_panel(callback_query):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(" Channels", callback_data="admin_channels"),
            InlineKeyboardButton(" Ban Users", callback_data="admin_ban")
        ],
        [
            InlineKeyboardButton(" Statistics", callback_data="admin_stats"),
            InlineKeyboardButton(" Settings", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton(" Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton(" Database", callback_data="admin_database")
        ],
        [
            InlineKeyboardButton(" Premium Users", callback_data="admin_premium"),
            InlineKeyboardButton(" Premium List", callback_data="admin_premium_list")
        ],
        [
            InlineKeyboardButton(" Images", callback_data="admin_images")
        ]
    ])
    
    await callback_query.message.edit_text(
        " **Admin Panel**\n\n"
        "Welcome to the admin control center.",
        reply_markup=buttons
    )

async def show_images_panel(callback_query):
    """Show images management panel"""
    progress_imgs = get_progress_images()
    start_pic = get_start_pic()
    local_folder = get_image_folder()
    
    # Check local folder
    local_count = 0
    if local_folder and os.path.isdir(local_folder):
        try:
            local_count = len([f for f in os.listdir(local_folder) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) 
                              and not f.startswith('.')])
        except Exception:
            pass
    
    text = (
        f" **Images Management**\n\n"
        f" **Progress Images:**\n"
        f"  Links: {len(progress_imgs)} images\n"
        f"  Local folder: `{local_folder}` ({local_count} files)\n\n"
        f" **Start Pic:** {start_pic[:50] if start_pic else 'Not set'}...\n\n"
        f" **Commands:**\n"
        f"  `/setprogresspic <link>` - Add progress image\n"
        f"  `/setprogresspics <link1,link2>` - Add multiple\n"
        f"  `/clearprogresspics` - Clear all progress images\n"
        f"  `/setstartpic <link>` - Set start image\n"
        f"  `/setimagefolder <path>` - Set local folder\n"
    )
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(" View Progress Pics", callback_data="admin_view_progress"),
            InlineKeyboardButton(" View Start Pic", callback_data="admin_view_start")
        ],
        [
            InlineKeyboardButton(" Clear Progress", callback_data="admin_clear_progress")
        ],
        [
            InlineKeyboardButton(" Back", callback_data="admin_back")
        ]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_premium_panel(callback_query):
    text = (
        " **Premium Management**\n\n"
        "**Commands:**\n"
        "  `/addpremium <user_id> <days>` - Add premium user\n"
        "  `/removepremium <user_id>` - Remove premium user\n"
        "  `/premiumlist` - List all premium users\n\n"
        "**Example:**\n"
        "`/addpremium 123456789 30` - 30 din premium\n"
        "`/addpremium 123456789 365` - 1 saal premium"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" View Premium List", callback_data="admin_premium_list")],
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_premium_list(callback_query):
    all_premium = premium_manager.get_all_premium_users()
    
    if not all_premium:
        text = "📋 No premium users found."
    else:
        text = " **Premium Users List**\n\n"
        for uid, data in all_premium.items():
            tier = data.get('tier', 'premium')
            expiry = data.get('expiry', 'Lifetime')
            text += f" `{uid}` | {tier} | Exp: {expiry}\n"
        
        if len(text) > 4000:
            text = text[:4000] + "\n\n...(truncated)"
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" Back", callback_data="admin_premium")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_channels(callback_query):
    channels = admin_data.get('channels', [])
    text = " **Channel Management**\n\n"
    
    if channels:
        text += "**Added Channels:**\n"
        for i, channel in enumerate(channels, 1):
            text += f"{i}. {channel.get('name', 'Unknown')} (`{channel.get('id', 'N/A')}`)\n"
    else:
        text += "No channels added yet.\n"
    
    text += "\n**Commands:**\n"
    text += "  `/addchannel <id> <name>` - Add channel\n"
    text += "  `/removechannel <id>` - Remove channel\n"
    text += "  `/listchannels` - List all channels\n"
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_ban_panel(callback_query):
    banned = admin_data.get('banned_users', [])
    text = " **Ban Management**\n\n"
    
    if banned:
        text += f"**Banned Users:** {len(banned)}\n"
        for user_id in banned[:5]:
            text += f"  `{user_id}`\n"
        if len(banned) > 5:
            text += f"... and {len(banned) - 5} more\n"
    else:
        text += "No banned users.\n"
    
    text += "\n**Commands:**\n"
    text += "  `/ban <user_id>` - Ban user\n"
    text += "  `/unban <user_id>` - Unban user\n"
    text += "  `/banlist` - List banned users\n"
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_stats(callback_query):
    try:
        total_users = await bimbo.total_users_count()
    except:
        total_users = "N/A"
    
    premium_count = len(premium_manager.get_all_premium_users())
    
    text = (
        f" **Bot Statistics**\n\n"
        f" Total Users: {total_users}\n"
        f" Premium Users: {premium_count}\n"
        f" Channels: {len(admin_data.get('channels', []))}\n"
        f" Banned Users: {len(admin_data.get('banned_users', []))}\n"
        f" Force Subscribe: {' Enabled' if admin_data['settings'].get('force_sub') else ' Disabled'}\n"
        f" Maintenance: {' ON' if admin_data['settings'].get('maintenance_mode') else ' OFF'}\n"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_settings(callback_query):
    settings = admin_data.get('settings', {})
    force_sub = settings.get('force_sub', False)
    maintenance = settings.get('maintenance_mode', False)
    
    text = (
        f" **Bot Settings**\n\n"
        f" **Force Subscribe:** {' Enabled' if force_sub else ' Disabled'}\n"
        f" **Maintenance Mode:** {' ON' if maintenance else ' OFF'}\n"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'Disable' if force_sub else 'Enable'} Force Sub", callback_data="toggle_forcesub")],
        [InlineKeyboardButton(f"{'Disable' if maintenance else 'Enable'} Maintenance", callback_data="toggle_maintenance")],
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

async def show_database(callback_query):
    from database.access import bimbo as db_access
    try:
        total_users = await db_access.total_users_count()
        db_status = " Connected"
        db_info = f" Total Users in DB: {total_users}\n"
    except Exception as e:
        db_status = f" Error: {e}"
        db_info = ""
    
    try:
        from database.users_chats_db import db as raw_db
        using_fallback = getattr(raw_db, "_use_fb", True)
        if using_fallback:
            db_status = " Fallback (in-memory) - MongoDB NOT connected"
    except Exception:
        pass

    text = (
        f" **Database Information**\n\n"
        f" Database URL: `{str(BIMBO_DATABASE_URL)[:45]}...`\n"
        f" Status: {db_status}\n"
        f"{db_info}"
        f"\n_If status is Fallback, check BIMBO_DATABASE_URL in Koyeb env._"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(" Back", callback_data="admin_back")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("^toggle_"))
async def toggle_settings(client: Client, callback_query):
    data = callback_query.data
    
    if data == "toggle_forcesub":
        admin_data['settings']['force_sub'] = not admin_data['settings'].get('force_sub', False)
        save_admin_data(admin_data)
        await callback_query.answer("Force Subscribe toggled!")
    elif data == "toggle_maintenance":
        admin_data['settings']['maintenance_mode'] = not admin_data['settings'].get('maintenance_mode', False)
        save_admin_data(admin_data)
        await callback_query.answer("Maintenance mode toggled!")
    
    await show_settings(callback_query)

# ── Image management commands ──

@Client.on_message(filters.command("setprogresspic") & filters.user(BIMBO_OWNER_ID))
async def set_progress_pic(client: Client, message: Message):
    """Add a progress image link"""
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/setprogresspic <image_url>`\n\n"
            "Add a progress header image. Use multiple times to add more images.\n"
            "Example: `/setprogresspic https://telegra.ph/file/xxx.jpg`"
        )
        return
    
    url = message.command[1].strip()
    images = get_progress_images()
    images.append(url)
    set_progress_images(images)
    
    await message.reply_text(
        f" Progress image added!\n\n"
        f" Total images: {len(images)}\n"
        f" Added: `{url[:60]}...`"
    )

@Client.on_message(filters.command("setprogresspics") & filters.user(BIMBO_OWNER_ID))
async def set_progress_pics(client: Client, message: Message):
    """Add multiple progress image links (comma separated)"""
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/setprogresspics <url1,url2,url3>`\n\n"
            "Add multiple progress images at once (comma separated)."
        )
        return
    
    urls = [url.strip() for url in message.text.split(None, 1)[1].split(',') if url.strip()]
    if not urls:
        await message.reply_text(" No valid URLs found!")
        return
    
    images = get_progress_images()
    images.extend(urls)
    set_progress_images(images)
    
    await message.reply_text(
        f" Added {len(urls)} progress images!\n\n"
        f" Total: {len(images)} images"
    )

@Client.on_message(filters.command("clearprogresspics") & filters.user(BIMBO_OWNER_ID))
async def clear_progress_pics(client: Client, message: Message):
    """Clear all progress images"""
    set_progress_images([])
    await message.reply_text(" All progress images cleared!")

@Client.on_message(filters.command("listprogresspics") & filters.user(BIMBO_OWNER_ID))
async def list_progress_pics(client: Client, message: Message):
    """List all progress images"""
    images = get_progress_images()
    if not images:
        await message.reply_text(" No progress images set.")
        return
    
    text = " **Progress Images**\n\n"
    for i, img in enumerate(images, 1):
        text += f"{i}. `{img[:60]}...`\n"
    
    await message.reply_text(text)

@Client.on_message(filters.command("setstartpic") & filters.user(BIMBO_OWNER_ID))
async def set_start_pic_cmd(client: Client, message: Message):
    """Set start pic"""
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/setstartpic <image_url>`\n\n"
            "Set the start command image."
        )
        return
    
    url = message.command[1].strip()
    set_start_pic(url)
    await message.reply_text(f" Start pic set to: `{url[:60]}...`")

@Client.on_message(filters.command("setimagefolder") & filters.user(BIMBO_OWNER_ID))
async def set_image_folder_cmd(client: Client, message: Message):
    """Set local image folder"""
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** `/setimagefolder <path>`\n\n"
            "Example: `/setimagefolder images/`"
        )
        return
    
    path = message.command[1].strip()
    if not os.path.isdir(path):
        await message.reply_text(f" Folder not found: `{path}`\n\nPlease create the folder first.")
        return
    
    set_image_folder(path)
    
    # Count files
    files = [f for f in os.listdir(path) 
             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) 
             and not f.startswith('.')]
    
    await message.reply_text(
        f" Image folder set to: `{path}`\n\n"
        f" Found {len(files)} images in folder."
    )

@Client.on_message(filters.command("addchannel") & filters.user(BIMBO_OWNER_ID))
async def add_channel(client: Client, message: Message):
    if len(message.command) < 3:
        await message.reply_text(" **Usage:** `/addchannel <channel_id> <channel_name>`")
        return
    
    channel_id = message.command[1]
    channel_name = " ".join(message.command[2:])
    
    if 'channels' not in admin_data:
        admin_data['channels'] = []
    
    admin_data['channels'].append({
        'id': channel_id,
        'name': channel_name,
        'added_at': datetime.now().isoformat()
    })
    save_admin_data(admin_data)
    
    await message.reply_text(f" **Channel Added**\n\n Name: {channel_name}\n ID: `{channel_id}`")

@Client.on_message(filters.command("removechannel") & filters.user(BIMBO_OWNER_ID))
async def remove_channel(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(" **Usage:** `/removechannel <channel_id>`")
        return
    channel_id = message.command[1]
    if 'channels' in admin_data:
        admin_data['channels'] = [c for c in admin_data['channels'] if c['id'] != channel_id]
        save_admin_data(admin_data)
    await message.reply_text(f" Channel `{channel_id}` removed!")

@Client.on_message(filters.command("listchannels") & filters.user(BIMBO_OWNER_ID))
async def list_channels(client: Client, message: Message):
    channels = admin_data.get('channels', [])
    if not channels:
        await message.reply_text(" No channels added yet.")
        return
    text = " **Added Channels:**\n\n"
    for i, channel in enumerate(channels, 1):
        text += f"{i}. **{channel['name']}**\n   ID: `{channel['id']}`\n\n"
    await message.reply_text(text)

@Client.on_message(filters.command("ban") & filters.user(BIMBO_OWNER_ID))
async def ban_user(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(" **Usage:** `/ban <user_id>`")
        return
    user_id = int(message.command[1])
    if 'banned_users' not in admin_data:
        admin_data['banned_users'] = []
    if user_id not in admin_data['banned_users']:
        admin_data['banned_users'].append(user_id)
        save_admin_data(admin_data)
    await message.reply_text(f" User `{user_id}` has been banned!")

@Client.on_message(filters.command("unban") & filters.user(BIMBO_OWNER_ID))
async def unban_user(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(" **Usage:** `/unban <user_id>`")
        return
    user_id = int(message.command[1])
    if 'banned_users' in admin_data:
        admin_data['banned_users'] = [u for u in admin_data['banned_users'] if u != user_id]
        save_admin_data(admin_data)
    await message.reply_text(f" User `{user_id}` has been unbanned!")

@Client.on_message(filters.command("banlist") & filters.user(BIMBO_OWNER_ID))
async def ban_list(client: Client, message: Message):
    banned = admin_data.get('banned_users', [])
    if not banned:
        await message.reply_text(" No banned users.")
        return
    text = " **Banned Users:**\n\n"
    for user_id in banned:
        text += f"  `{user_id}`\n"
    await message.reply_text(text)

def is_user_banned(user_id: int) -> bool:
    return user_id in admin_data.get('banned_users', [])
