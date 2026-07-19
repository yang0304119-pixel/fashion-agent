import unittest

try:
    from app.tools._registry import TOOL_DEFINITIONS, TOOL_HANDLERS
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class ReactToolScopeTests(unittest.TestCase):
    def test_only_readonly_tools_are_registered(self):
        expected = {
            "query_order",
            "query_inventory",
            "size_recommend",
            "search_products",
        }
        definition_names = {
            definition["function"]["name"] for definition in TOOL_DEFINITIONS
        }
        self.assertEqual(definition_names, expected)
        self.assertEqual(set(TOOL_HANDLERS), expected)

    def test_identity_fields_are_not_exposed_to_llm(self):
        forbidden = {"user_id", "tenant_id", "db"}
        for definition in TOOL_DEFINITIONS:
            with self.subTest(tool=definition["function"]["name"]):
                properties = definition["function"]["parameters"]["properties"]
                self.assertTrue(forbidden.isdisjoint(properties))


if __name__ == "__main__":
    unittest.main()
