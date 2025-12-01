"""
Angel One SmartAPI authentication helper.

Handles login, token generation, and session management.
"""

from __future__ import annotations

from typing import Optional

import pyotp
from SmartApi.smartConnect import SmartConnect

from src.config.settings import settings
from src.core.logger import get_logger


logger = get_logger("auth")

# Global authenticated SmartConnect instance
_authenticated_api: Optional[SmartConnect] = None


def get_authenticated_api() -> Optional[SmartConnect]:
    """Get the authenticated SmartConnect instance."""
    return _authenticated_api


def authenticate() -> bool:
    """
    Authenticate with Angel One SmartAPI and set tokens in settings.
    
    Returns:
        True if authentication successful, False otherwise.
    """
    global _authenticated_api
    try:
        smart_api = SmartConnect(api_key=settings.api_key)
        
        # Generate TOTP
        totp = pyotp.TOTP(settings.totp_secret).now()
        
        # Authenticate using MPIN (password-based login is deprecated)
        # Angel One now requires MPIN instead of password
        # The generateSession method should accept MPIN as the second parameter
        # If your SDK version has generateSessionByMPIN, it will be used automatically
        try:
            # Try generateSessionByMPIN if available (newer SDK versions)
            if hasattr(smart_api, 'generateSessionByMPIN'):
                logger.debug("Using generateSessionByMPIN method")
                session_data = smart_api.generateSessionByMPIN(
                    settings.client_id,
                    settings.mpin,
                    totp
                )
            else:
                # Use generateSession with MPIN (older SDK versions may support this)
                logger.debug("Using generateSession method with MPIN")
                session_data = smart_api.generateSession(
                    settings.client_id,
                    settings.mpin,
                    totp
                )
        except Exception as e:
            logger.error("Authentication method failed: %s", e)
            # If both methods fail, the error will be caught by outer try-except
            raise
        
        if session_data and session_data.get("status"):
            data = session_data.get("data", {})
            settings.access_token = data.get("jwtToken")
            settings.refresh_token = data.get("refreshToken")
            
            # Store authenticated instance globally
            _authenticated_api = smart_api
            
            # Get feed token for WebSocket
            try:
                feed_token_response = smart_api.getfeedToken()
                # getfeedToken() may return a string (token) or a dict with status/data
                if isinstance(feed_token_response, str):
                    # If it's a string, use it directly as the feed token
                    settings.feed_token = feed_token_response
                elif isinstance(feed_token_response, dict):
                    # If it's a dict, extract the token from the response
                    if feed_token_response.get("status"):
                        settings.feed_token = feed_token_response.get("data", {}).get("feedToken")
                    else:
                        logger.warning("Failed to get feed token: %s", feed_token_response.get("message", "Unknown error"))
                        settings.feed_token = None
                else:
                    logger.warning("Unexpected feed token response type: %s", type(feed_token_response))
                    settings.feed_token = None
            except Exception as feed_exc:
                logger.warning("Error getting feed token: %s", feed_exc)
                settings.feed_token = None
            
            logger.info("Authentication successful")
            logger.debug("Access token: %s...", settings.access_token[:20] if settings.access_token else "None")
            return True
        else:
            error_msg = session_data.get("message", "Unknown error") if session_data else "No response"
            logger.error("Authentication failed: %s", error_msg)
            return False
            
    except Exception as exc:
        logger.exception("Authentication error: %s", exc)
        return False


def refresh_token() -> bool:
    """
    Refresh the access token using refresh token.
    
    Returns:
        True if refresh successful, False otherwise.
    """
    if not settings.refresh_token:
        logger.error("No refresh token available")
        return False
    
    try:
        smart_api = SmartConnect(api_key=settings.api_key)
        refresh_response = smart_api.refreshToken(settings.refresh_token)
        
        if refresh_response and refresh_response.get("status"):
            data = refresh_response.get("data", {})
            settings.access_token = data.get("jwtToken")
            settings.refresh_token = data.get("refreshToken")
            logger.info("Token refreshed successfully")
            return True
        else:
            error_msg = refresh_response.get("message", "Unknown error") if refresh_response else "No response"
            logger.error("Token refresh failed: %s", error_msg)
            return False
            
    except Exception as exc:
        logger.exception("Token refresh error: %s", exc)
        return False

