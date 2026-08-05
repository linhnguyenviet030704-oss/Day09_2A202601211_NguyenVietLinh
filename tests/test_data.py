import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.core.data import DataLoader


class DataLoaderTests(unittest.TestCase):
    def test_get_order_bundle_filters_related_rows_and_returns_dataframes(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            pd.DataFrame([
                {"order_id": "o1", "order_status": "delivered"},
                {"order_id": "o2", "order_status": "canceled"},
            ]).to_csv(data_dir / "olist_orders_dataset.csv", index=False)
            pd.DataFrame([
                {"order_id": "o1", "order_item_id": "1", "seller_id": "s1"},
                {"order_id": "o2", "order_item_id": "1", "seller_id": "s2"},
            ]).to_csv(data_dir / "olist_order_items_dataset.csv", index=False)
            pd.DataFrame([
                {"order_id": "o1", "payment_sequential": "1", "payment_value": "10.00"},
                {"order_id": "o2", "payment_sequential": "1", "payment_value": "20.00"},
            ]).to_csv(data_dir / "olist_order_payments_dataset.csv", index=False)
            pd.DataFrame([
                {"seller_id": "s1", "seller_city": "A"},
                {"seller_id": "s2", "seller_city": "B"},
            ]).to_csv(data_dir / "olist_sellers_dataset.csv", index=False)
            for filename in (
                "olist_customers_dataset.csv",
                "olist_geolocation_dataset.csv",
                "olist_order_reviews_dataset.csv",
                "olist_products_dataset.csv",
                "product_category_name_translation.csv",
            ):
                pd.DataFrame({"unused": []}).to_csv(data_dir / filename, index=False)

            bundle = DataLoader(data_dir).get_order_bundle("o1")

            self.assertIsInstance(bundle.order, pd.DataFrame)
            self.assertEqual(bundle.order.iloc[0]["order_status"], "delivered")
            self.assertEqual(bundle.items["seller_id"].tolist(), ["s1"])
            self.assertEqual(bundle.payments["payment_value"].tolist(), ["10.00"])
            self.assertEqual(bundle.sellers["seller_id"].tolist(), ["s1"])


if __name__ == "__main__":
    unittest.main()
