"""
服务接口单元测试
Service Interface Tests
"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.modules.interfaces import (
    IListingService, IContentService, IMediaService,
    IOperationsService, IAnalyticsService, IAccountsService,
    ISchedulerService, IMonitorService
)


class TestIListingService:
    """IListingService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IListingService()
    
    @pytest.mark.asyncio
    async def test_create_listing_method_exists(self):
        """测试create_listing方法存在"""
        assert hasattr(IListingService, 'create_listing')
    
    @pytest.mark.asyncio
    async def test_batch_create_listings_method_exists(self):
        """测试batch_create_listings方法存在"""
        assert hasattr(IListingService, 'batch_create_listings')
    
    def test_all_methods_abstract(self):
        """测试所有方法都是抽象的"""
        import inspect
        methods = [
            'create_listing', 'batch_create_listings', 'update_listing',
            'delete_listing', 'get_my_listings'
        ]
        for method in methods:
            method_obj = getattr(IListingService, method)
            assert hasattr(method_obj, '__isabstractmethod__'), f"{method} should be abstract"


class TestIContentService:
    """IContentService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IContentService()
    
    def test_generate_title_method_exists(self):
        """测试generate_title方法存在"""
        assert hasattr(IContentService, 'generate_title')
    
    def test_generate_description_method_exists(self):
        """测试generate_description方法存在"""
        assert hasattr(IContentService, 'generate_description')


class TestIMediaService:
    """IMediaService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IMediaService()
    
    def test_resize_image_method_exists(self):
        """测试resize_image方法存在"""
        assert hasattr(IMediaService, 'resize_image_for_xianyu')
    
    def test_batch_process_method_exists(self):
        """测试batch_process方法存在"""
        assert hasattr(IMediaService, 'batch_process_images')


class TestIOperationsService:
    """IOperationsService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IOperationsService()
    
    @pytest.mark.asyncio
    async def test_batch_polish_method_exists(self):
        """测试batch_polish方法存在"""
        assert hasattr(IOperationsService, 'batch_polish')
    
    @pytest.mark.asyncio
    async def test_batch_update_price_method_exists(self):
        """测试batch_update_price方法存在"""
        assert hasattr(IOperationsService, 'batch_update_price')


class TestIAnalyticsService:
    """IAnalyticsService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IAnalyticsService()
    
    @pytest.mark.asyncio
    async def test_log_operation_method_exists(self):
        """测试log_operation方法存在"""
        assert hasattr(IAnalyticsService, 'log_operation')
    
    @pytest.mark.asyncio
    async def test_get_dashboard_stats_method_exists(self):
        """测试get_dashboard_stats方法存在"""
        assert hasattr(IAnalyticsService, 'get_dashboard_stats')
    
    @pytest.mark.asyncio
    async def test_get_trend_data_method_exists(self):
        """测试get_trend_data方法存在"""
        assert hasattr(IAnalyticsService, 'get_trend_data')


class TestIAccountsService:
    """IAccountsService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IAccountsService()
    
    def test_get_accounts_method_exists(self):
        """测试get_accounts方法存在"""
        assert hasattr(IAccountsService, 'get_accounts')
    
    def test_get_cookie_method_exists(self):
        """测试get_cookie方法存在"""
        assert hasattr(IAccountsService, 'get_cookie')
    
    def test_update_account_stats_method_exists(self):
        """测试update_account_stats方法存在"""
        assert hasattr(IAccountsService, 'update_account_stats')


class TestISchedulerService:
    """ISchedulerService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            ISchedulerService()
    
    @pytest.mark.asyncio
    async def test_start_method_exists(self):
        """测试start方法存在"""
        assert hasattr(ISchedulerService, 'start')
    
    @pytest.mark.asyncio
    async def test_stop_method_exists(self):
        """测试stop方法存在"""
        assert hasattr(ISchedulerService, 'stop')
    
    def test_create_task_method_exists(self):
        """测试create_task方法存在"""
        assert hasattr(ISchedulerService, 'create_task')


class TestIMonitorService:
    """IMonitorService接口测试"""
    
    def test_interface_requires_implementation(self):
        """测试接口必须被实现"""
        with pytest.raises(TypeError):
            IMonitorService()
    
    @pytest.mark.asyncio
    async def test_raise_alert_method_exists(self):
        """测试raise_alert方法存在"""
        assert hasattr(IMonitorService, 'raise_alert')
    
    @pytest.mark.asyncio
    async def test_resolve_alert_method_exists(self):
        """测试resolve_alert方法存在"""
        assert hasattr(IMonitorService, 'resolve_alert')
    
    @pytest.mark.asyncio
    async def test_get_active_alerts_method_exists(self):
        """测试get_active_alerts方法存在"""
        assert hasattr(IMonitorService, 'get_active_alerts')


class TestInterfaceCompliance:
    """接口合规性测试"""
    
    def test_all_interfaces_have_documentation(self):
        """测试所有接口都有文档"""
        interfaces = [
            IListingService, IContentService, IMediaService,
            IOperationsService, IAnalyticsService, IAccountsService,
            ISchedulerService, IMonitorService
        ]
        
        for interface in interfaces:
            doc = interface.__doc__
            assert doc is not None, f"{interface.__name__} should have docstring"
            assert len(doc) > 10, f"{interface.__name__} docstring should be meaningful"
    
    def test_all_methods_have_documentation(self):
        """测试所有方法都有文档"""
        interfaces = [
            IListingService, IContentService, IMediaService,
            IOperationsService, IAnalyticsService, IAccountsService,
            ISchedulerService, IMonitorService
        ]
        
        for interface in interfaces:
            for name in dir(interface):
                if not name.startswith('_') and callable(getattr(interface, name)):
                    method = getattr(interface, name)
                    if hasattr(method, '__isabstractmethod__'):
                        doc = method.__doc__
                        assert doc is not None, f"{interface.__name__}.{name} should have docstring"
                        assert 'Args:' in doc or 'Returns:' in doc, \
                            f"{interface.__name__}.{name} docstring should document args/returns"


class MockListingService(IListingService):
    """Mock商品上架服务（用于测试）"""
    
    async def create_listing(self, listing, account_id=None):
        return Mock(success=True, product_id="test_id", product_url="test_url")
    
    async def batch_create_listings(self, listings, account_id=None, delay_range=(5, 10)):
        return [Mock(success=True) for _ in listings]
    
    async def update_listing(self, product_id, updates):
        return True
    
    async def delete_listing(self, product_id):
        return True
    
    async def get_my_listings(self, limit=50):
        return []


class TestMockImplementation:
    """Mock实现测试"""
    
    @pytest.mark.asyncio
    async def test_mock_listing_service_implements_interface(self):
        """测试Mock服务实现接口"""
        service = MockListingService()
        assert isinstance(service, IListingService)
    
    @pytest.mark.asyncio
    async def test_mock_service_methods_work(self, sample_listing_data):
        """测试Mock服务方法可工作"""
        service = MockListingService()
        
        from src.modules.listing.models import Listing
        listing = Listing(**sample_listing_data)
        
        result = await service.create_listing(listing)
        assert result.success is True
        assert result.product_id == "test_id"
        
        results = await service.batch_create_listings([listing])
        assert len(results) == 1
        assert all(r.success for r in results)
