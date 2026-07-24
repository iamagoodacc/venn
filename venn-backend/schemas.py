# describes the shape of the data, this is good for input validation particularly for data going into and out of the database
# if you accidentally return the whole users table, FastAPI will filter it down so you dont expose any sensitive information as you define


from pydantic import BaseModel, EmailStr, ConfigDict, field_validator, model_validator # model_validator for bulk validation after, field_validator is field by field declaration validator
from datetime import time, date, datetime


# Auth

class UserRegister(BaseModel):
    """What the client sends to POST /auth/register"""
    email: EmailStr # a special Pydantic type representing an email string (x@y.z) shape does need pydantic[email] lib
    password: str
    display_name: str
    timezone: str = "UTC" # this makes the field optional, its either a provided timezone or UTC

    @field_validator("password") # run this validation on specifically the password field
    @classmethod # decorator
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Display name cannot be blank")
        return value.strip()



class UserLogin(BaseModel):
    """What the client sends to POST /auth/login"""
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """What the server sends back for a user — never includes password_hash"""
    id: int
    email: str
    display_name: str
    timezone: str

    # Pydantic expects to build a model from a dict but our endpoint actually returns a SQLAlchemy user object not a dict
    # from_attributes = True tells Pydantic "when validating input for this schema, also accept objects and read them using their properties"
    # otherwise it would fail because Pydantic is looking for a dict

    model_config = ConfigDict(from_attributes=True) # when we are returning data, it returns as an object not a dictionary


class Token(BaseModel):
    """What the server sends back after a successful login"""
    access_token: str
    token_type: str = "bearer"

# Profiles

class ProfileCreate(BaseModel):
    """What the client sends to POST /profiles"""
    name: str | None = None # this pattern means it can be a string or null/missing in that case set to None
    is_default: bool | None = None

class ProfileUpdate(BaseModel):
    """What the client sends to PATCH /profiles/{id} — all fields optional,
    since a PATCH only needs to include the fields actually being changed"""
    name: str | None = None
    is_default: bool | None = None

class ProfileOut(BaseModel):
    """What the server sends back for a profile"""
    id: int # id of profile
    name: str # name of profile
    is_default: bool # is default profile

    model_config = ConfigDict(from_attributes=True)


# Recurring availability
 
class RecurringBlockIn(BaseModel):
    """One block within a day's submitted set - used inside a list, no id
    (the day's whole set is replaced, so individual rows are never
    addressed directly on write)"""
    start_time: time
    end_time: time
    status: str = "free"
 
    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ("free", "if_needed", "busy"):
            raise ValueError("status must be 'free', 'if_needed', or 'busy'")
        return value
 
    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError("end_time must be after start_time")
        return value
 
 
class RecurringOut(BaseModel):
    """A single stored recurring block, as returned by the API"""
    id: int
    day_of_week: int
    start_time: time
    end_time: time
    status: str
 
    model_config = ConfigDict(from_attributes=True)
 
 
# Exceptions
 
class ExceptionBlockIn(BaseModel):
    """One block within a date's submitted exception set. start_time and
    end_time both None means "all day"."""
    start_time: time | None = None
    end_time: time | None = None
    status: str = "busy"
    reason: str | None = None
 
    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ("free", "if_needed", "busy"):
            raise ValueError("status must be 'free', 'if_needed', or 'busy'")
        return value
    
    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError("end_time must be after start_time")
        return value
 
 
class ExceptionOut(BaseModel):
    """A single stored exception, as returned by the API"""
    id: int
    exception_date: date
    start_time: time | None # without = None Pydantic requires the field to STILL be present so without that field its invalid
    end_time: time | None # this schema doesn't have = None because its an output schema all of the data will be given compared to an input schema
    status: str
    reason: str | None
 
    model_config = ConfigDict(from_attributes=True)

# Events

class EventCreate(BaseModel):
    """What the client sends IN to POST /events"""
    name: str
    range_start: date | None = None
    range_end: date | None = None

    @field_validator("range_end")
    @classmethod
    def end_after_start(cls, value: date | None, info) -> date | None:
        if value is None:
            return value
        start = info.data.get("range_start")
        if start is not None and value <= start:
            raise ValueError("range_end must be after range_start")
        return value

class EventOut(BaseModel):
    """Single event returned by the API used to show information of event for joined participants or host"""
    id: int 
    name: str
    created_by: int
    range_start: date | None
    range_end: date | None
    invite_code: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventJoin(BaseModel):
    """What the client sends to POST /events/{id}/join.
    A logged-in user is identified via their JWT (not sent in this body).
    A guest is identified via guest_name, sent here since there's no JWT.
    Sole purpose of this block is to determine the identity of user/guest and whether a profile is being used with 3 outcomes:
    This is the first stage of two steps (joining the event at all)
    
    1. Logged in user sends profile_id -> done, no need for fresh paint availability
    2. Logged in user sends neither profile_id nor guest_name (wants to fresh paint) -> participant row created with profile_id == NULL
    3. Guest, sends guest_name (+ optional guest_password) -> participant row created with profile_id = NULL again"""

    guest_name: str | None = None
    profile_id: int | None = None
    guest_password: str | None = None

    @model_validator(mode="after")
    def check_profile_and_guest_exclusive(self):
        if self.profile_id is not None and self.guest_name is not None:
            raise ValueError("Cannot provide both profile_id and guest_name")
        if self.guest_password is not None and self.guest_name is None:
            raise ValueError("guest_password can only be set alongside guest_name")
        return self
    
class EventAvailabilityBlock(BaseModel):
    """One block within a fresh-paint submission - now includes date,
    since a single submission can cover multiple days across the event's
    range, unlike RecurringBlockIn which was scoped to one day by the URL"""
    date: date
    start_time: time
    end_time: time
    status: str = "free"
 
    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ("free", "if_needed", "busy"):
            raise ValueError("status must be 'free', 'if_needed', or 'busy'")
        return value
 
    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError("end_time must be after start_time")
        return value
 
 
class EventAvailabilitySubmit(BaseModel):
    """What the client sends to POST /events/{id}/participants/{id}/availability -
    the whole submission, not a single block. guest_password lives here,
    once, describing the whole request, rather than repeated on every block -
    only relevant if this participant is a guest with a password set;
    ignored for logged-in users, who are authenticated via their JWT instead.
    
    This is the 2nd step of the process (submitting time blocks for fresh paint availability):
    
    This schema is one of two compared to just a singular time block schema for recurring availability and exceptions from earlier because guest_password is a field passed with a submission not each individual block explained above
    And the actual availability is comprised of EventAvailabilityBlocks"""
    blocks: list[EventAvailabilityBlock]
    guest_password: str | None = None
 
 
class EventAvailabilityOut(BaseModel):
    """A single stored fresh-paint block, as returned by the API"""
    id: int
    date: date
    start_time: time
    end_time: time
    status: str
 
    model_config = ConfigDict(from_attributes=True)

class EventParticipantOut(BaseModel):
    """Response for a successful join for a single participant (user or guest)"""
    id: int
    event_id: int
    user_id: int | None
    guest_name: str | None
    profile_id: int | None

    model_config = ConfigDict(from_attributes=True)

class EventDetailOut(EventOut):
    """EventOut, plus the participant list - used only for GET /events/{id} to provide a full list of participants"""
    participants: list[EventParticipantOut] # some schema inheritance which inherits all the fields of EventParticipantOut ands adds participants on top

class EventPreviewOut(BaseModel):
    """Public-safe preview shown before someone commits to joining - deliberately excludes the participant list compared to EventDetailOut and doesn't show created_by and invite_code"""
    id: int
    name: str
    range_start: date | None
    range_end: date | None

    model_config = ConfigDict(from_attributes=True)


# still need one more schema for overlap but will do that later as I am unsure of what is needed for now