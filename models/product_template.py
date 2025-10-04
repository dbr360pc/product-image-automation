from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Image automation fields
    image_auto_fetch_enabled = fields.Boolean('Auto-fetch Images', default=True)
    image_last_fetch_date = fields.Datetime('Last Image Fetch Date')
    image_fetch_attempts = fields.Integer('Image Fetch Attempts', default=0)
    image_fetch_source = fields.Selection([
        ('amazon', 'Amazon PA-API'),
        ('google', 'Google Images'),
        ('bing', 'Bing Images'),
        ('manual', 'Manual Upload'),
    ], string='Image Source')
    
    image_quality_score = fields.Float('Image Quality Score', help='Internal quality score for image')
    
    # Enhanced search fields for better matching
    manufacturer_part_number = fields.Char('Manufacturer Part Number (MPN)')
    upc_code = fields.Char('UPC Code')
    
    def action_fetch_images_manual(self):
        """Manual action to fetch images for selected products"""
        ImageFetcher = self.env['product.image.fetcher']
        ImageFetcher.process_products(self.ids, force_update=True, job_type='manual')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Image fetch initiated for {len(self)} products. Check logs for progress.',
                'type': 'info',
                'sticky': False,
            }
        }
    
    def has_product_image(self):
        """Check if product has at least one image"""
        self.ensure_one()
        return bool(self.image_1920)
    
    def get_search_keywords(self):
        """Get search keywords for image fetching"""
        self.ensure_one()
        keywords = []
        
        # Add product name
        if self.name:
            keywords.append(self.name.strip())
        
        # Add brand/manufacturer if available
        if hasattr(self, 'product_brand_id') and self.product_brand_id:
            keywords.append(self.product_brand_id.name)
        
        # Add category
        if self.categ_id and self.categ_id.name != 'All':
            keywords.append(self.categ_id.name)
        
        return ' '.join(keywords)
    
    def get_product_identifiers(self):
        """Get all available product identifiers for matching"""
        self.ensure_one()
        identifiers = {}
        
        if self.default_code:  # SKU
            identifiers['sku'] = self.default_code
        if self.barcode:  # EAN
            identifiers['ean'] = self.barcode
        if self.upc_code:
            identifiers['upc'] = self.upc_code
        if self.manufacturer_part_number:
            identifiers['mpn'] = self.manufacturer_part_number
        
        return identifiers