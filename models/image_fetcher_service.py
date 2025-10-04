import base64
import hashlib
import logging
import re
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

    def _handle_rate_limit(self, response, operation="API call", config=None):
        """Handle rate limit errors with API key rotation and exponential backoff"""
        if response.status_code == 429:
            _logger.warning(f"Rate limit hit for {operation}")
            
            # Try to rotate API key if available and it's a Google API call
            if config and "Google" in operation:
                if config.rotate_google_api_key(f"Rate limit during {operation}"):
                    _logger.info(f"Switched to next API key, retrying immediately")
                    return True  # Indicate retry without waiting
                else:
                    _logger.warning(f"No alternative API keys available, using backoff")
            
            # Fallback to wait strategy
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                wait_time = int(retry_after)
            else:
                wait_time = 20
            
            _logger.warning(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
            return True
        return False

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
            if not config:
                _logger.error("No active configuration found for backfill job")
                return
            
            batch_id = f"backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Find all products that could use images/descriptions
            all_products = self.env['product.template'].search([('sale_ok', '=', True)])
            
            _logger.info(f"Backfill job processing {len(all_products)} products")
            
            # Process in batches  
            self._process_products_in_batches(all_products, config, batch_id, 'backfill', force_update=False)
            
        except Exception as e:
            _logger.error(f"Error in backfill job: {str(e)}", exc_info=True)
            self.env['product.image.log'].log_operation(
                None, 'error', 'failed', f"Backfill job failed: {str(e)}", 
                job_type='backfill', batch_id=batch_id
            )

    @api.model
    def process_products(self, product_ids, force_update=False, job_type='manual'):
        """Process specific products for image fetching"""
        config = self.env['product.image.config'].get_active_config()
        if not config:
            raise UserError(_("No active configuration found. Please configure the image fetching settings."))
        
        batch_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        products = self.env['product.template'].browse(product_ids)
        
        return self._process_products_in_batches(products, config, batch_id, job_type, force_update)

    def _get_products_needing_images(self, config):
        """Get products that need images based on configuration"""
        domain = [('sale_ok', '=', True)]
        
        # Add conditions based on config
        if not config.process_products_with_images:
            domain.append(('image_1920', '=', False))
        
        products = self.env['product.template'].search(domain, limit=config.batch_size or 50)
        return products

    def _process_products_in_batches(self, products, config, batch_id, job_type, force_update=False):
        """Process products in smaller batches to avoid timeouts"""
        batch_size = min(config.batch_size or 10, 10)  # Max 10 per batch
        
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            _logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} products")
            
            for product in batch:
                try:
                    self._process_single_product(product, config, batch_id, job_type, force_update)
                    self.env.cr.commit()  # Commit after each product
                    
                    # Add delay between products to avoid overwhelming APIs
                    time.sleep(2)
                    
                except Exception as e:
                    _logger.error(f"Error processing product {product.id}: {str(e)}", exc_info=True)
                    self.env.cr.rollback()
                    continue
        
        return True

    def _process_single_product(self, product, config, batch_id, job_type, force_update=False):
        """Process a single product for image and description fetching"""
        start_time = time.time()
        
        _logger.info(f"Processing product: {product.name} (ID: {product.id})")
        
        # Determine what needs to be processed
        needs_image = not product.image_1920 or (force_update and config.process_products_with_images)
        needs_description = config.auto_generate_descriptions and not product.description_sale
        
        # Skip if nothing needs to be done
        if not needs_image and not needs_description:
            _logger.info(f"Skipping product {product.id} - has image and description")
            return
        
        # Prepare search keywords if we need to fetch anything
        search_keywords = self._prepare_search_keywords(product)
        identifiers = self._extract_product_identifiers(product)
        
        _logger.info(f"Search keywords: {search_keywords} (needs_image: {needs_image}, needs_description: {needs_description})")
        
        # Initialize result containers
        image_data = None
        image_info = {}
        description_data = {}
        
        # Only try to fetch images if needed
        if needs_image:
            # 1. Try Amazon first if configured
            if config.use_amazon_api and self._has_amazon_config(config):
                _logger.info("Trying Amazon...")
                image_data, image_info = self._fetch_from_amazon(product, identifiers, search_keywords, config)
            
            # 2. Try Google Images if no image found and configured
            if not image_data and config.use_google_images and self._has_google_config(config):
                _logger.info("Trying Google Images...")
                image_data, image_info = self._fetch_from_google(product, search_keywords, config)
            
            # 3. Try Bing if still no image and configured
            if not image_data and config.use_bing_images and self._has_bing_config(config):
                _logger.info("Trying Bing...")
                image_data, image_info = self._fetch_from_bing(product, search_keywords, config)
        
        # Fetch description if needed (independent of image processing)
        if needs_description:
            _logger.info("Fetching description from Google...")
            description_data = self._fetch_description_from_google(product, search_keywords, config)
        
        # Save results
        if image_data:
            self._save_product_image(product, image_data, image_info, config, batch_id, job_type, start_time)
        else:
            # Log no image found as info (not a failure, just no results available)
            self.env['product.image.log'].log_operation(
                product.id, 'fetch', 'info', 'No suitable image found from any source',
                batch_id=batch_id, job_type=job_type, processing_time=time.time() - start_time
            )
        
        # Save description if found
        if description_data and description_data.get('description'):
            self._save_product_description(product, description_data, batch_id, job_type)
        
        _logger.info(f"Completed processing product {product.id}")

    def _prepare_search_keywords(self, product):
        """Prepare search keywords for the product"""
        keywords = []
        
        # Extract brand from product name if available
        brand = None
        if hasattr(product, 'brand_id') and product.brand_id:
            brand = product.brand_id.name
        
        # Clean product name - remove internal codes and make more generic
        if product.name:
            name = product.name
            # Remove common internal identifiers
            name = re.sub(r'\b\d{8}\b', '', name)  # Remove 8-digit codes like 00002649
            name = re.sub(r'\s+', ' ', name).strip()  # Clean extra spaces
            
            # If we have a brand, make sure it's in the search
            if brand and brand.upper() not in name.upper():
                keywords.append(f"{brand} {name}")
            else:
                keywords.append(name)
        
        # Add category for better context
        if product.categ_id and product.categ_id.name and product.categ_id.name != 'All':
            category = product.categ_id.name
            if len(keywords) == 0 or category.lower() not in keywords[0].lower():
                keywords.append(category)
        
        # Join and limit length
        search_query = ' '.join(keywords[:2])  # Use top 2 elements
        
        # Add regional context for better Ecuador/Latin America results
        if search_query and not any(term in search_query.lower() for term in ['ecuador', 'latina', 'tech', 'producto']):
            # Don't add "Ecuador" to every search as it might be too restrictive
            # The country parameters will handle geographic targeting
            pass
        
        # Limit total length to avoid overly complex queries
        if len(search_query) > 100:
            search_query = search_query[:100].rsplit(' ', 1)[0]  # Cut at word boundary
            
        return search_query

    def _extract_product_identifiers(self, product):
        """Extract product identifiers like EAN, UPC, etc."""
        identifiers = {}
        
        if product.barcode:
            identifiers['barcode'] = product.barcode
            
        if product.default_code:
            identifiers['sku'] = product.default_code
            
        return identifiers

    def _fetch_from_amazon(self, product, identifiers, search_keywords, config):
        """Fetch image from Amazon Product Advertising API"""
        try:
            # This is a placeholder - Amazon API requires complex authentication
            # For now, we'll skip Amazon integration
            _logger.info("Amazon integration not yet implemented")
            
        except Exception as e:
            _logger.warning(f"Amazon fetch failed for product {product.id}: {str(e)}")
        
        return None, {}

    def _fetch_from_google(self, product, search_keywords, config):
        """Fetch image from Google Custom Search API with API key rotation"""
        
        try:
            # Get current API key (with rotation support)
            current_api_key = config.get_current_google_api_key()
            if not config.use_google_images or not current_api_key or not config.google_search_engine_id:
                available_keys = len(config.get_available_google_api_keys())
                _logger.warning(f"Google API not properly configured. Available keys: {available_keys}")
                return None, {}

            _logger.info(f"Using Google API key #{config.current_api_key_index + 1} (of {len(config.get_available_google_api_keys())})")

            # Google Custom Search API
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': current_api_key,
                'cx': config.google_search_engine_id,
                'q': search_keywords,
                'searchType': 'image',
                'imgSize': 'medium',  # Less restrictive than 'large'
                'num': 5,  # Get more results to choose from
                'safe': 'active',
                'gl': 'ec',  # Ecuador geolocation
                'hl': 'es'   # Spanish language
            }
            
            session = self._get_session()
            
            # Add delay before API call to respect rate limits
            time.sleep(1)  # 1 second delay between calls
            
            response = session.get(url, params=params, timeout=30)
            
            # Handle rate limiting with API key rotation
            if self._handle_rate_limit(response, "Google Images API", config):
                # Update API key if it was rotated
                current_api_key = config.get_current_google_api_key()
                params['key'] = current_api_key
                _logger.info(f"Retrying with API key #{config.current_api_key_index + 1}")
                # Retry after rate limit wait or key rotation
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
                            image_data, image_info = self._download_and_validate_image(image_url, config, 'google')
                            if image_data:
                                image_info.update({
                                    'title': item.get('title', ''),
                                    'source': 'google',
                                    'api_key_used': config.current_api_key_index + 1
                                })
                                return image_data, image_info
                else:
                    # No results found, log as info and try fallback searches
                    _logger.info("No results with original search, trying fallback strategies...")
                    # Log the info about no original results
                    self.env['product.image.log'].log_operation(
                        product.id, 'fetch', 'info', 'No results with original search, trying fallback strategies'
                    )
                    return self._try_fallback_searches(product, config, session, url, current_api_key)
                
            else:
                _logger.warning(f"Google API returned status {response.status_code}: {response.text}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Network error in Google fetch: {str(e)}")
        except Exception as e:
            _logger.error(f"Error in Google fetch: {str(e)}")
            
        return None, {}

    def _try_fallback_searches(self, product, config, session, url, api_key):
        """Try simplified search strategies when main search fails"""
        
        fallback_queries = []
        
        # Strategy 1: Just the product name without codes/categories
        if product.name:
            clean_name = re.sub(r'\b\d{5,}\b', '', product.name)  # Remove long number codes
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            if clean_name:
                fallback_queries.append(clean_name)
        
        # Try each fallback query
        for i, query in enumerate(fallback_queries[:3]):  # Limit to 3 attempts
            _logger.info(f"Trying fallback search #{i+1}: '{query}'")
            
            params = {
                'key': api_key,
                'cx': config.google_search_engine_id,
                'q': query,
                'searchType': 'image',
                'imgSize': 'medium',
                'num': 3,
                'safe': 'active',
                'gl': 'ec',
                'hl': 'es'
            }
            
            time.sleep(0.5)
            
            try:
                response = session.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    
                    _logger.info(f"Fallback search #{i+1} returned {len(items)} results")
                    
                    if items:
                        # Try each image
                        for item in items:
                            image_url = item.get('link')
                            if image_url:
                                image_data, image_info = self._download_and_validate_image(image_url, config, 'google')
                                if image_data:
                                    image_info.update({
                                        'title': item.get('title', ''),
                                        'source': 'google_fallback',
                                        'search_query': query,
                                        'api_key_used': config.current_api_key_index + 1
                                    })
                                    _logger.info(f"Found image using fallback search: '{query}'")
                                    return image_data, image_info
                                    
            except Exception as e:
                _logger.warning(f"Fallback search #{i+1} failed: {str(e)}")
                continue
        
        return None, {}

    def _fetch_description_from_google(self, product, search_keywords, config):
        """Fetch product description from Google Custom Search API"""
        
        try:
            # Get current API key
            current_api_key = config.get_current_google_api_key()
            if not current_api_key or not config.google_search_engine_id:
                _logger.warning("Google API not configured for description fetching")
                return {}

            _logger.info(f"Fetching description using Google API key #{config.current_api_key_index + 1}")

            # Google Custom Search API for web results
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': current_api_key,
                'cx': config.google_search_engine_id,
                'q': f"{search_keywords} product description specifications",
                'num': 5,  # Get multiple results for better description
                'safe': 'active',
                'gl': 'ec',  # Ecuador geolocation
                'hl': 'es'   # Spanish language
            }
            
            session = self._get_session()
            time.sleep(1)  # Rate limiting
            
            response = session.get(url, params=params, timeout=30)
            
            # Handle rate limiting with API key rotation
            if self._handle_rate_limit(response, "Google Description API", config):
                # Update API key if it was rotated
                current_api_key = config.get_current_google_api_key()
                params['key'] = current_api_key
                _logger.info(f"Retrying description fetch with API key #{config.current_api_key_index + 1}")
                response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                if items:
                    # Extract snippets from search results
                    descriptions = []
                    for item in items[:3]:  # Use top 3 results
                        snippet = item.get('snippet', '')
                        if snippet and len(snippet) > 20:  # Only meaningful snippets
                            descriptions.append(snippet)
                    
                    if descriptions:
                        # Combine and process descriptions
                        combined_description = self._create_product_description(descriptions, product.name)
                        return {
                            'description': combined_description,
                            'source': 'google_search',
                            'api_key_used': config.current_api_key_index + 1
                        }
            else:
                _logger.warning(f"Google Description API returned status {response.status_code}")
                
        except Exception as e:
            _logger.error(f"Error fetching description from Google: {str(e)}")
            
        return {}

    def _create_product_description(self, descriptions, product_name):
        """Create a product description from search results"""
        if not descriptions:
            return ""
        
        # Remove duplicates and clean up
        unique_descriptions = []
        seen = set()
        
        for desc in descriptions:
            # Clean up the description
            desc = desc.strip()
            desc = desc.replace('\n', ' ').replace('\r', '')
            
            # Remove common prefixes/suffixes
            for prefix in ['Buy ', 'Shop ', 'Get ', 'Find ']:
                if desc.startswith(prefix):
                    desc = desc[len(prefix):]
            
            # Skip if too short or already seen
            if len(desc) < 30 or desc.lower() in seen:
                continue
                
            seen.add(desc.lower())
            unique_descriptions.append(desc)
        
        if not unique_descriptions:
            return f"High-quality {product_name} available for purchase."
        
        # Combine descriptions intelligently
        if len(unique_descriptions) == 1:
            return unique_descriptions[0]
        
        # Create a comprehensive description
        main_desc = unique_descriptions[0]
        if len(main_desc) < 100 and len(unique_descriptions) > 1:
            main_desc += " " + unique_descriptions[1]
        
        # Ensure proper ending
        if not main_desc.endswith('.'):
            main_desc += '.'
            
        return main_desc[:500]  # Limit length

    def _fetch_from_bing(self, product, search_keywords, config):
        """Fetch image from Bing Image Search API"""
        try:
            if not config.bing_api_key:
                return None, {}
            
            url = "https://api.cognitive.microsoft.com/bing/v7.0/images/search"
            headers = {'Ocp-Apim-Subscription-Key': config.bing_api_key}
            params = {
                'q': search_keywords,
                'imageType': 'Photo',
                'size': 'Large',
                'count': 3
            }
            
            session = self._get_session()
            response = session.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                images = data.get('value', [])
                
                for image in images:
                    image_url = image.get('contentUrl')
                    if image_url:
                        image_data, image_info = self._download_and_validate_image(image_url, config, 'bing')
                        if image_data:
                            image_info.update({
                                'title': image.get('name', ''),
                                'source': 'bing'
                            })
                            return image_data, image_info
                            
        except Exception as e:
            _logger.warning(f"Bing fetch failed for product {product.id}: {str(e)}")
            
        return None, {}

    def _download_and_validate_image(self, image_url, config, source):
        """Download and validate an image"""
        try:
            session = self._get_session()
            
            # Download with timeout
            response = session.get(image_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'image' not in content_type:
                _logger.warning(f"Invalid content type: {content_type}")
                return None, {}
            
            # Read image data
            image_data = response.content
            
            # Basic validation with PIL
            try:
                image = Image.open(io.BytesIO(image_data))
                
                # Calculate quality score
                quality_score = self._calculate_image_quality(image)
                
                image_info = {
                    'width': image.width,
                    'height': image.height,
                    'format': image.format or 'JPEG',
                    'size_bytes': len(image_data),
                    'quality_score': quality_score,
                    'source_url': image_url,
                    'source': source
                }
                
                _logger.info(f"Image found: {image.width}x{image.height}, {len(image_data)} bytes, quality: {quality_score}")
                
                return base64.b64encode(image_data).decode('utf-8'), image_info
                
            except Exception as e:
                _logger.warning(f"PIL validation failed: {str(e)}")
                return None, {}
                
        except Exception as e:
            _logger.warning(f"Download failed for {image_url}: {str(e)}")
            
        return None, {}

    def _calculate_image_quality(self, image):
        """Calculate a simple quality score for the image"""
        try:
            # Basic quality metrics
            width, height = image.size
            
            # Resolution score (0-40 points)
            total_pixels = width * height
            if total_pixels >= 1000000:  # 1MP+
                resolution_score = 40
            elif total_pixels >= 500000:  # 0.5MP+
                resolution_score = 30
            elif total_pixels >= 200000:  # 0.2MP+
                resolution_score = 20
            else:
                resolution_score = 10
            
            # Aspect ratio score (0-20 points) - prefer standard ratios
            aspect_ratio = width / height
            if 0.7 <= aspect_ratio <= 1.5:  # Square-ish
                aspect_score = 20
            elif 0.5 <= aspect_ratio <= 2.0:  # Reasonable
                aspect_score = 15
            else:
                aspect_score = 5
            
            # Format score (0-10 points)
            if image.format in ['JPEG', 'PNG']:
                format_score = 10
            else:
                format_score = 5
            
            return min(resolution_score + aspect_score + format_score, 100)
            
        except Exception:
            return 50  # Default score

    def _save_product_image(self, product, image_data, image_info, config, batch_id, job_type, start_time):
        """Save the image to the product"""
        try:
            # Update product image
            product.write({
                'image_1920': image_data
            })
            
            # Create attachment record for tracking
            attachment_vals = {
                'name': f"{product.name}_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'res_model': 'product.template',
                'res_id': product.id,
                'type': 'binary',
                'datas': image_data,
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

    def _save_product_description(self, product, description_data, batch_id, job_type):
        """Save the generated description to the product"""
        try:
            description = description_data.get('description', '')
            if not description:
                return
                
            # Update product descriptions for ecommerce visibility
            update_vals = {}
            
            # Update description_sale (shown in shop)
            if not product.description_sale:
                update_vals['description_sale'] = description
            
            # Update description (internal description)  
            if not product.description:
                update_vals['description'] = description
                
            # Update website description if module exists
            if hasattr(product, 'website_description') and not product.website_description:
                update_vals['website_description'] = description
            
            if update_vals:
                product.write(update_vals)
                _logger.info(f"Updated descriptions for product {product.id}: {list(update_vals.keys())}")
                
                # Log success
                self.env['product.image.log'].log_operation(
                    product.id, 'update', 'success', 
                    f"Description generated and saved to {', '.join(update_vals.keys())}",
                    batch_id=batch_id, job_type=job_type,
                    source=description_data.get('source', 'unknown')
                )
            else:
                _logger.info(f"Product {product.id} already has descriptions, skipping update")
                
        except Exception as e:
            _logger.error(f"Failed to save description for product {product.id}: {str(e)}")
            self.env['product.image.log'].log_operation(
                product.id, 'error', 'failed', f"Failed to save description: {str(e)}",
                batch_id=batch_id, job_type=job_type
            )

    def _has_amazon_config(self, config):
        """Check if Amazon API configuration is complete"""
        return all([config.amazon_access_key, config.amazon_secret_key, config.amazon_partner_tag])

    def _has_google_config(self, config):
        """Check if Google API configuration is complete"""
        available_keys = config.get_available_google_api_keys()
        return len(available_keys) > 0 and bool(config.google_search_engine_id)

    def _has_bing_config(self, config):
        """Check if Bing API configuration is complete"""
        return bool(config.bing_api_key)