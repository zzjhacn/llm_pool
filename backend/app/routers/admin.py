from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..ledger import book
from ..schemas import (
    LedgerSummary,
    LoginIn,
    LoginOut,
    ModelCreate,
    ModelOut,
    ModelUpdate,
    PackageCreate,
    PackageOut,
    PackageUpdate,
    PlatformCreate,
    PlatformOut,
    PlatformUpdate,
)
from ..security import authenticate_admin, create_admin_token, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------- 登录 ----------------
@router.post("/login", response_model=LoginOut)
def login(body: LoginIn):
    if not authenticate_admin(body.username, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return LoginOut(token=create_admin_token(body.username), username=body.username)


# ---------------- Platform ----------------
@router.get("/platforms", response_model=list[PlatformOut], dependencies=[Depends(require_admin)])
def list_platforms(db: Session = Depends(get_db)):
    return db.query(models.Platform).all()


@router.post("/platforms", response_model=PlatformOut, dependencies=[Depends(require_admin)])
def create_platform(body: PlatformCreate, db: Session = Depends(get_db)):
    if db.get(models.Platform, body.id):
        raise HTTPException(status_code=409, detail=f"平台 {body.id} 已存在")
    p = models.Platform(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/platforms/{pid}", response_model=PlatformOut, dependencies=[Depends(require_admin)])
def get_platform(pid: str, db: Session = Depends(get_db)):
    p = db.get(models.Platform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="平台不存在")
    return p


@router.put("/platforms/{pid}", response_model=PlatformOut, dependencies=[Depends(require_admin)])
def update_platform(pid: str, body: PlatformUpdate, db: Session = Depends(get_db)):
    p = db.get(models.Platform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="平台不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/platforms/{pid}", dependencies=[Depends(require_admin)])
def delete_platform(pid: str, db: Session = Depends(get_db)):
    p = db.get(models.Platform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="平台不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------- ResourcePackage ----------------
@router.get("/packages", response_model=list[PackageOut], dependencies=[Depends(require_admin)])
def list_packages(db: Session = Depends(get_db)):
    return db.query(models.ResourcePackage).all()


@router.post("/packages", response_model=PackageOut, dependencies=[Depends(require_admin)])
def create_package(body: PackageCreate, db: Session = Depends(get_db)):
    if db.get(models.ResourcePackage, body.id):
        raise HTTPException(status_code=409, detail=f"额度包 {body.id} 已存在")
    pkg = models.ResourcePackage(**body.model_dump())
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.get("/packages/{pkid}", response_model=PackageOut, dependencies=[Depends(require_admin)])
def get_package(pkid: str, db: Session = Depends(get_db)):
    pkg = db.get(models.ResourcePackage, pkid)
    if not pkg:
        raise HTTPException(status_code=404, detail="额度包不存在")
    return pkg


@router.put("/packages/{pkid}", response_model=PackageOut, dependencies=[Depends(require_admin)])
def update_package(pkid: str, body: PackageUpdate, db: Session = Depends(get_db)):
    pkg = db.get(models.ResourcePackage, pkid)
    if not pkg:
        raise HTTPException(status_code=404, detail="额度包不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(pkg, k, v)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/packages/{pkid}", dependencies=[Depends(require_admin)])
def delete_package(pkid: str, db: Session = Depends(get_db)):
    pkg = db.get(models.ResourcePackage, pkid)
    if not pkg:
        raise HTTPException(status_code=404, detail="额度包不存在")
    db.delete(pkg)
    db.commit()
    return {"ok": True}


# ---------------- Model ----------------
def _model_out(m: models.Model) -> ModelOut:
    d = {c.name: getattr(m, c.name) for c in m.__table__.columns}
    d["package_balance"] = m.package.balance if m.package else None
    d["quota_source"] = m.quota_source
    d["quota_capacity"] = m.quota_capacity
    d["quota_used"] = m.quota_used
    d["quota_balance"] = m.quota_balance_eff
    d["effective_provider"] = m.provider or (m.platform.provider if m.platform else None)
    return ModelOut(**d)


@router.get("/models", response_model=list[ModelOut], dependencies=[Depends(require_admin)])
def list_models(db: Session = Depends(get_db)):
    return [_model_out(m) for m in db.query(models.Model).all()]


@router.post("/models", response_model=ModelOut, dependencies=[Depends(require_admin)])
def create_model(body: ModelCreate, db: Session = Depends(get_db)):
    if db.get(models.Model, body.id):
        raise HTTPException(status_code=409, detail=f"模型 {body.id} 已存在")
    if not db.get(models.Platform, body.platform_id):
        raise HTTPException(status_code=400, detail="platform_id 不存在")
    if body.package_id and body.quota_capacity is not None:
        raise HTTPException(status_code=400, detail="额度来源冲突：共享额度包与模型独立额度不能同时设置")
    if body.package_id:
        pkg = db.get(models.ResourcePackage, body.package_id)
        if not pkg:
            raise HTTPException(status_code=400, detail="package_id 不存在")
        if body.billing_type != pkg.unit:
            raise HTTPException(
                status_code=400,
                detail=f"同包计费必须一致：包的计费单位为 {pkg.unit}，模型的计费方式为 {body.billing_type}",
            )
    from ..schemas import parse_dt

    data = body.model_dump()
    data["expired_at"] = parse_dt(body.expired_at)
    if data.get("quota_used") is None:
        data["quota_used"] = 0.0
    m = models.Model(**data)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _model_out(m)


@router.get("/models/{mid}", response_model=ModelOut, dependencies=[Depends(require_admin)])
def get_model(mid: str, db: Session = Depends(get_db)):
    m = db.get(models.Model, mid)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    return _model_out(m)


@router.put("/models/{mid}", response_model=ModelOut, dependencies=[Depends(require_admin)])
def update_model(mid: str, body: ModelUpdate, db: Session = Depends(get_db)):
    m = db.get(models.Model, mid)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    upd = body.model_dump(exclude_unset=True)
    if "expired_at" in upd:
        from ..schemas import parse_dt

        upd["expired_at"] = parse_dt(body.expired_at)
    # 额度来源冲突：两者都显式设置时拒绝
    if "package_id" in upd and "quota_capacity" in upd and (
        upd["package_id"] is not None and upd["quota_capacity"] is not None
    ):
        raise HTTPException(status_code=400, detail="额度来源冲突：共享额度包与模型独立额度不能同时设置")
    # 共享包计费一致性：显式改了计费方式或换了包时校验
    if upd.get("package_id") is not None:
        pkg = db.get(models.ResourcePackage, upd["package_id"])
        if not pkg:
            raise HTTPException(status_code=400, detail="package_id 不存在")
        bt = upd.get("billing_type", m.billing_type)
        if bt != pkg.unit:
            raise HTTPException(
                status_code=400,
                detail=f"同包计费必须一致：包的计费单位为 {pkg.unit}，模型的计费方式为 {bt}",
            )
    # quota_used 在「无额度/共享包」模式下无意义，前端可能传 null；
    # 该列定义为 NOT NULL，归一成 0.0 以保证写入成功（package/none 模式下不会被读取）
    if "quota_used" in upd and upd["quota_used"] is None:
        upd["quota_used"] = 0.0
    for k, v in upd.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return _model_out(m)


@router.delete("/models/{mid}", dependencies=[Depends(require_admin)])
def delete_model(mid: str, db: Session = Depends(get_db)):
    m = db.get(models.Model, mid)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/models/{mid}/toggle", response_model=ModelOut, dependencies=[Depends(require_admin)])
def toggle_model(mid: str, enabled: bool, db: Session = Depends(get_db)):
    """手动启停：enabled=True 解除手动关闭；enabled=False 置手动关闭（优先级最高）。"""
    m = db.get(models.Model, mid)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    m.manual_disabled = not enabled
    m.enabled = enabled
    db.commit()
    db.refresh(m)
    return _model_out(m)


# ---------------- Ledger / 维护 ----------------
@router.get("/ledger", response_model=LedgerSummary, dependencies=[Depends(require_admin)])
def ledger(db: Session = Depends(get_db)):
    logs = db.query(models.UsageLog).all()
    total_cost = sum(l.cost for l in logs)
    total_calls = len(logs)
    total_units = sum(l.units for l in logs)
    by_model: dict[str, dict] = {}
    for l in logs:
        b = by_model.setdefault(l.model_id, {"model_id": l.model_id, "cost": 0.0, "calls": 0, "units": 0.0})
        b["cost"] += l.cost
        b["calls"] += 1
        b["units"] += l.units
    recent = [
        {
            "id": l.id,
            "model_id": l.model_id,
            "units": l.units,
            "cost": l.cost,
            "created_at": l.created_at.isoformat(),
        }
        for l in sorted(logs, key=lambda x: x.id, reverse=True)[:20]
    ]
    return LedgerSummary(
        total_cost=total_cost,
        total_calls=total_calls,
        total_units=total_units,
        by_model=list(by_model.values()),
        recent=recent,
    )


@router.post("/sync", dependencies=[Depends(require_admin)])
def sync(db: Session = Depends(get_db)):
    """重算所有模型的启用状态（过期/额度耗尽自动置否）。"""
    book.sync_model_states(db)
    return {"ok": True}
