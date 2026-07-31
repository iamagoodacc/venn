# SQLAlchemy table classes - my database schema in python

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, SmallInteger,
    TIMESTAMP, ForeignKey, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # convenience: user.profiles gives you all their profiles without a manual query
    profiles = relationship("AvailabilityProfile", back_populates="user", cascade="all, delete-orphan")
    events_created = relationship("Event", back_populates="host", cascade="all, delete-orphan")


class AvailabilityProfile(Base):
    __tablename__ = "availability_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="profiles")
    recurring_rules = relationship("RecurringAvailability", back_populates="profile", cascade="all, delete-orphan")
    exceptions = relationship("AvailabilityException", back_populates="profile", cascade="all, delete-orphan")


class RecurringAvailability(Base):
    __tablename__ = "recurring_availability"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("availability_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Monday ... 6=Sunday (matches Python's date.weekday())
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(10), nullable=False, default="free")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    profile = relationship("AvailabilityProfile", back_populates="recurring_rules")

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_recurring_day_of_week"),
        CheckConstraint("end_time > start_time", name="ck_recurring_time_order"),
        CheckConstraint("status IN ('free', 'if_needed', 'busy')", name="ck_recurring_status"),
    )


class AvailabilityException(Base):
    __tablename__ = "availability_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("availability_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    exception_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(10), nullable=False, default="busy")
    reason = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    profile = relationship("AvailabilityProfile", back_populates="exceptions")

    __table_args__ = (
        CheckConstraint("status IN ('free', 'if_needed', 'busy')", name="ck_exception_status"),
        CheckConstraint("end_time > start_time", name="ck_exception_time_order"),
    )


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    range_start = Column(Date, nullable=True)  # NULL = infer from respondents
    range_end = Column(Date, nullable=True)
    invite_code = Column(String(16), unique=True, nullable=False, index=True)
    window_start_time = Column(Time, nullable=True)  # NULL = no daily restriction, full day
    window_end_time = Column(Time, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    host = relationship("User", back_populates="events_created")
    participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "range_start IS NULL OR range_end IS NULL OR range_end >= range_start",
            name="ck_event_date_order",
        ),
        CheckConstraint(
            "(window_start_time IS NULL AND window_end_time IS NULL) OR "
            "(window_start_time IS NOT NULL AND window_end_time IS NOT NULL AND window_end_time > window_start_time)",
            name="ck_event_window_shape",
        ),
    )


class EventParticipant(Base):
    __tablename__ = "event_participants"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)   # NULL if guest
    guest_name = Column(String(100), nullable=True)                                        # set if guest
    guest_password_hash = Column(String(255), nullable=True)                                # NULL if blank
    profile_id = Column(Integer, ForeignKey("availability_profiles.id", ondelete="SET NULL"), nullable=True)     # NULL if guest / fresh-paint 
    joined_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    event = relationship("Event", back_populates="participants")
    fresh_availability = relationship(
        "EventParticipantAvailability", back_populates="participant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_event_user"),
        CheckConstraint(
            "(user_id IS NOT NULL AND guest_name IS NULL) OR "
            "(user_id IS NULL AND guest_name IS NOT NULL)",
            name="ck_participant_user_or_guest",
        ),
        # case-insensitive uniqueness of guest_name per event (partial index —
        # only applies to rows where guest_name is set, i.e. actual guests)
        Index(
            "idx_unique_guest_name_per_event",
            event_id, func.lower(guest_name),
            unique=True,
            postgresql_where=guest_name.isnot(None),
        ),
    )


class EventParticipantAvailability(Base):
    __tablename__ = "event_participant_availability"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("event_participants.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(10), nullable=False, default="free")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    participant = relationship("EventParticipant", back_populates="fresh_availability")

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_participant_avail_time_order"),
        CheckConstraint("status IN ('free', 'if_needed', 'busy')", name="ck_participant_avail_status"),
    )