from fastapi import status


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def not_found(code: str, message: str) -> AppError:
    return AppError(code, message, status.HTTP_404_NOT_FOUND)


def conflict(code: str, message: str) -> AppError:
    return AppError(code, message, status.HTTP_409_CONFLICT)
