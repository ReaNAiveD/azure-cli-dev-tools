import json

from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini

CALL_GUESS_PROMPT = """
---Role---
You are a helpful Python Static Analysis Assistant. You will receive:
1. a name representing a method or function call
2. a object including related args and related code lines
3. a list of candidate classes or functions
4. code snippet that related to the call
Your task is to analyze a method or function call and identify which items from a list of candidate classes or functions are involved in the call.

---Output Format---
Return a JSON list of strings. Each string must exactly match an item from the candidate list or a import in code snippet that is involved in the call.
* If one or more candidates match, return them in a list.
* If no candidates match, try extract a import which is exactly match from the code snippet. In this case, the item string should be in the following format: package.name#qual.name
* If still no match, return an empty list.

---Example Input 1---
_compute_client_factory.images.get
{{
    "type": "method",
    "args": [
        {{
            "variable": "namespace.resource_group_name",
            "type": "str",
            "description": "The input resource group name"
        }},
        {{
            "variable": "namespace.image",
            "type": "str",
            "description": "The input image name"
        }}
    ],
    "raw": "_compute_client_factory(cmd.cli_ctx).images.get(namespace.resource_group_name, namespace.image)"
}}

Candidate:
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
_compute_client_factory
logger
validate_asg_names_or_ids
validate_nsg_name
validate_keyvault
validate_vm_name_for_monitor_metrics
ImageSet.get
ImageSet.update

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


---Example Output 1---
["_compute_client_factory", "ImageSet.get"]

---Example Input 2---
_compute_client_factory.images.get
{{
    "type": "method",
    "args": [
        {{
            "variable": "cmd.cli_ctx",
            "type": "unknown",
            "key": None,
            "description": "Context about Azure CLI application"
        }},
        {{
            "variable": "namespace.resource_group_name",
            "type": "str",
            "description": "The input resource group name"
        }},
        {{
            "variable": "namespace.image",
            "type": "str",
            "description": "The input image name"
        }}
    ],
    "raw": "_compute_client_factory(cmd.cli_ctx).images.get(namespace.resource_group_name, namespace.image)"
}}

Candidate:
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
_network_client_factory
logger
validate_asg_names_or_ids
validate_nsg_name
validate_keyvault
validate_vm_name_for_monitor_metrics
ImageSet.update

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


---Example Output 2---
[]

---Example Input 2---
is_valid_resource_id
{{
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
}}

Candidate:
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
_network_client_factory
logger
validate_asg_names_or_ids
validate_nsg_name
validate_keyvault
validate_vm_name_for_monitor_metrics
ImageSet.update

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


---Example Output 3---
["azure.mgmt.core.tools#is_valid_resource_id"]

---Input---
{name}
{call_info}

Candidate:
{candidates}

Code Snippet:
{code_snippet}
"""


def call_guess(name, call_info, candidates, code_snippet, client=None):
    if not client:
        client = chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=CALL_GUESS_PROMPT.format(
                    name=name,
                    call_info=json.dumps(call_info),
                    candidates='\n'.join(candidates),
                    code_snippet=code_snippet,
                ),
            ),
            ChatRequestUserMessage(
                content='Please give the result in correct format.'
            )
        ],
        response_format='json_object',
    )

    content = resp.choices[0].message.content
    content_object = json.loads(content)
    if isinstance(content_object, list):
        return content_object
    elif isinstance(content_object, dict):
        if content_object:
            first = list(content_object.values())[0]
            if isinstance(first, list):
                return first
    return []
