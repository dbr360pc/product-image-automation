import base64
import hashlib
import hmac
import json
import logging
import urllib.parse
from datetime import datetime

_logger = logging.getLogger(__name__)


class AmazonPAAPIService:
    """Amazon Product Advertising API 5.0 Service"""
    
    def __init__(self, access_key, secret_key, partner_tag, marketplace='US'):
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.marketplace = marketplace
        
        # Marketplace endpoints
        self.endpoints = {
            'US': 'webservices.amazon.com',
            'CA': 'webservices.amazon.ca',
            'UK': 'webservices.amazon.co.uk',
            'DE': 'webservices.amazon.de',
            'FR': 'webservices.amazon.fr',
            'IT': 'webservices.amazon.it',
            'ES': 'webservices.amazon.es',
            'JP': 'webservices.amazon.co.jp',
        }
        
        self.host = self.endpoints.get(marketplace, self.endpoints['US'])
        self.region = self._get_region_for_marketplace(marketplace)
    
    def _get_region_for_marketplace(self, marketplace):
        """Get AWS region for marketplace"""
        regions = {
            'US': 'us-east-1',
            'CA': 'us-east-1', 
            'UK': 'eu-west-1',
            'DE': 'eu-west-1',
            'FR': 'eu-west-1',
            'IT': 'eu-west-1',
            'ES': 'eu-west-1',
            'JP': 'us-west-2',
        }
        return regions.get(marketplace, 'us-east-1')
    
    def search_items(self, keywords=None, identifiers=None):
        """Search for items using keywords or identifiers"""
        try:
            # Prepare request payload
            payload = {
                "PartnerTag": self.partner_tag,
                "PartnerType": "Associates",
                "Marketplace": f"www.amazon.{self.marketplace.lower()}",
                "Resources": [
                    "Images.Primary.Large",
                    "Images.Primary.Medium", 
                    "ItemInfo.Title",
                    "ItemInfo.ProductInfo"
                ]
            }
            
            # Add search parameters
            if identifiers:
                # Search by identifier (EAN, UPC, etc.)
                for id_type, value in identifiers.items():
                    if id_type.upper() in ['EAN', 'UPC', 'ISBN']:
                        payload["ItemIds"] = [value]
                        payload["ItemIdType"] = id_type.upper()
                        break
            else:
                # Search by keywords
                payload["Keywords"] = keywords
                payload["SearchIndex"] = "All"
            
            # Make the API request
            response = self._make_request('SearchItems', payload)
            
            if response and 'SearchResult' in response:
                items = response['SearchResult'].get('Items', [])
                if items:
                    return self._extract_image_info(items[0])
            
        except Exception as e:
            _logger.error(f"Amazon PA-API search failed: {str(e)}")
        
        return None
    
    def _extract_image_info(self, item):
        """Extract image information from Amazon item"""
        try:
            images = item.get('Images', {})
            primary = images.get('Primary', {})
            
            # Try large image first, fallback to medium
            large_image = primary.get('Large', {})
            if large_image and large_image.get('URL'):
                return {
                    'url': large_image['URL'],
                    'width': large_image.get('Width', 0),
                    'height': large_image.get('Height', 0)
                }
            
            medium_image = primary.get('Medium', {})
            if medium_image and medium_image.get('URL'):
                return {
                    'url': medium_image['URL'], 
                    'width': medium_image.get('Width', 0),
                    'height': medium_image.get('Height', 0)
                }
            
        except Exception as e:
            _logger.warning(f"Failed to extract image info: {str(e)}")
        
        return None
    
    def _make_request(self, operation, payload):
        """Make authenticated request to Amazon PA-API"""
        try:
            import requests
            
            # Request details
            method = 'POST'
            uri = '/paapi5/searchitems'
            
            if operation == 'GetItems':
                uri = '/paapi5/getitems'
            
            # Headers
            headers = {
                'Content-Type': 'application/json; charset=utf-8',
                'X-Amz-Target': f'com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{operation}',
                'Host': self.host
            }
            
            # Convert payload to JSON
            payload_json = json.dumps(payload, separators=(',', ':'))
            
            # Sign the request
            signed_headers = self._sign_request(
                method, uri, headers, payload_json
            )
            
            # Make the request
            url = f'https://{self.host}{uri}'
            response = requests.post(
                url, 
                data=payload_json,
                headers=signed_headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                _logger.error(f"Amazon API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            _logger.error(f"Amazon API request failed: {str(e)}")
            return None
    
    def _sign_request(self, method, uri, headers, payload):
        """Sign request using AWS Signature Version 4"""
        try:
            # Step 1: Create canonical request
            canonical_headers = []
            signed_headers_list = []
            
            # Add required headers for signing
            timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            date_stamp = timestamp[:8]
            
            headers['X-Amz-Date'] = timestamp
            
            # Sort headers for canonical request
            for key in sorted(headers.keys(), key=str.lower):
                canonical_headers.append(f'{key.lower()}:{headers[key].strip()}')
                signed_headers_list.append(key.lower())
            
            canonical_headers_str = '\n'.join(canonical_headers)
            signed_headers_str = ';'.join(signed_headers_list)
            
            # Create payload hash
            payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            
            # Create canonical request
            canonical_request = f"{method}\n{uri}\n\n{canonical_headers_str}\n\n{signed_headers_str}\n{payload_hash}"
            
            # Step 2: Create string to sign
            algorithm = 'AWS4-HMAC-SHA256'
            credential_scope = f'{date_stamp}/{self.region}/ProductAdvertisingAPI/aws4_request'
            string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
            
            # Step 3: Calculate signature
            signing_key = self._get_signature_key(date_stamp)
            signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
            
            # Step 4: Add authorization header
            authorization = (
                f'{algorithm} '
                f'Credential={self.access_key}/{credential_scope}, '
                f'SignedHeaders={signed_headers_str}, '
                f'Signature={signature}'
            )
            
            headers['Authorization'] = authorization
            
            return headers
            
        except Exception as e:
            _logger.error(f"Request signing failed: {str(e)}")
            return headers
    
    def _get_signature_key(self, date_stamp):
        """Generate signing key for AWS signature"""
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        k_date = sign(f'AWS4{self.secret_key}'.encode('utf-8'), date_stamp)
        k_region = sign(k_date, self.region)
        k_service = sign(k_region, 'ProductAdvertisingAPI')
        k_signing = sign(k_service, 'aws4_request')
        
        return k_signing