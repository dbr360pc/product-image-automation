from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductImageConfig(models.Model):
    _name = 'product.image.config'
    _description = 'Product Image Automation Configuration'
    _rec_name = 'name'

    name = fields.Char('Configuration Name', default='Default Configuration', required=True)
    active = fields.Boolean('Active', default=True)
    
    # Image Sources Configuration
    use_amazon_api = fields.Boolean('Use Amazon Product Advertising API', default=True)
    amazon_access_key = fields.Char('Amazon Access Key')
    amazon_secret_key = fields.Char('Amazon Secret Key')
    amazon_partner_tag = fields.Char('Amazon Partner Tag')
    amazon_marketplace = fields.Selection([
        ('US', 'United States'),
        ('CA', 'Canada'),
        ('UK', 'United Kingdom'),
        ('DE', 'Germany'),
        ('FR', 'France'),
        ('IT', 'Italy'),
        ('ES', 'Spain'),
        ('JP', 'Japan'),
    ], default='US', string='Amazon Marketplace')
    
    use_google_images = fields.Boolean('Use Google Images Fallback', default=True)
    google_api_keys = fields.Text('Google API Keys', help='Enter multiple API keys, one per line')
    google_search_engine_id = fields.Char('Google Search Engine ID')
    current_api_key_index = fields.Integer('Current API Key Index', default=0)
    api_keys_count = fields.Integer('Number of Available Keys', compute='_compute_api_keys_count', store=False)
    
    use_bing_images = fields.Boolean('Use Bing Images Fallback', default=False)
    bing_api_key = fields.Char('Bing API Key')
    
    # Image Quality Settings
    min_image_width = fields.Integer('Minimum Image Width (px)', default=800)
    min_image_height = fields.Integer('Minimum Image Height (px)', default=600)
    max_image_size_mb = fields.Float('Maximum Image Size (MB)', default=5.0)
    preferred_formats = fields.Selection([
        ('jpg', 'JPEG only'),
        ('png', 'PNG only'),
        ('jpg_png', 'JPEG and PNG'),
        ('all', 'All formats'),
    ], default='jpg_png', string='Preferred Image Formats')
    
    # Rate Limiting
    requests_per_minute = fields.Integer('Requests Per Minute', default=60)
    daily_requests_limit = fields.Integer('Daily Requests Limit', default=1000)
    
    # Processing Settings
    batch_size = fields.Integer('Batch Size for Processing', default=50)
    enable_deduplication = fields.Boolean('Enable Image Deduplication', default=True)
    skip_products_with_images = fields.Boolean('Skip Products Already Having Images', default=True)
    force_update_mode = fields.Boolean('Force Update Mode (Re-download)', default=False)
    
    # Test Mode
    test_mode = fields.Boolean('Test Mode (No actual downloads)', default=False)
    test_product_limit = fields.Integer('Test Product Limit', default=10)
    
    # Logging
    enable_detailed_logging = fields.Boolean('Enable Detailed Logging', default=True)
    log_retention_days = fields.Integer('Log Retention (Days)', default=30)
    
    # Cron Configuration
    cron_active = fields.Boolean('Enable Daily Cron Job', default=True)
    cron_hour = fields.Integer('Cron Hour (24h format)', default=2)
    cron_minute = fields.Integer('Cron Minute', default=0)
    
    @api.model
    def get_active_config(self):
        """Get the active configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            # Create default configuration
            config = self.create({
                'name': 'Default Configuration',
                'active': True,
            })
        return config
    
    @api.depends('google_api_keys')
    def _compute_api_keys_count(self):
        """Compute the number of available API keys"""
        for record in self:
            record.api_keys_count = len(record.get_available_google_api_keys())
    
    def migrate_legacy_api_keys(self):
        """Helper method to migrate from old 3-field structure to new dynamic structure"""
        self.ensure_one()
        if self.google_api_keys:
            return  # Already using new structure
        
        # Check if we have old field values (this would only work if fields still exist)
        legacy_keys = []
        for field_name in ['google_api_key', 'google_api_key_2', 'google_api_key_3']:
            if hasattr(self, field_name):
                value = getattr(self, field_name, None)
                if value:
                    legacy_keys.append(value)
        
        if legacy_keys:
            self.google_api_keys = '\n'.join(legacy_keys)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Migrated {len(legacy_keys)} API keys to new format',
                    'type': 'success',
                    'sticky': False,
                }
            }
    
    @api.constrains('google_api_keys')
    def _check_google_api_keys_format(self):
        """Validate Google API keys format"""
        for record in self:
            if not record.google_api_keys or not record.use_google_images:
                continue
            
            keys = record.get_available_google_api_keys()
            if not keys:
                raise ValidationError(_("At least one valid Google API key is required when Google Images is enabled."))
            
            # Basic validation for Google API key format
            for key in keys:
                if not key.startswith('AIza') or len(key) < 35:
                    raise ValidationError(_("Invalid Google API key format: '%s'. Google API keys should start with 'AIza' and be at least 35 characters long.") % key[:20] + "...")
    
    def get_available_google_api_keys(self):
        """Get list of available Google API keys"""
        if not self.google_api_keys:
            return []
        
        # Parse keys from text field (one per line)
        keys = []
        for line in self.google_api_keys.strip().split('\n'):
            key = line.strip()
            if key and not key.startswith('#'):  # Skip empty lines and comments
                keys.append(key)
        return keys
    
    def get_current_google_api_key(self):
        """Get the current Google API key for use"""
        keys = self.get_available_google_api_keys()
        if not keys:
            return None
        
        # Ensure index is within bounds
        if self.current_api_key_index >= len(keys):
            self.current_api_key_index = 0
        
        return keys[self.current_api_key_index]
    
    def rotate_google_api_key(self, reason="Rate limit"):
        """Rotate to the next available Google API key"""
        keys = self.get_available_google_api_keys()
        if len(keys) <= 1:
            return False  # No other keys available
        
        old_index = self.current_api_key_index
        self.current_api_key_index = (self.current_api_key_index + 1) % len(keys)
        
        # Log the rotation
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"API Key Rotation - Reason: {reason}, Index: {old_index} -> {self.current_api_key_index}, "
                    f"Key: ...{keys[self.current_api_key_index][-8:] if keys[self.current_api_key_index] else 'None'}")
        
        return True
    
    def reset_api_key_rotation(self):
        """Reset API key rotation to first key"""
        self.current_api_key_index = 0
    
    def action_test_configuration(self):
        """Test the configuration by fetching a sample image"""
        self.ensure_one()
        # This will be implemented in the service
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Configuration test initiated. Check logs for results.',
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_run_backfill(self):
        """Run backfill job to process existing products"""
        self.ensure_one()
        ImageFetcher = self.env['product.image.fetcher']
        ImageFetcher.run_backfill_job()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Backfill job started. Check logs for progress.',
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_rotate_api_key(self):
        """Manually rotate to next Google API key"""
        self.ensure_one()
        if self.rotate_google_api_key("Manual rotation"):
            keys_count = len(self.get_available_google_api_keys())
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Rotated to API Key #{self.current_api_key_index + 1} of {keys_count}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No additional API keys available for rotation',
                    'type': 'warning',
                    'sticky': False,
                }
            }
    
    def action_reset_api_key_rotation(self):
        """Reset API key rotation to first key"""
        self.ensure_one()
        self.reset_api_key_rotation()
        keys_count = len(self.get_available_google_api_keys())
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Reset to API Key #1 of {keys_count} available keys',
                'type': 'success',
                'sticky': False,
            }
        }