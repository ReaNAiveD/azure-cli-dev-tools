from azure.ai.inference import ChatCompletionsClient
from azure.identity import DefaultAzureCredential


def chat_client_4o_mini():
    return ChatCompletionsClient(
        endpoint='https://cli-copilot.openai.azure.com/openai/deployments/GPT-4o-mini',
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
        credential_scopes=["https://cognitiveservices.azure.com/.default"],
        model='gpt-4o-mini',
    )
