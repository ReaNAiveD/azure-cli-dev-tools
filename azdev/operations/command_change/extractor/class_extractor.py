import json

from azure.ai.inference.models._models import ChatRequestSystemMessage, ChatRequestUserMessage

from azdev.operations.command_change.extractor.utils import chat_client_4o_mini

DEPENDENCIES_EXTRACTOR_PROMPT = """
---Role---
You are a helpful Python Static Analysis Assistant. You will receive:
1. A Python code snippet which is a class
Your task is to analyze the composition of the class including fields, methods and consts, and then output a detailed, structured summary in JSON.

---Procedure---
1. Superclass Identification: Examine the class declaration line (e.g., class MyClass(BaseClass):) to determine if the class inherits from another. 
    * If a superclass is present, extract and record its name. If multiple inheritance is used, list all superclasses.
2. Code Structure Interpretation: Analyze the structure of the class by interpreting the code textually. Identify:
    * The class name and its inheritance (if any).
    * Class-level constants (typically all-uppercase variables defined directly under the class).
    * Instance fields (usually assigned to self within the __init__ method or other instance methods).
    * Method definitions, including their names, arguments, and decorators (e.g., @staticmethod, @classmethod).
3. Field Usage Mapping:
    * For each instance field, examine all method bodies to determine where and how the field is accessed or modified.
    * Categorize usage as: "read", "write", or "read/write".
    * Record the method names where each usage occurs.
4. Method Analysis:
    * List all methods with their names and arguments.
    * Identify the method type: constructor (__init__), static method, class method, or instance method.
    * Summarize the method’s purpose using docstrings or inferred behavior from the code.
5. Constant Identification:
    * Extract class-level constants and record their names and assigned values.
6. JSON Output Construction:
    * Format the extracted data into a JSON object with the following structure:
    ```json
    {{
        "class_name": "ClassName",
        "super_classes": ["BaseClass"],
        "constants": [{{ "name": "CONST_NAME", "value": "..." }}],
        "fields": [
            {{
                "name": "field_name",
                "defined_in": "__init__",
                "used_in": [
                    {{ "method": "method_name", "usage": "read/write", "context": "usage context description" }}
                ]
            }}
        ],
        "methods": [
            {{
                "name": "method_name",
                "type": "instance/static/class",
                "args": ["self", "arg1", "arg2"],
                "doc": "Optional docstring or inferred summary",
                "purpose": "Summarized the method’s purpose"
            }}
        ]
    }}
    ```
7. Validation:
    * Ensure the JSON is well-formed and all fields are populated.

---Input---
Code Snippet:
{code_snippet}
"""


def extract_class_info(
        code_snippet,
        client=None,
):
    client = client or chat_client_4o_mini()
    resp = client.complete(
        messages=[
            ChatRequestSystemMessage(
                content=DEPENDENCIES_EXTRACTOR_PROMPT.format(
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
    return json.loads(content)
