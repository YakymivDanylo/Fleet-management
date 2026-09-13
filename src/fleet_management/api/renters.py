from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Renter
from ..schemas import RenterCreate, RenterRead

router = APIRouter(prefix="/renters", tags=["renters"])


@router.post("", response_model=RenterRead, status_code=201)
async def create_renter(payload: RenterCreate, db: AsyncSession = Depends(get_db)):
    renter = Renter(full_name=payload.full_name, license_number=payload.license_number)
    db.add(renter)
    await db.commit()
    await db.refresh(renter)
    return renter


@router.get("", response_model=list[RenterRead])
async def list_renters(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Renter))
    return result.scalars().all()


@router.get("/{renter_id}", response_model=RenterRead)
async def get_renter(renter_id: int, db: AsyncSession = Depends(get_db)):
    renter = await db.get(Renter, renter_id)
    if renter is None:
        raise HTTPException(status_code=404, detail="Renter not found")
    return renter
