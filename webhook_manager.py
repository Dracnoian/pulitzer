import discord
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class WebhookManager:
    """Manages Discord webhooks for relaying messages"""
    
    def __init__(self, bot, webhook_name: str = "Relay Bot"):
        self.bot = bot
        self.webhook_name = webhook_name
        self.webhooks: Dict[int, discord.Webhook] = {}
    
    async def get_webhook(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        """Get or create a webhook for a channel"""
        channel_id = channel.id
        
        # Check if we already have a webhook cached
        if channel_id in self.webhooks:
            try:
                # Test if webhook is still valid
                webhook = self.webhooks[channel_id]
                await webhook.fetch()
                # Make sure the webhook has a token
                if not webhook.token:
                    logger.warning(f"Cached webhook for {channel.name} has no token, removing from cache")
                    del self.webhooks[channel_id]
                else:
                    return webhook
            except discord.NotFound:
                logger.info(f"Cached webhook for {channel.name} was deleted, removing from cache")
                del self.webhooks[channel_id]
            except discord.Forbidden:
                logger.warning(f"Lost access to cached webhook for {channel.name}, removing from cache")
                del self.webhooks[channel_id]
            except Exception as e:
                logger.warning(f"Webhook error for {channel.name}: {e}, removing from cache")
                del self.webhooks[channel_id]
        
        try:
            # Look for existing webhooks in the channel
            webhooks = await channel.webhooks()
            relay_webhook = None
            
            for webhook in webhooks:
                if webhook.name == self.webhook_name:
                    # Check if this webhook has a token and is accessible
                    try:
                        await webhook.fetch()
                        if webhook.token:
                            relay_webhook = webhook
                            logger.info(f"Found existing valid webhook for channel {channel.name}")
                            break
                        else:
                            logger.info(f"Found webhook for {channel.name} but it has no token, will delete and recreate")
                            try:
                                await webhook.delete(reason="Webhook has no token, recreating")
                            except:
                                pass
                    except Exception as webhook_error:
                        logger.info(f"Found webhook for {channel.name} but it's invalid: {webhook_error}")
                        try:
                            await webhook.delete(reason="Invalid webhook, recreating")
                        except:
                            pass
            
            # Create new webhook if none exists or existing one was invalid
            if not relay_webhook:
                relay_webhook = await channel.create_webhook(
                    name=self.webhook_name,
                    reason="Created for message relaying"
                )
                logger.info(f"Created new webhook for channel {channel.name}")
            
            # Cache the valid webhook
            self.webhooks[channel_id] = relay_webhook
            return relay_webhook
            
        except discord.Forbidden:
            logger.error(f"No permission to manage webhooks in {channel.name}")
            return None
        except Exception as e:
            logger.error(f"Error managing webhook for {channel.name}: {e}")
            return None
    
    async def send_webhook_message(self, channel: discord.TextChannel, 
                                   username: str, avatar_url: str, 
                                   content: str, embeds: list = None) -> bool:
        """Send a message via webhook"""
        try:
            webhook = await self.get_webhook(channel)
            if not webhook:
                logger.error(f"Could not get webhook for {channel.name}")
                return False
            
            # Don't send empty content unless there are embeds
            content_to_send = content if content or embeds else None
            
            # Build kwargs for webhook.send
            send_kwargs = {
                'username': username,
                'wait': False
            }
            
            if content_to_send:
                send_kwargs['content'] = content_to_send
            
            if avatar_url:
                send_kwargs['avatar_url'] = avatar_url
            
            # Only include embeds if there are any
            if embeds:
                send_kwargs['embeds'] = embeds
            
            await webhook.send(**send_kwargs)
            
            logger.info(f"Successfully sent webhook message to {channel.name}")
            return True
            
        except discord.HTTPException as e:
            logger.error(f"HTTP error sending webhook to {channel.name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending webhook to {channel.name}: {e}")
            return False