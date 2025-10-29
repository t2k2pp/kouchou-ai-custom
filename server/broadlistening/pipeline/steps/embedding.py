import logging
import os

import pandas as pd
from tqdm import tqdm

from services.llm import request_to_embed


def embedding(config):
    # フェーズ固有のAI設定を取得（なければデフォルト設定を使用）
    embedding_config = config.get("embedding", {})
    ai_config = embedding_config.get("ai_config", {})
    model = ai_config.get("model") or config.get("embedding", {}).get("model") or config["model"]
    provider = ai_config.get("provider") or config["provider"]
    user_api_key = ai_config.get("user_api_key") or config.get("user_api_key")
    is_embedded_at_local = config["is_embedded_at_local"]

    logging.info(f"[Embedding] Using provider={provider}, model={model}, is_embedded_at_local={is_embedded_at_local}")

    dataset = config["output_dir"]
    path = f"outputs/{dataset}/embeddings.pkl"
    arguments = pd.read_csv(f"outputs/{dataset}/args.csv", usecols=["arg-id", "argument"])
    embeddings = []
    batch_size = 1000
    for i in tqdm(range(0, len(arguments), batch_size)):
        args = arguments["argument"].tolist()[i : i + batch_size]
        embeds = request_to_embed(
            args,
            model,
            is_embedded_at_local,
            provider,
            local_llm_address=config.get("local_llm_address"),
            user_api_key=user_api_key,
        )
        embeddings.extend(embeds)
    df = pd.DataFrame([{"arg-id": arguments.iloc[i]["arg-id"], "embedding": e} for i, e in enumerate(embeddings)])
    df.to_pickle(path)
