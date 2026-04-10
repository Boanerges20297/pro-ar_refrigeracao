import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

if __package__ in {None, ''}:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license_api.config import settings
from license_api.database import Base, engine, get_db
from license_api.schemas import LicenseDetailsResponse, LicenseIssueRequest, LicenseIssueResponse, LicenseRevokeRequest, LicenseVerifyRequest, LicenseVerifyResponse
from license_api.security import ensure_keypair
from license_api.service import PLAN_FEATURES, get_license_details, issue_license, list_licenses, plan_features, revoke_license, verify_license


app = FastAPI(title=settings.app_name, version="1.0.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / 'templates'))


@app.on_event("startup")
def startup():
    ensure_keypair()
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)


def require_api_token(x_api_token: str = Header(default="")):
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_api_token")


def require_panel_auth(request: Request):
    if request.cookies.get('license_api_token') != settings.api_token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={'Location': '/admin/login'})


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.get('/admin/login', response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(request=request, name='login.html', context={'request': request, 'error': None})


@app.post('/admin/login', response_class=HTMLResponse)
def admin_login(request: Request, api_token: str = Form(...)):
    if api_token != settings.api_token:
        return templates.TemplateResponse(
            request=request,
            name='login.html',
            context={'request': request, 'error': 'Token administrativo inválido.'},
            status_code=401,
        )

    response = RedirectResponse(url='/admin', status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie('license_api_token', settings.api_token, httponly=True, samesite='lax')
    return response


@app.get('/admin/logout')
def admin_logout():
    response = RedirectResponse(url='/admin/login', status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie('license_api_token')
    return response


@app.get('/admin', response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    require_panel_auth(request)
    return templates.TemplateResponse(
        request=request,
        name='dashboard.html',
        context={
            'request': request,
            'licenses': list_licenses(db),
            'plans': PLAN_FEATURES,
            'issued_license': None,
            'error': None,
        },
    )


@app.post('/admin/licenses/issue', response_class=HTMLResponse)
def admin_issue_license(
    request: Request,
    company_name: str = Form(...),
    instance_fingerprint: str = Form(''),
    plan: str = Form('basic'),
    license_type: str = Form('perpetual'),
    duration_days: str = Form(''),
    max_users: str = Form(''),
    max_admin_users: str = Form(''),
    max_secretary_users: str = Form(''),
    db: Session = Depends(get_db),
):
    require_panel_auth(request)

    try:
        payload = LicenseIssueRequest(
            company_name=company_name,
            instance_fingerprint=instance_fingerprint or None,
            license_type=license_type,
            duration_days=int(duration_days) if duration_days else None,
            max_users=int(max_users) if max_users else None,
            max_admin_users=int(max_admin_users) if max_admin_users else None,
            max_secretary_users=int(max_secretary_users) if max_secretary_users else None,
            features=plan_features(plan),
            metadata={'plan': plan},
        )
        issued_license = issue_license(db, payload)
        error = None
    except Exception as exc:
        issued_license = None
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name='dashboard.html',
        context={
            'request': request,
            'licenses': list_licenses(db),
            'plans': PLAN_FEATURES,
            'issued_license': issued_license,
            'error': error,
        },
    )


@app.post('/admin/licenses/{license_id}/revoke')
def admin_revoke_license(request: Request, license_id: str, reason: str = Form(...), db: Session = Depends(get_db)):
    require_panel_auth(request)
    revoke_license(db, license_id, reason)
    return RedirectResponse(url='/admin', status_code=status.HTTP_303_SEE_OTHER)


@app.post("/licenses/issue", response_model=LicenseIssueResponse, dependencies=[Depends(require_api_token)])
def create_license(payload: LicenseIssueRequest, db: Session = Depends(get_db)):
    return issue_license(db, payload)


@app.post("/licenses/verify", response_model=LicenseVerifyResponse, dependencies=[Depends(require_api_token)])
def verify_existing_license(payload: LicenseVerifyRequest, db: Session = Depends(get_db)):
    return verify_license(
        db,
        payload.license_key,
        expected_company_name=payload.expected_company_name,
        expected_instance_fingerprint=payload.expected_instance_fingerprint,
    )


@app.get("/licenses/{license_id}", response_model=LicenseDetailsResponse, dependencies=[Depends(require_api_token)])
def read_license(license_id: str, db: Session = Depends(get_db)):
    return get_license_details(db, license_id)


@app.get('/licenses', response_model=list[LicenseDetailsResponse], dependencies=[Depends(require_api_token)])
def read_licenses(db: Session = Depends(get_db)):
    return list_licenses(db)


@app.post("/licenses/{license_id}/revoke", response_model=LicenseDetailsResponse, dependencies=[Depends(require_api_token)])
def revoke_existing_license(license_id: str, payload: LicenseRevokeRequest, db: Session = Depends(get_db)):
    return revoke_license(db, license_id, payload.reason)


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='127.0.0.1', port=8010)
