"""尺码工具适配器：将Service结果转换为LLM可消费的结构化数据。"""

from app.services.size_service import SizeService, SizeServiceError
from app.tools.executor import ToolErrorCategory, ToolErrorDetail, failure_result


def size_recommend(
    height: int,
    weight: int,
    style: str = "标准",
) -> dict:
    try:
        recommendation = SizeService().recommend(
            height=height,
            weight=weight,
            style=style,
        )
    except SizeServiceError as error:
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.VALIDATION,
            code="invalid_size_arguments",
            message=str(error),
            retryable=True,
            correction_hint="核对身高、体重单位和版型偏好后重新生成参数",
        ))

    return {
        "success": True,
        "data": {
            "size": recommendation.size,
            "base_size": recommendation.base_size,
            "height": recommendation.height,
            "weight": recommendation.weight,
            "style": recommendation.style,
            "reason": (
                f"根据身高 {recommendation.height}cm、"
                f"体重 {recommendation.weight}kg，"
                f"{recommendation.style}版型推荐 "
                f"{recommendation.size} 码"
            ),
        },
        "error": None,
    }
