from fastapi import APIRouter

from . import rentals, renters, stations, vehicles

router = APIRouter()
router.include_router(stations.router)
router.include_router(renters.router)
router.include_router(vehicles.router)
router.include_router(rentals.router)
