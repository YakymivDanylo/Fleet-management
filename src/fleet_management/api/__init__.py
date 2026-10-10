from fastapi import APIRouter

from . import admin, auth, home, privacy, rentals, renters, stations, vehicles

router = APIRouter()
router.include_router(auth.router)
router.include_router(home.router)
router.include_router(admin.router)
router.include_router(stations.router)
router.include_router(renters.router)
router.include_router(vehicles.router)
router.include_router(rentals.router)
router.include_router(privacy.router)
router.include_router(privacy.admin_router)
