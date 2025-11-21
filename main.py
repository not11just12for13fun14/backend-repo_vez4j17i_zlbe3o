import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict
from datetime import datetime

from database import db, create_document, get_documents
from schemas import (
    User, KYC, SPV, Vehicle, Offering, Investment, Instalment, Wallet,
    Transaction, Distribution, Notification, Document, SecondaryOrder,
)

app = FastAPI(title="DriveShare Capital API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------

def now_iso() -> str:
    return datetime.utcnow().isoformat()


def ensure_wallet(user_id: str):
    w = db["wallet"].find_one({"user_id": user_id})
    if not w:
        wid = create_document("wallet", Wallet(user_id=user_id, balance=0.0))
        return db["wallet"].find_one({"_id": db["wallet"].find_one({"_id": wid})})
    return w


def credit_wallet(user_id: str, amount: float, tx_type: str, reference_id: Optional[str] = None, meta: Optional[dict] = None):
    ensure_wallet(user_id)
    db["wallet"].update_one({"user_id": user_id}, {"$inc": {"balance": amount}, "$set": {"updated_at": datetime.utcnow()}})
    create_document("transaction", Transaction(user_id=user_id, type=tx_type, amount=amount, reference_id=reference_id, meta=meta or {}))


def notify(user_id: str, title: str, message: str):
    create_document("notification", Notification(user_id=user_id, title=title, message=message))


# ---------- Public ----------

@app.get("/")
def read_root():
    return {"name": "DriveShare Capital", "status": "ok", "time": now_iso()}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name or ""
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:15]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"

    return response


# ---------- Schemas (for tooling) ----------

class SchemaInfo(BaseModel):
    name: str
    fields: Dict[str, str]


@app.get("/schema", response_model=List[SchemaInfo])
def get_schema():
    # reflect pydantic models from schemas
    models = [User, KYC, SPV, Vehicle, Offering, Investment, Instalment, Wallet, Transaction, Distribution, Notification, Document, SecondaryOrder]
    infos: List[SchemaInfo] = []
    for m in models:
        fields = {name: str(field.annotation) for name, field in m.model_fields.items()}
        infos.append(SchemaInfo(name=m.__name__.lower(), fields=fields))
    return infos


# ---------- Users & KYC ----------

@app.post("/users")
def create_user(user: User):
    # upsert by email
    existing = db["user"].find_one({"email": user.email})
    if existing:
        return {"id": str(existing["_id"]), "message": "exists"}
    _id = create_document("user", user)
    ensure_wallet(_id)
    return {"id": _id}


@app.get("/users")
def list_users(role: Optional[str] = None):
    query = {"role": role} if role else {}
    users = get_documents("user", query, limit=100)
    for u in users:
        u["id"] = str(u.pop("_id"))
    return users


@app.post("/kyc/submit")
def submit_kyc(kyc: KYC):
    _id = create_document("kyc", kyc)
    notify(kyc.user_id, "KYC Submitted", "Your KYC is under review")
    return {"id": _id}


@app.post("/kyc/{kyc_id}/set")
def set_kyc_status(kyc_id: str, status: Literal["approved", "rejected"]):
    res = db["kyc"].update_one({"_id": db["kyc"].find_one({"_id": kyc_id}) or kyc_id}, {"$set": {"status": status, "updated_at": datetime.utcnow()}})
    return {"updated": res.modified_count}


@app.get("/kyc/user/{user_id}")
def get_user_kyc(user_id: str):
    k = db["kyc"].find_one({"user_id": user_id}, sort=[("created_at", -1)])
    if not k:
        return {"status": "none"}
    k["id"] = str(k.pop("_id"))
    return k


# ---------- Offerings / Marketplace ----------

@app.post("/offerings")
def create_offering(off: Offering):
    if off.shares_total < off.cars_count * 10:
        raise HTTPException(status_code=400, detail="shares_total must be at least cars_count * 10")
    _id = create_document("offering", off)
    return {"id": _id}


@app.get("/offerings")
def list_offerings(status: Optional[str] = None):
    query = {"status": status} if status else {}
    items = get_documents("offering", query, limit=100)
    for it in items:
        it["id"] = str(it.pop("_id"))
    return items


# ---------- Investments & Instalments ----------

@app.post("/investments")
def create_investment(inv: Investment):
    # Simple rule: pledge_amount should be shares * share_price; not strictly enforced here
    _id = create_document("investment", inv)
    notify(inv.user_id, "Investment Created", f"You pledged {inv.shares} shares")
    return {"id": _id}


@app.get("/investments/user/{user_id}")
def user_investments(user_id: str):
    items = get_documents("investment", {"user_id": user_id}, limit=200)
    for it in items:
        it["id"] = str(it.pop("_id"))
    return items


class InstalmentPayment(BaseModel):
    user_id: str
    investment_id: str
    amount: float


@app.post("/instalments/pay")
def pay_instalment(payload: InstalmentPayment):
    create_document("instalment", Instalment(user_id=payload.user_id, investment_id=payload.investment_id, amount=payload.amount, due_month=datetime.utcnow().month, paid=True))
    credit_wallet(payload.user_id, -abs(payload.amount), "instalment_payment", reference_id=payload.investment_id)
    notify(payload.user_id, "Instalment Paid", f"Payment of ${payload.amount:.2f} recorded")
    return {"status": "ok"}


# ---------- Wallet & Payments ----------

class TopUp(BaseModel):
    user_id: str
    amount: float


@app.get("/wallet/{user_id}")
def get_wallet(user_id: str):
    w = db["wallet"].find_one({"user_id": user_id}) or {"user_id": user_id, "balance": 0.0}
    if "_id" in w:
        w["id"] = str(w.pop("_id"))
    return w


@app.post("/wallet/topup")
def wallet_topup(t: TopUp):
    credit_wallet(t.user_id, abs(t.amount), "topup")
    notify(t.user_id, "Wallet Top-up", f"+${t.amount:.2f} added to your wallet")
    return {"status": "ok"}


# ---------- Distributions & Exit ----------

class RunDistribution(BaseModel):
    offering_id: str
    month: int
    total_amount: float


@app.post("/distributions/run")
def run_distribution(req: RunDistribution):
    # Compute per-share based on offering.shares_total
    off = db["offering"].find_one({"_id": req.offering_id}) or db["offering"].find_one({"id": req.offering_id})
    if not off:
        raise HTTPException(404, "Offering not found")
    shares_total = off.get("shares_total", 0) or 0
    if shares_total <= 0:
        raise HTTPException(400, "Offering has no shares_total")
    per_share = req.total_amount / shares_total

    invs = list(db["investment"].find({"offering_id": req.offering_id, "status": "active"}))

    for inv in invs:
        uid = inv["user_id"]
        user_shares = inv.get("shares", 0)
        amount = round(user_shares * per_share, 2)
        if amount == 0:
            continue
        credit_wallet(uid, amount, "rental_distribution", reference_id=str(inv.get("_id")), meta={"offering_id": req.offering_id, "month": req.month, "per_share": per_share})
        notify(uid, "Monthly Distribution", f"${amount:.2f} credited for month {req.month}")

    create_document("distribution", Distribution(offering_id=req.offering_id, month=req.month, total_amount=req.total_amount, per_share=per_share))
    return {"status": "ok", "per_share": per_share}


class ExitRequest(BaseModel):
    investment_id: str


@app.post("/investments/exit")
def exit_investment(body: ExitRequest):
    inv = db["investment"].find_one({"_id": body.investment_id}) or db["investment"].find_one({"id": body.investment_id})
    if not inv:
        raise HTTPException(404, "Investment not found")
    db["investment"].update_one({"_id": inv["_id"]}, {"$set": {"status": "exited", "updated_at": datetime.utcnow()}})
    payout = round(inv.get("shares", 0) * 0.9 * 100, 2)  # mock payout
    credit_wallet(inv["user_id"], payout, "exit_payout", reference_id=str(inv["_id"]))
    notify(inv["user_id"], "Exit Processed", f"Exit payout ${payout:.2f} credited")
    return {"status": "ok", "payout": payout}


# ---------- Secondary Market ----------

@app.post("/secondary/orders")
def place_order(order: SecondaryOrder):
    _id = create_document("secondaryorder", order)
    notify(order.user_id, "Order Placed", f"{order.side.title()} {order.shares} shares at ${order.price_per_share}")
    return {"id": _id}


@app.get("/secondary/book")
def order_book(offering_id: Optional[str] = None):
    q = {"offering_id": offering_id} if offering_id else {}
    items = get_documents("secondaryorder", q, 200)
    for it in items:
        it["id"] = str(it.pop("_id"))
    return items


# ---------- Documents & E-sign ----------

@app.post("/documents")
def create_document_record(doc: Document):
    _id = create_document("document", doc)
    return {"id": _id}


class SignBody(BaseModel):
    document_id: str


@app.post("/documents/sign")
def sign_document(body: SignBody):
    res = db["document"].update_one({"_id": body.document_id}, {"$set": {"status": "signed", "updated_at": datetime.utcnow()}})
    return {"updated": res.modified_count}


# ---------- Notifications ----------

@app.get("/notifications/{user_id}")
def list_notifications(user_id: str):
    items = get_documents("notification", {"user_id": user_id}, 100)
    for it in items:
        it["id"] = str(it.pop("_id"))
    return items


# ---------- Admin ----------

@app.get("/admin/overview")
def admin_overview():
    total_users = db["user"].count_documents({})
    total_offerings = db["offering"].count_documents({})
    total_investments = db["investment"].count_documents({})
    tvl = 0.0
    for w in db["wallet"].find({}):
        tvl += float(w.get("balance", 0))
    return {
        "users": total_users,
        "offerings": total_offerings,
        "investments": total_investments,
        "wallet_tvl": round(tvl, 2),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
