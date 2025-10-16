#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Enhanced Callback Button Handler for Professional Compression System
# Handles all button interactions for quality and encoding settings

import logging
import os
import time
import asyncio
from typing import Optional
from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

try:
    from bot.database import Database
except ImportError:
    Database = None

from bot import (
    DOWNLOAD_LOCATION,
    AUTH_USERS,
    LOG_CHANNEL,
    DATABASE_URL,
    SESSION_NAME
)

# Import from the new message handler
from bot.plugins.incoming_message_fn import (
    USER_SESSIONS,
    CURRENT_PROCESSES,
    handle_quality_selection,
    handle_encoding_setting,
    start_compression_process,
    cleanup_process,
    cleanup_files_and_process,
    QUALITY_PRESETS,
    ENCODING_SETTINGS
)

from bot.helper_funcs.display_progress import humanbytes, TimeFormatter
from bot.helper_funcs.utils import delete_downloads

LOGGER = logging.getLogger(__name__)

async def button(bot: Client, callback_query: CallbackQuery):
    """Enhanced callback button handler for compression system"""
    try:
        cb_data = callback_query.data
        user_id = callback_query.from_user.id
        
        LOGGER.info(f"Callback from user {user_id}: {cb_data}")

        # Handle quality selection
        if cb_data.startswith('quality_'):
            quality = cb_data.replace('quality_', '')
            if quality == "custom":
                await handle_custom_quality_selection(bot, callback_query)
            else:
                await handle_quality_selection(bot, callback_query, quality)

        # Handle encoding settings
        elif cb_data.startswith('setting_'):
            setting_type = cb_data.replace('setting_', '')
            await handle_encoding_setting(bot, callback_query, setting_type)

        # Handle specific setting values
        elif cb_data.startswith('set_'):
            await handle_setting_value_change(bot, callback_query, cb_data)

        # Handle navigation
        elif cb_data == 'back_to_quality':
            await show_quality_selection(bot, callback_query)
        
        elif cb_data == 'back_to_encoding':
            await show_encoding_settings(bot, callback_query)

        # Handle compression control
        elif cb_data == 'start_encoding':
            await start_compression_process(bot, callback_query)

        elif cb_data == 'cancel_compression':
            await handle_cancel_compression(bot, callback_query)

        elif cb_data == 'confirm_cancel':
            await confirm_cancel_compression(bot, callback_query)

        elif cb_data == 'keep_process':
            await callback_query.answer("✅ Process continued.", show_alert=True)

        # Handle other callbacks
        elif cb_data == 'help':
            await show_help_message(bot, callback_query)

        elif cb_data == 'settings':
            await show_user_settings(bot, callback_query)

        elif cb_data == 'status':
            await show_bot_status(bot, callback_query)

        else:
            await callback_query.answer("⚠️ Unknown action!", show_alert=True)

    except Exception as e:
        LOGGER.error(f"Error in button handler: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def handle_custom_quality_selection(bot: Client, callback_query: CallbackQuery):
    """Handle custom quality selection"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]
        session.quality = "custom"

        # Show resolution selection for custom quality
        resolution_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton('🔥 4K (3840x2160)', callback_data='set_resolution_3840x2160'),
                InlineKeyboardButton('📺 1440p (2560x1440)', callback_data='set_resolution_2560x1440')
            ],
            [
                InlineKeyboardButton('🎬 1080p (1920x1080)', callback_data='set_resolution_1920x1080'),
                InlineKeyboardButton('📱 720p (1280x720)', callback_data='set_resolution_1280x720')
            ],
            [
                InlineKeyboardButton('📱 480p (854x480)', callback_data='set_resolution_854x480'),
                InlineKeyboardButton('📱 360p (640x360)', callback_data='set_resolution_640x360')
            ],
            [
                InlineKeyboardButton('🔄 Keep Original', callback_data='set_resolution_original'),
                InlineKeyboardButton('🔙 Back', callback_data='back_to_quality')
            ]
        ])

        await callback_query.edit_message_text(
            f"⚙️ **Custom Quality Selected**\n\n"
            f"📏 **Select Output Resolution:**\n\n"
            f"🔹 Higher resolution = Better quality + Larger file\n"
            f"🔹 Lower resolution = Faster encoding + Smaller file\n"
            f"🔹 Original = Keep source resolution",
            reply_markup=resolution_keyboard
        )

    except Exception as e:
        LOGGER.error(f"Error in custom quality selection: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def handle_setting_value_change(bot: Client, callback_query: CallbackQuery, cb_data: str):
    """Handle specific setting value changes"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]

        # Parse callback data
        if cb_data.startswith('set_crf_'):
            crf_value = int(cb_data.replace('set_crf_', ''))
            session.crf = crf_value
            await callback_query.answer(f"✅ CRF set to {crf_value}")

        elif cb_data.startswith('set_audio_bitrate_'):
            bitrate = cb_data.replace('set_audio_bitrate_', '')
            session.audio_bitrate = bitrate
            await callback_query.answer(f"✅ Audio bitrate set to {bitrate}")

        elif cb_data.startswith('set_preset_'):
            preset = cb_data.replace('set_preset_', '')
            if preset:  # Check if preset is not empty
                session.preset = preset
                await callback_query.answer(f"✅ Preset set to {preset}")

        elif cb_data.startswith('set_video_codec_'):
            codec = cb_data.replace('set_video_codec_', '')
            session.video_codec = codec
            await callback_query.answer(f"✅ Video codec set to {codec}")

        elif cb_data.startswith('set_audio_codec_'):
            codec = cb_data.replace('set_audio_codec_', '')
            session.audio_codec = codec
            await callback_query.answer(f"✅ Audio codec set to {codec}")

        elif cb_data.startswith('set_pixel_format_'):
            pixel_format = cb_data.replace('set_pixel_format_', '')
            session.pixel_format = pixel_format
            await callback_query.answer(f"✅ Pixel format set to {pixel_format}")

        elif cb_data.startswith('set_resolution_'):
            resolution = cb_data.replace('set_resolution_', '')
            if resolution == 'original':
                session.resolution = None
                await callback_query.answer("✅ Resolution set to Original")
            else:
                session.resolution = resolution
                await callback_query.answer(f"✅ Resolution set to {resolution}")

        # Return to encoding settings after change
        await show_encoding_settings(bot, callback_query)

    except Exception as e:
        LOGGER.error(f"Error changing setting value: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def show_quality_selection(bot: Client, callback_query: CallbackQuery):
    """Show quality selection menu"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]
        video_message = session.video_message
        video = video_message.video or video_message.document

        quality_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton('🔥 1080p', callback_data='quality_1080p'),
                InlineKeyboardButton('🔥 1080p HEVC', callback_data='quality_1080p_hevc')
            ],
            [
                InlineKeyboardButton('⭐ 720p', callback_data='quality_720p'),
                InlineKeyboardButton('⭐ 720p HEVC', callback_data='quality_720p_hevc')
            ],
            [
                InlineKeyboardButton('📱 480p', callback_data='quality_480p'),
                InlineKeyboardButton('📱 480p HEVC', callback_data='quality_480p_hevc')
            ],
            [
                InlineKeyboardButton('⚙️ Custom +', callback_data='quality_custom'),
                InlineKeyboardButton('❌ Cancel', callback_data='cancel_compression')
            ]
        ])

        await callback_query.edit_message_text(
            f"🎬 **Video Received!**\n\n"
            f"📄 **File:** {video.file_name or 'Unknown'}\n"
            f"📏 **Size:** {humanbytes(video.file_size)}\n"
            f"⏱️ **Duration:** {TimeFormatter((video.duration or 0) * 1000)}\n\n"
            f"🎯 **Select Compression Quality:**",
            reply_markup=quality_keyboard
        )

    except Exception as e:
        LOGGER.error(f"Error showing quality selection: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def show_encoding_settings(bot: Client, callback_query: CallbackQuery):
    """Show encoding settings menu"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]

        # Create encoding settings keyboard
        encoding_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f'CRF: {session.crf}', callback_data='setting_crf'),
                InlineKeyboardButton(f'Audio: {session.audio_bitrate}', callback_data='setting_audio_bitrate')
            ],
            [
                InlineKeyboardButton(f'Resolution: {session.resolution or "Original"}', callback_data='setting_resolution'),
                InlineKeyboardButton(f'Preset: {session.preset}', callback_data='setting_preset')
            ],
            [
                InlineKeyboardButton(f'Video Codec: {session.video_codec}', callback_data='setting_video_codec'),
                InlineKeyboardButton(f'Audio Codec: {session.audio_codec}', callback_data='setting_audio_codec')
            ],
            [
                InlineKeyboardButton(f'Pixel Format: {session.pixel_format}', callback_data='setting_pixel_format')
            ],
            [
                InlineKeyboardButton('🔙 Back', callback_data='back_to_quality'),
                InlineKeyboardButton('🚀 Start Encode', callback_data='start_encoding')
            ]
        ])

        quality_name = session.quality.replace('_', ' ').upper() if session.quality else "CUSTOM"
        
        await callback_query.edit_message_text(
            f"🎯 **Quality Selected:** {quality_name}\n\n"
            f"⚙️ **Current Encoding Settings:**\n"
            f"🔹 **CRF:** {session.crf} (Lower = Better Quality)\n"
            f"🔹 **Audio Bitrate:** {session.audio_bitrate}\n"
            f"🔹 **Resolution:** {session.resolution or 'Original'}\n"
            f"🔹 **Preset:** {session.preset} (Slower = Better Compression)\n"
            f"🔹 **Video Codec:** {session.video_codec}\n"
            f"🔹 **Audio Codec:** {session.audio_codec}\n"
            f"🔹 **Pixel Format:** {session.pixel_format}\n\n"
            f"📝 **Adjust settings or start encoding:**",
            reply_markup=encoding_keyboard
        )

    except Exception as e:
        LOGGER.error(f"Error showing encoding settings: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def handle_cancel_compression(bot: Client, callback_query: CallbackQuery):
    """Handle compression cancellation"""
    try:
        user_id = callback_query.from_user.id

        # If user has an active process, ask for confirmation
        if user_id in CURRENT_PROCESSES:
            await callback_query.edit_message_text(
                "🗑️ **Cancel Active Compression?**\n\n"
                "⚠️ This will stop the current compression process!\n"
                "❌ This action cannot be undone!",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton('✅ Yes, Cancel', callback_data='confirm_cancel'),
                        InlineKeyboardButton('❌ No, Continue', callback_data='keep_process')
                    ]
                ])
            )
        else:
            # Just clean up session
            if user_id in USER_SESSIONS:
                del USER_SESSIONS[user_id]
            
            await callback_query.edit_message_text(
                "❌ **Process Cancelled**\n\n"
                "🔄 You can send a new video anytime to start again."
            )

    except Exception as e:
        LOGGER.error(f"Error handling cancel: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def confirm_cancel_compression(bot: Client, callback_query: CallbackQuery):
    """Confirm and execute compression cancellation"""
    try:
        user_id = callback_query.from_user.id

        # Cancel active process
        if user_id in CURRENT_PROCESSES:
            del CURRENT_PROCESSES[user_id]

        # Clean up session
        if user_id in USER_SESSIONS:
            del USER_SESSIONS[user_id]

        # Clean up any temporary files
        try:
            status_file = os.path.join(DOWNLOAD_LOCATION, "status.json")
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    status_data = json.load(f)
                    if status_data.get('user_id') == user_id:
                        # Kill FFmpeg process if running
                        pid = status_data.get('pid')
                        if pid:
                            try:
                                os.kill(pid, 9)  # Force kill
                                LOGGER.info(f"Killed process {pid} for user {user_id}")
                            except:
                                pass
                        os.remove(status_file)
        except:
            pass

        await delete_downloads()

        await callback_query.edit_message_text(
            "✅ **Compression Cancelled Successfully**\n\n"
            "🔄 You can send a new video anytime to start again."
        )

        # Log cancellation
        LOGGER.info(f"Compression cancelled by user {user_id}")

    except Exception as e:
        LOGGER.error(f"Error confirming cancel: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def show_help_message(bot: Client, callback_query: CallbackQuery):
    """Show help message"""
    try:
        help_text = (
            "📖 **How to Use Enhanced Video Compressor**\n\n"
            "🎬 **Step 1:** Send me any video file (up to 2GB)\n"
            "🎯 **Step 2:** Select quality preset (1080p, 720p, 480p, etc.)\n"
            "⚙️ **Step 3:** Customize encoding settings if needed\n"
            "🚀 **Step 4:** Start encoding and wait for result\n\n"
            "🔹 **Quality Presets:**\n"
            "• **1080p/720p/480p:** Standard H.264 encoding\n"
            "• **HEVC versions:** Better compression, smaller files\n"
            "• **Custom:** Full control over all settings\n\n"
            "🔹 **Encoding Settings:**\n"
            "• **CRF:** Quality control (15=best, 30=lowest)\n"
            "• **Preset:** Speed vs compression trade-off\n"
            "• **Codec:** H.264 (compatible) or H.265 (efficient)\n\n"
            "💡 **Tips:**\n"
            "• Lower CRF = better quality but larger files\n"
            "• Slower presets = better compression\n"
            "• HEVC codec = 50% smaller files\n"
            "• Keep original resolution for best quality"
        )

        await callback_query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('🔙 Back', callback_data='back_to_start')
            ]])
        )

    except Exception as e:
        LOGGER.error(f"Error showing help: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def show_user_settings(bot: Client, callback_query: CallbackQuery):
    """Show user settings"""
    try:
        user_id = callback_query.from_user.id
        
        # Get user stats from database if available
        user_stats = "📊 **Your Statistics:**\n\n"
        
        try:
            from bot.database import Database
            if Database and DATABASE_URL:
                db = Database(DATABASE_URL, SESSION_NAME)
                user = await db.get_user(user_id)
                if user:
                    user_stats += (
                        f"🎬 **Total Compressions:** {user.get('total_compressions', 0)}\n"
                        f"📦 **Data Processed:** {humanbytes(user.get('total_size_compressed', 0))}\n"
                        f"📅 **Member Since:** {user.get('join_date', 'Unknown')}\n"
                        f"⏰ **Last Active:** {user.get('last_active', 'Unknown')}\n"
                    )
                else:
                    user_stats += "📝 No statistics available yet."
        except:
            user_stats += "📝 Statistics temporarily unavailable."

        settings_text = (
            f"⚙️ **User Settings**\n\n"
            f"{user_stats}\n"
            f"🔹 **Default Quality:** Medium (can be customized per video)\n"
            f"🔹 **Progress Updates:** Enabled\n"
            f"🔹 **Notifications:** Enabled\n\n"
            f"💡 **Pro Tips:**\n"
            f"• Use HEVC for better compression\n"
            f"• Lower CRF for higher quality\n"
            f"• Slower presets for smaller files"
        )

        await callback_query.edit_message_text(
            settings_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('🔙 Back', callback_data='back_to_start')
            ]])
        )

    except Exception as e:
        LOGGER.error(f"Error showing settings: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def show_bot_status(bot: Client, callback_query: CallbackQuery):
    """Show bot status"""
    try:
        # Count active processes
        active_compressions = len(CURRENT_PROCESSES)
        active_sessions = len(USER_SESSIONS)
        
        # Get system info
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status_text = (
            f"📊 **Bot Status**\n\n"
            f"🔹 **Active Compressions:** {active_compressions}\n"
            f"🔹 **Active Sessions:** {active_sessions}\n"
            f"🔹 **System Load:** {cpu_percent:.1f}%\n"
            f"🔹 **Memory Usage:** {memory.percent:.1f}%\n"
            f"🔹 **Disk Space:** {(disk.used / disk.total * 100):.1f}% used\n\n"
            f"⚡ **Performance:**\n"
            f"• Average compression time: 2-5 minutes\n"
            f"• Supported formats: MP4, MKV, AVI, MOV, WEBM\n"
            f"• Max file size: {humanbytes(TG_MAX_FILE_SIZE)}\n"
            f"• Quality presets: 6 options + custom\n\n"
            f"✅ **All systems operational!**"
        )

        await callback_query.edit_message_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('🔄 Refresh', callback_data='status'),
                InlineKeyboardButton('🔙 Back', callback_data='back_to_start')
            ]])
        )

    except Exception as e:
        LOGGER.error(f"Error showing status: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

# Handle special navigation callbacks
async def handle_back_to_start(bot: Client, callback_query: CallbackQuery):
    """Handle back to start navigation"""
    try:
        from bot.localisation import Localisation
        
        await callback_query.edit_message_text(
            Localisation.START_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton('📖 Help', callback_data='help'),
                    InlineKeyboardButton('⚙️ Settings', callback_data='settings')
                ],
                [
                    InlineKeyboardButton('📊 Status', callback_data='status')
                ],
                [
                    InlineKeyboardButton('🔗 Updates Channel', url='https://t.me/Discovery_Updates'),
                    InlineKeyboardButton('💬 Support Group', url='https://t.me/linux_repo')
                ]
            ])
        )
    except Exception as e:
        LOGGER.error(f"Error handling back to start: {e}")

# Additional callback for back_to_start
async def handle_additional_callbacks(bot: Client, callback_query: CallbackQuery):
    """Handle additional callback patterns"""
    cb_data = callback_query.data
    
    if cb_data == 'back_to_start':
        await handle_back_to_start(bot, callback_query)
    elif cb_data.startswith('set_resolution_'):
        await handle_setting_value_change(bot, callback_query, cb_data)
    elif cb_data == 'setting_resolution':
        await handle_custom_quality_selection(bot, callback_query)

# Update the main button function to handle additional cases
async def button_enhanced(bot: Client, callback_query: CallbackQuery):
    """Main enhanced button handler with all cases"""
    try:
        await callback_query.answer()  # Acknowledge the callback
        
        # Handle all callback types
        await button(bot, callback_query)
        
        # Handle additional cases
        await handle_additional_callbacks(bot, callback_query)
        
    except Exception as e:
        LOGGER.error(f"Error in enhanced button handler: {e}")
        try:
            await callback_query.answer("❌ An error occurred!", show_alert=True)
        except:
            pass

# Export the main button handler
__all__ = ['button_enhanced']
