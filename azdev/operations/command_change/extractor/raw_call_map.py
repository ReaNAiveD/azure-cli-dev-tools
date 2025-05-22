import json

from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini

DEPENDENCIES_EXTRACTOR_PROMPT = """
---Role---
You are a helpful Python Static Analysis Assistant. You will receive:
1. A Python code snippet
2. Descriptions of possible inputs to that code
3. A list of related modules, functions, classes
4. (Optional) A class_context input, provided only if the snippet is part of a class definition
Your task is to analyze how the snippet uses external variables, functions, methods, and classes, and then output a detailed, structured summary in JSON.

---Procedure---
1. Line‑by‑Line Analysis
    * Examine each line of the snippet.
    * For every identifier that refers to something defined outside the snippet (variable, function, method, class), note its usage.
    * If class_context is provided, consider class-level attributes and methods as part of the local context.
2. Organize the usage of these calls and order by the sort of being called.
    1. Try identify the type of the call. Is it a function call, method invocation, or class instantiation?
    2. Identify the origin. If it is not included in the list of related modules, functions or classes, determine which module it comes from.
        * If there are `import` statements, identify the modules for those calls.
    3. Identify the arguments usage in this call just as the order.
        * If an argument is a literal, mark it "type": "literal".
        * If it’s a variable, record its name and, if you can infer it, its type.
        * If it’s a keyword argument, record its key.
        * Provide a brief description of each argument’s purpose or content.
3. Assemble your findings into a single JSON object. Each key is the name of an external call or class, and its value is an object with these fields:
    * "type": "function", "method", or "class"
    * (optional) "assignee": The variable name the return value is assigned to.
    * (optional) "module": the module where it’s defined
    * "args": an array of argument descriptors, each including:
        * "variable" which is the name of the variable
        * "key" if it is a keyword argument
        * "type" (if known)
        * "description"
    * "raw": The related code cut out from the snippet

---Example Input---
Code Snippet:
def process_vm_secret_format(cmd, namespace):
    from azure.mgmt.core.tools import is_valid_resource_id
    from azure.cli.core._output import (get_output_format, set_output_format)

    keyvault_usage = CLIError('usage error: [--keyvault NAME --resource-group NAME | --keyvault ID]')
    kv = namespace.keyvault
    rg = namespace.resource_group_name

    if rg:
        if not kv or is_valid_resource_id(kv):
            raise keyvault_usage
        validate_keyvault(cmd, namespace)
    else:
        if kv and not is_valid_resource_id(kv):
            raise keyvault_usage

    warning_msg = "This command does not support the {{}} output format. Showing JSON format instead."
    desired_formats = ["json", "jsonc"]

    output_format = get_output_format(cmd.cli_ctx)
    if output_format not in desired_formats:
        warning_msg = warning_msg.format(output_format)
        logger.warning(warning_msg)
        set_output_format(cmd.cli_ctx, format=desired_formats[0])

Possible Input:
{{
    "cmd": {{
        "description": "Context Info about current command. The parameter includes related command definition and also a cli_ctx field which includes context info of Azure CLI app."
    }},
    "namespace": {{
        "description": "A Field of parsed input arguments of current command. Each field is corresponding to a command argument."
    }}
}}

Related Items:
urlparse
get_logger
CLIError
ValidationError
ArgumentUsageError
get_default_location_from_resource_group
validate_file_or_dict
DISALLOWED_USER_NAMES
check_existence
StorageProfile
logger
validate_asg_names_or_ids
validate_nsg_name
validate_keyvault
validate_vm_name_for_monitor_metrics

---Example Output---
{{
    "CLIError": {{
        "type": "class",
        "assignee": "keyvault_usage",
        "args": [
            {{
                "type": "literal",
                "key": None,
                "description": "usage error: [--keyvault NAME --resource-group NAME | --keyvault ID]"
            }}
        ],
        "raw": "keyvault_usage = CLIError('usage error: [--keyvault NAME --resource-group NAME | --keyvault ID]')"
    }},
    "is_valid_resource_id": {{
        "type": "function",
        "args": [
            {{
                "variable": "kv",
                "type": "unknown",
                "key": None,
                "description": "kv field in the namespace, mostly like keyvault"
            }}
        ],
        "raw": "if not kv or is_valid_resource_id(kv):\nraise keyvault_usage"
    }},
    "validate_keyvault": {{
        "type": "function",
        "args": [
            {{
                "variable": "cmd",
                "type": "unknown",
                "key": None,
                "description": "Context about current command"
            }}
        ],
        "raw": "validate_keyvault(cmd, namespace)"
    }},
    "is_valid_resource_id": {{
        "type": "function",
        "module": "azure.mgmt.core.tools",
        "args": [
            {{
                "variable": "kv",
                "type": "unknown",
                "key": None,
                "description": "kv field in the namespace, mostly like keyvault"
            }}
        ],
        "raw": "if not kv or is_valid_resource_id(kv):\nraise keyvault_usage"
    }},
    "get_output_format": {{
        "type": "function",
        "module": "azure.cli.core._output",
        "args: [
            {{
                "variable": "cmd.cli_ctx",
                "type": "unknown",
                "key": None,
                "description": "Context about Azure CLI application"
            }}
        ],
        "raw": "output_format = get_output_format(cmd.cli_ctx)"
    }},
    "logger.warning": {{
        "type": "method",
        "args": [
            {{
                "variable": "warning_msg"
                "type": "str",
                "key": None,
                "description": "This command does not support the {{}} output format. Showing JSON format instead."
            }}
        ],
        "raw": "logger.warning(warning_msg)"
    }},
    "set_output_format": {{
        "type": "function",
        "module": "azure.cli.core._output",
        "args": [
            {{
                "variable": "cmd.cli_ctx",
                "type": "unknown",
                "key": None,
                "description": "Context about Azure CLI application"
            }},
            {{
                "variable": "desired_formats[0]",
                "type": "str",
                "key": "format",
                "description": "desired_formats is a list of str, and index 0 is \\"json\\""
            }}
        ],
        "raw": "set_output_format(cmd.cli_ctx, format=desired_formats[0])"
    }}
}}

---Input---
Code Snippet:
{code_snippet}

Possible Input:
{possible_input}

Related Items:
{related_items}

Class Context:
{class_context}
"""


def extract_raw_call_map(
        code_snippet,
        possible_input,
        related_items,
        class_context,
        client=None,
):
    client = client or chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=DEPENDENCIES_EXTRACTOR_PROMPT.format(
                    code_snippet=code_snippet and code_snippet[:50000],
                    possible_input=possible_input[:50000],
                    class_context=json.dumps(class_context)[:50000] if class_context else 'None',
                    related_items=related_items[:50000],
                ),
            ),
            ChatRequestUserMessage(
                content='Please give the result in correct format.'
            )
        ],
        response_format='json_object',
    )

    content = resp.choices[0].message.content
    return json.loads(content)
