"""
集成测试示例
Integration Tests
"""

import asyncio
from pathlib import Path

import aiosqlite
import pytest


class TestConfigIntegration:
    """配置模块集成测试"""

    @pytest.mark.asyncio
    async def test_config_with_real_yaml(self, temp_config_file):
        """测试使用真实YAML文件的配置加载"""
        from src.core.config import Config

        config = Config(str(temp_config_file))
        assert config.get("app.name") == "xianyu-openclaw"
        assert config.get("openclaw.port") == 9222
        assert len(config.get("accounts")) == 2

    def test_config_model_integration(self, temp_config_file):
        """测试配置模型集成"""
        from src.core.config import Config
        from src.core.config_models import ConfigModel

        config = Config(str(temp_config_file))
        config_data = config._config

        # 验证可以转换为ConfigModel
        model = ConfigModel.from_dict(config_data)
        assert model.app.name == "xianyu-openclaw"
        assert len(model.accounts) == 2

    def test_config_with_env_variables(self, temp_dir, monkeypatch):
        """测试配置与环境变量的集成"""
        from src.core.config import Config

        # 创建包含环境变量的配置文件
        config_file = temp_dir / "config_with_env.yaml"
        config_content = """
app:
  name: "test"
ai:
  api_key: "${TEST_KEY}"
"""
        config_file.write_text(config_content)

        monkeypatch.setenv("TEST_KEY", "resolved_value")

        config = Config(str(config_file))
        assert config.get("ai.api_key") == "resolved_value"


class TestServiceContainerIntegration:
    """服务容器集成测试"""

    def test_service_container_registration(self):
        """测试服务注册"""
        from src.core.service_container import ServiceContainer, get_container

        container = get_container()
        assert container is not None

    def test_service_container_singleton(self):
        """测试服务容器单例"""
        from src.core.service_container import get_container

        container1 = get_container()
        container2 = get_container()
        assert container1 is container2


class TestLoggerIntegration:
    """日志模块集成测试"""

    def test_logger_integration_with_config(self, temp_dir):
        """测试日志与配置的集成"""
        from src.core.config import Config
        from src.core.logger import Logger

        # 创建配置文件
        config_file = temp_dir / "config.yaml"
        config_content = f"""
app:
  name: "test"
  log_level: "DEBUG"
  logs_dir: "{temp_dir}"
"""
        config_file.write_text(config_content)

        logger = Logger()
        assert logger is not None

        # 测试日志方法
        logger.info("Test info message")
        logger.debug("Test debug message")
        logger.warning("Test warning message")
        logger.error("Test error message")
        logger.success("Test success message")


class TestErrorHandlerIntegration:
    """错误处理集成测试"""

    @pytest.mark.asyncio
    async def test_error_handler_with_logger(self):
        """测试错误处理与日志的集成"""
        from unittest.mock import Mock

        from src.core.error_handler import handle_controller_errors

        mock_logger = Mock()

        @handle_controller_errors(default_return="fallback")
        async def test_func(self):
            raise ConnectionError("Test error")

        mock_obj = Mock(logger=mock_logger)
        result = await test_func(mock_obj)

        assert result == "fallback"
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_with_logger(self):
        """测试重试机制与日志的集成"""
        from unittest.mock import Mock

        from src.core.error_handler import retry

        mock_logger = Mock()
        attempts = [0]

        @retry(max_attempts=3, delay=0.1)
        async def test_func():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("Temporary error")
            return "success"

        result = await test_func(logger=mock_logger)
        assert result == "success"
        assert attempts[0] == 2


class TestModelsIntegration:
    """数据模型集成测试"""

    def test_listing_model_integration(self, sample_listing_data):
        """测试商品模型集成"""
        from src.modules.listing.models import Listing

        listing = Listing(**sample_listing_data)
        assert listing.title == "iPhone 15 Pro Max 256GB"
        assert listing.price == 8999.0
        assert listing.category == "数码手机"
        assert len(listing.images) == 2
        assert len(listing.tags) == 3

    def test_publish_result_model_integration(self):
        """测试发布结果模型集成"""
        from src.modules.listing.models import PublishResult

        result = PublishResult(
            success=True,
            product_id="test_id",
            product_url="https://test.url/product/test_id"
        )
        assert result.success is True
        assert result.product_id == "test_id"
        assert result.error_message is None


@pytest.mark.integration
class TestDatabaseIntegration:
    """数据库集成测试（标记为integration）"""

    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_dir):
        """测试数据库初始化"""
        from src.modules.analytics.service import AnalyticsService

        db_path = temp_dir / "test.db"
        config = {
            "path": str(db_path),
            "max_connections": 5
        }

        AnalyticsService(config=config)
        assert db_path.exists()

        # 验证表已创建
        import aiosqlite
        async with aiosqlite.connect(str(db_path)) as db:
            tables = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [row[0] for row in await tables.fetchall()]

            assert "operation_logs" in table_names
            assert "product_metrics" in table_names
            assert "products" in table_names

    @pytest.mark.asyncio
    async def test_database_log_operation(self, temp_dir):
        """测试数据库操作日志记录"""
        from src.modules.analytics.service import AnalyticsService

        db_path = temp_dir / "test_log.db"
        config = {
            "path": str(db_path)
        }

        service = AnalyticsService(config=config)

        log_id = await service.log_operation(
            operation_type="publish",
            product_id="test_product",
            account_id="test_account",
            details={"title": "Test Product"},
            status="success"
        )

        assert log_id > 0

        # 验证日志已记录
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT * FROM operation_logs WHERE id = ?",
                (log_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[1] == "publish"  # operation_type


@pytest.mark.slow
class TestPerformanceIntegration:
    """性能集成测试（标记为slow）"""

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_dir):
        """测试并发操作性能"""
        import time

        from src.modules.analytics.service import AnalyticsService

        db_path = temp_dir / "test_perf.db"
        config = {"path": str(db_path)}

        service = AnalyticsService(config=config)

        # 并发记录100条日志
        start_time = time.time()

        tasks = [
            service.log_operation(
                operation_type=f"operation_{i}",
                product_id=f"product_{i}",
                account_id="test_account",
                status="success"
            )
            for i in range(100)
        ]

        await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        assert elapsed < 5.0  # 应该在5秒内完成

        # 验证所有日志已记录
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM operation_logs")
            count = await cursor.fetchone()
            assert count[0] == 100
