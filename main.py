
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


def order_date(order):
    return datetime.fromisoformat(
        order["created_at"].replace("Z", "+00:00")
    )


def filter_region(rows, s):
    for region in ["north", "south", "east", "west", "central"]:
        if re.search(r"\b" + region + r"\b", s):
            return [
                o for o in rows
                if o["region"].lower() == region
            ]
    return rows


def filter_month_year(rows, s):
    months = {
        "january": 1, "february": 2, "march": 3,
        "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }

    selected_month = next(
        (month for name, month in months.items() if name in s),
        None,
    )

    year_match = re.search(r"\b(20\d{2})\b", s)
    selected_year = int(year_match.group(1)) if year_match else None

    if selected_month is not None:
        rows = [
            o for o in rows
            if order_date(o).month == selected_month
        ]

    if selected_year is not None:
        rows = [
            o for o in rows
            if order_date(o).year == selected_year
        ]

    return rows


def filter_product(rows, s):
    products = sorted(
        {o["product"] for o in ORDERS},
        key=len,
        reverse=True,
    )

    for product in products:
        if re.search(r"\b" + re.escape(product.lower()) + r"\b", s):
            return [
                o for o in rows
                if o["product"].lower() == product.lower()
            ]

    return rows


def answer_question(q):
    s = q.lower().strip()
    rows = paid_orders()

    # Count distinct customers with matching paid orders.
    if (
        "customer" in s
        and any(word in s for word in [
            "how many", "different", "unique", "distinct"
        ])
    ):
        filtered = filter_product(rows, s)
        filtered = filter_region(filtered, s)
        filtered = filter_month_year(filtered, s)
        return len({o["customer"] for o in filtered})

    # Count orders, including refunded and void orders.
    if (
        "how many" in s
        or "number of orders" in s
        or "count" in s
    ):
        filtered = ORDERS

        if "refund" in s:
            filtered = [
                o for o in filtered if o["status"] == "refunded"
            ]
        elif "void" in s:
            filtered = [
                o for o in filtered if o["status"] == "void"
            ]
        elif "paid" in s:
            filtered = [
                o for o in filtered if o["status"] == "paid"
            ]

        filtered = filter_region(filtered, s)
        filtered = filter_product(filtered, s)
        filtered = filter_month_year(filtered, s)

        return len(filtered)

    
    # Average paid order value in USD.
    if any(word in s for word in [
        "average", "mean", "avg", "on average"
    ]):
        filtered = filter_region(rows, s)
        filtered = filter_product(filtered, s)
        filtered = filter_month_year(filtered, s)

        if not filtered:
            return 0.0

        total = sum(usd_amount(o) for o in filtered)
        return money(total / len(filtered))


    # Revenue / earnings in USD.
    if any(word in s for word in [
        "revenue", "earn", "earned", "sales", "income",
        "how much", "total amount"
    ]):
        filtered = rows

        if "refund" in s:
            filtered = [
                o for o in ORDERS if o["status"] == "refunded"
            ]
        elif "void" in s:
            filtered = [
                o for o in ORDERS if o["status"] == "void"
            ]

        filtered = filter_region(filtered, s)
        filtered = filter_product(filtered, s)
        filtered = filter_month_year(filtered, s)

        # Find the top-selling product by revenue.
        if any(word in s for word in [
            "top-selling", "top selling", "best-selling",
            "best selling", "most sold", "highest-selling",
            "highest selling"
        ]) or (
            any(word in s for word in ["top", "highest", "best"])
            and "product" in s
        ):
            totals = defaultdict(float)

            for o in filtered:
                totals[o["product"]] += usd_amount(o)

            if totals:
                return max(totals, key=totals.get)

            return ""

        return money(sum(usd_amount(o) for o in filtered))


    # Product sales and rankings.
    if "product" in s or any(
        p.lower() in s for p in {o["product"] for o in ORDERS}
    ):
        totals = defaultdict(float)

        for o in rows:
            totals[o["product"]] += usd_amount(o)

        if any(word in s for word in ["most", "highest", "top"]):
            return max(totals, key=totals.get)

        filtered = filter_product(rows, s)
        if filtered and any(
            p.lower() in s for p in {o["product"] for o in ORDERS}
        ):
            return money(sum(usd_amount(o) for o in filtered))

        return {
            k: money(v) for k, v in sorted(totals.items())
        }

    # Customer counts or a particular customer's order count.
    if "customer" in s:
        customer_ids = {o["customer"] for o in ORDERS}

        for customer in customer_ids:
            if customer.lower() in s:
                return sum(
                    o["customer"] == customer for o in ORDERS
                )

        return len(customer_ids)

    # Revenue totals by region.
    if "region" in s:
        totals = defaultdict(float)

        for o in rows:
            totals[o["region"]] += usd_amount(o)

        return {
            k: money(v) for k, v in sorted(totals.items())
        }

    return "I could not determine the answer from the question."


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/answer")
def answer(body: Question):
    return {"answer": answer_question(body.question)}
