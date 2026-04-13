# from app.extensions import db
# import json
# from datetime import datetime
#
# class Plugin(db.Model):
#     """Plugin model"""
#     __tablename__ = 'plugins'
#
#     id = db.Column(db.String(50), primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     type = db.Column(db.String(20), nullable=False)
#     executable_path = db.Column(db.String(500))
#     expected_host = db.Column(db.String(100))
#     expected_port = db.Column(db.Integer)
#     _config = db.Column('config', db.Text)
#     is_critical = db.Column(db.Boolean, default=True)
#     startup_priority = db.Column(db.Integer, default=99)
#     startup_delay_ms = db.Column(db.Integer, default=0)
#     status = db.Column(db.String(20), default='offline')
#     last_seen = db.Column(db.DateTime)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
#
#     @property
#     def config(self):
#         if self._config:
#             try:
#                 return json.loads(self._config)
#             except:
#                 return {}
#         return {}
#
#     @config.setter
#     def config(self, value):
#         if isinstance(value, dict):
#             self._config = json.dumps(value)
#         else:
#             self._config = value
#
#     def mark_online(self):
#         self.status = 'online'
#         self.last_seen = datetime.utcnow()
#         db.session.commit()
#
#     def mark_offline(self):
#         self.status = 'offline'
#         db.session.commit()
#
#     def __repr__(self):
#         return f'<Plugin {self.id} ({self.type})>'
