"""YAML 种子导入：平台 / 额度包 / 模型。仅缺省创建，不覆盖已有记录。"""

from datetime import datetime, timezone

import yaml
from sqlalchemy.orm import Session

from . import models
from .schemas import parse_dt


def load_seed(db: Session, path: str, force: bool = False) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    stats = {"platforms": 0, "packages": 0, "models": 0, "skipped": 0}

    for p in data.get("platforms", []):
        existing = db.get(models.Platform, p["id"])
        if existing and not force:
            stats["skipped"] += 1
            continue
        if existing:
            for k, v in p.items():
                setattr(existing, k, v)
        else:
            db.add(models.Platform(**p))
        stats["platforms"] += 1

    for pkg in data.get("packages", []):
        existing = db.get(models.ResourcePackage, pkg["id"])
        if existing and not force:
            stats["skipped"] += 1
            continue
        if existing:
            for k, v in pkg.items():
                setattr(existing, k, v)
        else:
            db.add(models.ResourcePackage(**pkg))
        stats["packages"] += 1

    for m in data.get("models", []):
        existing = db.get(models.Model, m["id"])
        if existing and not force:
            stats["skipped"] += 1
            continue
        rec = dict(m)
        rec["expired_at"] = parse_dt(m.get("expired_at"))
        if existing:
            for k, v in rec.items():
                setattr(existing, k, v)
        else:
            db.add(models.Model(**rec))
        stats["models"] += 1

    db.commit()
    return stats
