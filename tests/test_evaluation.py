import unittest

from barricator import UserContext
from barricator import evaluation
from barricator.murmur import bucket_0_to_99, bucket_100k


def _flag(**kwargs):
    base = {
        "key": "f",
        "on": True,
        "variations": [
            {"id": "on", "value": True},
            {"id": "off", "value": False},
        ],
        "rules": [],
        "offVariationId": "off",
        "fallthroughVariationId": "off",
    }
    base.update(kwargs)
    return base


class EvaluationTests(unittest.TestCase):
    def test_off_serves_off_variation(self):
        result = evaluation.evaluate(_flag(on=False), UserContext("u1"), True)
        self.assertFalse(result.value)
        self.assertEqual(result.reason, evaluation.REASON_OFF)

    def test_rule_ends_with_email(self):
        flag = _flag(
            rules=[{
                "id": "r1",
                "clauses": [{"attribute": "email", "op": "ENDS_WITH", "values": ["@enterprise.com"]}],
                "variationId": "on",
            }],
        )
        enterprise = UserContext("u1", email="user@enterprise.com")
        consumer = UserContext("u2", email="user@gmail.com")
        self.assertTrue(evaluation.evaluate(flag, enterprise, False).value)
        self.assertFalse(evaluation.evaluate(flag, consumer, False).value)

    def test_missing_flag_returns_fallback(self):
        result = evaluation.evaluate(None, UserContext("u1"), "fallback")
        self.assertEqual(result.value, "fallback")
        self.assertTrue(result.is_defaulted)

    def test_rollout_is_deterministic(self):
        flag = _flag(fallthroughRollout={
            "variations": [
                {"variationId": "on", "weight": 50000},
                {"variationId": "off", "weight": 50000},
            ],
        })
        user = UserContext("stable-user-123")
        first = evaluation.evaluate(flag, user, False).value
        second = evaluation.evaluate(flag, user, False).value
        self.assertEqual(first, second)

    def test_custom_attribute_targeting(self):
        flag = _flag(rules=[{
            "id": "r1",
            "clauses": [{"attribute": "plan", "op": "IN", "values": ["pro", "enterprise"]}],
            "variationId": "on",
        }])
        self.assertTrue(evaluation.evaluate(flag, UserContext("u", custom={"plan": "pro"}), False).value)
        self.assertFalse(evaluation.evaluate(flag, UserContext("u", custom={"plan": "free"}), False).value)


class MurmurTests(unittest.TestCase):
    def test_bucket_in_range_and_stable(self):
        b = bucket_0_to_99("flag", "salt", "user-1")
        self.assertTrue(0 <= b < 100)
        self.assertEqual(b, bucket_0_to_99("flag", "salt", "user-1"))
        self.assertTrue(0 <= bucket_100k("flag", "salt", "user-1") < 100000)


if __name__ == "__main__":
    unittest.main()
