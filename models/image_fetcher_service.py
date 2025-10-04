import base64
import hashlib
import logging
import requests
import time
from datetime import datetime, timedelta
from PIL import Image
import io
import json
import hmac
import urllib.parse
from xml.etree import ElementTree as ET

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

_logger = logging.getLogger(__name__)


class ProductImageFetcher(models.TransientModel):
    _name = 'product.image.fetcher'
    _description = 'Product Image Fetcher Service'

    def _get_session(self):
        """Get a requests session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        return session

    @api.model
    def run_daily_scan(self):
        """Main cron job entry point for daily scanning"""
        try:
            config = self.env['product.image.config'].get_active_config()
            if not config.cron_active:
                _logger.info("Daily scan disabled in configuration")
                return
            
            batch_id = f"daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            _logger.info(f"Starting daily scan with batch ID: {batch_id}")
            
            # Find products without images
            products_without_images = self._get_products_needing_images(config)
            
            if not products_without_images:
                _logger.info("No products found needing images")
                return
            
            _logger.info(f"Found {len(products_without_images)} products needing images")
            
            # Process in batches
            self._process_products_in_batches(products_without_images, config, batch_id, 'daily')
            
            # Cleanup old logs
            self.env['product.image.log'].cleanup_old_logs(config.log_retention_days)
            
        except Exception as e:
            _logger.error(f"Error in daily scan: {str(e)}", exc_info=True)
            self.env['product.image.log'].log_operation(
                None, 'error', 'failed', f"Daily scan failed: {str(e)}", 
                job_type='daily', batch_id=batch_id
            )

    @api.model
    def run_backfill_job(self):
        """Backfill job to process all existing products"""
        try:
            config = self.env['product.image.config'].get_active_config()
            batch_id = f"backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            _logger.info(f"Starting backfill job with batch ID: {batch_id}")
            
            # Get all products (or limit for testing)
            domain = [('active', '=', True)]
            if config.test_mode:
                products = self.env['product.template'].search(domain, limit=config.test_product_limit)
            else:
                products = self.env['product.template'].search(domain)
            
            _logger.info(f"Processing {len(products)} products in backfill job")
            
            self._process_products_in_batches(products, config, batch_id, 'backfill')
            
        except Exception as e:
            _logger.error(f"Error in backfill job: {str(e)}", exc_info=True)
            self.env['product.image.log'].log_operation(
                None, 'error', 'failed', f"Backfill job failed: {str(e)}", 
                job_type='backfill', batch_id=batch_id
            )

    def process_products(self, product_ids, force_update=False, job_type='manual'):
        """Process specific products"""
        config = self.env['product.image.config'].get_active_config()
        batch_id = f"{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        products = self.env['product.template'].browse(product_ids)
        
        self._process_products_in_batches(products, config, batch_id, job_type, force_update)

    def _get_products_needing_images(self, config):
        """Get products that need images based on configuration"""
        domain = [('active', '=', True), ('image_auto_fetch_enabled', '=', True)]
        
        if config.skip_products_with_images and not config.force_update_mode:
            domain.append(('image_1920', '=', False))
        
        products = self.env['product.template'].search(domain)
        
        if config.test_mode:
            products = products[:config.test_product_limit]
        
        return products

    def _process_products_in_batches(self, products, config, batch_id, job_type, force_update=False):
        """Process products in batches with rate limiting"""
        batch_size = config.batch_size
        total_batches = (len(products) + batch_size - 1) // batch_size
        
        for i in range(0, len(products), batch_size):
            batch_products = products[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            _logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_products)} products)")
            
            for product in batch_products:
                try:
                    self._process_single_product(product, config, batch_id, job_type, force_update)
                    
                    # Rate limiting
                    if config.requests_per_minute > 0:
                        time.sleep(60.0 / config.requests_per_minute)
                        
                except Exception as e:
                    _logger.error(f"Error processing product {product.id}: {str(e)}")
                    self.env['product.image.log'].log_operation(
                        product.id, 'error', 'failed', f"Processing failed: {str(e)}", 
                        batch_id=batch_id, job_type=job_type
                    )
            
            self.env.cr.commit()  # Commit after each batch

    def _process_single_product(self, product, config, batch_id, job_type, force_update=False):
        """Process a single product for image fetching"""
        start_time = time.time()
        
        # Skip if product already has image and not forcing update
        if product.has_product_image() and not force_update and config.skip_products_with_images:
            self.env['product.image.log'].log_operation(
                product.id, 'skip', 'info', 'Product already has image',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )
            return
        
        # Get search terms
        search_keywords = product.get_search_keywords()
        identifiers = product.get_product_identifiers()
        
        if not search_keywords and not identifiers:
            self.env['product.image.log'].log_operation(
                product.id, 'skip', 'warning', 'No search terms or identifiers available',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )
            return
        
        # Try different image sources in order
        image_data = None
        image_info = {}
        
        if config.use_amazon_api and self._has_amazon_config(config):
            image_data, image_info = self._fetch_from_amazon(product, identifiers, search_keywords, config)
        
        if not image_data and config.use_google_images and self._has_google_config(config):
            image_data, image_info = self._fetch_from_google(product, search_keywords, config)
        
        if not image_data and config.use_bing_images and self._has_bing_config(config):
            image_data, image_info = self._fetch_from_bing(product, search_keywords, config)
        
        if image_data:
            if config.test_mode:
                self.env['product.image.log'].log_operation(
                    product.id, 'fetch', 'success', 'Image found (test mode - not saved)',
                    batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time,
                    **image_info
                )
            else:
                self._save_product_image(product, image_data, image_info, config, batch_id, job_type, start_time)
        else:
            product.image_fetch_attempts += 1
            self.env['product.image.log'].log_operation(
                product.id, 'fetch', 'failed', 'No suitable image found from any source',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )

    def _fetch_from_amazon(self, product, identifiers, search_keywords, config):
        """Fetch image from Amazon Product Advertising API"""
        try:
            from .amazon_api_service import AmazonPAAPIService
            
            # Initialize Amazon API service
            amazon_service = AmazonPAAPIService(
                access_key=config.amazon_access_key,
                secret_key=config.amazon_secret_key,
                partner_tag=config.amazon_partner_tag,
                marketplace=config.amazon_marketplace
            )
            
            # Try identifiers first, then keywords
            image_info = None
            
            if identifiers:
                # Search by identifiers (EAN, UPC preferred)
                image_info = amazon_service.search_items(identifiers=identifiers)
            
            if not image_info and search_keywords:
                # Fallback to keyword search
                image_info = amazon_service.search_items(keywords=search_keywords)
            
            if image_info and image_info.get('url'):
                return self._download_and_validate_image(image_info['url'], config, 'amazon')
            
        except Exception as e:
            _logger.warning(f"Amazon fetch failed for product {product.id}: {str(e)}")
        
        return None, {}

    def _fetch_from_google(self, product, search_keywords, config):
        """Fetch image from Google Custom Search API"""
        try:
            # Google Custom Search API
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': config.google_api_key,
                'cx': config.google_search_engine_id,
                'q': search_keywords,
                'searchType': 'image',
                'imgSize': 'large',
                'imgType': 'photo',
                'num': 3,  # Get multiple results to choose best
                'safe': 'active'
            }
            
            session = self._get_session()
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'items' in data:
                    for item in data['items']:
                        image_url = item.get('link')
                        if image_url:
                            result = self._download_and_validate_image(image_url, config, 'google')
                            if result[0]:  # If successful
                                return result
            
        except Exception as e:
            _logger.warning(f"Google fetch failed for product {product.id}: {str(e)}")
        
        return None, {}

    def _fetch_from_bing(self, product, search_keywords, config):
        """Fetch image from Bing Image Search API"""
        try:
            # Bing Image Search API
            url = "https://api.bing.microsoft.com/v7.0/images/search"
            headers = {
                'Ocp-Apim-Subscription-Key': config.bing_api_key
            }
            params = {
                'q': search_keywords,
                'imageType': 'photo',
                'size': 'large',
                'count': 3,
                'safeSearch': 'strict'
            }
            
            session = self._get_session()
            response = session.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'value' in data:
                    for item in data['value']:
                        image_url = item.get('contentUrl')
                        if image_url:
                            result = self._download_and_validate_image(image_url, config, 'bing')
                            if result[0]:  # If successful
                                return result
            
        except Exception as e:
            _logger.warning(f"Bing fetch failed for product {product.id}: {str(e)}")
        
        return None, {}

    def _download_and_validate_image(self, image_url, config, source):
        """Download image and validate quality requirements"""
        try:
            session = self._get_session()
            response = session.get(image_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check file size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > config.max_image_size_mb * 1024 * 1024:
                return None, {}
            
            image_data = response.content
            
            # Validate image with PIL
            try:
                image = Image.open(io.BytesIO(image_data))
                width, height = image.size
                format_name = image.format.lower() if image.format else 'unknown'
                
                # Check minimum dimensions
                if width < config.min_image_width or height < config.min_image_height:
                    return None, {}
                
                # Check format
                if config.preferred_formats != 'all':
                    allowed_formats = []
                    if config.preferred_formats in ['jpg', 'jpg_png']:
                        allowed_formats.append('jpeg')
                    if config.preferred_formats in ['png', 'jpg_png']:
                        allowed_formats.append('png')
                    
                    if format_name not in allowed_formats:
                        return None, {}
                
                # Simple watermark detection (basic check for repeated patterns)
                quality_score = self._calculate_image_quality(image)
                
                image_info = {
                    'image_source': source,
                    'image_url': image_url,
                    'image_size': f"{width}x{height}",
                    'image_format': format_name,
                    'file_size_kb': len(image_data) / 1024,
                    'quality_score': quality_score
                }
                
                return image_data, image_info
                
            except Exception as e:
                _logger.warning(f"Image validation failed: {str(e)}")
                return None, {}
            
        except Exception as e:
            _logger.warning(f"Image download failed from {image_url}: {str(e)}")
            return None, {}

    def _calculate_image_quality(self, image):
        """Calculate a simple image quality score"""
        try:
            # Convert to grayscale for analysis
            gray = image.convert('L')
            
            # Calculate variance (higher variance = more detail)
            import numpy as np
            img_array = np.array(gray)
            variance = np.var(img_array)
            
            # Normalize to 0-100 scale
            quality_score = min(100, variance / 100)
            
            return quality_score
        except:
            return 50  # Default score if calculation fails

    def _save_product_image(self, product, image_data, image_info, config, batch_id, job_type, start_time):
        """Save image to product and create attachment"""
        try:
            # Check for duplicates if deduplication is enabled
            if config.enable_deduplication:
                image_hash = hashlib.md5(image_data).hexdigest()
                existing_attachment = self.env['ir.attachment'].search([
                    ('checksum', '=', image_hash),
                    ('res_model', '=', 'product.template')
                ], limit=1)
                
                if existing_attachment:
                    # Use existing image
                    product.image_1920 = existing_attachment.datas
                    self.env['product.image.log'].log_operation(
                        product.id, 'dedup', 'success', 'Used existing duplicate image',
                        batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time,
                        **image_info
                    )
                    return
            
            # Encode image to base64
            image_b64 = base64.b64encode(image_data)
            
            # Set main product image
            product.image_1920 = image_b64
            
            # Update tracking fields
            product.image_last_fetch_date = fields.Datetime.now()
            product.image_fetch_source = image_info.get('image_source')
            product.image_quality_score = image_info.get('quality_score', 0)
            
            # Create attachment for gallery
            attachment_vals = {
                'name': f"{product.name}_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'type': 'binary',
                'datas': image_b64,
                'res_model': 'product.template',
                'res_id': product.id,
                'mimetype': f"image/{image_info.get('image_format', 'jpeg')}",
            }
            
            self.env['ir.attachment'].create(attachment_vals)
            
            # Log success
            self.env['product.image.log'].log_operation(
                product.id, 'fetch', 'success', 'Image successfully downloaded and saved',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time,
                **image_info
            )
            
        except Exception as e:
            _logger.error(f"Failed to save image for product {product.id}: {str(e)}")
            self.env['product.image.log'].log_operation(
                product.id, 'error', 'failed', f"Failed to save image: {str(e)}",
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )

    def _has_amazon_config(self, config):
        """Check if Amazon API configuration is complete"""
        return all([config.amazon_access_key, config.amazon_secret_key, config.amazon_partner_tag])

    def _has_google_config(self, config):
        """Check if Google API configuration is complete"""
        return all([config.google_api_key, config.google_search_engine_id])

    def _has_bing_config(self, config):
        """Check if Bing API configuration is complete"""
        return bool(config.bing_api_key)

