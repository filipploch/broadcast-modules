"""Shootout — moduł futsal-nalf.

Futsal nie rozszerza BaseShootout o żadne dodatkowe pola —
struktura konkursu rzutów karnych jest identyczna jak w BaseShootout.
Klasa istnieje żeby zdefiniować __tablename__ i backref 'kicks' w Shootout.
"""
from core.extensions import db
from core.models.base_shootout import BaseShootout


class Shootout(BaseShootout):
    __tablename__ = 'shootouts'

    # Backref 'kicks' definiowany tutaj — po stronie Shootout (parent ShootoutKick)
    # ShootoutKick.shootout nie definiuje backref (unika kolizji)
    # kicks = db.relationship(
    #     'ShootoutKick',
    #     backref='shootout',
    #     lazy='dynamic',
    #     order_by='ShootoutKick.round_number, ShootoutKick.kick_order',
    #     cascade='all, delete-orphan',
    # )
