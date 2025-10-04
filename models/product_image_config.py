from odoo import api, fields, models


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
    google_api_key = fields.Char('Google API Key')
    google_search_engine_id = fields.Char('Google Search Engine ID')
    
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