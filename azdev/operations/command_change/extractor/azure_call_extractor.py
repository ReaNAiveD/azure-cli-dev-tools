import json

from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini


AZURE_CALL_EXTRACTOR_PROMPT="""
---Role---
* You are a helpful assistant tasked with extracting Azure-related operations from code snippets.
* You will be provided with a code snippet that may involve interactions with Azure resources. Your objective is to identify:
    * The Azure resource being operated on
    * The type of operation performed
    * The approach used to perform the operation (allow only API or SDK or ARMTemplate or Terraform or Bicep!)
* You should return empty JSON when not found! This is usually the case!

---Resource---
An Azure resource refers to any manageable item available through Microsoft Azure. This includes services such as Virtual Machines, SQL Databases, Storage Accounts, Web Apps, and more.

---Operation---
An operation on an Azure resource denotes any action that can be executed via the Azure Resource Manager (ARM). Common operations include creating, reading, updating, deleting, starting, stopping, or configuring a resource.

---Approach---
Operations may be performed using various approaches, including:
* Azure REST APIs
* Azure SDKs (Not Azure CLI SDK!)
* ARM templates
* Infrastructure-as-Code tools such as Terraform and Bicep
You are expected to identify the approach used and provide detailed information, such as:
* The specific SDK (e.g., azure-mgmt-compute)
* The exact API endpoint (e.g., Microsoft.Compute/virtualMachines/start)
* Relevant template keywords or constructs

---Output---
Please return the result as a JSON object with the following fields:
```json
{{
  "resource": "Azure Resource Name",
  "operation": "Operation Name on Azure Resource",
  "approach": "Approach to the operation",  // API or SDK or ARMTemplate or Terraform or Bicep!
  "package": "package.name",
  "function": "function_name",  // The function called to perform the operation
  "detail": "Description",
  "sdk": "Optional SDK Name",           // optional
  "api": "Optional API URI",           // optional
  "parameters": {{}}     // optional, parameter to formatter the template
}}
```
If no Azure-related Operation is found, return a empty json `{{}}`.

---Input---
Code Snippet:
{code_snippet}
"""


def extract_azure_call(
        code_snippet,
        client=None,
):
    client = client or chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=AZURE_CALL_EXTRACTOR_PROMPT.format(
                    code_snippet=code_snippet and code_snippet[:100000],
                ),
            ),
            ChatRequestUserMessage(
                content='Please give the result in correct format.'
            )
        ],
        response_format='json_object',
    )

    content = resp.choices[0].message.content
    if not content:
        return None
    try:
        result = json.loads(content)
        return dict((key, value) for key, value in result.items() if value)
    except Exception:
        return None
