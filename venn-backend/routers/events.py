# core
from fastapi import APIRouter, Depends, HTTPException # HTTPException for raising proper error responses
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# my helpers
from database import get_db
from datetime import date as date_type

import models
import schemas
import auth
import secrets

router = APIRouter(tags=["events"])

def generate_unique_invite_code(db: Session) -> str:
    while True: # unlikely case there is an error caused by a collision due to UNIQUE invite code key
        code = secrets.token_urlsafe(8) # 8 random bytes
        exists = db.query(models.Event).filter(models.Event.invite_code == code).first()
        if not exists:
            return code

@router.post("/events", response_model=list[schemas.EventOut])
def create_event(event: schemas.EventCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    new_event = models.Event(
        name=event.name,
        created_by=current_user.id,
        range_start=event.range_start,
        range_end=event.range_end,
        window_start_time=event.window_start_time,
        window_end_time=event.window_end_time,
        invite_code=generate_unique_invite_code(db),
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event

@router.get("/events/mine", response_model=schemas.EventOut)
def get_created_events(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Event).filter(models.Event.created_by == current_user.id).all() # list endpoint and returns an empty list if none compared to single item endpoints which return None (causes errors for output schema)

@router.get("/events/joined", response_model=list[schemas.EventOut])
def get_joined_events(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Event).join(
        models.EventParticipant, models.EventParticipant.event_id == models.Event.id
    ).filter(
        models.EventParticipant.user_id == current_user.id
    ).all() # get Event rows, joined against EventParticipant wherever their event_id matches the event's own id, then filtered down to only the rows where that participant's user_id is me

@router.get("/events/{id}", response_model=schemas.EventDetailOut)
def get_event_details(id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # need this otherwise anyone can view any events details
    is_host = event.created_by == current_user.id
    is_participant = db.query(models.EventParticipant).filter(
        models.EventParticipant.event_id == id,
        models.EventParticipant.user_id == current_user.id,
    ).first() is not None

    if not (is_host or is_participant):
        raise HTTPException(status_code=403, detail="Not authorized to view this event")

    return event

@router.get("/join/{invite_code}", response_model=schemas.EventPreviewOut) # more restricted verison of EventOut
def preview_joined_event(invite_code: str, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.invite_code == invite_code).first()
    if not event:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return event

@router.post("/events/{id}/join", response_model=schemas.EventParticipantOut)
def join_event(event_id: int, join_details: schemas.EventJoin, current_user: models.User | None = Depends(auth.get_current_user_optional), db: Session = Depends(get_db)):
    """Register user as a participant of the event and sets profile_id if they chose/have one"""
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # validate the identity combination - my schema's model_validator already rules out "both profile_id and guest_name", but it can't know whether a JWT was actually sent, since it only ever sees the request body
    if current_user is None and join_details.guest_name is None:
        raise HTTPException(status_code=400, detail="Must provide guest_name if not logged in")
    if current_user is not None and join_details.guest_name is not None:
        raise HTTPException(status_code=400, detail="Logged-in users cannot join as a guest")

    if current_user is not None:
        # logged-in path: if a profile was chosen, confirm it's actually theirs
        if join_details.profile_id is not None:
            profile = db.query(models.AvailabilityProfile).filter(
                models.AvailabilityProfile.id == join_details.profile_id
            ).first()
            if not profile or profile.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not your profile")

        new_participant = models.EventParticipant(
            event_id=event_id,
            user_id=current_user.id,
            profile_id=join_details.profile_id,  # None if they chose to paint fresh instead
        )
    else:
        # guest path
        new_participant = models.EventParticipant(
            event_id=event_id,
            guest_name=join_details.guest_name,
            guest_password_hash=(
                auth.hash_password(join_details.guest_password)
                if join_details.guest_password
                else None
            ),
        )

    db.add(new_participant)
    try:
        db.commit()
    except IntegrityError: # saves another query and overall, you are unlikely to get collisions so forcing a query with a pre-check would be less efficient. so fewer round checks overall
        db.rollback() # required otherwise session is left in a broken state unless rolled back
        # it rolls back everything staged in the current transactions within the current session, back to last successful commit nothing further and nothing out of this session
        raise HTTPException(
            status_code=409,
            detail="That name is already in use for this event - enter its password to edit it, or choose a different name", # this is specific as this is a guest not a logged in user so there is no risk of account enumeration as its only per event not a global user
        )

    db.refresh(new_participant)
    return new_participant
    
@router.post("/events/{id}/participants/{participant_id}/availability", response_model=list[schemas.EventAvailabilityOut]) # now using optional get user as it could be a guest
def join_event_fresh(event_id: int, participant_id: int, submission: schemas.EventAvailabilitySubmit, current_user: models.User = Depends(auth.get_current_user_optional), db: Session = Depends(get_db)):
    """This is after being registered as a participant, used to actually record the timeblocks of anyone who wants to paint a fresh availability individually (not recurring)"""
    participant = db.query(models.EventParticipant).filter(
        models.EventParticipant.id == participant_id,
        models.EventParticipant.event_id == event_id,
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    if participant.user_id is not None:
        # real logged-in user's fresh-paint entry - check JWT ownership
        if current_user is None or current_user.id != participant.user_id:
            raise HTTPException(status_code=403, detail="Not your entry")
    else:
        # guest entry - check password instead, no JWT involved
        if participant.guest_password_hash is not None:
            if submission.guest_password is None or not auth.verify_password(submission.guest_password, participant.guest_password_hash):
                raise HTTPException(status_code=401, detail="Incorrect password")
        # if guest_password_hash is None, the entry was left open, no check needed 
    
    # replace-the-set: delete everything currently stored for this participant
    db.query(models.EventParticipantAvailability).filter(
        models.EventParticipantAvailability.participant_id == participant_id
    ).delete()

    # now add new availability
    new_rows = []
    for block in submission.blocks:
        row = models.EventParticipantAvailability(
            participant_id=participant_id,
            date=block.date,
            start_time=block.start_time,
            end_time=block.end_time,
            status=block.status,
        )
        db.add(row)
        new_rows.append(row)

    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows


@router.get("/events/{id}/overlap", response_model=schemas.EventOut)
def get_event_availability(mode: str, participant_ids: list,invite_code: str, id: int, event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Get the data for heatmap/overlap, which will pull all participant availability"""
    # focus on this later as I have to make merge helper
    pass