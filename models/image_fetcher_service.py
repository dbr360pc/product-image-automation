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
            _logger.info(f"Daily scan - Config loaded: {bool(config)}")
            if config and hasattr(config, 'cron_active') and not config.cron_active:
                _logger.info("Daily scan disabled in configuration")
                return
            elif not config:
                _logger.error("No active configuration found for daily scan")
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
            _logger.info(f"Config loaded: {bool(config)}")
            
            if not config:
                _logger.error("No active configuration found for backfill job")
                return
            
            # Get all products (or limit for testing)
            domain = [('active', '=', True)]
            if config.test_mode:
                _logger.info(f"Test mode enabled - limiting to {config.test_product_limit} products")
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
        """Get products that need images or descriptions based on configuration"""
        domain = [('active', '=', True), ('image_auto_fetch_enabled', '=', True)]
        
        # Products needing images OR descriptions
        if config.skip_products_with_images and not config.force_update_mode:
            domain.append('|')
            domain.append(('image_1920', '=', False))
            domain.append('|')
            domain.append(('description', '=', False))
            domain.append(('description', '=', ''))
        
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
        """Process a single product for image and description fetching"""
        start_time = time.time()
        
        _logger.info(f"Processing Product: {product.name} (ID: {product.id})")
        
        # Check what needs to be processed
        needs_image = not product.has_product_image() or force_update
        needs_description = not product.description or product.description.strip() == ''
        

        
        if not needs_image and not needs_description:
            _logger.info(f"Product {product.id} already has image and description, skipping")
            self.env['product.image.log'].log_operation(
                product.id, 'skip', 'info', 'Product already has image and description',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )
            return
        
        # Get search terms
        search_keywords = product.get_search_keywords()
        identifiers = product.get_product_identifiers()
        

        
        if not search_keywords and not identifiers:
            _logger.warning(f"No search terms or identifiers available for product {product.id}")
            self.env['product.image.log'].log_operation(
                product.id, 'skip', 'warning', 'No search terms or identifiers available',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )
            return
        
        # Process images and descriptions
        image_data = None
        image_info = {}
        product_description = None
        
        if needs_image or needs_description:

            
            if config.use_google_images and self._has_google_config(config):

                
                if needs_image:
                    image_data, image_info = self._fetch_from_google(product, search_keywords, config)
                
                if needs_description:
                    product_description = self._fetch_description_from_google(product, search_keywords, config)
        
        # Save results
        success_messages = []
        
        if image_data and needs_image:
            if config.test_mode:
                success_messages.append("Image found (test mode - not saved)")
            else:
                self._save_product_image(product, image_data, image_info, config, batch_id, job_type, start_time)
                success_messages.append("Image saved successfully")
        
        if product_description and needs_description:
            if config.test_mode:
                success_messages.append("Description found (test mode - not saved)")
            else:
                product.description = product_description
                success_messages.append("Description saved successfully")
        
        # Log results
        if success_messages:
            self.env['product.image.log'].log_operation(
                product.id, 'fetch', 'success', '; '.join(success_messages),
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time,
                **image_info
            )
        else:
            failure_reasons = []
            if needs_image and not image_data:
                failure_reasons.append("No suitable image found")
            if needs_description and not product_description:
                failure_reasons.append("No description found")
            
            product.image_fetch_attempts += 1
            self.env['product.image.log'].log_operation(
                product.id, 'fetch', 'failed', '; '.join(failure_reasons),
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
            if not config.use_google_images or not config.google_api_key or not config.google_search_engine_id:
                return None, {}

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
                items = data.get('items', [])
                
                _logger.info(f"Google returned {len(items)} image results")
                
                if items:
                    
                    # Try each image until we find a valid one
                    for item in items:
                        image_url = item.get('link')
                        if image_url:
                            result = self._download_and_validate_image(image_url, config, 'google')
                            if result[0]:  # If successful
                                _logger.info(f"Successfully downloaded image from Google")
                                return result
                else:
                    _logger.warning("No items found in Google response")
            else:
                _logger.error(f"Google API Error: {response.status_code}")
            
        except Exception as e:
            _logger.error(f"Google fetch failed for product {product.id}: {str(e)}")
        
        return None, {}

    def _fetch_description_from_google(self, product, search_keywords, config):
        """Fetch product description from Google Custom Search API"""
        
        try:
            if not config.google_api_key or not config.google_search_engine_id:

                return None

            # Google Custom Search API for web results (not images)
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': config.google_api_key,
                'cx': config.google_search_engine_id,
                'q': search_keywords,
                'num': 5,  # Get multiple results
                'safe': 'active'
            }
            
            session = self._get_session()
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                _logger.info(f"Google returned {len(items)} web results for description")
                
                if items:
                    # Extract descriptions from search results
                    descriptions = []
                    for i, item in enumerate(items[:3]):  # Use first 3 results
                        title = item.get('title', '')
                        snippet = item.get('snippet', '')
                        
                        if snippet and len(snippet.strip()) > 20:
                            descriptions.append(snippet.strip())
                    
                    if descriptions:
                        # Combine and clean up the best description
                        best_description = self._create_product_description(descriptions, product.name)
                        _logger.info(f"Generated product description successfully")
                        return best_description
                    else:
                        _logger.warning("No useful descriptions found in search results")
                else:
                    _logger.warning("No web results found for description")
            else:
                _logger.error(f"Google API Error for description: {response.status_code}")
                
        except Exception as e:
            _logger.error(f"Description fetch failed for product {product.id}: {str(e)}")
        
        return None

    def _create_product_description(self, descriptions, product_name):
        """Create a clean product description from search results"""
        if not descriptions:
            return None
            
        # Use the longest, most descriptive snippet
        best_desc = max(descriptions, key=len)
        
        # Clean up the description
        # Remove common unwanted phrases
        unwanted_phrases = [
            'Buy online', 'Free shipping', 'Best price', 'Click here',
            'Add to cart', 'In stock', 'Out of stock', 'Sale price',
            'www.', 'http:', 'https:', '€', '$', '£', '...',
            'Read more', 'See more', 'View details'
        ]
        
        cleaned_desc = best_desc
        for phrase in unwanted_phrases:
            cleaned_desc = cleaned_desc.replace(phrase, '')
        
        # Clean up extra spaces and punctuation
        import re
        cleaned_desc = re.sub(r'\s+', ' ', cleaned_desc).strip()
        cleaned_desc = re.sub(r'[.]{2,}', '.', cleaned_desc)
        
        # Ensure it ends with proper punctuation
        if cleaned_desc and not cleaned_desc.endswith(('.', '!', '?')):
            cleaned_desc += '.'
            
        # Limit length (Odoo description field limit)
        if len(cleaned_desc) > 500:
            cleaned_desc = cleaned_desc[:497] + '...'
            
        return cleaned_desc

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
            max_size_bytes = config.max_image_size_mb * 1024 * 1024
            _logger.info(f"File size check - Content length: {content_length}, Max allowed: {max_size_bytes} bytes")
            
            if content_length and int(content_length) > max_size_bytes:
                return None, {}
            
            image_data = response.content
            
            # Validate image with PIL
            try:
                image = Image.open(io.BytesIO(image_data))
                width, height = image.size
                format_name = image.format.lower() if image.format else 'unknown'
                
                # Simple quality score calculation
                quality_score = self._calculate_image_quality(image)
                
                image_info = {
                    'image_source': source,
                    'image_url': image_url,
                    'image_size': f"{width}x{height}",
                    'image_format': format_name,
                    'file_size_kb': len(image_data) / 1024,
                    'quality_score': quality_score
                }
                
                _logger.info(f"Image validation successful: {width}x{height} {format_name}")
                return image_data, image_info
                
            except Exception as e:
                _logger.error(f"PIL validation failed: {str(e)}")
                return None, {}
            
        except Exception as e:
            _logger.error(f"Image download failed from {image_url}: {str(e)}")
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
        return all([config.use_google_images, config.google_api_key, config.google_search_engine_id])

    def _has_bing_config(self, config):
        """Check if Bing API configuration is complete"""
        return bool(config.bing_api_key)

