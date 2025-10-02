"""
Utility functions for the relay bot
"""

def build_message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    """
    Build a Discord message jump link
    Format: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
    """
    if not all([guild_id, channel_id, message_id]):
        return ""
    
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

def format_message_footer(guild_name: str, channel_name: str, message_link: str = None) -> str:
    """
    Format the footer that appears at the end of relayed messages
    Shows origin server/channel and jump link if available
    """
    footer_parts = [""]
    
    # Add origin info
    origin = f"-# 📍 **{guild_name}** | #{channel_name}"
    footer_parts.append(origin)
    
    # Add jump link if available
    if message_link:
        footer_parts.append(f"-# [Jump to Message]({message_link})")
    
    return "\n".join(footer_parts)

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length"""
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def sanitize_webhook_username(username: str) -> str:
    """
    Sanitize username for webhook use
    Discord webhook usernames can't contain certain characters
    """
    if not username:
        return "Unknown User"
    
    # Remove or replace forbidden characters
    forbidden = ['@', '#', ':', '```', 'discord']
    sanitized = username
    
    for forbidden_str in forbidden:
        sanitized = sanitized.replace(forbidden_str, '')
    
    # Trim whitespace
    sanitized = sanitized.strip()
    
    # Ensure it's not empty after sanitization
    if not sanitized:
        return "Unknown User"
    
    # Limit length (Discord limit is 80 characters for webhook usernames)
    if len(sanitized) > 80:
        sanitized = sanitized[:80]
    
    return sanitized

def format_attachment_text(attachments: list) -> str:
    """Format attachment list as text"""
    if not attachments:
        return ""
    
    lines = ["\n📎 **Attachments:**"]
    for att in attachments[:10]:  # Limit to 10
        filename = att.get('filename', 'unknown')
        url = att.get('url', '')
        if url:
            lines.append(f"• [{filename}]({url})")
        else:
            lines.append(f"• {filename}")
    
    return "\n".join(lines)

def validate_discord_id(id_str: str) -> bool:
    """Validate that a string is a valid Discord snowflake ID"""
    if not id_str:
        return False
    
    try:
        # Discord IDs are numeric strings
        int(id_str)
        # Discord IDs are typically 17-19 characters
        return 17 <= len(id_str) <= 19
    except ValueError:
        return False

def parse_author_info(author_data: dict) -> dict:
    """Parse and validate author information from message data"""
    if not author_data:
        return {
            'username': 'Unknown User',
            'discriminator': '0000',
            'avatar': None,
            'id': None,
            'bot': False
        }
    
    return {
        'username': author_data.get('username', 'Unknown User'),
        'discriminator': author_data.get('discriminator', '0000'),
        'avatar': author_data.get('avatar'),
        'id': author_data.get('id'),
        'bot': author_data.get('bot', False)
    }