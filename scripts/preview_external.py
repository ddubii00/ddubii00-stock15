"""Local UI preview: public Telemoa data only. Never connects to a Telegram account."""
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from backend.app.telemoa import Telemoa, TelemoaUnavailable

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
provider = Telemoa()


@app.get('/api/insights/telemoa')
async def preview(mode: Literal['latest', 'cumulative'] = 'latest'):
    try:
        return JSONResponse(await provider.get(mode), headers={'Cache-Control': 'no-store'})
    except TelemoaUnavailable:
        return JSONResponse({'detail': 'Telemoa 정보를 불러올 수 없습니다. 원문 사이트를 확인해 주세요.'}, status_code=502, headers={'Cache-Control': 'no-store'})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8015, access_log=False, log_level='warning')
