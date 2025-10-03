import json
import logging
import os
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class Config:
    """Configuration manager for the relay bot"""
    
    def __init__(self, config_file="./tbi/config.json"):
        self.config_file = config_file
        self.data = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                logger.info(f"Configuration loaded from {self.config_file}")
            else:
                logger.warning("No config file found, creating default configuration")
                self.create_default_config()
                self.save_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.create_default_config()
    
    def create_default_config(self):
        """Create default configuration"""
        self.data = {
            "bot_token": "",
            "auth_token": "",
            "port": 25600,
            "webhook_name": "Relay Bot",
            "admin_users": [
                "123456789012345678"
            ],
            "relay_groups": {
                "example_group": {
                    "name": "Example Relay Group",
                    "source_channels": {
                        "123456789012345678": {
                            "guild_id": "987654321098765432",
                            "guild_name": "Source Server",
                            "channel_name": "general"
                        }
                    },
                    "destination_channels": [
                        "111222333444555666",
                        "222333444555666777"
                    ],
                    "earthmc_towns": False,
                    "earthmc_nations": False
                }
            },
            "earthmc": {
                "enabled": False,
                "poll_interval": 60,
                "minecraft_colors": {
                    "0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA",
                    "4": "#AA0000", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
                    "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
                    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF"
                },
                "notifications": {
                    "town": {
                        "templates": {
                            "created": "§6[Towny] §b{leader} created a new town {name}",
                            "removed": "§6[Towny] §bThe town {name} has fallen into ruins!",
                            "renamed": "§6[Towny] §bThe town {old_name} has been renamed to {new_name}"
                        },
                        "crop": {
                            "buffer_pixels": 0,
                            "panel_padding": 3
                        }
                    },
                    "nation": {
                        "templates": {
                            "created": "§6[Towny] §b{leader} created a new nation called {name}",
                            "removed": "§6[Towny] §bThe nation {name} was disbanded!",
                            "renamed": "§6[Towny] §bThe nation {old_name} has been renamed to {new_name}"
                        },
                        "crop": {
                            "buffer_pixels": 0,
                            "panel_padding": 3
                        }
                    }
                }
            }
        }
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    @property
    def bot_token(self) -> str:
        """Get Discord bot token"""
        return self.data.get("bot_token", "")
    
    @property
    def auth_token(self) -> str:
        """Get authorization token for relay server"""
        return self.data.get("auth_token", "")
    
    @property
    def port(self) -> int:
        """Get server port"""
        return self.data.get("port", 25600)
    
    @property
    def webhook_name(self) -> str:
        """Get webhook name for created webhooks"""
        return self.data.get("webhook_name", "Relay Bot")
    
    @property
    def admin_users(self) -> List[int]:
        """Get list of admin user IDs"""
        admin_list = self.data.get("admin_users", [])
        return [int(user_id) for user_id in admin_list if user_id]
    
    def is_admin(self, user_id: int) -> bool:
        """Check if a user ID is in the admin list"""
        return user_id in self.admin_users
    
    @property
    def relay_groups(self) -> Dict[str, Dict[str, Any]]:
        """Get all relay groups"""
        return self.data.get("relay_groups", {})
    
    def get_relay_group_for_channel(self, channel_id: str) -> Optional[str]:
        """Find which relay group a source channel belongs to"""
        for group_name, group_config in self.relay_groups.items():
            source_channels = group_config.get("source_channels", {})
            if channel_id in source_channels:
                return group_name
        return None
    
    def get_source_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get source channel information"""
        for group_config in self.relay_groups.values():
            source_channels = group_config.get("source_channels", {})
            if channel_id in source_channels:
                return source_channels[channel_id]
        return None
    
    def get_destination_channel_ids(self, group_name: str) -> List[int]:
        """Get all destination channel IDs for a relay group"""
        if group_name not in self.relay_groups:
            return []
        
        dest_channels = self.relay_groups[group_name].get("destination_channels", [])
        # Convert string IDs to integers
        return [int(ch_id) for ch_id in dest_channels if ch_id]
    
    # EarthMC configuration properties
    @property
    def earthmc_enabled(self) -> bool:
        """Check if EarthMC monitoring is enabled"""
        return self.data.get("earthmc", {}).get("enabled", False)
    
    @property
    def earthmc_poll_interval(self) -> int:
        """Get EarthMC polling interval in seconds"""
        return self.data.get("earthmc", {}).get("poll_interval", 60)
    
    @property
    def minecraft_colors(self) -> Dict[str, str]:
        """Get Minecraft color codes"""
        return self.data.get("earthmc", {}).get("minecraft_colors", {})
    
    def get_notification_templates(self, notif_type: str) -> Dict[str, str]:
        """Get notification templates for town or nation"""
        notifications = self.data.get("earthmc", {}).get("notifications", {})
        return notifications.get(notif_type, {}).get("templates", {})
    
    def get_notification_crop_settings(self, notif_type: str) -> Dict[str, int]:
        """Get crop settings for notification images"""
        notifications = self.data.get("earthmc", {}).get("notifications", {})
        return notifications.get(notif_type, {}).get("crop", {"buffer_pixels": 0, "panel_padding": 3})
    
    def get_notification_relay_groups(self, notif_type: str) -> List[str]:
        """Get relay groups that should receive this notification type"""
        relay_groups = []
        key = f"earthmc_{notif_type}s"  # 'earthmc_towns' or 'earthmc_nations'
        
        for group_name, group_config in self.relay_groups.items():
            if group_config.get(key, False):
                relay_groups.append(group_name)
        
        return relay_groups