# core
from fastapi import APIRouter, Depends, HTTPException # HTTPException for raising proper error responses
from sqlalchemy.orm import Session

# my helpers
from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/auth", tags=["auth"])


# auth routes is for login purposes
# POST register is for registering and creating accounts, which also creates a JWT
# POST login is for allowing user to login which is where password hash is checked
# GET me is for validation and security, ensuring when a client tried to access some data that it is 1. logged in 2. data is related to THEM and not someone else

@router.post("/register", response_model=schemas.UserOut)
def register(user: schemas.UserRegister, db: Session = Depends(get_db)):
    # check for existing email
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        email=user.email,
        password_hash=auth.hash_password(user.password),
        display_name=user.display_name,
        timezone=user.timezone,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user   # UserOut schema object

@router.post("/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first() # will fetch user data

    if not user or not auth.verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    jwt = auth.create_access_token({"sub": str(user.id)}) # the other stuff already automatically added on auth.py
    return jwt

@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)): # all of the work is done before the function is even called in .get_current_user()
    return current_user