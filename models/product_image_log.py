from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class ProductImageLog(models.Model):
    _name = 'product.image.log'
    _description = 'Product Image Processing Log'
    _order = 'create_date desc'
    _rec_name = 'product_name'

    product_id = fields.Many2one('product.template', string='Product', ondelete='cascade')
    product_name = fields.Char('Product Name', required=True)
    product_sku = fields.Char('SKU')
    product_ean = fields.Char('EAN')
    
    operation_type = fields.Selection([
        ('fetch', 'Image Fetch'),
        ('update', 'Image Update'),
        ('skip', 'Skipped'),
        ('error', 'Error'),
        ('dedup', 'Deduplication'),
    ], string='Operation Type', required=True)
    
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('warning', 'Warning'),
        ('info', 'Information'),
    ], string='Status', required=True)
    
    message = fields.Text('Message')
    error_details = fields.Text('Error Details')
    
    # Image Information
    image_source = fields.Selection([
        ('amazon', 'Amazon PA-API'),
        ('google', 'Google Images'),
        ('bing', 'Bing Images'),
        ('manual', 'Manual Upload'),
    ], string='Image Source')
    
    image_url = fields.Char('Source Image URL')
    image_size = fields.Char('Image Size (WxH)')
    image_format = fields.Char('Image Format')
    file_size_kb = fields.Float('File Size (KB)')
    
    # Processing Details
    processing_time = fields.Float('Processing Time (seconds)')
    batch_id = fields.Char('Batch ID')
    job_type = fields.Selection([
        ('daily', 'Daily Scan'),
        ('backfill', 'Backfill'),
        ('manual', 'Manual'),
    ], string='Job Type')
    
    # System fields
    create_date = fields.Datetime('Created On', readonly=True)
    
    @api.model
    def log_operation(self, product_id, operation_type, status, message, **kwargs):
        """Helper method to create log entries"""
        product = self.env['product.template'].browse(product_id) if product_id else None
        
        vals = {
            'product_id': product_id,
            'product_name': product.name if product else kwargs.get('product_name', 'Unknown'),
            'product_sku': product.default_code if product else kwargs.get('product_sku'),
            'product_ean': product.barcode if product else kwargs.get('product_ean'),
            'operation_type': operation_type,
            'status': status,
            'message': message,
        }
        
        # Add optional fields
        for field in ['error_details', 'image_source', 'image_url', 'image_size', 
                     'image_format', 'file_size_kb', 'processing_time', 'batch_id', 'job_type']:
            if field in kwargs:
                vals[field] = kwargs[field]
        
        return self.create(vals)
    
    @api.model
    def cleanup_old_logs(self, retention_days=30):
        """Clean up logs older than retention_days"""
        cutoff_date = fields.Datetime.now() - fields.timedelta(days=retention_days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info(f"Cleaned up {count} old log entries")
        return count
    
    def action_retry_failed(self):
        """Retry failed operations"""
        failed_logs = self.filtered(lambda l: l.status == 'failed' and l.product_id)
        if failed_logs:
            product_ids = failed_logs.mapped('product_id.id')
            ImageFetcher = self.env['product.image.fetcher']
            ImageFetcher.process_products(product_ids, force_update=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Retry initiated for {len(failed_logs)} failed operations.',
                'type': 'info',
                'sticky': False,
            }
        }