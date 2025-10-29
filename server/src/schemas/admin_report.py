from typing import Literal

from src.schemas.base import SchemaBaseModel
from src.schemas.report import ReportVisibility


class Comment(SchemaBaseModel):
    id: str
    comment: str
    source: str | None = None
    url: str | None = None

    class Config:
        extra = "allow"


class Prompt(SchemaBaseModel):
    extraction: str
    initial_labelling: str
    merge_labelling: str
    overview: str


class PhaseAISettings(SchemaBaseModel):
    """各フェーズのAI設定（UI入力用）"""

    provider: str | None = None
    model: str | None = None
    user_api_key: str | None = None


class AIPhaseSettings(SchemaBaseModel):
    """全フェーズのAI設定をまとめたもの（UI入力用）"""

    extraction: PhaseAISettings | None = None
    embedding: PhaseAISettings | None = None
    initial_labelling: PhaseAISettings | None = None
    merge_labelling: PhaseAISettings | None = None
    overview: PhaseAISettings | None = None


class ReportInput(SchemaBaseModel):
    input: str  # レポートのID
    question: str  # レポートのタイトル
    intro: str  # レポートの調査概要
    cluster: list[int]  # 層ごとのクラスタ数定義
    model: str  # 利用するLLMの名称（デフォルト）
    workers: int  # LLM APIの並列実行数
    prompt: Prompt  # プロンプト
    comments: list[Comment]  # コメントのリスト
    is_pubcom: bool = False  # CSV出力モード出力フラグ
    inputType: Literal["file", "spreadsheet"] = "file"  # 入力タイプ
    is_embedded_at_local: bool = False  # エンベデッド処理をローカルで行うかどうか
    provider: str = "openai"  # LLMプロバイダー（デフォルト）（openai, azure, openrouter, gemini, local）
    local_llm_address: str | None = None  # LocalLLM用アドレス（例: "127.0.0.1:1234"）
    user_api_key: str | None = None  # ユーザー提供のAPIキー（デフォルト、オプション）
    ai_phase_settings: AIPhaseSettings | None = None  # 各フェーズのAI設定（オプション）

    # NOTE: team-mirai feature
    enable_source_link: bool = False  # ソースリンク機能を有効にするかどうか。有効にする場合はtrue


class ReportVisibilityUpdate(SchemaBaseModel):
    """レポートの可視性更新用スキーマ"""

    visibility: ReportVisibility  # レポートの可視性
