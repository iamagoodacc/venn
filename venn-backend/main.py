from fastapi import FastAPI

# api endpoints
from routers import auth_routes
from routers import profiles
from routers import availability
from routers import events

app = FastAPI()
app.include_router(auth_routes.router)
app.include_router(profiles.router)
app.include_router(availability.router)
app.include_router(events.router)

@app.get("/ping")
def ping():
    return {"status": "ok"}