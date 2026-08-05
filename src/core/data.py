from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class OrderBundle:
    order: pd.DataFrame
    items: pd.DataFrame
    payments: pd.DataFrame
    sellers: pd.DataFrame


class DataLoader:
    _FILES = {
        "customers": "olist_customers_dataset.csv",
        "geolocation": "olist_geolocation_dataset.csv",
        "orders": "olist_orders_dataset.csv",
        "items": "olist_order_items_dataset.csv",
        "payments": "olist_order_payments_dataset.csv",
        "reviews": "olist_order_reviews_dataset.csv",
        "products": "olist_products_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
        "category_translation": "product_category_name_translation.csv",
    }
    _REQUIRED_COLUMNS = {
        "orders": {"order_id"},
        "items": {"order_id", "seller_id"},
        "payments": {"order_id"},
        "sellers": {"seller_id"},
    }

    def __init__(self, data_dir: str | Path):
        data_dir = Path(data_dir)
        self._tables = {
            name: pd.read_csv(
                data_dir / filename,
                dtype=str,
                keep_default_na=False,
            )
            for name, filename in self._FILES.items()
        }
        for name, required in self._REQUIRED_COLUMNS.items():
            missing = required - set(self._tables[name].columns)
            if missing:
                raise ValueError(f"{name} CSV missing columns: {sorted(missing)}")

    def get_order_bundle(self, order_id: str) -> OrderBundle:
        order_id = str(order_id)
        orders = self._tables["orders"]
        items = self._tables["items"]
        payments = self._tables["payments"]
        sellers = self._tables["sellers"]

        order = orders.loc[orders["order_id"].eq(order_id)].copy()
        order_items = items.loc[items["order_id"].eq(order_id)].copy()
        order_payments = payments.loc[payments["order_id"].eq(order_id)].copy()
        seller_ids = order_items["seller_id"].drop_duplicates().tolist()
        order_sellers = sellers.loc[sellers["seller_id"].isin(seller_ids)].copy()

        return OrderBundle(
            order=order,
            items=order_items,
            payments=order_payments,
            sellers=order_sellers,
        )
