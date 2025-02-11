from typing import TypedDict, List, Literal
from typing_extensions import NotRequired
# -------------------------
# Type Definitions
# -------------------------

class ComponentDict(TypedDict):
    name: str
    type: Literal["component", "page"]
    description: str
    path: NotRequired[str]

class SplitComponentDict(TypedDict):
    name: str
    type: Literal["component", "page"]
    parts: List[ComponentDict]

def validate_component_dict(data: dict, agent_name: str) -> ComponentDict:
    """Validates that a dictionary matches the ComponentDict structure"""
    try:
        if not all(key in data for key in ["name", "type", "description"]):
            raise ValueError("Missing required fields: name, type, description")
            
        if not isinstance(data["name"], str):
            raise ValueError("name must be a string")
            
        if data["type"] not in ["component", "page"]:
            raise ValueError("type must be either 'component' or 'page'")
            
        if not isinstance(data["description"], str):
            raise ValueError("description must be a string")
            
        return data
    except Exception as e:
        raise ValueError(f"{agent_name} output validation failed: {str(e)}")

def validate_split_output(data: dict, agent_name: str) -> SplitComponentDict:
    """Validates that a dictionary matches the SplitComponentDict structure"""
    try:
        if not isinstance(data, dict):
            raise ValueError("Output must be a dictionary")
            
        if not all(key in data for key in ["name", "type", "parts"]):
            raise ValueError("Missing required fields: name, type, parts")
            
        if not isinstance(data["parts"], list):
            raise ValueError("parts must be a list")
            
        # Validate each part
        for part in data["parts"]:
            validate_component_dict(part, f"{agent_name} (part validation)")
            
        return data
    except Exception as e:
        raise ValueError(f"{agent_name} output validation failed: {str(e)}")

