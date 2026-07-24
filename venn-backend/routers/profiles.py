# core
from fastapi import APIRouter, Depends, HTTPException # HTTPException for raising proper error responses
from sqlalchemy.orm import Session

# my helpers
from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/profiles", tags=["profile"])

# this router is used for any availability profile handling for logged in users
# GET profiles fetches the list of my profiles
# POST profiles creates a new profile
# PATCH profiles allows users to update their profiles
# DELETE profiles allows a user to delete their profile

@router.get("", response_model=list[schemas.ProfileOut])
def get_profiles(current_user: Session = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.AvailabilityProfile).filter(models.AvailabilityProfile.user_id == current_user.id).all()

@router.post("", response_model=schemas.ProfileOut)
def create_profile(profile: schemas.ProfileCreate, current_user: Session = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # if this new profile is being set as default, unset any existing default first
    if profile.is_default:
        db.query(models.AvailabilityProfile).filter(
            models.AvailabilityProfile.user_id == current_user.id
        ).update({"is_default": False})
 
    new_profile = models.AvailabilityProfile(
        user_id=current_user.id,
        name=profile.name,
        is_default=profile.is_default,
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return new_profile

@router.patch("/{profile_id}", response_model=schemas.ProfileOut)
def update_profile(profile_id: int, profile_update: schemas.ProfileUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    profile = db.query(models.AvailabilityProfile).filter(
        models.AvailabilityProfile.id == profile_id
    ).first()
 
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your profile")
 
    # only touch fields that were actually provided
    if profile_update.name is not None:
        profile.name = profile_update.name
 
    if profile_update.is_default is not None:
        if profile_update.is_default:
            # unset any other default profile this user has, before setting this one
            db.query(models.AvailabilityProfile).filter(
                models.AvailabilityProfile.user_id == current_user.id,
                models.AvailabilityProfile.id != profile_id,
            ).update({"is_default": False})
        profile.is_default = profile_update.is_default
 
    db.commit()
    db.refresh(profile)
    return profile # return updated profile

@router.delete("/{profile_id}", status_code=204) # status code 204 = No Content which means that this endpoint deliberately has nothing to send back
def delete_profile(
    profile_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(models.AvailabilityProfile).filter(
        models.AvailabilityProfile.id == profile_id
    ).first()
 
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your profile")
 
    was_default = profile.is_default # logic below is to prevent no default profile if a default profile was deleted
 
    db.delete(profile)
    db.flush()  # apply the delete within this transaction before querying again, without committing yet
    # this forces the deletion to occur FIRST then call the query below otherwise there might be a conflict of access
 
    if was_default:
        # promote the user's next-oldest remaining profile to default, if any exist
        next_profile = db.query(models.AvailabilityProfile).filter(
            models.AvailabilityProfile.user_id == current_user.id
        ).order_by(models.AvailabilityProfile.created_at).first()
 
        if next_profile:
            next_profile.is_default = True
 
    db.commit() # commit changes now
    return None