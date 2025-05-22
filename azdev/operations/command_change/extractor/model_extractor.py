import json

from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini


MODEL_EXTRACTOR_PROMPT="""
---Role---
You are a helpful assistant to extract all cmd.get_models call from code snippet.
You need to return the result in a list of json object. Each object has a name field, a optional resource_type and a optional operation_group.

---Introduction---
`get_models` is a function that retrieves a class based on the name (the first parameter). Sometimes, the caller may pass keyword arguments like `resource_type` and `operation_group`. Your task is to extract these details.

---Example Input---
Code Snippet:
def capture_vm(cmd, resource_group_name, vm_name, vhd_name_prefix,
               storage_container='vhds', overwrite=True):
    VirtualMachineCaptureParameters = cmd.get_models('VirtualMachineCaptureParameters')
    client = _compute_client_factory(cmd.cli_ctx)
    parameter = VirtualMachineCaptureParameters(vhd_prefix=vhd_name_prefix,
                                                destination_container_name=storage_container,
                                                overwrite_vhds=overwrite)
    client = get_mgmt_service_client(cmd.cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES,
                                     aux_subscriptions=aux_subscriptions).deployments
    DeploymentProperties = cmd.get_models('DeploymentProperties', resource_type=ResourceType.MGMT_RESOURCE_RESOURCES)
    properties = DeploymentProperties(template=template, parameters=parameters, mode='incremental')
    Deployment = cmd.get_models('Deployment', resource_type=ResourceType.MGMT_RESOURCE_RESOURCES)
    deployment = Deployment(properties=properties)

---Example Output---
[
    {{
        "name": "VirtualMachineCaptureParameters"
    }},
    {{
        "name": "DeploymentProperties",
        "resource_type": "ResourceType.MGMT_RESOURCE_RESOURCES"
    }},
    {{
        "name": "Deployment",
        "resource_type": "ResourceType.MGMT_RESOURCE_RESOURCES"
    }}
]

---Input---
Code Snippet:
{code_snippet}
"""


def extract_model(
        code_snippet,
        client=None,
):
    client = client or chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=MODEL_EXTRACTOR_PROMPT.format(
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
        return result
    except Exception:
        return None
