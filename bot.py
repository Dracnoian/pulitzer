#!/usr/bin/env python3
"""
Discord Message Relay Bot
Receives messages from BetterDiscord plugin via Flask relay and forwards to Discord channels
"""

from flask import Flask, request, jsonify
import discord
import logging
import sys
import asyncio
from threading import Thread
from config import Config
from message_handler import MessageHandler
from webhook_manager import WebhookManager

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
    
    async def on_error(self, event, *args, **kwargs):
        """Handle errors"""
        logger.error(f'Discord error in {event}', exc_info=True)

def run_discord_bot():
    """Run the Discord bot in a separate thread"""
    global bot_client, webhook_manager, message_handler
    
    # Set up Discord bot
    intents = discord.Intents.default()
    intents.guilds = True
    
    bot_client = RelayBotClient(intents=intents)
    
    # Set up webhook manager
    webhook_manager = WebhookManager(bot_client, config.webhook_name)
    
    # Set up message handler
    message_handler = MessageHandler(config, webhook_manager, bot_client)
    
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
        
        return jsonify({
            'status': 'healthy',
            'bot_ready': True,
            'bot_user': str(bot_client.user),
            'guilds': len(bot_client.guilds),
            'relay_groups': relay_groups_count,
            'total_destinations': total_destinations
        }), 200
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/message', methods=['POST'])
def receive_message():
    """Receive and process message from relay server"""
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
        return jsonify({'status': 'success', 'message': 'Configuration reloaded'}), 200
        
    except Exception as e:
        logger.error(f"Error reloading config: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Discord Message Relay Bot")
    
    # Check bot token
    if not config.bot_token:
        logger.error("Bot token not found in config. Please set your Discord bot token.")
        sys.exit(1)
    
    logger.info(f"Configured relay groups: {len(config.relay_groups)}")
    
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
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)