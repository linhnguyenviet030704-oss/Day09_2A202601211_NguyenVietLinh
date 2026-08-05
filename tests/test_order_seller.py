import unittest

from src.agents.order_seller import _extract


class OrderSellerTests(unittest.TestCase):
    def test_extract_reports_only_late_seller_and_item_ids(self):
        result = _extract({
            "order_id": "o1",
            "order_status": "delivered",
            "order_delivered_carrier_date": "2018-01-12 00:00:00",
            "items": [
                {
                    "order_item_id": "1",
                    "seller_id": "seller_late",
                    "price": "10",
                    "freight_value": "2",
                    "shipping_limit_date": "2018-01-10 00:00:00",
                },
                {
                    "order_item_id": "2",
                    "seller_id": "seller_ok",
                    "price": "20",
                    "freight_value": "3",
                    "shipping_limit_date": "2018-01-15 00:00:00",
                },
            ],
        })

        self.assertEqual(result["late_seller_ids"], ["seller_late"])
        self.assertEqual(result["late_item_ids"], ["1"])


if __name__ == "__main__":
    unittest.main()
