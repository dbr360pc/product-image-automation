{
    'name': 'Product Image Automation',
    'version': '16.0.1.0.0',
    'summary': 'Automated product image fetching and management',
    'description': '''
        Daily automation for Odoo 16 that ensures every product has at least one image.
        
        Features:
        - Daily cron job to scan all product.template records
        - Match products by SKU/EAN/UPC/MPN/name
        - Fetch images from Amazon PA-API with fallback options
        - Image quality control (min 800px, no watermarks)
        - Deduplication and proper linking in Odoo
        - Idempotent operations with force update option
        - Configurable settings and comprehensive logging
        - Backfill job for existing catalog
    ''',
    'author': 'trionica',
    'website': 'https://trionica.ec/',
    'category': 'Sales',
    'depends': ['product', 'base_automation'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/product_image_config_views.xml',
        'views/product_image_log_views.xml',
        'views/product_template_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}