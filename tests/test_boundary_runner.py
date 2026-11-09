import unittest

from turbo.agents.boundary_runner import _role_model


class BoundaryRunnerTest(unittest.TestCase):
    def test_role_specific_models_allow_cross_vendor_assignments(self) -> None:
        execution = {
            "role_models": {
                "specialist-a": "vendor-a/model-a",
                "specialist-b": "vendor-b/model-b",
                "adjudicator": "vendor-c/model-c",
            }
        }
        self.assertEqual(_role_model(execution, "specialist-a"), "vendor-a/model-a")
        self.assertEqual(_role_model(execution, "specialist-b"), "vendor-b/model-b")
        self.assertEqual(_role_model(execution, "adjudicator"), "vendor-c/model-c")


if __name__ == "__main__":
    unittest.main()
