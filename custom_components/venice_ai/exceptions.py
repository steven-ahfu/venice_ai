"""Custom exceptions for Venice AI integration."""
from homeassistant.exceptions import HomeAssistantError


class FunctionNotFound(HomeAssistantError):
    """Raised when a requested function type is not registered."""
    def __init__(self, function_type: str) -> None:
        super().__init__(f"Function type '{function_type}' does not exist")
        self.function_type = function_type


class FunctionLoadFailed(HomeAssistantError):
    """Raised when function YAML fails to parse or validate."""


class InvalidFunction(HomeAssistantError):
    """Raised when a function config fails schema validation."""
    def __init__(self, function_name: str, cause: str) -> None:
        super().__init__(f"Failed to validate function '{function_name}': {cause}")


class ParseArgumentsFailed(HomeAssistantError):
    """Raised when tool call arguments cannot be parsed."""
    def __init__(self, arguments: str) -> None:
        super().__init__(f"Failed to parse arguments: {arguments}")


class EntityNotFound(HomeAssistantError):
    """Raised when a referenced entity does not exist."""
    def __init__(self, entity_id: str) -> None:
        super().__init__(f"Entity not found: {entity_id}")


class EntityNotExposed(HomeAssistantError):
    """Raised when a referenced entity is not exposed to the assistant."""
    def __init__(self, entity_id: str) -> None:
        super().__init__(f"Entity '{entity_id}' is not exposed to the assistant")


class CallServiceError(HomeAssistantError):
    """Raised when a service call fails."""
    def __init__(self, domain: str, service: str, error: str) -> None:
        super().__init__(f"Service call {domain}.{service} failed: {error}")
