import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE = Path(__file__).parent

with open(BASE / "clean_orders.json", encoding="utf-8") as f:
    ORDERS = json.load(f)

with open(BASE / "rates_response.json", encoding="utf-8") as f:
    RATES = json.load(f)["usd_per_unit"]

app = FastAPI(title="Ledger Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Question(BaseModel):
    question: str

def paid_orders():
    return [o for o in ORDERS if o["status"] == "paid"]

def usd_amount(order):
    return float(order["amount"]) * RATES[order["currency"]]

def money(value):
    return round(value + 1e-8, 2)

def answer_question(q):
    s = q.lower()
    rows = paid_orders()

    # Average paid order value, converted to USD.
    if "average" in s or "average order value" in s or "mean order value" in s:
        filtered = rows

        regions = ["north", "south", "east", "west", "central"]
        for region in regions:
            if re.search(r"\b" + region + r"\b", s):
                filtered = [
                    o for o in filtered
                    if o["region"].lower() == region
                ]
                break

        if not filtered:
            return 0.0

        total = sum(usd_amount(o) for o in filtered)
        return money(total / len(filtered))

    # Revenue in USD, optionally filtered by region and month.
    if "revenue" in s:
        filtered = rows

        regions = ["north", "south", "east", "west", "central"]
        for region in regions:
            if re.search(r"\b" + region + r"\b", s):
                filtered = [o for o in filtered if o["region"].lower() == region]
                break

        months = {
            "january": 1, "february": 2, "march": 3,
            "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9,
            "october": 10, "november": 11, "december": 12,
        }
        for name, month in months.items():
            if name in s:
                filtered = [
                    o for o in filtered
                    if datetime.fromisoformat(
                        o["created_at"].replace("Z", "+00:00")
                    ).month == month
                ]
                break

        total = sum(usd_amount(o) for o in filtered)
        return money(total)
    
    # Count distinct customers who placed paid orders for a product.
    if "customer" in s and any(
        word in s for word in ["how many", "different", "unique", "distinct"]
    ):
        product_name = next(
            (
                p for p in {o["product"] for o in ORDERS}
                if p.lower() in s
            ),
            None,
        )

        filtered = rows
        if product_name:
            filtered = [
                o for o in filtered
                if o["product"].lower() == product_name.lower()
            ]

        return len({o["customer"] for o in filtered})
    
    # Count orders with optional region, product, and month filters.
    if "how many" in s or "number of orders" in s or "count" in s:
        filtered = ORDERS

        if "refund" in s:
            filtered = [o for o in filtered if o["status"] == "refunded"]
        elif "void" in s:
            filtered = [o for o in filtered if o["status"] == "void"]
        elif "paid" in s:
            filtered = [o for o in filtered if o["status"] == "paid"]

        for region in ["north", "south", "east", "west", "central"]:
            if re.search(r"\b" + region + r"\b", s):
                filtered = [
                    o for o in filtered
                    if o["region"].lower() == region
                ]
                break

        months = {
            "january": 1, "february": 2, "march": 3,
            "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9,
            "october": 10, "november": 11, "december": 12,
        }

        for name, month in months.items():
            if name in s:
                filtered = [
                    o for o in filtered
                    if datetime.fromisoformat(
                        o["created_at"].replace("Z", "+00:00")
                    ).month == month
                    and datetime.fromisoformat(
                        o["created_at"].replace("Z", "+00:00")
                    ).year == 2026
                ]
                break

        return len(filtered)

    # Number of orders, optionally filtered by status.
    if "how many" in s or "number of orders" in s or "count" in s:
        if "refund" in s:
            return sum(o["status"] == "refunded" for o in ORDERS)
        if "void" in s:
            return sum(o["status"] == "void" for o in ORDERS)
        if "paid" in s:
            return len(rows)
        return len(ORDERS)

    # Refund-related questions.
    if "refund" in s:
        refunded = [o for o in ORDERS if o["status"] == "refunded"]
        return money(sum(usd_amount(o) for o in refunded))

    # Product questions.
    if "product" in s or any(
        p.lower() in s
        for p in {o["product"] for o in ORDERS}
    ):
        totals = defaultdict(float)
        for o in rows:
            totals[o["product"]] += usd_amount(o)

        if "most" in s or "highest" in s or "top" in s:
            return max(totals, key=totals.get)
        for product in totals:
            if product.lower() in s:
                return money(totals[product])
        return dict(sorted(
            ((k, money(v)) for k, v in totals.items()),
            key=lambda x: x[0]
        ))

    # Customer questions.
    if "customer" in s:
        customer_ids = set(o["customer"] for o in ORDERS)
        for customer in customer_ids:
            if customer.lower() in s:
                return sum(o["customer"] == customer for o in ORDERS)
        return len(customer_ids)

    # Region questions.
    if "region" in s:
        totals = defaultdict(float)
        for o in rows:
            totals[o["region"]] += usd_amount(o)
        return {k: money(v) for k, v in sorted(totals.items())}

    return "I could not determine the answer from the question."

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/answer")
def answer(body: Question):
    return {"answer": answer_question(body.question)}

