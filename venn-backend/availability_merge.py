import os
from datetime import timedelta, date, timezone, datetime, time
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

import models
from database import get_db

def resolve_event_range(event: models.Event) -> tuple[date, date]: # return start, end
    today = date.today()

    # both None
    if event.range_start is None and event.range_end is None:
        return today, today + timedelta(days=30)

    # end = None but not start
    if event.range_start is not None and event.range_end is None:
        return event.range_start, event.range_start + timedelta(days=30)

    # start = None but not end
    if event.range_start is None and event.range_end is not None:
        # if 30 days prior is in the past then only go from today onwards
        if event.range_end - timedelta(days=30) < today:
            return today, event.range_end
            
        return event.range_end - timedelta(days=30), event.range_end
    
    return event.range_start, event.range_end  # both set, use as-is 

def resolve_profile_availability(profile_id: int, start_date: date, end_date: date, db: Session) -> dict[date, list[tuple[time, time, str]]]:
    """Returns, for each date in range, a list of (start_time, end_time, status)
    blocks - merging recurring_availability by day-of-week with any
    availability_exceptions override for that exact date."""
    blocks = {}

    current = start_date
    while current <= end_date:

        day_of_week = current.weekday()
        exceptions = db.query(models.AvailabilityException).filter(
            models.AvailabilityException.profile_id == profile_id, 
            models.AvailabilityException.exception_date == current,
        ).all()

        if len(exceptions) > 0:
            for exception in exceptions:
                block = (exception.start_time, exception.end_time, exception.status) # in database they have nullable = False so they cant be null from DB

                blocks[current] = blocks.get(current, [])
                blocks[current].append(block)
        else:
            recurring = db.query(models.RecurringAvailability).filter(
                models.RecurringAvailability.profile_id == profile_id,
                models.RecurringAvailability.day_of_week == day_of_week,
            ).all()

            for day_availability in recurring:
                blocks[current] = blocks.get(current, [])
                blocks[current].append((day_availability.start_time, day_availability.end_time, day_availability.status))
        current += timedelta(days=1)

    return blocks


def resolve_fresh_availability(participant_id: int, start_date: date, end_date: date, db: Session) -> dict[date, list[tuple[time, time, str]]]:
    """Same return shape as resolve_profile_availability, but reads
    event_participant_availability directly. Dates with nothing submitted
    are simply absent from the returned dict - compute_slot_scores treats
    any date/slot with no data as busy by default, so this function doesn't
    need to manufacture explicit "all day busy" blocks itself."""

    blocks = {}

    current = start_date
    while current <= end_date:
        slots = db.query(models.EventParticipantAvailability).filter(
            models.EventParticipantAvailability.participant_id == participant_id,
            models.EventParticipantAvailability.date == current
        ).all()

        if len(slots) > 0:
            for slot in slots: # each individual availability slot (like with exceptions)
                block = (slot.start_time, slot.end_time, slot.status)

                blocks[current] = blocks.get(current, [])
                blocks[current].append(block)
        current += timedelta(days=1)

    return blocks

def local_block_to_utc(block_date: date, start_time: time, end_time: time, tz_name: str) -> tuple[datetime, datetime]:
    """Combines block_date + each time into a full datetime, attaches
    tz_name via zoneinfo, and converts both to UTC."""
    tz = ZoneInfo(tz_name)
    start_dt = datetime.combine(block_date, start_time).replace(tzinfo=tz)
    end_dt = datetime.combine(block_date, end_time).replace(tzinfo=tz)
    return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc)

def resolve_participant_utc_availability(participant: models.EventParticipant, start_date: date, end_date: date, db: Session) -> dict[date, list[tuple[datetime, datetime, str]]]:
    """Branches on participant.profile_id (call resolve_profile_availability) vs not (call resolve_fresh_availability),
    determines the correct tz_name (profile owner's timezone, or the
    event host's timezone for fresh-paint), then runs every block
    through local_block_to_utc."""

    utc_blocks = []

    profile_id = participant.profile_id
    if profile_id:
        availability = resolve_profile_availability(profile_id, start_date, end_date, db)
        if participant.user_id: # if you have a profile id you are a user but just in case
            user = db.query(models.User).filter(models.User.id == participant.user_id).first()
            # timezone has nullable = False with a default UTC

            for date in availability:
                start_time, end_time, status = availability[date]
                start_dt, end_dt = local_block_to_utc(date, start_time, end_time, user.timezone)
                utc_blocks.append((start_dt, end_dt, status))

    else:
        availability = resolve_fresh_availability(participant.id, start_date, end_date, db)

        for date in availability:
            start_time, end_time, status = availability[date]
            start_dt, end_dt = local_block_to_utc(date, start_time, end_time, participant.event.host.timezone) # this is why SQLAlchemy is so neat, it gives these features to allow such convenience instead of using large join statemetns like:
            # result = (
            #     db.query(models.User.timezone)
            #     .join(models.Event, models.Event.created_by == models.User.id)
            #     .join(models.EventParticipant, models.EventParticipant.event_id == models.Event.id)
            #     .filter(models.EventParticipant.id == participant_id)
            #     .first()
            # )
            # host_timezone = result[0] if result else None
            utc_blocks.append((start_dt, end_dt, status))

def compute_slot_scores(all_participants_utc: list[dict[date, list[tuple[datetime, datetime, str]]]],slot_minutes: int = 30,) -> dict[datetime, dict[str, int]]:
    """For each 30-minute slot across the whole range, count how many
    participants are free/if_needed/busy at that slot."""
    pass

def apply_overlap_mode(slot_scores: dict[datetime, dict[str, int]], total_participants: int, mode: str) -> dict[datetime, dict]:
    if mode == "best-effort":
        pass
    elif mode == "all-required":
        pass
