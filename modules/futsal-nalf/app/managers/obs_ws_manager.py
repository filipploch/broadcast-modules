"""OBS-Websocket Manager - Manages obs websocket plugin communication and state"""
from flask import current_app
from datetime import datetime
# from app.managers import get_timer_manager
import threading


class ObsWsManager:
    """Manages communication with Timer Plugin and caches timer states"""
    
    def __init__(self, hub_client):
        """
        Initialize OBS-Websocket Manager
        
        Args:
            hub_client: HubClient instance for WebSocket communication
        """
        self.hub_client = hub_client
        # plugin_manager = get_timer_manager()
        self.obs_ws_plugin_id = 'obs-ws-plugin'
        self.timers = {}  # Cache: {timer_id: timer_state}
        self.lock = threading.Lock()
        
        current_app.logger.info("ObsWsManager initialized")