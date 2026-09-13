import copy
import unittest
from unittest.mock import AsyncMock
from open_llm_vtuber.mcpp.tool_adapter import ToolAdapter
from open_llm_vtuber.mcpp.types import FormattedTool
from open_llm_vtuber.mcpp.tool_schema import provider_schema, validate_arguments, schema_digest, SchemaError


class SchemaTests(unittest.TestCase):
    def test_nested_bounds_nullable_union_array_and_local_ref(self):
        schema = {"type":"object", "$defs":{"n":{"type":"integer","minimum":1,"maximum":4}},
                  "properties":{"options":{"type":"object","required":["count"],"properties":{"count":{"$ref":"#/$defs/n"}}},
                                "values":{"type":"array","items":{"anyOf":[{"type":"string"},{"type":"null"}]}}}, "required":["options"]}
        original = copy.deepcopy(schema)
        validate_arguments(schema, {"options":{"count":2},"values":[None,"x"]})
        for args in ({}, {"options":{}}, {"options":{"count":5}}, {"options":{"count":2},"values":[1]}):
            with self.assertRaises(SchemaError):
                validate_arguments(schema, args)
        for profile in ('openai_non_strict','claude','prompt'):
            projection = provider_schema(schema,profile)
            self.assertNotIn('additionalProperties',projection)
            self.assertEqual(projection['required'],['options'])
        self.assertEqual(schema,original)
        self.assertEqual(schema_digest(schema),schema_digest(copy.deepcopy(schema)))

    def test_strict_rejects_semantic_changes(self):
        schema = {"type":"object","properties":{"value":{"type":"string"}}}
        with self.assertRaises(SchemaError):
            provider_schema(schema,'openai_strict')
        schema.update(required=['value'],additionalProperties=False)
        self.assertEqual(provider_schema(schema,'openai_strict'),schema)
        with self.assertRaises(SchemaError):
            provider_schema(schema,'unreviewed-provider')

    def test_remote_cyclic_large_and_deep_schema_refused(self):
        for schema in (
            {"type":"object","properties":{"x":{"$ref":"https://example.invalid/schema"}}},
            {"type":"object","$defs":{"x":{"$ref":"#/$defs/x"}}},
            {"type":"object","description":"x"*(256*1024)},
        ):
            with self.assertRaises(SchemaError):
                provider_schema(schema)
        schema = {"type":"object"}
        child = schema
        for _ in range(40):
            child['properties']={'x':{'type':'object'}}
            child=child['properties']['x']
        with self.assertRaises(SchemaError):
            provider_schema(schema)

    def test_non_json_args_refused(self):
        for args in ([], {'value':float('nan')}, {'value':float('inf')}):
            with self.assertRaises(SchemaError):
                validate_arguments({'type':'object'},args)

    def test_reference_shaped_values_are_data_and_other_dialects_rejected(self):
        schema={'type':'object','properties':{'x':{'const':{'$ref':'an ordinary data value'}}}}
        validate_arguments(schema,{'x':{'$ref':'an ordinary data value'}})
        self.assertEqual(provider_schema(schema),schema)
        with self.assertRaises(SchemaError):
            provider_schema({'type':'object','$schema':'https://example.invalid/custom-dialect'})

    def test_draft7_local_refs_preserve_sibling_semantics(self):
        schema={'$schema':'http://json-schema.org/draft-07/schema#','type':'object',
                'definitions':{'n':{'type':'integer','minimum':1}},
                'properties':{'n':{'$ref':'#/definitions/n','maximum':0}}}
        validate_arguments(schema,{'n':2})
        with self.assertRaises(SchemaError):
            validate_arguments(schema,{'n':0})
        self.assertEqual(provider_schema(schema)['properties']['n'],{'type':'integer','minimum':1})


class SchemaExposureTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_tool_excluded_from_native_and_prompt(self):
        adapter = object.__new__(ToolAdapter)
        adapter.schema_profile = 'openai_non_strict'
        adapter.get_server_and_tool_info = AsyncMock(return_value=({}, {
            'a::good':FormattedTool({'type':'object','properties':{'n':{'type':'integer','minimum':2}}},'a'),
            'a::invalid':FormattedTool({'type':'invalid'},'a'),
        }))
        prompt, openai, claude = await adapter.get_tools(['a'])
        self.assertNotIn('a::invalid',prompt)
        self.assertEqual(len(openai),1)
        self.assertEqual(len(claude),1)
        self.assertIn('minimum',prompt)
        self.assertEqual(list(adapter.get_last_formatted_tools_dict()),['a::good'])
