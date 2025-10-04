import logging
from odoo.tests.common import TransactionCase
from unittest.mock import patch, MagicMock

_logger = logging.getLogger(__name__)


class TestProductImageAutomation(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test product
        self.test_product = self.env['product.template'].create({
            'name': 'Test Product for Image Fetching',
            'default_code': 'TEST-SKU-001',
            'barcode': '1234567890123',
            'upc_code': '123456789012',
            'manufacturer_part_number': 'MPN-001',
            'image_auto_fetch_enabled': True,
        })
        
        # Create test configuration
        self.test_config = self.env['product.image.config'].create({
            'name': 'Test Configuration',
            'active': True,
            'use_google_images': True,
            'google_api_key': 'test_api_key',
            'google_search_engine_id': 'test_engine_id',
            'test_mode': True,
            'test_product_limit': 1,
            'min_image_width': 400,  # Lower for testing
            'min_image_height': 300,
        })
    
    def test_product_identifiers(self):
        """Test that product identifiers are correctly extracted"""
        identifiers = self.test_product.get_product_identifiers()
        
        self.assertEqual(identifiers['sku'], 'TEST-SKU-001')
        self.assertEqual(identifiers['ean'], '1234567890123')
        self.assertEqual(identifiers['upc'], '123456789012')
        self.assertEqual(identifiers['mpn'], 'MPN-001')
    
    def test_search_keywords(self):
        """Test that search keywords are properly generated"""
        keywords = self.test_product.get_search_keywords()
        
        self.assertIn('Test Product for Image Fetching', keywords)
    
    def test_has_product_image(self):
        """Test image detection functionality"""
        # Initially should have no image
        self.assertFalse(self.test_product.has_product_image())
        
        # Add a test image (base64 encoded 1x1 pixel)
        test_image = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        
        import base64
        self.test_product.image_1920 = base64.b64encode(test_image)
        
        # Now should detect image
        self.assertTrue(self.test_product.has_product_image())
    
    def test_configuration_validation(self):
        """Test configuration validation methods"""
        fetcher = self.env['product.image.fetcher']
        
        # Test Google config validation
        self.assertTrue(fetcher._has_google_config(self.test_config))
        
        # Test Amazon config validation (should fail without credentials)
        self.assertFalse(fetcher._has_amazon_config(self.test_config))
    
    def test_get_products_needing_images(self):
        """Test finding products that need images"""
        fetcher = self.env['product.image.fetcher']
        
        products_needing_images = fetcher._get_products_needing_images(self.test_config)
        
        # Should include our test product
        self.assertIn(self.test_product, products_needing_images)
    
    def test_log_creation(self):
        """Test log entry creation"""
        log_entry = self.env['product.image.log'].log_operation(
            self.test_product.id,
            'fetch',
            'success',
            'Test log message',
            image_source='google',
            processing_time=1.5
        )
        
        self.assertEqual(log_entry.product_id, self.test_product)
        self.assertEqual(log_entry.operation_type, 'fetch')
        self.assertEqual(log_entry.status, 'success')
        self.assertEqual(log_entry.message, 'Test log message')
        self.assertEqual(log_entry.image_source, 'google')
        self.assertEqual(log_entry.processing_time, 1.5)
    
    @patch('requests.Session.get')
    def test_image_download_validation(self, mock_get):
        """Test image download and validation"""
        # Mock a successful image download
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': '50000'}  # 50KB
        
        # Create a simple test image (1x1 pixel PNG)
        import io
        from PIL import Image
        
        test_image = Image.new('RGB', (800, 600), color='red')
        img_bytes = io.BytesIO()
        test_image.save(img_bytes, format='PNG')
        mock_response.content = img_bytes.getvalue()
        
        mock_get.return_value = mock_response
        
        fetcher = self.env['product.image.fetcher']
        
        image_data, image_info = fetcher._download_and_validate_image(
            'http://test.com/image.png',
            self.test_config,
            'test'
        )
        
        # Should successfully download and validate
        self.assertIsNotNone(image_data)
        self.assertEqual(image_info['image_size'], '800x600')
        self.assertEqual(image_info['image_format'], 'png')
    
    def test_manual_fetch_action(self):
        """Test manual image fetch action"""
        result = self.test_product.action_fetch_images_manual()
        
        # Should return a notification action
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
    
    def test_config_get_active(self):
        """Test getting active configuration"""
        active_config = self.env['product.image.config'].get_active_config()
        
        # Should return our test configuration (since it's active)
        self.assertEqual(active_config, self.test_config)