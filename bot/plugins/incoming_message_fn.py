#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Enhanced Incoming Message Handler with Button-Based Compression System
# Implements professional quality and encoding settings selection

import datetime
import logging
import os
import time
import re
import asyncio
import json
from typing import Optional, Dict, Any
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant, UsernameNotOccupied

try:
    from bot.database import Database
except ImportError:
    Database = None

from bot.localisation import Localisation
from bot import (
    DOWNLOAD_LOCATION,
    AUTH_USERS,
    LOG_CHANNEL,
    UPDATES_CHANNEL,
    DATABASE_URL,
    SESSION_NAME,
    ALLOWED_FILE_TYPES,
    TG_MAX_FILE_SIZE
)

from bot.helper_funcs.ffmpeg import (
    convert_video,
    media_info,
    take_screen_shot
)

from bot.helper_funcs.display_progress import (
    progress_for_pyrogram,
    TimeFormatter,
    humanbytes
)

from bot.helper_funcs.utils import (
    delete_downloads,
    ValidationUtils
)

LOGGER = logging.getLogger(__name__)

# Initialize database if available
db = None
if Database and DATABASE_URL:
    try:
        db = Database(DATABASE_URL, SESSION_NAME)
    except Exception as e:
        LOGGER.error(f"Database initialization failed: {e}")

# Track current processes and user selections
CURRENT_PROCESSES = {}
USER_SESSIONS = {}

class CompressionSettings:
    """Store user's compression settings"""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.video_message = None
        self.quality = None
        self.resolution = None
        self.video_codec = "libx264"
        self.audio_codec = "aac"
        self.preset = "medium"
        self.crf = 23
        self.audio_bitrate = "128k"
        self.pixel_format = "yuv420p"
        self.created_at = time.time()

# Quality presets mapping
QUALITY_PRESETS = {
    "1080p": {"resolution": "1920x1080", "crf": 18, "preset": "slow"},
    "1080p_hevc": {"resolution": "1920x1080", "crf": 20, "preset": "medium", "codec": "libx265"},
    "720p": {"resolution": "1280x720", "crf": 20, "preset": "medium"},
    "720p_hevc": {"resolution": "1280x720", "crf": 22, "preset": "medium", "codec": "libx265"},
    "480p": {"resolution": "854x480", "crf": 23, "preset": "fast"},
    "480p_hevc": {"resolution": "854x480", "crf": 25, "preset": "fast", "codec": "libx265"},
    "360p": {"resolution": "640x360", "crf": 25, "preset": "fast"},
}

ENCODING_SETTINGS = {
    "crf_options": [15, 18, 20, 23, 25, 28, 30],
    "audio_bitrates": ["64k", "96k", "128k", "192k", "256k"],
    "presets": ["veryslow", "slower", "slow", "medium", "fast", "faster", "ultrafast"],
    "video_codecs": ["libx264", "libx265"],
    "audio_codecs": ["aac", "libmp3lame", "copy"],
    "pixel_formats": ["yuv420p", "yuv444p", "yuv420p10le"]
}

async def incoming_start_message_f(bot: Client, update: Message):
    """Enhanced /start command handler"""
    try:
        # Add user to database if available
        if db and not await db.is_user_exist(update.from_user.id):
            await db.add_user(
                update.from_user.id,
                update.from_user.username,
                update.from_user.first_name
            )

        # Update last activity
        if db:
            await db.update_user_activity(update.from_user.id)

        # Check force subscription
        if UPDATES_CHANNEL and not await check_subscription(bot, update):
            return

        # Send enhanced start message
        await bot.send_message(
            chat_id=update.chat.id,
            text=Localisation.START_TEXT,
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
            ]),
            reply_to_message_id=update.id
        )

    except Exception as e:
        LOGGER.error(f"Error in start handler: {e}")
        await update.reply_text("❌ An error occurred. Please try again later.")

async def handle_video_message(bot: Client, update: Message):
    """Handle incoming video messages and show quality selection"""
    try:
        # Check if user exists and update activity
        if db and not await db.is_user_exist(update.from_user.id):
            await db.add_user(
                update.from_user.id,
                update.from_user.username,
                update.from_user.first_name
            )

        if db:
            await db.update_user_activity(update.from_user.id)

        # Check subscription
        if UPDATES_CHANNEL and not await check_subscription(bot, update):
            return

        # Validate video file
        video = update.video or update.document
        if not video:
            return

        if not await validate_video_file(video, update):
            return

        # Check if user has active process
        if update.from_user.id in CURRENT_PROCESSES:
            await update.reply_text(
                "⚠️ You already have a compression in progress!\n"
                "⏰ Please wait for it to complete."
            )
            return

        # Store video message in user session
        session = CompressionSettings(update.from_user.id)
        session.video_message = update
        USER_SESSIONS[update.from_user.id] = session

        # Send quality selection keyboard
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

        await update.reply_text(
            f"🎬 **Video Received!**\n\n"
            f"📄 **File:** {video.file_name or 'Unknown'}\n"
            f"📏 **Size:** {humanbytes(video.file_size)}\n"
            f"⏱️ **Duration:** {TimeFormatter((video.duration or 0) * 1000)}\n\n"
            f"🎯 **Select Compression Quality:**",
            reply_markup=quality_keyboard
        )

    except Exception as e:
        LOGGER.error(f"Error handling video message: {e}")
        await update.reply_text("❌ An error occurred while processing your video.")

async def handle_quality_selection(bot: Client, callback_query, quality: str):
    """Handle quality selection from user"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]
        session.quality = quality

        # Set preset values based on quality selection
        if quality in QUALITY_PRESETS:
            preset = QUALITY_PRESETS[quality]
            session.resolution = preset["resolution"]
            session.crf = preset["crf"]
            session.preset = preset["preset"]
            
            if "codec" in preset and preset["codec"] == "libx265":
                session.video_codec = "libx265"

        # Show encoding settings keyboard
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

        quality_name = quality.replace('_', ' ').upper()
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
        LOGGER.error(f"Error in quality selection: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def handle_encoding_setting(bot: Client, callback_query, setting_type: str):
    """Handle encoding setting selection"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        session = USER_SESSIONS[user_id]
        
        if setting_type == "crf":
            # Show CRF options
            keyboard = []
            for i, crf_val in enumerate(ENCODING_SETTINGS["crf_options"]):
                if i % 2 == 0:
                    if i + 1 < len(ENCODING_SETTINGS["crf_options"]):
                        keyboard.append([
                            InlineKeyboardButton(f'CRF {crf_val}', callback_data=f'set_crf_{crf_val}'),
                            InlineKeyboardButton(f'CRF {ENCODING_SETTINGS["crf_options"][i+1]}', 
                                               callback_data=f'set_crf_{ENCODING_SETTINGS["crf_options"][i+1]}')
                        ])
                    else:
                        keyboard.append([
                            InlineKeyboardButton(f'CRF {crf_val}', callback_data=f'set_crf_{crf_val}')
                        ])
            
            keyboard.append([InlineKeyboardButton('🔙 Back', callback_data='back_to_encoding')])
            
            await callback_query.edit_message_text(
                f"🎛️ **Select CRF Value:**\n\n"
                f"🔹 **CRF 15-18:** Near Lossless (Large files)\n"
                f"🔹 **CRF 20-23:** High Quality (Recommended)\n"
                f"🔹 **CRF 24-28:** Good Quality (Smaller files)\n"
                f"🔹 **CRF 28+:** Lower Quality (Very small files)\n\n"
                f"📝 **Current:** {session.crf}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif setting_type == "audio_bitrate":
            # Show audio bitrate options
            keyboard = []
            for i, bitrate in enumerate(ENCODING_SETTINGS["audio_bitrates"]):
                if i % 2 == 0:
                    if i + 1 < len(ENCODING_SETTINGS["audio_bitrates"]):
                        keyboard.append([
                            InlineKeyboardButton(bitrate, callback_data=f'set_audio_bitrate_{bitrate}'),
                            InlineKeyboardButton(ENCODING_SETTINGS["audio_bitrates"][i+1], 
                                               callback_data=f'set_audio_bitrate_{ENCODING_SETTINGS["audio_bitrates"][i+1]}')
                        ])
                    else:
                        keyboard.append([
                            InlineKeyboardButton(bitrate, callback_data=f'set_audio_bitrate_{bitrate}')
                        ])
            
            keyboard.append([InlineKeyboardButton('🔙 Back', callback_data='back_to_encoding')])
            
            await callback_query.edit_message_text(
                f"🎵 **Select Audio Bitrate:**\n\n"
                f"📝 **Current:** {session.audio_bitrate}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif setting_type == "preset":
            # Show preset options
            keyboard = []
            for i, preset in enumerate(ENCODING_SETTINGS["presets"]):
                if i % 2 == 0:
                    if i + 1 < len(ENCODING_SETTINGS["presets"]):
                        keyboard.append([
                            InlineKeyboardButton(preset, callback_data=f'set_preset_{preset}'),
                            InlineKeyboardButton(ENCODING_SETTINGS["presets"][i+1] if i+1 < len(ENCODING_SETTINGS["presets"]) else "", 
                                               callback_data=f'set_preset_{ENCODING_SETTINGS["presets"][i+1] if i+1 < len(ENCODING_SETTINGS["presets"]) else ""}')
                        ])
                    else:
                        keyboard.append([
                            InlineKeyboardButton(preset, callback_data=f'set_preset_{preset}')
                        ])
            
            keyboard.append([InlineKeyboardButton('🔙 Back', callback_data='back_to_encoding')])
            
            await callback_query.edit_message_text(
                f"⚙️ **Select Encoding Preset:**\n\n"
                f"🔹 **ultrafast/faster/fast:** Quick encoding\n"
                f"🔹 **medium:** Balanced (Recommended)\n"
                f"🔹 **slow/slower/veryslow:** Better compression\n\n"
                f"📝 **Current:** {session.preset}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif setting_type == "video_codec":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton('H.264 (libx264)', callback_data='set_video_codec_libx264'),
                    InlineKeyboardButton('H.265 (libx265)', callback_data='set_video_codec_libx265')
                ],
                [InlineKeyboardButton('🔙 Back', callback_data='back_to_encoding')]
            ])
            
            await callback_query.edit_message_text(
                f"📹 **Select Video Codec:**\n\n"
                f"🔹 **H.264 (libx264):** Universal compatibility\n"
                f"🔹 **H.265 (libx265):** Better compression, newer devices\n\n"
                f"📝 **Current:** {session.video_codec}",
                reply_markup=keyboard
            )

        elif setting_type == "audio_codec":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton('AAC', callback_data='set_audio_codec_aac'),
                    InlineKeyboardButton('MP3', callback_data='set_audio_codec_libmp3lame')
                ],
                [
                    InlineKeyboardButton('Copy (No Re-encode)', callback_data='set_audio_codec_copy')
                ],
                [InlineKeyboardButton('🔙 Back', callback_data='back_to_encoding')]
            ])
            
            await callback_query.edit_message_text(
                f"🎵 **Select Audio Codec:**\n\n"
                f"🔹 **AAC:** Best quality and compatibility\n"
                f"🔹 **MP3:** Universal compatibility\n"
                f"🔹 **Copy:** Keep original audio (fastest)\n\n"
                f"📝 **Current:** {session.audio_codec}",
                reply_markup=keyboard
            )

    except Exception as e:
        LOGGER.error(f"Error in encoding setting: {e}")
        await callback_query.answer("❌ An error occurred.", show_alert=True)

async def start_compression_process(bot: Client, callback_query):
    """Start the actual compression process"""
    try:
        user_id = callback_query.from_user.id
        
        if user_id not in USER_SESSIONS:
            await callback_query.answer("❌ Session expired. Please send video again.", show_alert=True)
            return

        if user_id in CURRENT_PROCESSES:
            await callback_query.answer("❌ You already have an active compression!", show_alert=True)
            return

        session = USER_SESSIONS[user_id]
        video_message = session.video_message
        video = video_message.video or video_message.document

        # Mark user as having active process
        CURRENT_PROCESSES[user_id] = True

        # Update message to show compression started
        await callback_query.edit_message_text(
            f"🚀 **Encoding Started!**\n\n"
            f"⚙️ **Settings:**\n"
            f"🔹 **Quality:** {session.quality}\n"
            f"🔹 **CRF:** {session.crf}\n"
            f"🔹 **Preset:** {session.preset}\n"
            f"🔹 **Resolution:** {session.resolution or 'Original'}\n"
            f"🔹 **Codec:** {session.video_codec}\n\n"
            f"📥 **Starting download...**"
        )

        # Generate file paths
        user_file = f"{user_id}_{int(time.time())}.mkv"
        saved_file_path = os.path.join(DOWNLOAD_LOCATION, user_file)

        # Start download
        d_start = time.time()
        
        try:
            video_download = await bot.download_media(
                message=video_message,
                file_name=saved_file_path,
                progress=progress_for_pyrogram,
                progress_args=(
                    "Downloading",
                    callback_query.message,
                    d_start,
                    bot
                )
            )

            if not video_download or not os.path.exists(video_download):
                await cleanup_process(user_id, callback_query.message, None, "Download failed")
                return

        except Exception as e:
            LOGGER.error(f"Download error: {e}")
            await cleanup_process(user_id, callback_query.message, None, f"Download failed: {e}")
            return

        # Get media info
        duration, bitrate = await media_info(saved_file_path)
        if duration is None:
            await cleanup_process(user_id, callback_query.message, None, "Invalid video file")
            return

        # Generate thumbnail
        thumb_image_path = await take_screen_shot(
            saved_file_path,
            os.path.dirname(saved_file_path),
            duration / 2
        )

        # Start compression with custom settings
        await callback_query.message.edit_text(
            f"🎬 **Compressing Video...**\n\n"
            f"⚙️ **Using your custom settings**\n"
            f"⏳ **Please wait...**"
        )

        c_start = time.time()
        
        # Use custom compression function with user settings
        compressed_file = await convert_video_with_custom_settings(
            saved_file_path,
            DOWNLOAD_LOCATION,
            duration,
            bot,
            callback_query.message,
            session
        )

        if not compressed_file or not os.path.exists(compressed_file):
            await cleanup_process(user_id, callback_query.message, None, "Compression failed")
            return

        # Upload compressed file
        await callback_query.message.edit_text(
            f"📤 **Uploading compressed video...**\n"
            f"⏳ **Please wait...**"
        )

        u_start = time.time()
        
        # Calculate compression stats
        original_size = os.path.getsize(saved_file_path)
        compressed_size = os.path.getsize(compressed_file)
        compression_ratio = ((original_size - compressed_size) / original_size) * 100

        caption = (
            f"✅ **Compression Completed!**\n\n"
            f"📊 **Statistics:**\n"
            f"🔹 **Original:** {humanbytes(original_size)}\n"
            f"🔹 **Compressed:** {humanbytes(compressed_size)}\n"
            f"🔹 **Saved:** {compression_ratio:.1f}%\n"
            f"🔹 **Quality:** {session.quality}\n"
            f"🔹 **CRF:** {session.crf}\n"
            f"🔹 **Codec:** {session.video_codec}\n\n"
            f"⏱️ **Processing Time:** {TimeFormatter((time.time() - d_start) * 1000)}"
        )

        upload = await bot.send_video(
            chat_id=callback_query.message.chat.id,
            video=compressed_file,
            caption=caption,
            supports_streaming=True,
            duration=int(duration),
            thumb=thumb_image_path,
            reply_to_message_id=video_message.id,
            progress=progress_for_pyrogram,
            progress_args=(
                "Uploading",
                callback_query.message,
                u_start,
                bot
            )
        )

        if upload:
            # Update database stats
            if db:
                try:
                    await db.increment_user_compression(user_id, original_size)
                except:
                    pass

            # Delete progress message
            await callback_query.message.delete()
            
            # Log success
            LOGGER.info(f"Compression completed successfully for user {user_id}")

        # Cleanup
        await cleanup_files_and_process(user_id, [saved_file_path, compressed_file, thumb_image_path])

    except Exception as e:
        LOGGER.error(f"Error in compression process: {e}")
        if user_id in CURRENT_PROCESSES:
            del CURRENT_PROCESSES[user_id]
        await callback_query.message.edit_text("❌ An error occurred during compression.")

async def convert_video_with_custom_settings(video_file, output_directory, total_time, bot, message, session):
    """Convert video with custom user settings"""
    try:
        out_put_file_name = os.path.join(output_directory, f"{int(time.time())}.mp4")
        progress_file = os.path.join(output_directory, "progress.txt")
        
        with open(progress_file, 'w') as f:
            pass

        # Build FFmpeg command with user settings
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "quiet",
            "-progress", progress_file,
            "-i", video_file,
            "-c:v", session.video_codec,
            "-preset", session.preset,
            "-crf", str(session.crf),
            "-pix_fmt", session.pixel_format
        ]

        # Add resolution if specified
        if session.resolution and session.resolution != "Original":
            cmd.extend(["-s", session.resolution])

        # Add audio settings
        if session.audio_codec == "copy":
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-c:a", session.audio_codec, "-b:a", session.audio_bitrate])

        # Add output optimizations
        cmd.extend(["-movflags", "+faststart", "-y", out_put_file_name])

        LOGGER.info(f"FFmpeg command: {' '.join(cmd)}")

        # Start process
        start_time = time.time()
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        LOGGER.info(f"Compression process started: {process.pid}")

        # Monitor progress
        while process.returncode is None:
            await asyncio.sleep(3)
            
            try:
                if not os.path.exists(progress_file):
                    continue
                    
                with open(progress_file, 'r') as file:
                    text = file.read()

                # Parse progress
                time_match = re.findall(r"out_time_ms=(\d+)", text)
                progress_match = re.findall(r"progress=(\w+)", text)
                speed_match = re.findall(r"speed=([\d.]+)", text)

                if progress_match and progress_match[-1] == "end":
                    LOGGER.info("Compression completed")
                    break

                if time_match and total_time > 0:
                    elapsed_time = int(time_match[-1]) / 1000000
                    percentage = min(int(elapsed_time * 100 / total_time), 100)

                    # Calculate ETA
                    if speed_match and float(speed_match[-1]) > 0:
                        remaining_time = (total_time - elapsed_time) / float(speed_match[-1])
                        eta = TimeFormatter(int(remaining_time * 1000)) if remaining_time > 0 else "-"
                    else:
                        eta = "-"

                    # Update progress
                    execution_time = TimeFormatter((time.time() - start_time) * 1000)
                    stats = (
                        f"🎬 **Compressing Video** ({session.quality})\n\n"
                        f"📊 **Progress:** {percentage}%\n"
                        f"⏰ **ETA:** {eta}\n"
                        f"⏱️ **Elapsed:** {execution_time}\n"
                        f"🎯 **CRF:** {session.crf}\n"
                        f"⚙️ **Preset:** {session.preset}\n"
                        f"📹 **Codec:** {session.video_codec}"
                    )

                    try:
                        await message.edit_text(
                            text=stats,
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton('❌ Cancel', callback_data='cancel_compression')
                            ]])
                        )
                    except:
                        pass

            except Exception as e:
                LOGGER.error(f"Progress monitoring error: {e}")
                continue

        # Wait for completion
        stdout, stderr = await process.communicate()

        # Cleanup
        try:
            if os.path.exists(progress_file):
                os.remove(progress_file)
        except:
            pass

        # Check result
        if os.path.exists(out_put_file_name) and os.path.getsize(out_put_file_name) > 0:
            LOGGER.info(f"Compression successful: {out_put_file_name}")
            return out_put_file_name
        else:
            LOGGER.error("Output file not created or empty")
            return None

    except Exception as e:
        LOGGER.error(f"Custom video conversion error: {e}")
        return None

# Keep existing helper functions...
async def check_subscription(bot: Client, update: Message) -> bool:
    """Check if user is subscribed to updates channel"""
    try:
        user = await bot.get_chat_member(UPDATES_CHANNEL, update.from_user.id)
        if user.status == "kicked":
            await update.reply_text(
                "🚫 **You are banned from the updates channel.**\n"
                "📞 Contact support group for assistance.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('💬 Support Group', url='https://t.me/linux_repo')
                ]])
            )
            return False
    except UserNotParticipant:
        await update.reply_text(
            "📢 **Please join our updates channel to use this bot!**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    '🔗 Join Updates Channel',
                    url=f'https://t.me/{UPDATES_CHANNEL}'
                )
            ]])
        )
        return False
    except Exception as e:
        LOGGER.error(f"Error checking subscription: {e}")
        return False

    return True

async def validate_video_file(video, update: Message) -> bool:
    """Validate video file for compression"""
    if video.file_size > TG_MAX_FILE_SIZE:
        max_size_mb = TG_MAX_FILE_SIZE // (1024 * 1024)
        await update.reply_text(
            f"❌ **File too large!**\n\n"
            f"📏 **Size:** {humanbytes(video.file_size)}\n"
            f"🔢 **Limit:** {max_size_mb}MB"
        )
        return False

    if hasattr(video, 'file_name') and video.file_name:
        if not ValidationUtils.validate_file_extension(video.file_name, ALLOWED_FILE_TYPES):
            await update.reply_text("❌ **Unsupported file format!**")
            return False

    return True

async def cleanup_process(user_id: int, sent_message, log_message, reason: str):
    """Cleanup failed process"""
    try:
        if user_id in CURRENT_PROCESSES:
            del CURRENT_PROCESSES[user_id]
        
        if user_id in USER_SESSIONS:
            del USER_SESSIONS[user_id]

        await sent_message.edit_text(f"❌ **Process Failed**\n\n🔍 **Reason:** {reason}")
        await delete_downloads()

    except Exception as e:
        LOGGER.error(f"Cleanup error: {e}")

async def cleanup_files_and_process(user_id: int, files: list):
    """Cleanup files and process"""
    try:
        if user_id in CURRENT_PROCESSES:
            del CURRENT_PROCESSES[user_id]
        
        if user_id in USER_SESSIONS:
            del USER_SESSIONS[user_id]

        for file_path in files:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

        await delete_downloads()

    except Exception as e:
        LOGGER.error(f"File cleanup error: {e}")

# Legacy function - Remove /compress command, now handled by video messages directly
async def incoming_compress_message_f(bot: Client, update: Message):
    """Deprecated - compression now handled automatically on video upload"""
    await update.reply_text(
        "ℹ️ **New System Active!**\n\n"
        "🎬 Simply send me a video file and I'll show you quality options!\n"
        "📱 No need for /compress command anymore."
    )

async def incoming_cancel_message_f(bot: Client, update: Message):
    """Enhanced /cancel command handler"""
    try:
        if update.from_user.id not in AUTH_USERS:
            await update.reply_text("❌ You don't have permission to use this command.")
            return

        user_id = update.from_user.id
        
        if user_id in CURRENT_PROCESSES or user_id in USER_SESSIONS:
            await update.reply_text(
                "🗑️ **Cancel Current Process?**\n\n"
                "⚠️ This will stop any active compression!\n"
                "❌ This action cannot be undone!",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton('✅ Yes, Cancel', callback_data='confirm_cancel'),
                        InlineKeyboardButton('❌ No, Keep', callback_data='keep_process')
                    ]
                ])
            )
        else:
            await update.reply_text("❌ No active process found.")

    except Exception as e:
        LOGGER.error(f"Error in cancel handler: {e}")
        await update.reply_text("❌ An error occurred.")
