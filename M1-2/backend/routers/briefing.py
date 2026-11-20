from fastapi import APIRouter, Depends, HTTPException

from services import briefing, daily
from services.firebase import get_db

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


@router.get("", summary="오늘의 AI 브리핑 (NOAA 일별 기반 특이사항, 새 데이터 날짜당 1회 생성)")
def get_briefing(db=Depends(get_db)):
    try:
        return briefing.get_briefing(db)
    except daily.DailyUnavailable as e:
        raise HTTPException(503, str(e))
