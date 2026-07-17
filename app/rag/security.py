import re
import unicodedata
from dataclasses import dataclass


HIDDEN_CONTROL_CATEGORIES = {"Cc", "Cf"}
ALLOWED_CONTROL_CHARACTERS = {"\n", "\r", "\t"}
SOURCE_BOUNDARY_PATTERN = re.compile(
    r"(?i)\[/?(?:begin|end)_source[^\]]*\]"
)
SOURCE_CITATION_PATTERN = re.compile(
    r"\[S(\d+)\]",
    flags=re.IGNORECASE,
)
HTML_COMMENT_PATTERN = re.compile(
    r"<!--.*?-->",
    flags=re.DOTALL,
)
INSTRUCTION_LINE_PATTERNS = (
    re.compile(
        r"^\s*(?:system|assistant|developer)\s*[:：]",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*</?(?:system|assistant|developer|prompt)>\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:忽略|无视|覆盖|忘记).{0,24}"
        r"(?:指令|提示词|规则|系统消息)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:不要|无需).{0,16}"
        r"(?:遵守|理会).{0,16}"
        r"(?:指令|规则|系统)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:你现在是|从现在开始你是|执行以下指令)",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class SanitizedContent:
    text: str
    removed_instruction_lines: int
    removed_control_characters: int


def sanitize_document_content(
    content: str,
) -> SanitizedContent:
    without_comments = HTML_COMMENT_PATTERN.sub(
        "",
        content,
    )
    without_boundaries = SOURCE_BOUNDARY_PATTERN.sub(
        "[已清理的来源边界文本]",
        without_comments,
    )
    without_fake_citations = SOURCE_CITATION_PATTERN.sub(
        r"[文档标记-S\1]",
        without_boundaries,
    )
    clean_characters: list[str] = []
    removed_control_characters = 0

    for character in without_fake_citations:
        if (
            character not in ALLOWED_CONTROL_CHARACTERS
            and unicodedata.category(character)
            in HIDDEN_CONTROL_CATEGORIES
        ):
            removed_control_characters += 1
            continue

        clean_characters.append(character)

    clean_lines: list[str] = []
    removed_instruction_lines = 0

    for line in "".join(clean_characters).splitlines():
        if any(
            pattern.search(line)
            for pattern in INSTRUCTION_LINE_PATTERNS
        ):
            removed_instruction_lines += 1
            continue

        clean_lines.append(line.rstrip())

    text = "\n".join(clean_lines).strip()
    return SanitizedContent(
        text=text,
        removed_instruction_lines=(
            removed_instruction_lines
        ),
        removed_control_characters=(
            removed_control_characters
        ),
    )


HIGH_RISK_ACTION_PATTERNS = (
    re.compile(
        r"(?:帮我|给我|替我|我要|立即|现在)"
        r".{0,12}(?:退款|退货|换货|取消订单)",
    ),
    re.compile(
        r"(?:申请|执行|发起|操作)"
        r".{0,8}(?:退款|退货|换货|取消订单)",
    ),
    re.compile(
        r"(?:修改|调整|增加|减少|清空|改|设为|设置)"
        r".{0,12}(?:库存|价格|售价)"
        r"|(?:库存|价格|售价)"
        r".{0,12}(?:修改|调整|增加|减少|清空|改|设为|设置)",
    ),
    re.compile(
        r"(?:改价|下架|上架|扣款|打款|赔付)",
    ),
)


def requires_business_tool(question: str) -> bool:
    return any(
        pattern.search(question)
        for pattern in HIGH_RISK_ACTION_PATTERNS
    )
