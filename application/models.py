from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)

class Slot(db.Model):
    __tablename__ = 'slot'
    id = db.Column(db.Integer, primary_key=True)
    slot_date = db.Column(db.Date, nullable=False)
    slot_start_time = db.Column(db.Time, nullable=False)
    slot_end_time = db.Column(db.Time, nullable=False)
    available = db.Column(db.Boolean, default=True)

    @property
    def is_booked(self):
        return len(self.bookings) > 0

class Booking(db.Model):
    __tablename__ = 'booking'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    slot_id = db.Column(db.Integer, db.ForeignKey('slot.id'))
    description = db.Column(db.String(255))
    event_id = db.Column(db.String(80), nullable=False)
    user = db.relationship('User', backref='bookings')
    slot = db.relationship('Slot', backref='bookings')