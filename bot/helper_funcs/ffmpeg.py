#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Enhanced FFmpeg Handler - Compatible with Button-Based Compression System
# (c) Enhanced by Research Team | Original by @AbirHasan2005

import logging
import asyncio
import os
import time
import re
import json
import subprocess
import math
from typing import Optional, Dict, Any

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.helper_funcs.display_progress import TimeFormatter
from bot.localisation import Localisation
from bot import (
    FINISHED_PROGRESS_STR,
    UN_FINISHED_PROGRESS_STR,
    DOWNLOAD_LOCATION
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

LOGGER = logging.getLogger(__name__)

# Enhanced quality presets for button system compatibility
QUALITY_PRESETS = {
    '1080p': {'resolution': '1920x1080', 'crf': 18, 'preset': 'slow'},
    '1080p_hevc': {'resolution': '1920x1080', 'crf': 20, 'preset': 'medium', 'codec': 'libx265'},
    '720p': {'resolution': '1280x720', 'crf': 20, 'preset': 'medium'},
    '720p_hevc': {'resolution': '1280x720', 'crf': 22, 'preset': 'medium', 'codec': 'libx265'},
    '480p': {'resolution': '854x480', 'crf': 23, 'preset': 'fast'},
    '480p_hevc': {'resolution': '854x480', 'crf': 25, 'preset': 'fast', 'codec': 'libx265'},
    'custom': {'crf': 23, 'preset': 'medium'}
}

async def convert_video(video_file, output_directory, total_time, bot, message, target_percentage, isAuto=False, bug=None):
    """Enhanced video conversion compatible with both old and new systems"""
    try:
        # Generate output filename
        out_put_file_name = os.path.join(output_directory, f"{int(time.time())}.mp4")
        progress = os.path.join(output_directory, "progress.txt")
        
        with open(progress, 'w') as f:
            pass

        # Default FFmpeg command
        file_genertor_command = [
            "ffmpeg",
            "-hide_banner", 
            "-loglevel", "quiet",
            "-progress", progress,
            "-i", video_file
        ]

        # Check if this is button-based system call (new system)
        if hasattr(message, 'from_user') and hasattr(message.from_user, 'id'):
            # Try to get custom settings from USER_SESSIONS
            try:
                from bot.plugins.incoming_message_fn import USER_SESSIONS
                user_id = message.from_user.id
                
                if user_id in USER_SESSIONS:
                    session = USER_SESSIONS[user_id]
                    LOGGER.info(f"Using custom settings for user {user_id}")
                    
                    # Use custom settings from button system
                    file_genertor_command.extend([
                        "-c:v", session.video_codec,
                        "-preset", session.preset,
                        "-crf", str(session.crf),
                        "-pix_fmt", session.pixel_format
                    ])
                    
                    # Add resolution if specified
                    if session.resolution and session.resolution != "original":
                        file_genertor_command.extend(["-s", session.resolution])
                    
                    # Add audio settings
                    if session.audio_codec == "copy":
                        file_genertor_command.extend(["-c:a", "copy"])
                    else:
                        file_genertor_command.extend([
                            "-c:a", session.audio_codec,
                            "-b:a", session.audio_bitrate
                        ])
                    
                    # Add optimization flags
                    file_genertor_command.extend([
                        "-movflags", "+faststart",
                        "-tune", "film"
                    ])
                    
                    target_percentage = f"{session.quality}_CRF{session.crf}"
                    
                else:
                    raise Exception("No session found")
                    
            except Exception as e:
                LOGGER.info(f"No custom settings found, using legacy mode: {e}")
                # Fall back to legacy system
                await use_legacy_compression(
                    file_genertor_command, video_file, target_percentage, 
                    total_time, isAuto, out_put_file_name
                )
        else:
            # Legacy system
            await use_legacy_compression(
                file_genertor_command, video_file, target_percentage,
                total_time, isAuto, out_put_file_name
            )
        
        # Add output file
        file_genertor_command.append(out_put_file_name)
        
        LOGGER.info(f"FFmpeg command: {' '.join(file_genertor_command)}")
        
        # Start compression
        COMPRESSION_START_TIME = time.time()
        
        process = await asyncio.create_subprocess_exec(
            *file_genertor_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        LOGGER.info(f"FFmpeg process started: {process.pid}")
        
        # Update status file
        status = os.path.join(output_directory, "status.json")
        try:
            with open(status, 'r') as f:
                statusMsg = json.load(f)
        except:
            statusMsg = {}
        
        statusMsg['pid'] = process.pid
        statusMsg['message'] = getattr(message, 'id', getattr(message, 'message_id', 0))
        
        with open(status, 'w') as f:
            json.dump(statusMsg, f, indent=2)
        
        # Monitor progress
        isDone = False
        last_percentage = 0
        
        while process.returncode is None:
            await asyncio.sleep(3)
            
            try:
                if not os.path.exists(progress):
                    continue
                    
                with open(progress, 'r') as file:
                    text = file.read()
                
                frame = re.findall(r"frame=(\d+)", text)
                time_in_us = re.findall(r"out_time_ms=(\d+)", text)
                progress_match = re.findall(r"progress=(\w+)", text)
                speed = re.findall(r"speed=([\d.]+)", text)
                
                if len(progress_match) and progress_match[-1] == "end":
                    LOGGER.info("Compression completed")
                    isDone = True
                    break
                
                if len(time_in_us) and total_time > 0:
                    elapsed_time = int(time_in_us[-1]) / 1000000
                    percentage = min(math.floor(elapsed_time * 100 / total_time), 100)
                    
                    # Update progress only if significant change
                    if abs(percentage - last_percentage) >= 2 or percentage >= 100:
                        last_percentage = percentage
                        
                        # Calculate ETA
                        if len(speed) and float(speed[-1]) > 0:
                            difference = math.floor((total_time - elapsed_time) / float(speed[-1]))
                            ETA = TimeFormatter(difference * 1000) if difference > 0 else "-"
                        else:
                            ETA = "-"
                        
                        execution_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
                        
                        # Create progress bar
                        progress_str = "📊 **Progress:** {0}%\n[{1}{2}]".format(
                            round(percentage, 2),
                            ''.join([FINISHED_PROGRESS_STR for i in range(math.floor(percentage / 10))]),
                            ''.join([UN_FINISHED_PROGRESS_STR for i in range(10 - math.floor(percentage / 10))])
                        )
                        
                        stats = (
                            f'🎬 **Compressing** {target_percentage}\n\n'
                            f'⏰ **ETA:** {ETA}\n'
                            f'⏱️ **Elapsed:** {execution_time}\n\n'
                            f'{progress_str}'
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
                        
                        if bug:
                            try:
                                await bug.edit_text(text=stats)
                            except:
                                pass
                
            except Exception as e:
                LOGGER.error(f"Progress monitoring error: {e}")
                continue
        
        # Wait for process completion
        stdout, stderr = await process.communicate()
        
        # Log output
        if stderr:
            e_response = stderr.decode().strip()
            if e_response:
                LOGGER.info(f"FFmpeg stderr: {e_response}")
        
        if stdout:
            t_response = stdout.decode().strip()
            if t_response:
                LOGGER.info(f"FFmpeg stdout: {t_response}")
        
        # Clean up
        try:
            if os.path.exists(progress):
                os.remove(progress)
            if os.path.exists(status):
                os.remove(status)
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
        LOGGER.error(f"Video conversion error: {e}")
        return None

async def use_legacy_compression(file_genertor_command, video_file, target_percentage, total_time, isAuto, out_put_file_name):
    """Handle legacy compression for backward compatibility"""
    
    # Default legacy settings with improvements
    file_genertor_command.extend([
        "-c:v", "libx264",  # Fixed: was "h264" 
        "-preset", "medium",  # Improved: was "ultrafast"
        "-tune", "film",
        "-c:a", "copy"
    ])
    
    # Handle percentage-based compression (legacy mode)
    if not isAuto and isinstance(target_percentage, (int, float)):
        try:
            filesize = os.stat(video_file).st_size
            calculated_percentage = 100 - target_percentage
            target_size = (calculated_percentage / 100) * filesize
            target_bitrate = int(math.floor(target_size * 8 / total_time))
            
            if target_bitrate >= 1000000:
                bitrate = f"{target_bitrate//1000000}M"
            elif target_bitrate >= 1000:
                bitrate = f"{target_bitrate//1000}k"
            else:
                bitrate = "500k"  # Minimum fallback instead of returning None
            
            # Insert bitrate control
            extra = ["-b:v", bitrate, "-bufsize", bitrate]
            for elem in reversed(extra):
                file_genertor_command.insert(-1, elem)  # Insert before output file
                
            LOGGER.info(f"Using legacy bitrate mode: {bitrate}")
            
        except Exception as e:
            LOGGER.error(f"Error in legacy bitrate calculation: {e}")
            # Fallback to CRF mode
            file_genertor_command.extend(["-crf", "23"])
    else:
        # Auto mode - use CRF
        file_genertor_command.extend(["-crf", "23"])
        target_percentage = 'auto_CRF23'

async def media_info(saved_file_path):
    """Enhanced media info with better async handling"""
    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-hide_banner', '-i', saved_file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        output = stderr.decode().strip()  # ffmpeg prints info to stderr
        
        # Parse duration
        duration = re.search(r"Duration:\s*(\d*):(\d*):(\d+\.?\d*)[\s\w*$]", output)
        bitrates = re.search(r"bitrate:\s*(\d+)[\s\w*$]", output)
        
        if duration is not None:
            hours = int(duration.group(1))
            minutes = int(duration.group(2))
            seconds = math.floor(float(duration.group(3)))
            total_seconds = (hours * 60 * 60) + (minutes * 60) + seconds
        else:
            total_seconds = None
        
        if bitrates is not None:
            bitrate = bitrates.group(1)
        else:
            bitrate = None
        
        return total_seconds, bitrate
        
    except Exception as e:
        LOGGER.error(f"Error getting media info: {e}")
        return None, None

async def take_screen_shot(video_file, output_directory, ttl):
    """Enhanced screenshot with better quality and error handling"""
    try:
        out_put_file_name = os.path.join(
            output_directory,
            f"{int(time.time())}.jpg"
        )
        
        if video_file.upper().endswith(("MKV", "MP4", "WEBM", "AVI", "MOV", "FLV", "WMV")):
            file_genertor_command = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-ss", str(ttl),
                "-i", video_file,
                "-vframes", "1",
                "-q:v", "2",  # High quality
                "-vf", "scale=320:240:force_original_aspect_ratio=increase,crop=320:240",
                out_put_file_name
            ]
            
            process = await asyncio.create_subprocess_exec(
                *file_genertor_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if stderr:
                e_response = stderr.decode().strip()
                if e_response and "error" in e_response.lower():
                    LOGGER.warning(f"Thumbnail warning: {e_response}")
            
            if os.path.exists(out_put_file_name) and os.path.getsize(out_put_file_name) > 0:
                return out_put_file_name
            else:
                return None
        else:
            return None
            
    except Exception as e:
        LOGGER.error(f"Error generating thumbnail: {e}")
        return None

# Additional helper function for button system compatibility
def get_quality_preset(quality_name: str) -> Dict[str, Any]:
    """Get quality preset configuration"""
    return QUALITY_PRESETS.get(quality_name, QUALITY_PRESETS['custom'])

async def convert_video_with_custom_settings(video_file, output_directory, total_time, bot, message, session):
    """Convert video with custom settings from button system"""
    return await convert_video(
        video_file=video_file,
        output_directory=output_directory,
        total_time=total_time,
        bot=bot,
        message=message,
        target_percentage=session.quality,
        isAuto=False,
        bug=None
    )

# Export main functions
__all__ = [
    'convert_video',
    'media_info', 
    'take_screen_shot',
    'convert_video_with_custom_settings',
    'get_quality_preset'
]