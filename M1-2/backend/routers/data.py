import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from schemas import DataIn, DataList, DataOut
from services import repository as repo
from services.firebase import get_db
from services.summary import build_statistics, summarize

router = APIRouter(prefix="/api/data", tags=["data"])


def _payload(body: DataIn) -> dict:
    return {"date": body.date.isoformat(), "value": body.value, "memo": body.memo}


@router.post("", response_model=DataOut, status_code=201, summary="새 데이터 추가")
def create(body: DataIn, db=Depends(get_db)):
    return repo.create_data(db, _payload(body))


@router.get("", response_model=DataList, summary="데이터 목록 조회")
def list_items(limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0),
               order: Literal["asc", "desc"] = "desc", db=Depends(get_db)):
    items = repo.list_data(db)
    if order == "desc":
        items.reverse()
    return {"total": len(items), "items": items[offset:offset + limit]}


@router.get("/summary", summary="데이터 요약 (프롬프트 주입용)")
def summary(db=Depends(get_db)):
    return summarize(repo.list_data(db))


@router.get("/statistics", summary="추가 통계 (연평균 시계열 · 연간 증가량)")
def statistics(db=Depends(get_db)):
    return build_statistics(repo.list_data(db))


def _safe_cell(text: str) -> str:
    # CSV 수식 주입 방지: 엑셀이 =,+,-,@ 로 시작하는 셀을 수식으로 해석하지 않게 한다
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get("/export", summary="데이터 내보내기 (CSV 또는 JSON 다운로드)")
def export(format: Literal["csv", "json"] = "csv", db=Depends(get_db)):
    items = repo.list_data(db)
    if format == "json":
        body = json.dumps([{k: i[k] for k in ("id", "date", "value", "memo")} for i in items],
                          ensure_ascii=False, indent=2)
        media, name = "application/json; charset=utf-8", "co2_data.json"
    else:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "date", "value", "memo"])
        for i in items:
            w.writerow([i["id"], i["date"], i["value"], _safe_cell(i["memo"])])
        body = "\ufeff" + buf.getvalue()  # BOM: 엑셀에서 한글 memo 가 깨지지 않게
        media, name = "text/csv; charset=utf-8", "co2_data.csv"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.put("/{item_id}", response_model=DataOut, summary="데이터 수정")
def update(item_id: str, body: DataIn, db=Depends(get_db)):
    item = repo.update_data(db, item_id, _payload(body))
    if item is None:
        raise HTTPException(404, "데이터를 찾을 수 없습니다.")
    return item


@router.delete("/{item_id}", status_code=204, summary="데이터 삭제")
def delete(item_id: str, db=Depends(get_db)):
    if not repo.delete_data(db, item_id):
        raise HTTPException(404, "데이터를 찾을 수 없습니다.")
