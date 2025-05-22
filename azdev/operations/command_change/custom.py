# -----------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# -----------------------------------------------------------------------------
import os
from enum import Enum
from importlib import import_module

import yaml
from knack.log import get_logger

from azure.cli.core.commands.command_operation import GenericUpdateCommandOperation
from .util import get_command_tree

logger = get_logger(__name__)

STORED_DEPRECATION_KEY = ["expiration", "target", "redirect", "hide"]


class DiffExportFormat(Enum):
    DICT = "dict"
    TEXT = "text"
    TREE = "tree"


def process_aaz_argument(az_arguments_schema, argument_settings, para):
    from azure.cli.core.aaz import has_value  # pylint: disable=import-error
    _fields = az_arguments_schema._fields  # pylint: disable=protected-access
    aaz_type = _fields.get(argument_settings["dest"], None)
    if aaz_type:
        para["aaz_type"] = aaz_type.__class__.__name__
        if aaz_type._type_in_help and aaz_type._type_in_help.lower() != "undefined":  # pylint: disable=protected-access
            para["type"] = aaz_type._type_in_help  # pylint: disable=protected-access
        if has_value(aaz_type._default):  # pylint: disable=protected-access
            para["aaz_default"] = str(aaz_type._default)  # pylint: disable=protected-access
        if para["aaz_type"] in ["AAZArgEnum"] and aaz_type.get("enum", None) and aaz_type.enum.get("items", None):
            para["aaz_choices"] = [str(item) for item in aaz_type.enum["items"]]


def process_arg_options(argument_settings, para):
    para["options"] = []
    if not argument_settings.get("options_list", None):
        return
    raw_options_list = argument_settings["options_list"]
    option_list = set()
    for opt in raw_options_list:
        opt_type = opt.__class__.__name__
        if opt_type == "str":
            option_list.add(opt)
        elif opt_type == "Deprecated":
            if hasattr(opt, "hide") and opt.hide:
                continue
            if hasattr(opt, "target"):
                option_list.add(opt.target)
        else:
            logger.warning("Unsupported option type: %i", opt_type)
    para["options"] = sorted(option_list)


def process_arg_options_deprecation(argument_settings, para):
    if not argument_settings.get("options_list", None):
        return
    raw_options_list = argument_settings["options_list"]
    option_deprecation_list = []
    for opt in raw_options_list:
        opt_type = opt.__class__.__name__
        if opt_type != "Deprecated":
            continue
        opt_deprecation = {}
        for info_key in STORED_DEPRECATION_KEY:
            if hasattr(opt, info_key) and getattr(opt, info_key):
                opt_deprecation[info_key] = getattr(opt, info_key)
        option_deprecation_list.append(opt_deprecation)
    if len(option_deprecation_list) != 0:
        para["options_deprecate_info"] = option_deprecation_list


def process_arg_deprecation(argument_settings, para):
    if argument_settings.get("deprecate_info", None) is None:
        return
    for info_key in STORED_DEPRECATION_KEY:
        if hasattr(argument_settings["deprecate_info"], info_key) and \
                getattr(argument_settings["deprecate_info"], info_key):
            if para.get("deprecate_info", None) is None:
                para["deprecate_info"] = {}
            para["deprecate_info"][info_key] = getattr(argument_settings["deprecate_info"], info_key)


def process_arg_type(argument_settings, para):
    if not argument_settings.get("type", None):
        return
    configured_type = argument_settings["type"]
    raw_type = None
    if hasattr(configured_type, "__name__"):
        raw_type = configured_type.__name__
    elif hasattr(configured_type, "__class__"):
        raw_type = configured_type.__class__.__name__
    else:
        print("unsupported type", configured_type)
        return
    para["type"] = raw_type if raw_type in ["str", "int", "float", "bool", "file_type"] else "custom_type"


def normalize_para_types(para):
    type_string_opts = ["string", "str", "aazstrarg",
                        "aazresourcelocationarg", "aazresourcegroupnamearg", "aazresourceidarg",
                        "aazpaginationtokenarg", "aazfilearg"]

    type_int_opts = ["int", "aazintarg", "aazpaginationlimitarg"]
    type_float_opts = ["float", "aazfloatarg"]
    type_bool_opts = ["boolean", "bool", "aazboolarg", "aazgenericupdateforcestringarg"]

    def normalize_para_type(type_opts, value):
        if para.get("type", None) and para["type"].lower() in type_opts:
            para["type"] = value
        if para.get("aaz_type", None) and para["aaz_type"].lower() in type_opts:
            para["aaz_type"] = value

    normalize_para_type(type_string_opts, "string")
    normalize_para_type(type_int_opts, "int")
    normalize_para_type(type_float_opts, "float")
    normalize_para_type(type_bool_opts, "bool")


def get_command_examples(command_info, command_meta):
    example_items = []
    if command_info and command_info.get("help", None) and hasattr(command_info["help"], "examples"):
        for example_obj in command_info["help"].examples:
            example_items.append({"name": example_obj.name, "text": example_obj.text})
    if example_items:
        command_meta["examples"] = example_items


def gen_command_meta(command_info, with_help=False, with_example=False, extractor=None, output_dir=None):
    if output_dir:
        path = os.path.join(output_dir, *command_info["name"].split()) + '.yml'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)

    command_name = command_info["name"]
    stored_property_when_exist = ["confirmation", "supports_no_wait", "is_preview", "deprecate_info"]
    command_meta = {
        "name": command_name,
        "is_aaz": command_info["is_aaz"],
    }
    if "handler" not in command_info and not command_info["is_aaz"]:
        print(f"WARNING: {command_info['name']} is not an AAZ command but has no handler!")
    if "operation" in command_info:
        if isinstance(command_info["operation"], GenericUpdateCommandOperation):
            command_meta["getter_op_path"] = command_info["operation"].getter_op_path
            command_meta["setter_op_path"] = command_info["operation"].setter_op_path
            command_meta["custom_function_op_path"] = command_info["operation"].custom_function_op_path
        else:
            command_meta["op_path"] = command_info["operation"].op_path
    for prop in stored_property_when_exist:
        if command_info.get(prop, None):
            command_meta[prop] = command_info[prop]
    if with_example:
        get_command_examples(command_info, command_meta)
    if with_help:
        if command_info.get("help", None) and hasattr(command_info["help"], "short_summary"):
            command_meta["desc"] = command_info["help"].short_summary
    parameters = []
    for _, argument in command_info["arguments"].items():
        if argument.type is None:
            continue
        settings = argument.type.settings
        if settings.get("action", None):
            action = settings["action"]
            if hasattr(action, "__name__") and action.__name__ == "IgnoreAction":
                # ignore argument like: cmd
                continue
        arg_name = settings["dest"]
        para = {
            "name": arg_name,
        }
        process_arg_deprecation(settings, para)
        process_arg_options(settings, para)
        process_arg_options_deprecation(settings, para)
        process_arg_type(settings, para)
        if settings.get("required", False):
            para["required"] = True
        if settings.get("choices", None):
            para["choices"] = sorted([str(choice) for choice in settings["choices"]])
        if settings.get("id_part", None):
            para["id_part"] = settings["id_part"]
        if settings.get("nargs", None):
            para["nargs"] = settings["nargs"]
        if settings.get("completer", None):
            para["has_completer"] = True
        if settings.get("default", None):
            if not isinstance(settings["default"], (float, int, str, list, bool)):
                para["default"] = str(settings["default"])
            else:
                para["default"] = str(settings["default"]) if extractor else settings["default"]
        if with_help:
            para["desc"] = str(settings.get("help", ""))
        if command_info["is_aaz"] and command_info["az_arguments_schema"]:
            process_aaz_argument(command_info["az_arguments_schema"], settings, para)
        if extractor and argument.validator:
            para["validator"] = handle_arg_validator(argument.validator, arg_name, para, f"{command_name}#{arg_name}#validator", extractor=extractor)
        normalize_para_types(para)
        parameters.append(para)
    command_meta["parameters"] = parameters
    if extractor and command_info["validator"]:
        args = dict((para["name"], para) for para in parameters)
        command_meta["validator"] = handle_validator(command_info["validator"], args, f'{command_name}#validator', extractor=extractor)
    if extractor and "operation" in command_info:
        if isinstance(command_info["operation"], GenericUpdateCommandOperation):
            command_meta["getter_operation"] = (
                    command_info["operation"].getter_op_path and
                    handle_op(command_info["operation"].getter_op_path, parameters, f'{command_name}#getter_op', extractor=extractor))
            command_meta["setter_operation"] = (
                    command_info["operation"].setter_op_path and
                    handle_op(command_info["operation"].setter_op_path, parameters, f'{command_name}#setter_op', extractor=extractor))
            command_meta["custom_function_operation"] = (
                    command_info["operation"].custom_function_op_path and
                    handle_op(command_info["operation"].custom_function_op_path, parameters, f'{command_name}#custom_function_op', extractor=extractor))
        else:
            command_meta["operation"] = handle_op(command_info["operation"].op_path, parameters, f'{command_name}#op', extractor=extractor)
    if output_dir:
        group_dir = os.path.join(output_dir, *command_info["name"].split()[:-1])
        os.makedirs(group_dir, exist_ok=True)
        path = os.path.join(output_dir, *command_info["name"].split()) + '.yml'
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(command_meta, f, indent=2, allow_unicode=True)
        # if extractor:
        #     with open(os.path.join(output_dir, 'cache.yml'), 'w', encoding='utf-8') as f:
        #         yaml.safe_dump(extractor.dump_cache(), f, allow_unicode=True, indent=2)
    return command_meta


def process_command_group_deprecation(command_group_obj, command_group_info):
    if not hasattr(command_group_obj, "group_kwargs"):
        return
    group_kwargs = getattr(command_group_obj, "group_kwargs")
    if group_kwargs.get("deprecate_info", None) is None:
        return
    for info_key in STORED_DEPRECATION_KEY:
        if hasattr(group_kwargs["deprecate_info"], info_key) and getattr(group_kwargs["deprecate_info"], info_key):
            if command_group_info.get("deprecate_info", None) is None:
                command_group_info["deprecate_info"] = {}
            command_group_info["deprecate_info"][info_key] = getattr(group_kwargs["deprecate_info"], info_key)


def get_commands_meta(command_group_table, commands_info, with_help, with_example, output_dir=None):
    from .extractor import CallExtractor

    extractor = CallExtractor(cache_path=os.path.join(output_dir, 'cache.yml'))
    commands_meta = {}

    for command_info in commands_info:  # pylint: disable=too-many-nested-blocks
        module_name = command_info["source"]["module"]
        command_name = command_info["name"]
        if module_name not in commands_meta:
            commands_meta[module_name] = {
                "module_name": module_name,
                "name": "az",
                "commands": {},
                "sub_groups": {}
            }
        command_group_info = commands_meta[module_name]
        command_tree = get_command_tree(command_name)
        while True:
            if "is_group" not in command_tree:
                break
            if command_tree["is_group"]:
                group_name = command_tree["group_name"]
                if group_name not in command_group_info["sub_groups"]:
                    group_info = command_group_table.get(group_name, None)
                    command_group_info["sub_groups"][group_name] = {
                        "name": group_name,
                        "commands": {},
                        "sub_groups": {}
                    }
                    process_command_group_deprecation(group_info, command_group_info["sub_groups"][group_name])
                    if with_help:
                        try:
                            command_group_info["sub_groups"][group_name]["desc"] = group_info.help["short-summary"]
                        except AttributeError:
                            pass

                command_tree = command_tree["sub_info"]
                command_group_info = command_group_info["sub_groups"][group_name]
            else:
                if command_name in command_group_info["commands"]:
                    logger.warning("repeated command: %i", command_name)
                    break
                command_meta = gen_command_meta(command_info, with_help, with_example, extractor, output_dir)
                command_group_info["commands"][command_name] = command_meta
                break
    return commands_meta


def module_attr(module, name):
    item = module
    try:
        for name in name.split("."):
            item = getattr(item, name)
    except AttributeError as e:
        return None
    except Exception as e:
        return None
    return item


def handle_op(op_path, parameters, key, *, extractor):
    module, name = op_path.split("#", maxsplit=1)
    try:
        module = import_module(module)
    except ModuleNotFoundError as e:
        return {
            "module": str(module),
            "name": name,
        }
    op = module_attr(module, name)
    return op and extractor.extract_cmd_call(
        op,
        arg_types={
            "cmd": {
                "description": "Context Info about current command. The parameter includes related command definition and also a cli_ctx field which includes context info of Azure CLI app."
            },
            **dict((para['name'], para) for para in parameters)
        },
        key=key,
    ).to_dict()


def handle_validator(validator, args, key, *, extractor):
    return extractor.extract_cmd_call(
        validator,
        arg_types={
            "cmd": {
                "description": "Context Info about current command. The parameter includes related command definition and also a cli_ctx field which includes context info of Azure CLI app."
            },
            "namespace": {
                "description": "A Field of parsed input arguments of current command. Each field is corresponding to a command argument.",
                "fields": args,
            }
        },
        key=key,
    ).to_dict()


def handle_arg_validator(validator, arg_name, arg, key, *, extractor):
    return extractor.extract_cmd_call(
        validator,
        arg_types={
            "cmd": {
                "description": "Context Info about current command. The parameter includes related command definition and also a cli_ctx field which includes context info of Azure CLI app."
            },
            arg_name: arg,
        },
        key=key,
    ).to_dict()
