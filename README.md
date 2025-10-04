# Product Image Automation for Odoo 16

A comprehensive Odoo 16 module that provides automated product image fetching and management for trionica.ec.

## Features

- **Daily Automation**: Automated cron job that scans all product.template records daily
- **Multiple Image Sources**: 
  - Amazon Product Advertising API (preferred)
  - Google Custom Search API (fallback)
  - Bing Image Search API (fallback)
- **Smart Product Matching**: Match products by SKU/EAN/UPC/MPN/name
- **Image Quality Control**: 
  - Minimum size requirements (min 800px)
  - Format preferences
  - Watermark detection
  - File size limits
- **Deduplication**: Avoid downloading duplicate images
- **Idempotent Operations**: Skip products already covered unless force update is enabled
- **Comprehensive Configuration**: Configurable via Settings interface
- **Rate Limiting**: Configurable API rate limits and daily caps
- **Test Mode**: Test configuration without actual downloads
- **Detailed Logging**: Complete audit trail of all operations
- **Backfill Jobs**: Process existing catalog and daily deltas

## Installation

1. Copy this module to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the "Product Image Automation" module
4. Configure the image sources and settings

## Configuration

### 1. Basic Setup

Go to **Sales → Image Automation → Configuration** or **Settings → Image Automation**

1. **Enable Image Sources**: Configure at least one image source:
   - **Amazon PA-API**: Requires Access Key, Secret Key, and Partner Tag
   - **Google Images**: Requires multiple API Keys (one per line) and Custom Search Engine ID  
   - **Bing Images**: Requires Subscription Key

2. **Quality Settings**: 
   - Set minimum image dimensions (default: 800x600px)
   - Choose preferred formats (JPEG, PNG, or both)
   - Set maximum file size limit

3. **Rate Limiting**:
   - Configure requests per minute to respect API limits
   - Set daily request limits to control costs

### 2. API Configuration

#### Amazon Product Advertising API

1. Sign up for Amazon Associates program
2. Apply for Product Advertising API access
3. Get your credentials:
   - Access Key ID
   - Secret Access Key  
   - Associate Tag (Partner Tag)
4. Choose your marketplace (US, CA, UK, DE, FR, IT, ES, JP)

#### Google Custom Search API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Custom Search API
3. Create API credentials (API Key) - **Create multiple keys for higher limits**
4. Set up a Custom Search Engine at [Google CSE](https://cse.google.com/)
5. Configure it to search for images
6. Get the Search Engine ID

**Multiple API Keys (Recommended):**
- Each Google API key has a daily limit (100 queries free, 10,000 paid)
- You can configure unlimited API keys (one per line) for automatic rotation
- When one key hits the rate limit, the system automatically switches to the next
- This multiplies your effective daily quota by the number of keys
- Format: Enter each API key on a separate line in the text field
- Comments: Lines starting with # are ignored as comments

**Example API Keys Configuration:**
```
AIzaSyC4567890abcdef1234567890ABCDEF123
AIzaSyD4567890abcdef1234567890ABCDEF124
AIzaSyE4567890abcdef1234567890ABCDEF125
# This is a comment - backup key for later
# AIzaSyF4567890abcdef1234567890ABCDEF126
```

#### Bing Image Search API

1. Go to [Azure Portal](https://portal.azure.com/)
2. Create a Bing Search v7 resource
3. Get the subscription key from the Keys and Endpoint section

### 3. Product Configuration

For each product, you can configure:

- **Auto-fetch Images**: Enable/disable automatic image fetching
- **Additional Identifiers**: 
  - UPC Code
  - Manufacturer Part Number (MPN)

These help improve image matching accuracy.

### 4. Scheduling

The module includes automated daily scanning:

- **Daily Cron Job**: Configurable time (default: 2:00 AM)
- **Log Cleanup**: Weekly cleanup of old logs (configurable retention)

## Usage

### Daily Operations

The system automatically:
1. Scans all products without images (or all products if force update is enabled)
2. Attempts to fetch images from configured sources in priority order
3. Validates image quality (size, format, etc.)
4. Saves images to product records
5. Creates detailed logs of all operations

### Manual Operations

You can manually:
1. **Test Configuration**: Verify API credentials and settings
2. **Run Backfill**: Process all existing products once
3. **Fetch Images**: Manually trigger image fetching for selected products
4. **Retry Failed**: Retry previously failed operations

### Monitoring

Monitor operations through:
1. **Processing Logs**: Detailed logs of all operations with filtering and search
2. **Products Needing Images**: Quick view of products without images
3. **Configuration Dashboard**: Overview of settings and status

## Test Mode

Before going live:

1. Enable **Test Mode** in configuration
2. Set a low **Test Product Limit** (e.g., 10 products)  
3. Run a backfill job to test the configuration
4. Check the logs to verify everything works correctly
5. Disable test mode when ready for production

## Troubleshooting

### Common Issues

1. **No Images Found**: 
   - Check API credentials
   - Verify product has sufficient identifying information (name, SKU, etc.)
   - Check image quality requirements aren't too strict

2. **Rate Limiting Errors (429)**:
   - Reduce requests per minute in configuration
   - Check if you've exceeded daily API limits
   - Verify API subscription status

3. **Timeout Errors**:
   - Check internet connectivity
   - Verify API endpoints are accessible
   - Consider reducing batch size

### Log Analysis

Check processing logs for:
- **Success Rate**: How many products got images
- **Error Patterns**: Common failure reasons
- **Source Performance**: Which image sources work best
- **Processing Time**: Performance metrics

### Performance Tuning

For large catalogs:
- Reduce batch size if experiencing timeouts
- Increase processing intervals during business hours
- Use test mode to optimize settings
- Monitor API usage to stay within limits

## API Rate Limits

### Typical Limits

- **Amazon PA-API**: 1 request per second, 8640 requests per day (free tier)
- **Google Custom Search**: 100 queries per day per API key (free tier), paid plans available
  - With multiple API keys: 100 × number of keys per day
- **Bing Image Search**: Varies by subscription level

### Best Practices

- Start with conservative rate limits
- Monitor actual usage vs. limits
- Configure daily caps to prevent overuse
- Use test mode to estimate requirements

## Support

For issues and feature requests, check:
1. Processing logs for error details
2. Odoo server logs for system-level errors
3. API provider documentation for service-specific issues

## Security Notes

- API keys are stored encrypted in the database
- Use password-protected fields for sensitive configuration
- Consider using environment variables for production API keys
- Regularly rotate API credentials

## Compliance

This module respects:
- API terms of service for all integrated services
- Rate limiting requirements
- Image usage rights (links to original sources)
- GDPR considerations for logging (configurable retention)