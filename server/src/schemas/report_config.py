from src.schemas.base import SchemaBaseModel


class PhaseAIConfig(SchemaBaseModel):
    """各フェーズで使用するAI設定"""

    provider: str | None = None  # LLMプロバイダー（openai, azure, openrouter, gemini, local）
    model: str | None = None  # LLMモデル名
    user_api_key: str | None = None  # ユーザー提供のAPIキー（オプション）


class ExtractionConfig(SchemaBaseModel):
    prompt: str
    workers: int | None = None
    limit: int | None = None
    ai_config: PhaseAIConfig | None = None  # このフェーズ専用のAI設定（オプション）


class EmbeddingConfig(SchemaBaseModel):
    """埋め込みフェーズの設定"""

    ai_config: PhaseAIConfig | None = None  # このフェーズ専用のAI設定（オプション）


class HierarchicalClusteringConfig(SchemaBaseModel):
    cluster_nums: list[int]


class HierarchicalInitialLabellingConfig(SchemaBaseModel):
    prompt: str
    sampling_num: int | None = None
    workers: int | None = None
    ai_config: PhaseAIConfig | None = None  # このフェーズ専用のAI設定（オプション）


class HierarchicalMergeLabellingConfig(SchemaBaseModel):
    prompt: str
    sampling_num: int | None = None
    workers: int | None = None
    ai_config: PhaseAIConfig | None = None  # このフェーズ専用のAI設定（オプション）


class HierarchicalOverviewConfig(SchemaBaseModel):
    prompt: str
    ai_config: PhaseAIConfig | None = None  # このフェーズ専用のAI設定（オプション）


class HierarchicalAggregationConfig(SchemaBaseModel):
    sampling_num: int | None = None


class ReportConfig(SchemaBaseModel):
    name: str
    input: str
    question: str
    intro: str
    model: str
    provider: str | None = None
    is_pubcom: bool | None = None
    is_embedded_at_local: bool | None = None
    local_llm_address: str | None = None
    extraction: ExtractionConfig
    embedding: EmbeddingConfig | None = None  # 埋め込みフェーズの設定（オプション、後方互換性のため）
    hierarchical_clustering: HierarchicalClusteringConfig
    hierarchical_initial_labelling: HierarchicalInitialLabellingConfig
    hierarchical_merge_labelling: HierarchicalMergeLabellingConfig
    hierarchical_overview: HierarchicalOverviewConfig
    hierarchical_aggregation: HierarchicalAggregationConfig


class ReportConfigUpdate(SchemaBaseModel):
    """レポートのメタデータ更新用スキーマ"""

    question: str | None = None  # レポートのタイトル
    intro: str | None = None  # レポートの調査概要
