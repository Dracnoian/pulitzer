"""
EarthMC Town and Nation Monitor
Monitors EarthMC API for town/nation changes and sends notifications
"""

import discord
import aiohttp
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io
import random

logger = logging.getLogger(__name__)

class EarthMCMonitor:
    """Monitors EarthMC API for town and nation changes"""
    
    def __init__(self, bot_client, config, webhook_manager):
        self.bot = bot_client
        self.config = config
        self.webhook_manager = webhook_manager
        
        # Store as dict: {uuid: name}
        self.previous_towns = {}
        self.previous_nations = {}
        self.session = None
        self.monitor_task = None
        
        # State file
        self.state_file = Path('./tbi/data/state.json')
        self.state_file.parent.mkdir(exist_ok=True)
        
    async def start(self):
        """Start the monitoring loop"""
        if not self.config.earthmc_enabled:
            logger.info("EarthMC monitoring is disabled in config")
            return
            
        self.session = aiohttp.ClientSession()
        self.load_state()
        
        # Start monitoring task
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("EarthMC monitor started")
    
    async def stop(self):
        """Stop the monitoring loop"""
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
        
        logger.info("EarthMC monitor stopped")
    
    def load_state(self):
        """Load previous state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    
                    towns = data.get('towns', {})
                    if isinstance(towns, dict):
                        self.previous_towns = towns
                    else:
                        logger.warning(f"Towns in state file is not a dict, resetting")
                        self.previous_towns = {}
                    
                    nations = data.get('nations', {})
                    if isinstance(nations, dict):
                        self.previous_nations = nations
                    else:
                        logger.warning(f"Nations in state file is not a dict, resetting")
                        self.previous_nations = {}
                    
                logger.info(f"Loaded EarthMC state: {len(self.previous_towns)} towns, {len(self.previous_nations)} nations")
            except Exception as e:
                logger.error(f"Error loading EarthMC state: {e}")
                self.previous_towns = {}
                self.previous_nations = {}
    
    def save_state(self):
        """Save current state to file"""
        try:
            data = {
                'towns': self.previous_towns,
                'nations': self.previous_nations,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving EarthMC state: {e}")
    
    async def fetch_api_data(self):
        """Fetch towns and nations from EarthMC API"""
        try:
            towns_url = 'https://api.earthmc.net/v3/aurora/towns'
            nations_url = 'https://api.earthmc.net/v3/aurora/nations'
            
            async with self.session.get(towns_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    towns = await resp.json()
                else:
                    logger.error(f"Towns API returned status {resp.status}")
                    return None, None
            
            async with self.session.get(nations_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    nations = await resp.json()
                else:
                    logger.error(f"Nations API returned status {resp.status}")
                    return None, None
                    
            return towns, nations
        except Exception as e:
            logger.error(f"Error fetching EarthMC API data: {e}")
            return None, None
    
    async def fetch_town_details(self, town_name_or_uuid):
        """Fetch detailed town information via POST request"""
        try:
            url = 'https://api.earthmc.net/v3/aurora/towns'
            payload = {"query": [town_name_or_uuid]}
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        return data[0]
                return None
        except Exception as e:
            logger.error(f"Error fetching town details: {e}")
            return None
    
    async def fetch_nation_details(self, nation_name_or_uuid):
        """Fetch detailed nation information via POST request"""
        try:
            url = 'https://api.earthmc.net/v3/aurora/nations'
            payload = {"query": [nation_name_or_uuid]}
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        return data[0]
                return None
        except Exception as e:
            logger.error(f"Error fetching nation details: {e}")
            return None
    
    def parse_color_codes(self, text):
        """Parse Minecraft color codes and return segments with colors"""
        mc_colors = self.config.minecraft_colors
        segments = []
        current_color = '#FFFFFF'
        current_text = ''
        
        i = 0
        while i < len(text):
            if text[i] == '§' and i + 1 < len(text):
                if current_text:
                    segments.append((current_text, current_color))
                    current_text = ''
                
                code = text[i + 1].lower()
                if code in mc_colors:
                    current_color = mc_colors[code]
                i += 2
            else:
                current_text += text[i]
                i += 1
        
        if current_text:
            segments.append((current_text, current_color))
        
        return segments
    
    def darken_color(self, hex_color, factor=0.25):
        """Darken a hex color by a given factor"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def generate_minecraft_image(self, message_text, notif_type='town'):
        """Generate a Minecraft-style chat message image"""
        
        # Get crop settings from config
        crop_settings = self.config.get_notification_crop_settings(notif_type)
        
        bg_color = '#1C1C1C'
        text_bg_opacity = 180
        panel_color = (0, 0, 0)
        buffer_pixels = crop_settings.get('buffer_pixels', 0)
        panel_padding = crop_settings.get('panel_padding', 3)
        shadow_offset = 2
        
        # Load font
        font_loaded = False
        font_path = './tbi/data/minecraft.otf'
        
        if Path(font_path).exists():
            try:
                font = ImageFont.truetype(font_path, 20)
                shadow_font = font
                font_loaded = True
                logger.debug(f"Using Minecraft font: {font_path}")
            except Exception as e:
                logger.warning(f"Failed to load Minecraft font: {e}")
        
        if not font_loaded:
            try:
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 18)
                shadow_font = font
                logger.debug("Using fallback font: DejaVu Sans Mono")
            except:
                try:
                    font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 18)
                    shadow_font = font
                    logger.debug("Using fallback font: Consolas")
                except:
                    font = ImageFont.load_default()
                    shadow_font = font
                    logger.warning("Using default font (low quality)")
        
        # Parse color codes
        segments = self.parse_color_codes(message_text)
        
        # Calculate text dimensions
        temp_img = Image.new('RGB', (2000, 200), bg_color)
        temp_draw = ImageDraw.Draw(temp_img)
        
        x_offset = 0
        max_height = 0
        for text, color in segments:
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x_offset += text_width
            max_height = max(max_height, text_height)
        
        total_text_width = x_offset
        total_text_height = max_height + shadow_offset
        
        # Panel dimensions
        panel_width = total_text_width + panel_padding * 2 + shadow_offset
        panel_height = total_text_height + panel_padding * 2
        
        # Try to load random background image
        background_dir = Path('./tbi/data/backgrounds')
        background_images = []
        
        if background_dir.exists():
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']:
                background_images.extend(background_dir.glob(ext))
        
        background = None
        if background_images:
            bg_path = random.choice(background_images)
            try:
                background = Image.open(bg_path).convert('RGBA')
                logger.debug(f"Using background: {bg_path.name}")
                
                min_width = panel_width + buffer_pixels * 2
                min_height = panel_height + buffer_pixels * 2
                
                if background.width < min_width or background.height < min_height:
                    logger.warning(f"Background too small, need at least {min_width}x{min_height}")
                    background = None
            except Exception as e:
                logger.warning(f"Failed to load background: {e}")
                background = None
        
        # Create image and choose text position
        if background:
            max_x = background.width - panel_width - buffer_pixels * 2
            max_y = background.height - panel_height - buffer_pixels * 2
            
            if max_x > 0 and max_y > 0:
                text_x = random.randint(buffer_pixels, max_x)
                text_y = random.randint(buffer_pixels, max_y)
            else:
                text_x = (background.width - panel_width) // 2
                text_y = (background.height - panel_height) // 2
            
            img = background.copy()
        else:
            from PIL import ImageColor
            bg_rgba = ImageColor.getrgb(bg_color) + (255,)
            img = Image.new('RGBA', 
                          (panel_width + buffer_pixels * 2, panel_height + buffer_pixels * 2), 
                          bg_rgba)
            text_x = buffer_pixels
            text_y = buffer_pixels
        
        # Draw semi-transparent panel
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        
        panel_rect = [
            text_x,
            text_y,
            text_x + panel_width,
            text_y + panel_height
        ]
        overlay_draw.rectangle(panel_rect, fill=(*panel_color, text_bg_opacity))
        
        img = Image.alpha_composite(img, overlay)
        
        # Draw text
        draw = ImageDraw.Draw(img)
        x_pos = text_x + panel_padding
        y_pos = text_y + panel_padding
        
        for text, color in segments:
            shadow_color = self.darken_color(color, factor=0.25)
            draw.text((x_pos + shadow_offset, y_pos + shadow_offset), 
                     text, fill=shadow_color, font=shadow_font)
            draw.text((x_pos, y_pos), text, fill=color, font=font)
            
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            x_pos += text_width
        
        # Crop to text area
        crop_box = (
            max(0, text_x - buffer_pixels),
            max(0, text_y - buffer_pixels),
            min(img.width, text_x + panel_width + buffer_pixels),
            min(img.height, text_y + panel_height + buffer_pixels)
        )
        
        img = img.crop(crop_box)
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    
    async def send_notification(self, message_text, relay_groups, notif_type='town'):
        """Send notification to relay groups via webhooks"""
        if not relay_groups:
            logger.warning(f"No relay groups configured for {notif_type} notifications")
            return
        
        image = self.generate_minecraft_image(message_text, notif_type)
        
        for group_name in relay_groups:
            dest_channel_ids = self.config.get_destination_channel_ids(group_name)
            
            for channel_id in dest_channel_ids:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel {channel_id} not found")
                        continue
                    
                    if not isinstance(channel, discord.TextChannel):
                        logger.warning(f"Channel {channel_id} is not a text channel")
                        continue
                    
                    webhook = await self.webhook_manager.get_webhook(channel)
                    if not webhook:
                        logger.error(f"Could not get webhook for {channel.name}")
                        continue
                    
                    image.seek(0)
                    file = discord.File(image, filename='image.png')
                    
                    await webhook.send(
                        username="Project Pulitzer",
                        file=file,
                        wait=False
                    )
                    
                    logger.info(f"Sent {notif_type} notification to {channel.name}")
                    
                except Exception as e:
                    logger.error(f"Error sending notification to channel {channel_id}: {e}")
                
                await asyncio.sleep(0.5)
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        # Wait for bot to be ready
        await self.bot.wait_until_ready()
        
        poll_interval = self.config.earthmc_poll_interval
        
        while not self.bot.is_closed():
            try:
                logger.info(f"Polling EarthMC API at {datetime.now().strftime('%H:%M:%S')}")
                
                towns_data, nations_data = await self.fetch_api_data()
                if not towns_data or not nations_data:
                    logger.warning("Failed to fetch API data, skipping this cycle")
                    await asyncio.sleep(poll_interval)
                    continue
                
                # Handle API response format
                if isinstance(towns_data, dict):
                    towns_list = towns_data.get('towns', towns_data.get('data', []))
                else:
                    towns_list = towns_data
                    
                if isinstance(nations_data, dict):
                    nations_list = nations_data.get('nations', nations_data.get('data', []))
                else:
                    nations_list = nations_data
                
                # Build current state
                current_towns = {town['uuid']: town['name'] for town in towns_list}
                current_nations = {nation['uuid']: nation['name'] for nation in nations_list}
                
                # Check for changes
                if self.previous_towns:
                    await self._check_town_changes(current_towns)
                
                if self.previous_nations:
                    await self._check_nation_changes(current_nations)
                
                # Update state
                self.previous_towns = current_towns
                self.previous_nations = current_nations
                self.save_state()
                
                logger.info(f"Monitoring complete: {len(current_towns)} towns, {len(current_nations)} nations")
                
            except asyncio.CancelledError:
                logger.info("EarthMC monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in EarthMC monitor loop: {e}", exc_info=True)
            
            await asyncio.sleep(poll_interval)
    
    async def _check_town_changes(self, current_towns):
        """Check for town changes"""
        templates = self.config.get_notification_templates('town')
        relay_groups = self.config.get_notification_relay_groups('town')
        
        # New towns
        new_town_uuids = set(current_towns.keys()) - set(self.previous_towns.keys())
        for uuid in sorted(new_town_uuids):
            town_name = current_towns[uuid]
            details = await self.fetch_town_details(uuid)
            leader = details.get('mayor', {}).get('name', 'Unknown') if details else 'Unknown'
            
            message = templates['created'].format(name=town_name, leader=leader)
            logger.info(f"New town: {town_name} (Mayor: {leader})")
            await self.send_notification(message, relay_groups, 'town')
            await asyncio.sleep(0.5)
        
        # Removed towns
        removed_town_uuids = set(self.previous_towns.keys()) - set(current_towns.keys())
        for uuid in sorted(removed_town_uuids):
            town_name = self.previous_towns[uuid]
            message = templates['removed'].format(name=town_name)
            logger.info(f"Removed town: {town_name}")
            await self.send_notification(message, relay_groups, 'town')
            await asyncio.sleep(0.5)
        
        # Renamed towns
        for uuid in current_towns:
            if uuid in self.previous_towns:
                old_name = self.previous_towns[uuid]
                new_name = current_towns[uuid]
                if old_name != new_name:
                    message = templates['renamed'].format(old_name=old_name, new_name=new_name)
                    logger.info(f"Town renamed: {old_name} → {new_name}")
                    await self.send_notification(message, relay_groups, 'town')
                    await asyncio.sleep(0.5)
    
    async def _check_nation_changes(self, current_nations):
        """Check for nation changes"""
        templates = self.config.get_notification_templates('nation')
        relay_groups = self.config.get_notification_relay_groups('nation')
        
        # New nations
        new_nation_uuids = set(current_nations.keys()) - set(self.previous_nations.keys())
        for uuid in sorted(new_nation_uuids):
            nation_name = current_nations[uuid]
            details = await self.fetch_nation_details(uuid)
            leader = details.get('king', {}).get('name', 'Unknown') if details else 'Unknown'
            
            message = templates['created'].format(name=nation_name, leader=leader)
            logger.info(f"New nation: {nation_name} (King: {leader})")
            await self.send_notification(message, relay_groups, 'nation')
            await asyncio.sleep(0.5)
        
        # Removed nations
        removed_nation_uuids = set(self.previous_nations.keys()) - set(current_nations.keys())
        for uuid in sorted(removed_nation_uuids):
            nation_name = self.previous_nations[uuid]
            message = templates['removed'].format(name=nation_name)
            logger.info(f"Removed nation: {nation_name}")
            await self.send_notification(message, relay_groups, 'nation')
            await asyncio.sleep(0.5)
        
        # Renamed nations
        for uuid in current_nations:
            if uuid in self.previous_nations:
                old_name = self.previous_nations[uuid]
                new_name = current_nations[uuid]
                if old_name != new_name:
                    message = templates['renamed'].format(old_name=old_name, new_name=new_name)
                    logger.info(f"Nation renamed: {old_name} → {new_name}")
                    await self.send_notification(message, relay_groups, 'nation')
                    await asyncio.sleep(0.5)