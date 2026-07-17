from dataclasses import dataclass


@dataclass(frozen=True)
class RagErrorInfo:
    code: str
    stage: str
    error_type: str


class RagError(Exception):
    def __init__(
        self,
        *,
        code: str,
        stage: str,
        cause: Exception,
    ) -> None:
        super().__init__(
            f"RAG {stage} failed: "
            f"{type(cause).__name__}"
        )
        self.info = RagErrorInfo(
            code=code,
            stage=stage,
            error_type=type(cause).__name__,
        )
        self.__cause__ = cause
