# couple of helper functions to help with user authentication

import os
from datetime import datetime, timedelta, timezone
 
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import bcrypt

from database import get_db
import models

JWT_SECRET = os.getenv("JWT_SECRET") # used to add to signature of JWT
JWT_ALGORITHM = "HS256" # the algorithm which is to be included in the header
DEFAULT_EXPIRES_MINUTES = 600  # 10 hours
 
# this has two functions:
# it tells FastAPI, for any endpoint that relies on this, look for a Authorization: Bearer <token> (in header of a HTTP request), and if present hand me only the token which removes need for parsing
# if auth bearer token is missing, it will auto raise 401 error 
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# password flow (form-encoded username/password), it's a custom JSON login,
# so OAuth2PasswordBearer's built-in /docs login form doesn't actually match
# our /auth/login endpoint's request shape. HTTPBearer just extracts
# whatever's in the Authorization header, no assumptions about how it got there.
http_bearer = HTTPBearer()


# hashes a password
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# verifies password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# creates the JWT
def create_access_token(data: dict, expires_minutes: int = 600) -> str:
    # JWT format: header.payload.signature
    # data is what to embed (includes our subject )

    to_encode = data.copy() # this will be all of the data given in to act as payload
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)

    to_encode["iat"] = now # adds iat
    to_encode["exp"] = expire # adds an expiry datetime

    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM) # jwt.encode automatically performs checks for expiry so I never have to check the timestamp manually

# decodes and validates a JWT from the Authorization header, look up the user in the database and returns the user object
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer), db: Session = Depends(get_db)) -> models.User:
    token = credentials.credentials
    credentials_error = HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]) # decoding the JWT to check if its valid with our JWT_SECRET
        user_id: str = payload.get("sub") # gets the user_id from the payload
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error
 
    user = db.query(models.User).filter(models.User.id == int(user_id)).first() # check if the user exists in users table
    if user is None:
        raise credentials_error
 
    return user # all is fine return the user

# this is a second version of get_current_user that allows no user_id and just returns None instead of an error, used for guests
def get_current_user_optional(credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)), db: Session = Depends(get_db)) -> models.User | None:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None