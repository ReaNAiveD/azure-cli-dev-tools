import dataclasses
import inspect
import json
import logging
import os.path
from collections import defaultdict
from importlib import import_module

import yaml

from azdev.operations.command_change.extractor.azure_call_extractor import extract_azure_call
from azdev.operations.command_change.extractor.class_extractor import extract_class_info
from azdev.operations.command_change.extractor.import_extractor import extract_import
from azdev.operations.command_change.extractor.model_extractor import extract_model
from azdev.operations.command_change.extractor.raw_call_map import extract_raw_call_map
from azdev.operations.command_change.extractor.summarize import logic_summarize, logic_detail, args_summarize, \
    exceptions_summarize, return_summarize
from azdev.operations.command_change.extractor.utils import chat_client_4o_mini
from azdev.utilities import display

logger = logging.getLogger(__name__)


def load_call_obj(module, name, *, package=None):
    try:
        module = import_module(module, package=package)
        return module.__getattribute__(name)
    except ModuleNotFoundError as e:
        logger.warning(f'Module Not Found: {module}', exc_info=e)
        return None
    except AttributeError as e:
        logger.warning(f'Attribute Not Found in Module {module}: {name}', exc_info=e)
        return None


@dataclasses.dataclass
class ExtractResult:
    name: str
    logic_summary: str
    logic_desc: str
    models: list | None = dataclasses.field(default=None)
    docs: str = dataclasses.field(default="")
    exceptions: list[dict] = dataclasses.field(default_factory=lambda:dict)
    args: list[dict] = dataclasses.field(default_factory=lambda:list)
    call_map: dict[str, dict] = dataclasses.field(default_factory=lambda:dict)
    code_snippets: dict[str, str | dict] = dataclasses.field(default_factory=lambda:dict)
    azure_calls: set[str] = dataclasses.field(default_factory=lambda:set)
    return_types: list[dict] = dataclasses.field(default_factory=lambda:list)
    used_in: set[str] = dataclasses.field(default_factory=lambda:set)

    def to_dict(self, detailed_call_map=True):
        if detailed_call_map:
            return {
                'name': self.name,
                'logic_summary': self.logic_summary,
                'logic_desc': self.logic_desc,
                'models': self.models,
                'docs': self.docs,
                'exceptions': self.exceptions,
                'args': self.args,
                "call_map": self.call_map,
                'code_snippet': self.code_snippets.get(''),
                'azure_calls': list([json.loads(call) for call in self.azure_calls]),
                'return_types': self.return_types,
                'used_in': list(self.used_in),
            }
        return {
            'name': self.name,
            'logic_summary': self.logic_summary,
            'logic_desc': self.logic_desc,
            'models': self.models,
            'docs': self.docs,
            'exceptions': self.exceptions,
            'args': self.args,
            "call_map": dict((name, {'overrides': [{'name': o.get('name'), 'call_map': o.get('call_mapp')} for o in v.get('overrides', [])]}) for name, v in self.call_map.items()) if self.call_map and isinstance(self.call_map, dict) else None,
            'code_snippet': self.code_snippets.get(''),
            'azure_calls': list([json.loads(call) for call in self.azure_calls]),
            'return_types': self.return_types,
            'used_in': list(self.used_in),
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(
            name=value.get('name'),
            logic_summary=value.get('logic_summary', ''),
            logic_desc=value.get('logic_desc'),
            models=value.get('models'),
            docs=value.get('docs', ''),
            exceptions=value.get('exceptions', []),
            args=value.get('args', []),
            call_map=value.get('call_map', {}),
            code_snippets={'': value.get('code_snippet', '')},
            azure_calls=set([json.dumps(call) for call in value.get('azure_calls', [])]),
            return_types=value.get('return_types', []),
            used_in=set(value.get('used_in', [])),
        )

    def add_azure_call(self, azure_call: dict):
        self.azure_calls.add(json.dumps(azure_call))


def is_constant(member):
    return (
        not inspect.isfunction(member) and
        not inspect.isclass(member) and
        not inspect.ismodule(member)
    )


def module_in_scope(module):
    return module.startswith('azure.cli') or module.startswith('azext') or module.startswith('knack')


def try_get_source(call_obj):
    try:
        return inspect.getsource(call_obj)
    except TypeError as e:
        logger.error(f'Type Error for {call_obj}', exc_info=e)
        return None
    except Exception as e:
        logger.error(f'Exception for {call_obj}', exc_info=e)
        return None


def _extract_info(call_obj):
    if isinstance(call_obj, type):
        try:
            code_snippet = try_get_source(call_obj.__init__)
            doc = (inspect.getdoc(call_obj) or '') + (inspect.getdoc(call_obj.__init__) or '')
            return code_snippet, doc, call_obj.__name__
        except TypeError as e:
            logger.warning("TypeError when inspecting", exc_info=e)
            code_snippet = try_get_source(call_obj)
            doc = inspect.getdoc(call_obj)
            return code_snippet, doc, call_obj.__name__
    else:
        code_snippet = try_get_source(call_obj)
        doc = inspect.getdoc(call_obj)
        if "." in call_obj.__qualname__:
            class_context_name = call_obj.__qualname__.split(".")[0]
            return code_snippet, doc, class_context_name
        return code_snippet, doc, None


def find_mod_definitions(module):
    classes = dict(inspect.getmembers(module, inspect.isclass))
    functions = dict(inspect.getmembers(module, inspect.isfunction))
    consts = dict(inspect.getmembers(module, is_constant))
    methods = {}
    for class_name, class_obj in classes.items():
        for method_name, method in inspect.getmembers(class_obj, inspect.ismethod):
            methods[method.__qualname__] = method
    definitions = {
        **classes,
        **functions,
        **consts,
        **methods,
    }
    return definitions


def find_definitions(module, code_snippet, *, client=None):
    definitions = find_mod_definitions(module)
    code_imports = extract_import(code_snippet, client=client)
    for code_import in code_imports:
        if '#' in code_import:
            mod_name, name = code_import.rsplit("#", maxsplit=1)
            if call_obj := load_call_obj(mod_name, name, package=module.__package__):
                definitions[name] = call_obj
    return definitions


def _find_callables(call_detail, definitions, name, variable_classes, package=None):
    candidate_call_objs = {}
    if name in definitions:
        candidate_call_objs = {name: definitions[name]}
    elif "." in name:
        variable, method = name.split(".", maxsplit=1)
        if variable in variable_classes:
            for class_name in variable_classes[variable]:
                if f'{class_name}.{method}' in definitions:
                    candidate_call_objs[f'{class_name}.{method}'] = definitions[f'{class_name}.{method}']
    elif 'module' in call_detail:
        if call_obj := load_call_obj(call_detail['module'], name, package=package):
            candidate_call_objs[name] = call_obj
    return candidate_call_objs


class CallExtractor:
    def __init__(self, cache_path=None):
        self.stack = []
        self.cache: dict[str, ExtractResult] = {}
        self.class_cache = {}
        self.cache_path = cache_path
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_items = yaml.safe_load(f)
                self.load_cache(cache_items)

    def load_cache(self, cache):
        self.cache = dict((name, ExtractResult.from_dict(item)) for name, item in cache.items())

    def dump_cache(self):
        return dict((name, item.to_dict(detailed_call_map=False)) for name, item in self.cache.items())

    def store_cache(self):
        if self.cache_path:
            parent = os.path.dirname(self.cache_path)
            if not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.dump_cache(), f, allow_unicode=True, indent=2)

    @staticmethod
    def _patch_arg_type(arg):
        if isinstance(arg, dict):
            if "type" not in arg or arg["type"] == "unknown":
                arg["type"] = []
            else:
                arg["type"] = [arg["type"]]

    def _get_class_context(self, class_obj):
        module = inspect.getmodule(class_obj)
        name = class_obj.__qualname__
        key = f"{module.__name__}#{name}"
        class_context = self.class_cache.get(key)
        if not class_context:
            source = try_get_source(class_obj)
            if not source:
                return None
            class_context = extract_class_info(source)
            self.class_cache[key] = class_context
        return class_context

    def extract_cmd_call(self, call_obj, arg_types, key: str, client=None):
        self.stack.append(key)
        result = self.extract_call(call_obj, arg_types, client)
        self.stack.pop()
        return result

    def extract_call(self, main_call_obj, arg_types, client=None):
        client = client or chat_client_4o_mini()

        key = call_obj_key(main_call_obj)
        if not key:
            return None
        module = inspect.getmodule(main_call_obj)
        package = module.__package__
        used_in = list(self.stack)

        if key in self.cache:
            display(f"Use Cached {key}")
            result = self.cache[key]
            result.used_in.update(used_in)
            return result

        display(f"Handling {key}")
        self.stack.append(key)
        code_snippet, doc, class_ctx_name = _extract_info(main_call_obj)
        definitions = find_definitions(module, code_snippet, client=client)

        class_context = None
        if class_ctx_name:
            if class_context_obj := definitions.get(class_ctx_name):
                class_context = self._get_class_context(class_context_obj)

        variable_classes = defaultdict(lambda :[])
        if class_context and 'super_classes' in class_context and isinstance(class_context['super_classes'], list):
            variable_classes['super'] = class_context['super_classes']

        models = extract_model(code_snippet=code_snippet, client=client)

        call_map = extract_raw_call_map(
            code_snippet=code_snippet,
            possible_input=json.dumps(arg_types, default=str),
            related_items='\n'.join(list(definitions)),
            class_context=class_context,
            client=client,
        )

        code_snippets = {'': code_snippet}
        azure_calls = set()
        for name, call_detail in call_map.items():
            if not isinstance(call_detail, dict):
                logger.error(f"Analyzed Call Detail({name}) is not dict:\n{call_detail}")
                continue
            args = call_detail.get('args', [])
            if isinstance(args, list):
                for arg in call_detail.get('args', []):
                    self._patch_arg_type(arg)
            candidates = _find_callables(call_detail, definitions, name, variable_classes, package=package)

            for name, call_obj in candidates.items():
                if 'overrides' not in call_detail :
                    call_detail['overrides'] = []

                module = inspect.getmodule(call_obj)
                sub_key = call_obj_key(call_obj)
                if not sub_key:
                    continue
                if not module or sub_key in self.stack or not module_in_scope(module.__name__):
                    call_detail['overrides'].append({
                        'docs': inspect.getdoc(call_obj),
                        'code_snippet': try_get_source(call_obj),
                        'module': module.__name__ if module else None,
                    })
                    continue
                extracted = self.extract_call(
                    main_call_obj=call_obj,
                    arg_types=call_detail.get("args", []),
                    client=client,
                )
                if not extracted:
                    continue
                qualname = call_obj.__qualname__
                code_snippets[f'{module}#{qualname}'] = extracted.code_snippets
                for return_type in extracted.return_types:
                    if 'return' not in call_detail:
                        call_detail['return'] = []
                    call_detail['return'].append(return_type)
                    if "name" in return_type and "module" in return_type:
                        if class_obj := load_call_obj(return_type["module"], return_type["name"], package=package):
                            for method_name, method in inspect.getmembers(class_obj, inspect.ismethod):
                                definitions[method.__qualname__] = method
                            definitions[return_type["name"]] = class_obj
                        if "assignee" in call_obj:
                            variable_classes[call_detail["assignee"]].append(return_type["name"])

                call_detail['overrides'].append(extracted.to_dict(detailed_call_map=False))
                azure_calls.update(extracted.azure_calls)

        azure_call = extract_azure_call(code_snippet)
        if azure_call:
            azure_calls.add(json.dumps(azure_call))
        logic_summary = logic_summarize(code_snippet, call_map, client=client)
        logic_description = logic_detail(code_snippet, call_map, logic_summary, client=client)
        args = args_summarize(code_snippet, call_map, client=client)
        exceptions = exceptions_summarize(code_snippet, call_map, client=client)
        returns = return_summarize(code_snippet, call_map, client=client)

        result = ExtractResult(
            name=key,
            logic_summary=logic_summary,
            logic_desc=logic_description,
            models=models,
            docs=doc,
            exceptions=exceptions,
            args=args,
            call_map=call_map,
            code_snippets=code_snippets,
            azure_calls=azure_calls,
            return_types=returns,
            used_in=set(used_in),
        )
        self.stack.pop()
        self.cache[key] = result
        self.store_cache()
        return result


def call_obj_key(call_obj):
        if not (inspect.isfunction(call_obj) or inspect.ismethod(call_obj) or inspect.isclass(call_obj)):
            return None
        module = inspect.getmodule(call_obj)
        return f"{module.__name__}#{call_obj.__qualname__}"


def _trimmed_call_map(call_map):
    def trimmed(d, f):
        nd = dict(d)
        try:
            nd.pop(f)
        except KeyError:
            return nd
        return nd

    return dict((name, {
        **detail,
        **({
            "overrides": [trimmed(item, 'call_map') for item in detail["overrides"] if isinstance(item, dict)],
        } if "overrides" in detail else {})
    }) for name, detail in call_map.items() if isinstance(detail, dict))
