"""Binder REST routes: the domain routers, gathered under one router for the application."""

from fastapi import APIRouter

from binder.api import agent, deadlines, documents, folders, imports, local_ai, system
from binder.api.common import disposition as _disposition

__all__ = ["_disposition", "router"]

router = APIRouter()
for _domain in (system, documents, folders, deadlines, imports, local_ai, agent):
    router.include_router(_domain.router)
