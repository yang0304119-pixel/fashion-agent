"""尺码领域服务：执行确定性的身高、体重和版型规则。"""

from dataclasses import dataclass


SIZE_TABLE: tuple[tuple[range, range, str], ...] = (
    (range(155, 165), range(45, 60), "S"),
    (range(155, 165), range(60, 75), "M"),
    (range(165, 175), range(50, 65), "S"),
    (range(165, 175), range(60, 75), "M"),
    (range(165, 175), range(75, 90), "L"),
    (range(175, 185), range(55, 70), "M"),
    (range(175, 185), range(65, 80), "L"),
    (range(175, 185), range(80, 100), "XL"),
    (range(185, 195), range(65, 80), "L"),
    (range(185, 195), range(75, 95), "XL"),
    (range(185, 195), range(95, 115), "XXL"),
)

STYLE_OFFSET = {"修身": -1, "标准": 0, "宽松": 1}
SIZE_ORDER = ("S", "M", "L", "XL", "XXL", "XXXL")


class SizeServiceError(Exception):
    pass


class InvalidSizeInputError(SizeServiceError):
    pass


class SizeNotFoundError(SizeServiceError):
    pass


@dataclass(frozen=True)
class SizeRecommendation:
    height: int
    weight: int
    style: str
    base_size: str
    size: str


class SizeService:
    def recommend(
        self,
        *,
        height: int,
        weight: int,
        style: str = "标准",
    ) -> SizeRecommendation:
        if height < 100 or height > 250:
            raise InvalidSizeInputError("身高数据不合理（100-250cm）")
        if weight < 30 or weight > 200:
            raise InvalidSizeInputError("体重数据不合理（30-200kg）")
        if style not in STYLE_OFFSET:
            raise InvalidSizeInputError("版型偏好仅支持：修身/标准/宽松")

        base_size = next(
            (
                size
                for height_range, weight_range, size in SIZE_TABLE
                if height in height_range and weight in weight_range
            ),
            None,
        )
        if base_size is None:
            raise SizeNotFoundError(
                f"身高 {height}cm / 体重 {weight}kg 未找到匹配尺码"
            )

        base_index = SIZE_ORDER.index(base_size)
        final_index = max(
            0,
            min(
                len(SIZE_ORDER) - 1,
                base_index + STYLE_OFFSET[style],
            ),
        )
        return SizeRecommendation(
            height=height,
            weight=weight,
            style=style,
            base_size=base_size,
            size=SIZE_ORDER[final_index],
        )
