#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Enhanced Main Entry Point with Button-Based Compression System
# Handles both media messages and traditional commands

import os
import sys
import asyncio
import signal
from pyrogram import Client, idle
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram import filters
from pyrogram.enums import ParseMode

# Import all configurations and modules
from bot import (
    APP_ID,
    API_HASH,
    AUTH_USERS,
    DOWNLOAD_LOCATION,
    LOGGER,
    TG_BOT_TOKEN,
    BOT_USERNAME,
    SESSION_NAME,
    DATABASE_URL,
    MAX_CONCURRENT_PROCESSES
)

# Import all handlers
from bot.plugins.incoming_message_fn import (
    incoming_start_message_f,
    incoming_compress_message_f,  # This is now deprecated but kept for compatibility
    incoming_cancel_message_f,
    handle_video_message  # NEW: Direct video message handler
)

from bot.plugins.admin import (
    sts,
    ban,
    unban,
    _banned_usrs,
    get_logs
)

from bot.plugins.broadcast import (
    broadcast_
)

from bot.plugins.status_message_fn import (
    exec_message_f,
    upload_log_file
)

from bot.plugins.new_join_fn import (
    help_message_f
)

# Import the enhanced callback handler
from bot.plugins.call_back_button_handler import button_enhanced

class EnhancedVideoCompressBot:
    def __init__(self):
        self.app = None
        self.running_processes = 0
        self.shutdown = False

    async def initialize_bot(self):
        """Initialize the bot and all its components"""
        try:
            # Create download directory if not exists
            if not os.path.isdir(DOWNLOAD_LOCATION):
                os.makedirs(DOWNLOAD_LOCATION)

            # Initialize Pyrogram client
            self.app = Client(
                SESSION_NAME,
                bot_token=TG_BOT_TOKEN,
                api_id=APP_ID,
                api_hash=API_HASH,
                workers=8,
                sleep_threshold=10,
                parse_mode=ParseMode.HTML
            )

            # Register all handlers
            await self.register_handlers()

            LOGGER.info("Enhanced VideoCompress Bot v2.0 initialized successfully!")
            return True

        except Exception as e:
            LOGGER.error(f"Failed to initialize bot: {e}")
            return False

    async def register_handlers(self):
        """Register all message and callback handlers with enhanced video handling"""

        # Admin Commands
        self.app.add_handler(MessageHandler(
            sts,
            filters=filters.command(["status", "stats"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            ban,
            filters=filters.command(["ban_user", "ban"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            unban,
            filters=filters.command(["unban_user", "unban"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            _banned_usrs,
            filters=filters.command(["banned_users", "banned"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            broadcast_,
            filters=filters.command(["broadcast"]) & filters.user(AUTH_USERS) & filters.reply
        ))

        self.app.add_handler(MessageHandler(
            get_logs,
            filters=filters.command(["logs"]) & filters.user(AUTH_USERS)
        ))

        # Public Commands
        self.app.add_handler(MessageHandler(
            incoming_start_message_f,
            filters=filters.command(["start", f"start@{BOT_USERNAME}"])
        ))

        # DEPRECATED: Keep for compatibility but show new system message
        self.app.add_handler(MessageHandler(
            incoming_compress_message_f,
            filters=filters.command(["compress", f"compress@{BOT_USERNAME}"])
        ))

        self.app.add_handler(MessageHandler(
            help_message_f,
            filters=filters.command(["help", f"help@{BOT_USERNAME}"])
        ))

        # Control Commands
        self.app.add_handler(MessageHandler(
            incoming_cancel_message_f,
            filters=filters.command(["cancel", f"cancel@{BOT_USERNAME}"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            exec_message_f,
            filters=filters.command(["exec", f"exec@{BOT_USERNAME}"]) & filters.user(AUTH_USERS)
        ))

        self.app.add_handler(MessageHandler(
            upload_log_file,
            filters=filters.command(["log", f"log@{BOT_USERNAME}"]) & filters.user(AUTH_USERS)
        ))

        # ========== ENHANCED VIDEO HANDLING ==========
        
        # NEW: Direct video message handler (replaces /compress command)
        # This will automatically handle any video sent to the bot
        self.app.add_handler(MessageHandler(
            handle_video_message,
            filters=(filters.video | filters.document) & filters.private & ~filters.command(["start", "help", "cancel", "status", "compress"])
        ))

        # NEW: Enhanced callback query handler for button interactions
        self.app.add_handler(CallbackQueryHandler(button_enhanced))

        LOGGER.info("All handlers registered successfully!")
        LOGGER.info("🎬 NEW SYSTEM: Send video directly for compression options!")

async def main():
    """Main function to run the bot"""
    bot = EnhancedVideoCompressBot()

    if await bot.initialize_bot():
        try:
            await bot.app.start()
            LOGGER.info("Enhanced VideoCompress Bot v2.0 started successfully!")
            LOGGER.info("🔄 NEW BUTTON-BASED SYSTEM ACTIVE!")

            # Send startup message to log channel
            try:
                from bot import LOG_CHANNEL
                if LOG_CHANNEL:
                    startup_message = (
                        "🚀 **Enhanced VideoCompress Bot v2.0 Started!**\n\n"
                        "✅ All systems operational\n"
                        "🎬 **NEW:** Button-based compression system\n"
                        "📱 **Features:**\n"
                        "• Direct video upload handling\n"
                        "• Quality preset selection (1080p, 720p, 480p, HEVC)\n"
                        "• Custom encoding settings (CRF, presets, codecs)\n"
                        "• Real-time progress tracking\n"
                        "• Professional compression options\n\n"
                        "🎯 **How to use:** Simply send a video file!\n"
                        "⚙️ **Old /compress command deprecated**"
                    )
                    
                    await bot.app.send_message(
                        LOG_CHANNEL,
                        startup_message
                    )
            except Exception as e:
                LOGGER.warning(f"Could not send startup message to log channel: {e}")

            await idle()

        except KeyboardInterrupt:
            LOGGER.info("Bot stopped by user")
        finally:
            if bot.app.is_connected:
                try:
                    from bot import LOG_CHANNEL
                    if LOG_CHANNEL:
                        shutdown_message = (
                            "🔄 **Enhanced VideoCompress Bot v2.0 Shutting Down**\n\n"
                            "⏹️ All processes stopped\n"
                            "💾 Data saved successfully\n"
                            "🔒 System secured"
                        )
                        await bot.app.send_message(
                            LOG_CHANNEL,
                            shutdown_message
                        )
                except:
                    pass
                await bot.app.stop()
    else:
        LOGGER.error("Failed to initialize bot. Exiting...")
        sys.exit(1)

if __name__ == "__main__":
    try:
        # Check Python version
        if sys.version_info < (3, 8):
            LOGGER.error("Python 3.8 or higher is required!")
            sys.exit(1)

        # Display startup banner
        print("="*60)
        print("🎬 Enhanced VideoCompress Bot v2.0 with Button System")
        print("="*60)
        print("🔥 Features:")
        print("   • Button-based quality selection")
        print("   • Professional encoding settings")
        print("   • Real-time progress tracking")
        print("   • Custom compression presets")
        print("   • Direct video upload handling")
        print("="*60)

        # Run the bot
        asyncio.run(main())

    except KeyboardInterrupt:
        LOGGER.info("Bot interrupted by user")
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}")
        sys.exit(1)
