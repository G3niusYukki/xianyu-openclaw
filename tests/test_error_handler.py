"""
异常处理单元测试
Error Handler Tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.core.error_handler import (
    handle_controller_errors, handle_operation_errors, safe_execute,
    retry, log_execution_time,
    XianyuError, ConfigError, BrowserError, AIError, MediaError,
    AccountError, DatabaseError, handle_errors
)
import httpx


class TestHandleControllerErrors:
    """控制器错误处理装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_success(self):
        """测试成功执行"""
        @handle_controller_errors(default_return="fallback")
        async def test_func(self):
            return "success"
        
        mock_obj = Mock()
        result = await test_func(mock_obj)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_connection_error(self):
        """测试连接错误"""
        @handle_controller_errors(default_return="fallback")
        async def test_func(self):
            raise ConnectionError("Connection failed")
        
        mock_obj = Mock(logger=Mock())
        result = await test_func(mock_obj)
        assert result == "fallback"
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_http_error(self):
        """测试HTTP错误"""
        @handle_controller_errors(default_return="fallback")
        async def test_func(self):
            raise httpx.HTTPError("HTTP request failed")
        
        mock_obj = Mock(logger=Mock())
        result = await test_func(mock_obj)
        assert result == "fallback"
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_timeout(self):
        """测试超时错误"""
        @handle_controller_errors(default_return="fallback")
        async def test_func(self):
            raise httpx.TimeoutException("Request timeout")
        
        mock_obj = Mock(logger=Mock())
        result = await test_func(mock_obj)
        assert result == "fallback"
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_cancelled(self):
        """测试任务取消"""
        @handle_controller_errors(default_return="fallback", raise_on_error=False)
        async def test_func(self):
            raise asyncio.CancelledError()
        
        mock_obj = Mock(logger=Mock())
        with pytest.raises(asyncio.CancelledError):
            await test_func(mock_obj)
    
    @pytest.mark.asyncio
    async def test_handle_controller_errors_raise_on_error(self):
        """测试raise_on_error参数"""
        @handle_controller_errors(default_return="fallback", raise_on_error=True)
        async def test_func(self):
            raise ConnectionError("Connection failed")
        
        mock_obj = Mock(logger=Mock())
        with pytest.raises(ConnectionError):
            await test_func(mock_obj)


class TestHandleOperationErrors:
    """操作错误处理装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_handle_operation_errors_async(self):
        """测试异步操作"""
        @handle_operation_errors(default_return=False)
        async def test_func(self):
            return True
        
        mock_obj = Mock(logger=Mock())
        result = await test_func(mock_obj)
        assert result is True
    
    def test_handle_operation_errors_sync(self):
        """测试同步操作"""
        @handle_operation_errors(default_return=False)
        def test_func(self):
            return True
        
        mock_obj = Mock(logger=Mock())
        result = test_func(mock_obj)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_handle_operation_errors_exception(self):
        """测试异常处理"""
        @handle_operation_errors(default_return=False)
        async def test_func(self):
            raise ValueError("Test error")
        
        mock_obj = Mock(logger=Mock())
        result = await test_func(mock_obj)
        assert result is False


class TestSafeExecute:
    """安全执行装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_safe_execute_async_success(self):
        """测试异步成功执行"""
        @safe_execute()
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_safe_execute_async_error(self):
        """测试异步错误处理"""
        @safe_execute()
        async def test_func():
            raise ValueError("Test error")
        
        result = await test_func()
        assert result is None
    
    def test_safe_execute_sync_success(self):
        """测试同步成功执行"""
        @safe_execute()
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_safe_execute_sync_error(self):
        """测试同步错误处理"""
        @safe_execute()
        def test_func():
            raise ValueError("Test error")
        
        result = test_func()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_safe_execute_custom_logger(self):
        """测试自定义logger"""
        custom_logger = Mock()
        
        @safe_execute(logger=custom_logger)
        async def test_func():
            raise ValueError("Test error")
        
        result = await test_func()
        custom_logger.debug.assert_called()


class TestRetry:
    """重试装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """测试第一次尝试成功"""
        @retry(max_attempts=3, delay=0.1)
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """测试第二次尝试成功"""
        attempts = [0]
        
        @retry(max_attempts=3, delay=0.1)
        async def test_func():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("Temporary error")
            return "success"
        
        result = await test_func()
        assert result == "success"
        assert attempts[0] == 2
    
    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self):
        """测试超过最大尝试次数"""
        @retry(max_attempts=2, delay=0.1)
        async def test_func():
            raise ValueError("Persistent error")
        
        with pytest.raises(ValueError, match="Persistent error"):
            await test_func()
    
    @pytest.mark.asyncio
    async def test_retry_backoff(self):
        """测试指数退避"""
        call_times = []
        
        @retry(max_attempts=3, delay=0.1, backoff_factor=2.0)
        async def test_func():
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise ValueError("Temporary error")
            return "success"
        
        await test_func()
        assert len(call_times) == 3
        # 验证退避时间
        assert call_times[1] - call_times[0] >= 0.1
        assert call_times[2] - call_times[1] >= 0.2
    
    @pytest.mark.asyncio
    async def test_retry_sync_function(self):
        """测试同步函数重试"""
        attempts = [0]
        
        @retry(max_attempts=3, delay=0.1)
        def test_func():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("Temporary error")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert attempts[0] == 2


class TestLogExecutionTime:
    """执行时间记录装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_log_execution_time_async(self):
        """测试异步函数执行时间记录"""
        mock_logger = Mock()
        
        @log_execution_time(logger=mock_logger)
        async def test_func():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await test_func()
        assert result == "success"
        mock_logger.debug.assert_called()
        assert "executed in" in str(mock_logger.debug.call_args)
    
    def test_log_execution_time_sync(self):
        """测试同步函数执行时间记录"""
        mock_logger = Mock()
        
        @log_execution_time(logger=mock_logger)
        def test_func():
            import time
            time.sleep(0.05)
            return "success"
        
        result = test_func()
        assert result == "success"
        mock_logger.debug.assert_called()
    
    @pytest.mark.asyncio
    async def test_log_execution_time_with_error(self):
        """测试错误时的执行时间记录"""
        mock_logger = Mock()
        
        @log_execution_time(logger=mock_logger)
        async def test_func():
            await asyncio.sleep(0.05)
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await test_func()
        mock_logger.error.assert_called()
        assert "failed after" in str(mock_logger.error.call_args)


class TestErrorClasses:
    """异常类测试"""
    
    def test_xianyu_error_basic(self):
        """测试基础异常类"""
        error = XianyuError("Test error")
        assert error.message == "Test error"
        assert error.details == {}
    
    def test_xianyu_error_with_details(self):
        """测试带details的异常"""
        details = {"key": "value", "number": 42}
        error = XianyuError("Test error", details=details)
        assert error.message == "Test error"
        assert error.details == details
    
    def test_xianyu_error_to_dict(self):
        """测试to_dict方法"""
        details = {"key": "value"}
        error = XianyuError("Test error", details=details)
        error_dict = error.to_dict()
        assert error_dict["message"] == "Test error"
        assert error_dict["details"] == details
        assert error_dict["type"] == "XianyuError"
    
    def test_config_error(self):
        """测试配置错误"""
        error = ConfigError("Config is invalid")
        assert isinstance(error, XianyuError)
        assert error.message == "Config is invalid"
    
    def test_browser_error(self):
        """测试浏览器错误"""
        error = BrowserError("Browser disconnected")
        assert isinstance(error, XianyuError)
    
    def test_ai_error(self):
        """测试AI错误"""
        error = AIError("AI service unavailable")
        assert isinstance(error, XianyuError)
    
    def test_media_error(self):
        """测试媒体错误"""
        error = MediaError("Image processing failed")
        assert isinstance(error, XianyuError)
    
    def test_account_error(self):
        """测试账号错误"""
        error = AccountError("Account locked")
        assert isinstance(error, XianyuError)
    
    def test_database_error(self):
        """测试数据库错误"""
        error = DatabaseError("Database connection failed")
        assert isinstance(error, XianyuError)


class TestHandleErrors:
    """通用错误处理装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_handle_errors_async(self):
        """测试异步错误处理"""
        @handle_errors(default_return="fallback")
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_handle_errors_async_with_exception(self):
        """测试异步异常处理"""
        @handle_errors(default_return="fallback")
        async def test_func():
            raise ValueError("Test error")
        
        result = await test_func()
        assert result == "fallback"
    
    def test_handle_errors_sync(self):
        """测试同步错误处理"""
        @handle_errors(default_return="fallback")
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_handle_errors_sync_with_exception(self):
        """测试同步异常处理"""
        @handle_errors(default_return="fallback")
        def test_func():
            raise ValueError("Test error")
        
        result = test_func()
        assert result == "fallback"
    
    @pytest.mark.asyncio
    async def test_handle_errors_specific_exception(self):
        """测试特定异常类型"""
        @handle_errors(exceptions=(ValueError,), default_return="value_error")
        async def test_func():
            raise ValueError("Test error")
        
        result = await test_func()
        assert result == "value_error"
    
    @pytest.mark.asyncio
    async def test_handle_errors_raise_on_error(self):
        """测试raise_on_error参数"""
        @handle_errors(raise_on_error=True)
        async def test_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await test_func()
