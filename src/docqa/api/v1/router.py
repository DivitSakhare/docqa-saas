from fastapi import APIRouter

from docqa.api.v1.auth import router as auth_router
from docqa.api.v1.chat import router as chat_router
from docqa.api.v1.conversations import router as conversations_router
from docqa.api.v1.documents import router as documents_router
from docqa.api.v1.team import router as team_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(team_router)
