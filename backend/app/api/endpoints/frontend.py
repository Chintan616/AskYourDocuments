from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/")
async def hero_page(request: Request):
    return templates.TemplateResponse(request=request, name="hero-geometric.html")

@router.get("/chatui")
async def chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html")
