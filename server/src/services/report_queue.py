"""
レポート生成キュー管理サービス

複数のレポート作成リクエストを順次処理するためのキューイングシステム。
1つのレポートが完了してから次のレポートを処理します。
"""

import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings
from src.schemas.admin_report import ReportInput
from src.services.report_launcher import save_config_file, save_input_file
from src.services.report_status import add_new_report_to_status, set_status
from src.utils.logger import setup_logger

logger = setup_logger()

# キューディレクトリ
QUEUE_DIR = settings.REPORT_DIR / "_queue"
LOCK_FILE = QUEUE_DIR / "_processing.lock"


class ReportQueueManager:
    """レポート生成キューを管理するクラス"""

    _instance = None
    _lock = threading.Lock()
    _worker_thread = None
    _should_stop = False

    def __new__(cls):
        """シングルトンパターンでインスタンスを管理"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初期化処理"""
        if self._initialized:
            return

        self._initialized = True
        self._ensure_queue_dir()
        self._start_worker()

    def _ensure_queue_dir(self):
        """キューディレクトリが存在することを確認"""
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Queue directory ensured: {QUEUE_DIR}")

    def _start_worker(self):
        """ワーカースレッドを開始"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._should_stop = False
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()
            logger.info("Report queue worker started")

    def _process_queue(self):
        """キューを監視して順次処理"""
        logger.info("Queue processor started")

        while not self._should_stop:
            try:
                # 現在処理中のレポートがあるかチェック
                if self._is_processing():
                    time.sleep(5)  # 5秒待機
                    continue

                # キューから次のジョブを取得
                job = self._get_next_job()
                if job is None:
                    time.sleep(5)  # キューが空の場合は5秒待機
                    continue

                # ジョブを処理
                self._process_job(job)

            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                time.sleep(5)

        logger.info("Queue processor stopped")

    def _is_processing(self) -> bool:
        """現在処理中のレポートがあるかチェック"""
        # ロックファイルの存在をチェック
        if LOCK_FILE.exists():
            try:
                with open(LOCK_FILE) as f:
                    lock_data = json.load(f)
                    locked_at = datetime.fromisoformat(lock_data.get("locked_at", ""))
                    # ロックが24時間以上前の場合は古いロックとみなして削除
                    if (datetime.now() - locked_at).total_seconds() > 86400:
                        logger.warning("Removing stale lock file")
                        LOCK_FILE.unlink()
                        return False
                    return True
            except Exception as e:
                logger.error(f"Error reading lock file: {e}")
                # エラーの場合はロックファイルを削除
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass
                return False

        # report_status.jsonをチェックして実行中のレポートがあるか確認
        status_file = settings.REPORT_DIR / "report_status.json"
        if status_file.exists():
            try:
                with open(status_file) as f:
                    reports = json.load(f)
                    for report in reports.get("reports", []):
                        if report.get("status") in ["pending", "running"]:
                            logger.debug(f"Report {report.get('slug')} is still processing")
                            return True
            except Exception as e:
                logger.error(f"Error checking report status: {e}")

        return False

    def _get_next_job(self) -> dict[str, Any] | None:
        """キューから次のジョブを取得"""
        try:
            # キューファイルを作成日時順にソート
            queue_files = sorted(QUEUE_DIR.glob("*.json"), key=lambda p: p.stat().st_ctime)

            for queue_file in queue_files:
                try:
                    with open(queue_file) as f:
                        job = json.load(f)

                    # ジョブファイルを削除
                    queue_file.unlink()
                    logger.info(f"Retrieved job from queue: {job.get('slug')}")
                    return job

                except Exception as e:
                    logger.error(f"Error reading queue file {queue_file}: {e}")
                    # 読み取りエラーの場合はファイルを削除
                    try:
                        queue_file.unlink()
                    except Exception:
                        pass

            return None

        except Exception as e:
            logger.error(f"Error getting next job: {e}")
            return None

    def _process_job(self, job: dict[str, Any]):
        """ジョブを処理"""
        slug = job.get("slug")
        config_path = job.get("config_path")
        user_api_key = job.get("user_api_key")

        logger.info(f"[Queue] Processing report: {slug}")

        try:
            # ロックファイルを作成
            self._create_lock(slug)

            # パイプラインを実行
            cmd = ["python", "hierarchical_main.py", config_path, "--skip-interaction", "--without-html"]
            execution_dir = settings.TOOL_DIR / "pipeline"

            env = os.environ.copy()
            if user_api_key:
                env["USER_API_KEY"] = user_api_key

            process = subprocess.Popen(cmd, cwd=execution_dir, env=env)

            # プロセスの完了を待機
            retcode = process.wait()

            if retcode == 0:
                logger.info(f"[Queue] Report {slug} completed successfully, performing post-processing")
                self._handle_success(slug)
            else:
                logger.error(f"[Queue] Report {slug} failed with return code {retcode}")
                set_status(slug, "error")

        except Exception as e:
            logger.error(f"[Queue] Error processing job {slug}: {e}", exc_info=True)
            set_status(slug, "error")

        finally:
            # ロックファイルを削除
            self._remove_lock()

    def _handle_success(self, slug: str):
        """
        レポート生成成功時の後処理
        トークン使用量の更新とストレージ同期を実行
        """
        try:
            from src.services.report_status import update_token_usage
            from src.services.report_sync import ReportSyncService

            # トークン使用量を更新
            status_file = settings.REPORT_DIR / slug / "hierarchical_status.json"
            if status_file.exists():
                with open(status_file) as f:
                    status_data = json.load(f)
                    total_token_usage = status_data.get("total_token_usage", 0)
                    token_usage_input = status_data.get("token_usage_input", 0)
                    token_usage_output = status_data.get("token_usage_output", 0)

                    config_file = settings.CONFIG_DIR / f"{slug}.json"
                    provider = None
                    model = None
                    if config_file.exists():
                        with open(config_file) as f:
                            config_data = json.load(f)
                            provider = config_data.get("provider")
                            model = config_data.get("model")

                    logger.info(
                        f"[Queue] Token usage for {slug}: total={total_token_usage}, "
                        f"input={token_usage_input}, output={token_usage_output}, "
                        f"provider={provider}, model={model}"
                    )
                    update_token_usage(
                        slug, total_token_usage, token_usage_input, token_usage_output, provider or None, model or None
                    )
            else:
                logger.warning(f"[Queue] Status file not found for {slug}, skipping token usage update")

        except Exception as e:
            logger.error(f"[Queue] Error updating token usage for {slug}: {e}", exc_info=True)

        # ステータスを ready に更新
        set_status(slug, "ready")

        # ストレージ同期
        try:
            logger.info(f"[Queue] Syncing files for {slug} to storage")
            report_sync_service = ReportSyncService()
            report_sync_service.sync_report_files_to_storage(slug)
            report_sync_service.sync_input_file_to_storage(slug)
            report_sync_service.sync_config_file_to_storage(slug)
            report_sync_service.sync_status_file_to_storage()
            logger.info(f"[Queue] Storage sync completed for {slug}")
        except Exception as e:
            logger.error(f"[Queue] Error syncing files for {slug}: {e}", exc_info=True)

    def _create_lock(self, slug: str):
        """ロックファイルを作成"""
        try:
            lock_data = {"slug": slug, "locked_at": datetime.now().isoformat()}
            with open(LOCK_FILE, "w") as f:
                json.dump(lock_data, f)
            logger.debug(f"Lock created for {slug}")
        except Exception as e:
            logger.error(f"Error creating lock: {e}")

    def _remove_lock(self):
        """ロックファイルを削除"""
        try:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
                logger.debug("Lock removed")
        except Exception as e:
            logger.error(f"Error removing lock: {e}")

    def add_to_queue(self, report_input: ReportInput, user_api_key: str | None = None) -> str:
        """
        レポート生成ジョブをキューに追加

        Args:
            report_input: レポート作成リクエスト
            user_api_key: ユーザー提供のAPIキー（オプション）

        Returns:
            キューに追加されたジョブのID（slug）
        """
        try:
            # レポートステータスを追加
            add_new_report_to_status(report_input)

            # 設定ファイルと入力ファイルを保存
            config_path = save_config_file(report_input)
            save_input_file(report_input)

            # キューファイルを作成
            slug = report_input.input
            queue_file = QUEUE_DIR / f"{slug}_{datetime.now().timestamp()}.json"

            job_data = {
                "slug": slug,
                "config_path": str(config_path),
                "user_api_key": user_api_key,
                "created_at": datetime.now().isoformat(),
            }

            with open(queue_file, "w") as f:
                json.dump(job_data, f, indent=2)

            logger.info(f"Added report {slug} to queue: {queue_file}")
            return slug

        except Exception as e:
            logger.error(f"Error adding report to queue: {e}", exc_info=True)
            set_status(report_input.input, "error")
            raise

    def get_queue_status(self) -> dict[str, Any]:
        """
        キューの状態を取得

        Returns:
            キューの状態情報
        """
        try:
            queue_files = list(QUEUE_DIR.glob("*.json"))
            is_processing = self._is_processing()

            current_job = None
            if is_processing and LOCK_FILE.exists():
                try:
                    with open(LOCK_FILE) as f:
                        lock_data = json.load(f)
                        current_job = lock_data.get("slug")
                except Exception:
                    pass

            return {
                "queue_length": len(queue_files),
                "is_processing": is_processing,
                "current_job": current_job,
                "worker_alive": self._worker_thread.is_alive() if self._worker_thread else False,
            }

        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {
                "queue_length": 0,
                "is_processing": False,
                "current_job": None,
                "worker_alive": False,
            }

    def stop(self):
        """ワーカースレッドを停止"""
        self._should_stop = True
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        logger.info("Report queue manager stopped")


# グローバルインスタンス
_queue_manager = None


def get_queue_manager() -> ReportQueueManager:
    """キューマネージャーのシングルトンインスタンスを取得"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = ReportQueueManager()
    return _queue_manager
