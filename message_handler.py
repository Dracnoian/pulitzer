import discord
import logging
from typing import Dict, Any, Tuple, List
from utils import build_message_link, format_message_footer

logger = logging.getLogger(__name__)

class MessageHandler:
    """Handles processing and routing of relayed messages"""
    
    def __init__(self, config, webhook_manager, bot_client):
        self.config = config
        self.webhook_manager = webhook_manager
        self.bot = bot_client
    
    async def process_message(self, message_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Process incoming message and relay to destinations
        Returns: (success, error_message)
        """
        try:
            # Extract basic message info
            channel_id = str(message_data.get('channel_id', ''))
            message_id = str(message_data.get('message_id', ''))
            
            if not channel_id:
                logger.error("Message missing channel_id")
                return False, "Missing channel_id"
            
            # Find which relay group this channel belongs to
            group_name = self.config.get_relay_group_for_channel(channel_id)
            if not group_name:
                logger.info(f"Channel {channel_id} not configured for relay")
                return False, "Channel not in any relay group"
            
            logger.info(f"Processing message for relay group: {group_name}")
            
            # Get source channel info
            source_info = self.config.get_source_channel_info(channel_id)
            if not source_info:
                logger.warning(f"No source info found for channel {channel_id}")
                source_info = {
                    "guild_id": "unknown",
                    "guild_name": "Unknown Server",
                    "channel_name": "unknown"
                }
            
            # Get destination channel IDs
            dest_channel_ids = self.config.get_destination_channel_ids(group_name)
            if not dest_channel_ids:
                logger.warning(f"No destinations configured for group {group_name}")
                return False, "No destinations configured"
            
            # Build message components
            username, avatar_url = self.extract_author_info(message_data)
            content = self.build_message_content(message_data, source_info)
            embeds = self.build_embeds(message_data)
            
            # Send to all destination channels
            success_count = 0
            fail_count = 0
            
            for dest_channel_id in dest_channel_ids:
                channel = self.bot.get_channel(dest_channel_id)
                if not channel:
                    logger.warning(f"Destination channel {dest_channel_id} not found or not accessible")
                    fail_count += 1
                    continue
                
                if not isinstance(channel, discord.TextChannel):
                    logger.warning(f"Channel {dest_channel_id} is not a text channel")
                    fail_count += 1
                    continue
                
                try:
                    success = await self.webhook_manager.send_webhook_message(
                        channel, username, avatar_url, content, embeds
                    )
                    
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to send to channel {channel.name}: {e}")
                    fail_count += 1
            
            # Return result
            if success_count > 0:
                msg = f"Sent to {success_count}/{len(dest_channel_ids)} destinations"
                logger.info(msg)
                return True, msg
            else:
                return False, f"Failed to send to all {fail_count} destinations"
                
        except Exception as e:
            logger.error(f"Error in process_message: {e}", exc_info=True)
            return False, str(e)
    
    def extract_author_info(self, message_data: Dict[str, Any]) -> Tuple[str, str]:
        """Extract username and avatar URL from message data"""
        author = message_data.get('author', {})
        username = author.get('username', 'Unknown User')
        avatar = author.get('avatar')
        
        # Build avatar URL if available
        avatar_url = None
        if avatar:
            user_id = author.get('id')
            if user_id:
                # Discord CDN avatar URL
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"
        
        return username, avatar_url
    
    def build_message_content(self, message_data: Dict[str, Any], 
                             source_info: Dict[str, Any]) -> str:
        """Build the message content with footer"""
        content = message_data.get('content', '')
        
        # Build message link
        message_link = build_message_link(
            source_info.get('guild_id'),
            message_data.get('channel_id'),
            message_data.get('message_id')
        )
        
        # Format footer with source info
        footer = format_message_footer(
            source_info.get('guild_name', 'Unknown Server'),
            source_info.get('channel_name', 'unknown'),
            message_link
        )
        
        # Append footer to content
        full_content = content
        if footer:
            if full_content:
                full_content += f"\n{footer}"
            else:
                full_content = footer
        
        # ADD ATTACHMENTS BELOW FOOTER as single-line compact list
        attachments = message_data.get('attachments', [])
        if attachments:
            attachment_links = []
            for att in attachments[:10]:
                url = att.get('url') or att.get('proxy_url')
                filename = att.get('filename', 'file')
                if url:
                    attachment_links.append(f"[{filename}]({url})")
            
            if attachment_links:
                full_content += f"\n-# {', '.join(attachment_links)}"
        
        # Limit content length (Discord limit is 2000 characters)
        if len(full_content) > 2000:
            full_content = full_content[:1997] + "..."
        
        return full_content
    
    def build_embeds(self, message_data: Dict[str, Any]) -> List[discord.Embed]:
        """Build embeds from message data"""
        embeds = []
        
        # Add original embeds if present
        original_embeds = message_data.get('embeds', [])
        if original_embeds and isinstance(original_embeds, list):
            # Limit to 10 embeds (Discord limit)
            for embed_data in original_embeds[:10]:
                try:
                    embed = discord.Embed.from_dict(embed_data)
                    embeds.append(embed)
                except Exception as e:
                    logger.warning(f"Failed to parse embed: {e}")
        
        # Handle attachments as embeds
        attachments = message_data.get('attachments', [])
        if attachments and isinstance(attachments, list):
            for att in attachments[:10]:  # Limit total embeds
                if len(embeds) >= 10:
                    break
                
                url = att.get('url') or att.get('proxy_url')
                if not url:
                    continue
                
                # Check if it's an image
                if any(url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    embed = discord.Embed()
                    embed.set_image(url=url)
                    embeds.append(embed)
        
        # Return list or None (webhook_manager will handle None properly)
        return embeds if embeds else None