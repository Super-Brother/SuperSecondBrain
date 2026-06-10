"""笔记管理 Pydantic 模型"""

from pydantic import BaseModel, Field


class NoteMetadata(BaseModel):
    """笔记元数据（列表和详情共用）"""

    title: str
    relative_path: str
    folder: str
    domain: str
    tags: list[str] = []
    date: str | None = None
    content_hash: str = ""
    outbound_links: list[str] = []
    headings: list[str] = []
    format: str  # "markdown" | "pdf" | "docx" | "pptx" | "xlsx"


class NoteDetail(NoteMetadata):
    """笔记详情（含内容）"""

    content: str = ""  # 渲染用正文（不含 frontmatter）
    raw_content: str = ""  # 原始内容（含 frontmatter，可编辑）
    word_count: int = 0
    is_downloadable: bool = False  # 非 Markdown 格式时提供下载


class NoteCreateRequest(BaseModel):
    """新建笔记请求"""

    relative_path: str = Field(..., description="相对于 vault 根目录的路径，必须含 .md 扩展名")
    title: str = Field(..., min_length=1)
    content: str = ""
    tags: list[str] = []
    date: str | None = None
    frontmatter: dict = {}  # 可选自定义 frontmatter 字段


class NoteUpdateRequest(BaseModel):
    """更新笔记请求"""

    content: str | None = None
    tags: list[str] | None = None
    date: str | None = None
    frontmatter: dict | None = None


class NoteListResponse(BaseModel):
    """笔记列表响应"""

    total: int
    page: int
    page_size: int
    items: list[NoteMetadata]


class NoteSearchResult(BaseModel):
    """笔记搜索结果"""

    score: float
    note: NoteMetadata
    matched_chunks: list[str]  # 匹配的文本片段


class FolderListResponse(BaseModel):
    """文件夹列表响应"""

    folders: list[str]


class TagInfo(BaseModel):
    """标签信息"""

    name: str
    count: int | None = None


class TagListResponse(BaseModel):
    """标签列表响应"""

    tags: list[TagInfo]
