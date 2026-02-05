# """Plugin Manager - Simplified (HUB manages plugin processes)
#
# This manager now only handles plugin METADATA from database.
# Plugin PROCESS MANAGEMENT is handled by HUB.
#
# Responsibilities:
# - Load plugin list from database
# - Provide plugin list for HubClient.declare_required_plugins()
# - Mark plugins as online/offline in database
# - Track plugin status
#
# What was REMOVED (now in HUB):
# - subprocess.Popen() - starting plugin processes
# - Process monitoring and management
# - Hub startup
# """
# from flask import current_app
# # from app.models import Plugin
#
#
# class PluginManager:
#     """Manages plugin metadata and database state"""
#
#     def __init__(self):
#         """Initialize Plugin Manager (metadata only)"""
#         self._plugins_cache = []
#         current_app.logger.info("PluginManager initialized (metadata only - HUB manages processes)")
#
#     def load_plugins(self):
#         """
#         Load plugins from database
#
#         Returns:
#             list: List of Plugin models from database
#         """
#         # self._plugins_cache = Plugin.query.order_by(Plugin.startup_priority).all()
#         self._plugins_cache = current_app.config['REQUIRED_PLUGINS']
#
#         current_app.logger.info(f"Loaded {len(self._plugins_cache)} plugins from database")
#
#         # Log each plugin
#         for plugin in self._plugins_cache:
#             print(f"plugin: {plugin}")
#             current_app.logger.info(
#                 f"   - {plugin}"
#             )
#
#         return self._plugins_cache
#
#     def get_plugin_list(self):
#         """
#         Get list of plugins for Hub registration
#
#         This list will be sent to HUB via declare_required_plugins.
#         HUB will then start these plugins automatically.
#
#         Returns:
#             list: List of plugin dicts for HUB
#                   Format: [{'id': 'timer-plugin', 'name': 'Timer', 'type': 'local'}, ...]
#         """
#         plugins = []
#
#         for plugin in self._plugins_cache:
#             # Don't register Hub itself as a required plugin
#             if plugin.type != 'hub':
#                 plugins.append({
#                     'id': plugin.id,
#                     'name': plugin.name,
#                     'type': plugin.type
#                 })
#
#         current_app.logger.info(f"Prepared {len(plugins)} plugins for HUB registration:")
#         for p in plugins:
#             current_app.logger.info(f"   - {p['id']} ({p['name']})")
#
#         return plugins
#
#     def get_plugin(self, plugin_id):
#         """
#         Get plugin by ID from cache
#
#         Args:
#             plugin_id: Plugin identifier
#
#         Returns:
#             Plugin model or None
#         """
#         for plugin in self._plugins_cache:
#             if plugin.id == plugin_id:
#                 return plugin
#         return None
#
#     def mark_plugin_online(self, plugin_id):
#         """
#         Mark plugin as online in database
#
#         Called when HubClient receives 'plugin_online' from HUB
#
#         Args:
#             plugin_id: Plugin identifier
#         # """
#         # plugin = Plugin.query.get(plugin_id)
#         # if plugin:
#         #     plugin.mark_online()
#         #     current_app.logger.info(f"✅ Plugin {plugin_id} marked as online in DB")
#         # else:
#         #     current_app.logger.warning(f"⚠️  Plugin {plugin_id} not found in database")
#
#     def mark_plugin_offline(self, plugin_id):
#         """
#         Mark plugin as offline in database
#
#         Called when HubClient receives 'plugin_offline' from HUB
#
#         Args:
#             plugin_id: Plugin identifier
#         """
#         # plugin = Plugin.query.get(plugin_id)
#         # if plugin:
#         #     plugin.mark_offline()
#         #     current_app.logger.info(f"🔌 Plugin {plugin_id} marked as offline in DB")
#         # else:
#         #     current_app.logger.warning(f"⚠️  Plugin {plugin_id} not found in database")
#
#     def get_plugin_status(self, plugin_id):
#         """
#         Get plugin status from database
#
#         Args:
#             plugin_id: Plugin identifier
#
#         Returns:
#             dict: Plugin status {'online': bool, 'last_seen': datetime, ...}
#         """
#         plugin = Plugin.query.get(plugin_id)
#         if not plugin:
#             return None
#
#         return {
#             'id': plugin.id,
#             'name': plugin.name,
#             'type': plugin.type,
#             'online': plugin.is_online,
#             'last_seen': plugin.last_seen,
#             'expected_host': plugin.expected_host,
#             'expected_port': plugin.expected_port
#         }
#
#     def get_all_plugin_statuses(self):
#         """
#         Get status of all plugins from database
#
#         Returns:
#             list: List of plugin status dicts
#         """
#         statuses = []
#
#         for plugin in self._plugins_cache:
#             statuses.append({
#                 'id': plugin.id,
#                 'name': plugin.name,
#                 'type': plugin.type,
#                 'online': plugin.is_online,
#                 'last_seen': plugin.last_seen,
#                 'is_critical': plugin.is_critical
#             })
#
#         return statuses
