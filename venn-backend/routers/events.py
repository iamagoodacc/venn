# core
from fastapi import APIRouter, Depends, HTTPException # HTTPException for raising proper error responses
from sqlalchemy.orm import Session

# my helpers
from database import get_db
from datetime import date as date_type
import models
import schemas
import auth

router = APIRouter(tags=["events"])

@router.post("/events", response_model=schemas.EventOut)
def create_event(event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    pass

@router.get("/events/mine", response_model=schemas.EventOut)
def get_created_events(event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    pass

@router.get("/events/joined", response_model=schemas.EventOut)
def get_joined_events(event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    pass

@router.get("/events/{id}", response_model=schemas.EventOut)
def get_event_details(id: int, event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    pass

@router.get("/join/{invite_code}", response_model=schemas.EventOut)
def preview_joined_event(invite_code: str, id: int, event: schemas.EventCreate, db: Session = Depends(get_db)):
    pass

@router.post("/events/{id}/join", response_model=schemas.EventOut)
def join_event(invite_code: str, id: int, event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Register user as a participant of the event and sets profile_id if they chose/have one"""
    pass

@router.post("/events/{id}/participants/{participant_id}/availability", response_model=schemas.EventOut)
def join_event_fresh(invite_code: str, id: int, event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """This is after being registered as a participant, used to actually record the timeblocks of anyone who wants to paint a fresh availability"""
    pass

@router.get("/events/{id}/overlap?mode=&participant_ids=", response_model=schemas.EventOut)
def get_event_availability(invite_code: str, id: int, event: schemas.EventCreate,current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Get the data for heatmap/overlap, which will pull all participant availability"""
    pass