"""Custom exceptions for the framework."""


class FrameworkError(Exception):
    def __init__(self, message: str = "An error occurred in the framework"):
        self.message = message
        super().__init__(self.message)


class LLMClientError(FrameworkError):
    pass


class MemoryError(FrameworkError):
    pass


class ConfigurationError(FrameworkError):
    pass


class DomainClassifierError(FrameworkError):
    pass


HTTP_STATUS_CODES = {
    LLMClientError: 503,
    MemoryError: 500,
    ConfigurationError: 500,
    DomainClassifierError: 503,
    FrameworkError: 500,
}
