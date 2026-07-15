"""
尺码推荐工具

根据用户的身高、体重和穿衣偏好，推荐合适的服装尺码。

# 关键设计说明
# ─────────────────────────────
# 为什么用规则计算而非 LLM：
# - 尺码推荐是确定性规则，计算机算比 LLM 快 100 倍且零成本
# - 规则可解释（"因为您 175cm/70kg，偏宽松选 L"）
# - 后续可扩展：接入真实尺码表（不同品牌版型不同）
# 为什么 style 参数有默认值：
# - 部分用户不表达偏好，默认"标准"最安全
# - 后续可扩展到"修身 / 标准 / 宽松"三档
# ─────────────────────────────
"""

# 尺码速查表：基于 (身高, 体重) 的推荐尺码
# 行 = 身高区间(cm)，列 = 体重区间(kg)
# 数据来源：GB/T 1335-2008 男装标准尺码
_SIZE_TABLE: list[tuple[range, range, str]] = [
    # (身高范围, 体重范围, 推荐尺码)
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
]

# 版型偏移量：修身-1 码，宽松+1 码
_STYLE_OFFSET: dict[str, int] = {
    "修身": -1,
    "标准": 0,
    "宽松": 1,
}

# 尺码顺序（用于偏移计算）
_SIZE_ORDER: list[str] = ["S", "M", "L", "XL", "XXL", "XXXL"]


def size_recommend(height: int, weight: int, style: str = "标准") -> dict:
    """根据身高体重推荐服装尺码。

    Args:
        height: 身高（cm），如 175。
        weight: 体重（kg），如 70。
        style: 版型偏好，"修身"/"标准"/"宽松"，默认"标准"。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {size, reason} | None
        - error: str | None
    """
    # ── 参数校验 ──
    if height < 100 or height > 250:
        return {"success": False, "data": None, "error": "身高数据不合理（100-250cm）"}
    if weight < 30 or weight > 200:
        return {"success": False, "data": None, "error": "体重数据不合理（30-200kg）"}
    if style not in _STYLE_OFFSET:
        return {"success": False, "data": None, "error": f"版型偏好仅支持：修身/标准/宽松"}

    # ── 查表匹配 ──
    base_size: str | None = None
    for h_range, w_range, size in _SIZE_TABLE:
        if height in h_range and weight in w_range:
            base_size = size
            break

    if not base_size:
        return {
            "success": False,
            "data": None,
            "error": f"身高 {height}cm / 体重 {weight}kg 未找到匹配尺码",
        }

    # ── 按版型偏好偏移 ──
    offset = _STYLE_OFFSET[style]
    base_idx = _SIZE_ORDER.index(base_size)
    final_idx = max(0, min(len(_SIZE_ORDER) - 1, base_idx + offset))
    final_size = _SIZE_ORDER[final_idx]

    return {
        "success": True,
        "data": {
            "size": final_size,
            "reason": f"根据身高 {height}cm、体重 {weight}kg，{style}版型推荐 {final_size} 码",
        },
        "error": None,
    }
