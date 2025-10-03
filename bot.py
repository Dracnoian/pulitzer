#!/usr/bin/env python3
"""
Discord Message Relay Bot
Receives messages from BetterDiscord plugin and forwards to Discord channels
Includes EarthMC town/nation monitoring
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import discord
import logging
import sys
import asyncio
from threading import Thread
from config import Config
from message_handler import MessageHandler
from webhook_manager import WebhookManager
from earthmc_monitor import EarthMCMonitor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('relay_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global variables
app = Flask(__name__)
config = Config()
bot_client = None
webhook_manager = None
message_handler = None
earthmc_monitor = None

class RelayBotClient(discord.Client):
    """Discord bot client for managing webhooks"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready = False
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'Discord bot logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guilds')
        self.ready = True
        
        # Start EarthMC monitor if enabled
        global earthmc_monitor
        if config.earthmc_enabled and earthmc_monitor:
            await earthmc_monitor.start()
            logger.info("EarthMC monitoring started")
    
    async def on_error(self, event, *args, **kwargs):
        """Handle errors"""
        logger.error(f'Discord error in {event}', exc_info=True)
    
    async def on_message(self, message):
        """Handle incoming messages for commands"""
        # Ignore messages from the bot itself
        if message.author.bot:
            return
        
        # Check for command prefix
        if not message.content.startswith('>>'):
            return
        
        # Parse command
        parts = message.content[2:].strip().split(maxsplit=1)
        if not parts:
            return
        
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Handle notify command
        if command == 'notify':
            await self.handle_notify_command(message, args)
    
    async def handle_notify_command(self, message, args):
        """Handle the >>notify command"""
        global earthmc_monitor, config
        
        # Check if user is admin
        if not config.is_admin(message.author.id):
            await message.channel.send("❌ You don't have permission to use this command.")
            return
        
        # Check if EarthMC monitor is initialized
        if not earthmc_monitor:
            await message.channel.send("❌ EarthMC monitor is not initialized.")
            return
        
        # Parse arguments
        if not args:
            help_text = (
                "**>>notify command usage:**\n"
                "```\n"
                ">>notify town_created <name> <leader>\n"
                ">>notify town_removed <name>\n"
                ">>notify town_renamed <old_name> <new_name>\n"
                ">>notify nation_created <name> <leader>\n"
                ">>notify nation_removed <name>\n"
                ">>notify nation_renamed <old_name> <new_name>\n"
                "```\n"
                "**Examples:**\n"
                "`>>notify town_created TestTown PlayerName`\n"
                "`>>notify nation_renamed OldNation NewNation`"
            )
            await message.channel.send(help_text)
            return
        
        parts = args.split(maxsplit=2)
        if not parts:
            await message.channel.send("❌ Invalid command format. Use `>>notify` for help.")
            return
        
        notification_type = parts[0].lower()
        
        # Define valid notification types
        valid_types = {
            'town_created', 'town_removed', 'town_renamed',
            'nation_created', 'nation_removed', 'nation_renamed'
        }
        
        if notification_type not in valid_types:
            await message.channel.send(f"[**I**] Notification type not recognized. Valid types: `{', '.join(valid_types)}`")
            return
        
        # Determine if it's a town or nation
        notif_category = 'town' if 'town' in notification_type else 'nation'
        template_key = notification_type.replace('town_', '').replace('nation_', '')
        
        # Get the template
        templates = config.get_notification_templates(notif_category)
        if template_key not in templates:
            await message.channel.send(f"❌ Template '{template_key}' not found for {notif_category}.")
            return
        
        # Parse the rest of the arguments
        remaining_args = parts[1:] if len(parts) > 1 else []
        
        try:
            # Format the message based on type
            if template_key in ['created']:
                if len(remaining_args) < 2:
                    await message.channel.send(f"❌ Usage: `>>notify {notification_type} <name> <leader>`")
                    return
                name = remaining_args[0]
                leader = ' '.join(remaining_args[1:])
                notification_message = templates[template_key].format(name=name, leader=leader)
            
            elif template_key in ['removed']:
                if len(remaining_args) < 1:
                    await message.channel.send(f"❌ Usage: `>>notify {notification_type} <name>`")
                    return
                name = ' '.join(remaining_args)
                notification_message = templates[template_key].format(name=name)
            
            elif template_key in ['renamed']:
                if len(remaining_args) < 2:
                    await message.channel.send(f"❌ Usage: `>>notify {notification_type} <old_name> <new_name>`")
                    return
                old_name = remaining_args[0]
                new_name = ' '.join(remaining_args[1:])
                notification_message = templates[template_key].format(old_name=old_name, new_name=new_name)
            
            else:
                await message.channel.send(f"❌ Unknown template key: {template_key}")
                return
            
            # Generate the image
            image = earthmc_monitor.generate_minecraft_image(notification_message, notif_category)
            
            # Send the image to the channel
            file = discord.File(image, filename=f'{notification_type}_test.png')
            await message.channel.send(file=file)
            
            logger.info(f"Admin {message.author} ({message.author.id}) used >>notify {notification_type}")
            
        except KeyError as e:
            await message.channel.send(f"[**E**] Template formatting error: Missing placeholder {e}")
        except Exception as e:
            await message.channel.send(f"[**E**] Error generating notification: {e}")
            logger.error(f"Error in notify command: {e}", exc_info=True)

def run_discord_bot():
    """Run the Discord bot in a separate thread"""
    global bot_client, webhook_manager, message_handler, earthmc_monitor
    
    # Set up Discord bot
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True  # Required for reading message content
    
    bot_client = RelayBotClient(intents=intents)
    
    # Set up webhook manager
    webhook_manager = WebhookManager(bot_client, config.webhook_name)
    
    # Set up message handler
    message_handler = MessageHandler(config, webhook_manager, bot_client)
    
    # Set up EarthMC monitor
    earthmc_monitor = EarthMCMonitor(bot_client, config, webhook_manager)
    
    # Run the bot
    try:
        bot_client.run(config.bot_token)
    except Exception as e:
        logger.error(f"Error running Discord bot: {e}")
        sys.exit(1)

@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        'status': 'running',
        'service': 'Discord Message Relay Bot',
        'version': '1.0.0',
        'bot_ready': bot_client.ready if bot_client else False
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        if not bot_client or not bot_client.ready:
            return jsonify({
                'status': 'starting',
                'message': 'Discord bot not ready yet'
            }), 503
        
        relay_groups_count = len(config.relay_groups)
        total_destinations = sum(
            len(group.get('destination_channels', [])) 
            for group in config.relay_groups.values()
        )
        
        response = {
            'status': 'healthy',
            'bot_ready': True,
            'bot_user': str(bot_client.user),
            'guilds': len(bot_client.guilds),
            'relay_groups': relay_groups_count,
            'total_destinations': total_destinations,
            'earthmc': {
                'enabled': config.earthmc_enabled,
                'monitoring': earthmc_monitor is not None and earthmc_monitor.monitor_task is not None
            }
        }
        
        if config.earthmc_enabled and earthmc_monitor:
            response['earthmc']['towns_tracked'] = len(earthmc_monitor.previous_towns)
            response['earthmc']['nations_tracked'] = len(earthmc_monitor.previous_nations)
        
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/relay', methods=['POST'])
def relay():
    """
    Direct relay endpoint for BetterDiscord plugin
    Receives messages directly from the plugin without intermediate relay server
    """
    try:
        # Check if bot is ready
        if not bot_client or not bot_client.ready:
            return jsonify({
                'error': 'Bot not ready',
                'status': 'starting'
            }), 503
        
        # Validate authorization
        auth_header = request.headers.get('Authorization', '')
        if config.auth_token and auth_header != config.auth_token:
            logger.warning(f"Unauthorized relay request from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get message data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Received relay message from channel {data.get('channel_id')}")
        
        # Process the message asynchronously
        future = asyncio.run_coroutine_threadsafe(
            message_handler.process_message(data),
            bot_client.loop
        )
        
        # Wait for result with timeout
        try:
            success, error_msg = future.result(timeout=30)
            
            if success:
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({
                    'status': 'partial_success',
                    'message': error_msg
                }), 200
        except TimeoutError:
            return jsonify({
                'error': 'Processing timeout',
                'status': 'timeout'
            }), 504
            
    except Exception as e:
        logger.error(f"Error processing relay: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/message', methods=['POST'])
def receive_message():
    """
    Receive and process message from relay server (legacy endpoint)
    Kept for backward compatibility if using intermediate relay
    """
    try:
        # Check if bot is ready
        if not bot_client or not bot_client.ready:
            return jsonify({
                'error': 'Bot not ready',
                'status': 'starting'
            }), 503
        
        # Validate authorization
        auth_header = request.headers.get('Authorization', '')
        if config.auth_token and auth_header != config.auth_token:
            logger.warning(f"Unauthorized request from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get message data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Received message from channel {data.get('channel_id')}")
        
        # Process the message asynchronously
        future = asyncio.run_coroutine_threadsafe(
            message_handler.process_message(data),
            bot_client.loop
        )
        
        # Wait for result with timeout
        try:
            success, error_msg = future.result(timeout=30)
            
            if success:
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({
                    'status': 'partial_success',
                    'message': error_msg
                }), 200
        except TimeoutError:
            return jsonify({
                'error': 'Processing timeout',
                'status': 'timeout'
            }), 504
            
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/reload-config', methods=['POST'])
def reload_config():
    """Reload configuration (requires auth)"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if config.auth_token and auth_header != config.auth_token:
            return jsonify({'error': 'Unauthorized'}), 401
        
        config.load_config()
        logger.info("Configuration reloaded")
        
        # Restart EarthMC monitor if config changed
        if earthmc_monitor:
            asyncio.run_coroutine_threadsafe(
                earthmc_monitor.stop(),
                bot_client.loop
            )
            
            if config.earthmc_enabled:
                asyncio.run_coroutine_threadsafe(
                    earthmc_monitor.start(),
                    bot_client.loop
                )
                logger.info("EarthMC monitor restarted with new config")
        
        return jsonify({'status': 'success', 'message': 'Configuration reloaded'}), 200
        
    except Exception as e:
        logger.error(f"Error reloading config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/earthmc/status', methods=['GET'])
def earthmc_status():
    """Get EarthMC monitoring status"""
    try:
        if not config.earthmc_enabled:
            return jsonify({
                'enabled': False,
                'message': 'EarthMC monitoring is disabled'
            }), 200
        
        if not earthmc_monitor:
            return jsonify({
                'enabled': True,
                'status': 'not_initialized'
            }), 503
        
        return jsonify({
            'enabled': True,
            'status': 'running' if earthmc_monitor.monitor_task else 'stopped',
            'towns_tracked': len(earthmc_monitor.previous_towns),
            'nations_tracked': len(earthmc_monitor.previous_nations),
            'poll_interval': config.earthmc_poll_interval,
            'relay_groups': {
                'towns': config.get_notification_relay_groups('town'),
                'nations': config.get_notification_relay_groups('nation')
            }
        }), 200
    except Exception as e:
        logger.error(f"EarthMC status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/earthmc/force-check', methods=['POST'])
def earthmc_force_check():
    """Force an immediate EarthMC API check (requires auth)"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if config.auth_token and auth_header != config.auth_token:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if not config.earthmc_enabled:
            return jsonify({
                'error': 'EarthMC monitoring is disabled'
            }), 400
        
        if not earthmc_monitor or not earthmc_monitor.monitor_task:
            return jsonify({
                'error': 'EarthMC monitor is not running'
            }), 503
        
        # Cancel current task and restart it
        earthmc_monitor.monitor_task.cancel()
        
        async def restart():
            try:
                await earthmc_monitor.monitor_task
            except asyncio.CancelledError:
                pass
            earthmc_monitor.monitor_task = asyncio.create_task(earthmc_monitor._monitor_loop())
        
        asyncio.run_coroutine_threadsafe(restart(), bot_client.loop)
        
        logger.info("EarthMC force check triggered")
        return jsonify({
            'status': 'success',
            'message': 'Force check initiated'
        }), 200
        
    except Exception as e:
        logger.error(f"Error forcing EarthMC check: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Discord Message Relay Bot")
    
    # Check bot token
    if not config.bot_token:
        logger.error("Bot token not found in config. Please set your Discord bot token.")
        sys.exit(1)
    
    logger.info(f"Configured relay groups: {len(config.relay_groups)}")
    logger.info(f"EarthMC monitoring: {'enabled' if config.earthmc_enabled else 'disabled'}")
    
    # Start Discord bot in separate thread
    logger.info("Starting Discord bot...")
    bot_thread = Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()
    
    # Wait a moment for bot to initialize
    import time
    time.sleep(3)
    
    # Start Flask server
    port = config.port
    logger.info(f"Starting Flask server on port {port}")
    logger.info(f"Direct relay endpoint available at: http://0.0.0.0:{port}/relay")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)