from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini

EXTRACT_IMPORT_PROMPT = """
---Role---
You are a helpful Python Static Analysis Assistant. You will receive a code snippet and your task is to identify the import statement and organize the imported items.

---Output Format---
The output is a multi-line string. Each line contains a import item in the format of "package.name#qual.name"

---Example Input---
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

---Example Output---
azure.mgmt.core.tools#is_valid_resource_id
azure.cli.core._output#get_output_format
azure.cli.core._output#set_output_format

---Input---
{code_snippet}
"""


def extract_import(code_snippet, client=None):
    if not client:
        client = chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=EXTRACT_IMPORT_PROMPT.format(
                    code_snippet=code_snippet[:50000] if code_snippet else 'None',
                ),
            ),
            ChatRequestUserMessage(
                content='Please give the result in correct format.'
            )
        ]
    )

    content = resp.choices[0].message.content
    content_object = [line.strip("\n") for line in content.splitlines() if line]
    return content_object
