"""
Data loader for the Olist CSV dataset (Member A: Data + Coordinator + Runner).

Loads the 9 CSVs once and exposes get_order_bundle(order_id) so every
agent reads from the same in-memory tables instead of re-parsing CSVs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


@dataclass
class OrderBundle:
    order_id: str
    order: dict | None
    items: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    sellers: dict[str, dict] = field(default_factory=dict)


class DataStore:
    def __init__(self, data_dir: str = DATA_DIR):
        self.orders = pd.read_csv(os.path.join(data_dir, "olist_orders_dataset.csv"))
        self.items = pd.read_csv(os.path.join(data_dir, "olist_order_items_dataset.csv"))
        self.payments = pd.read_csv(os.path.join(data_dir, "olist_order_payments_dataset.csv"))
        self.sellers = pd.read_csv(os.path.join(data_dir, "olist_sellers_dataset.csv"))
        self.products = pd.read_csv(os.path.join(data_dir, "olist_products_dataset.csv"))
        self.customers = pd.read_csv(os.path.join(data_dir, "olist_customers_dataset.csv"))
        self.reviews = pd.read_csv(os.path.join(data_dir, "olist_order_reviews_dataset.csv"))

        for col in [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ]:
            self.orders[col] = pd.to_datetime(self.orders[col], errors="coerce")
        self.items["shipping_limit_date"] = pd.to_datetime(
            self.items["shipping_limit_date"], errors="coerce"
        )

        self._orders_by_id = self.orders.set_index("order_id", drop=False)
        self._sellers_by_id = self.sellers.set_index("seller_id", drop=False)

    def get_order_bundle(self, order_id: str) -> OrderBundle:
        order_row = None
        if order_id in self._orders_by_id.index:
            row = self._orders_by_id.loc[order_id]
            order_row = row.to_dict() if not isinstance(row, pd.DataFrame) else row.iloc[0].to_dict()

        item_rows = self.items[self.items["order_id"] == order_id]
        items = item_rows.sort_values("order_item_id").to_dict("records")

        payment_rows = self.payments[self.payments["order_id"] == order_id]
        payment_rows = payment_rows.sort_values("payment_sequential")
        payments = payment_rows.to_dict("records")

        seller_ids = {it["seller_id"] for it in items if pd.notna(it.get("seller_id"))}
        sellers = {}
        for sid in seller_ids:
            if sid in self._sellers_by_id.index:
                srow = self._sellers_by_id.loc[sid]
                sellers[sid] = srow.to_dict() if not isinstance(srow, pd.DataFrame) else srow.iloc[0].to_dict()

        return OrderBundle(order_id=order_id, order=order_row, items=items, payments=payments, sellers=sellers)


_store: DataStore | None = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store


def get_order_bundle(order_id: str) -> OrderBundle:
    return get_store().get_order_bundle(order_id)
