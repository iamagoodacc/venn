# core
from fastapi import APIRouter, Depends, HTTPException # HTTPException for raising proper error responses
from sqlalchemy.orm import Session

# my helpers
from database import get_db
from datetime import date as date_type
import models
import schemas
import auth

router = APIRouter(tags=["availability"])

def _get_owned_profile(profile_id: int, current_user: models.User, db: Session) -> models.AvailabilityProfile:
    """Helper -> fetch a profile and confirm it belongs to current_user.
    Used by every endpoint below, since they all need this exact check."""
    profile = db.query(models.AvailabilityProfile).filter(
        models.AvailabilityProfile.id == profile_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your profile")
    return profile

@router.get("/profiles/{profile_id}/recurring", response_model=list[schemas.RecurringOut])
def get_recurring(profile_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _get_owned_profile(profile_id, current_user, db)

    return db.query(models.RecurringAvailability).filter( models.RecurringAvailability.profile_id == profile_id).all()

@router.post("/profiles/{profile_id}/recurring/{day_of_week}", response_model=list[schemas.RecurringOut])
def edit_recurring(profile_id: int, day_of_week: int, blocks: list[schemas.RecurringBlockIn], current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _get_owned_profile(profile_id, current_user, db)
 
    if not 0 <= day_of_week <= 6:
        raise HTTPException(status_code=400, detail="day_of_week must be 0-6 (0=Monday)")
 
    # delete all blocks that are for current day and for this user to replace them
    db.query(models.RecurringAvailability).filter(
        models.RecurringAvailability.profile_id == profile_id,
        models.RecurringAvailability.day_of_week == day_of_week,
    ).delete()
 
    new_rows = []
    for block in blocks: # new recurring avail for the day
        row = models.RecurringAvailability(
            profile_id=profile_id,
            day_of_week=day_of_week,
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

# profile_id is a path paramter as it is wrapped in curly brackets, 
@router.get("/profiles/{profile_id}/exceptions", response_model=list[schemas.ExceptionOut])
def get_exceptions(profile_id: int, from_date: date_type | None = None, to_date: date_type | None = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _get_owned_profile(profile_id, current_user, db)

    query = db.query(models.AvailabilityException).filter(
        models.AvailabilityException.profile_id == profile_id
    )

    # if the request wants the data with starting point
    if from_date is not None:
        query = query.filter(models.AvailabilityException.exception_date >= from_date)

    # if the request wants data with end point
    if to_date is not None:
        query = query.filter(models.AvailabilityException.exception_date <= to_date)
    
    return query.all()

@router.post("/profiles/{profile_id}/exceptions/{exception_date}", response_model=list[schemas.ExceptionOut])
def replace_exception(profile_id: int, exception_date: date_type, blocks: list[schemas.ExceptionBlockIn], current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _get_owned_profile(profile_id, current_user, db)
 
    db.query(models.AvailabilityException).filter(
        models.AvailabilityException.profile_id == profile_id,
        models.AvailabilityException.exception_date == exception_date,
    ).delete()
 
    new_rows = []
    for block in blocks:
        row = models.AvailabilityException(
            profile_id=profile_id,
            exception_date=exception_date,
            start_time=block.start_time,
            end_time=block.end_time,
            status=block.status,
            reason=block.reason,
        )
        db.add(row)
        new_rows.append(row)
 
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows