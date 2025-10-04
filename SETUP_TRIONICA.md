# Setup Guide for trionica.ec - Product Image Automation

## Quick Start for trionica.ec

This guide provides specific setup instructions for implementing automated product image fetching on trionica.ec using Odoo 16.

## 1. Pre-Installation Requirements

### System Requirements
- Odoo 16 Enterprise or Community
- Python 3.8+ with pip
- Internet access for API calls
- At least 1GB free disk space for images

### API Accounts Setup

Before installation, set up accounts with image providers:

#### Option A: Google Images (Recommended for Starting)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable "Custom Search API"
4. Create credentials (API Key)
5. Go to [Google Custom Search](https://cse.google.com/cse/)
6. Create a new search engine
7. Set search the entire web
8. Enable Image search
9. Note down the Search Engine ID

**Cost**: 100 free queries/day, then $5 per 1000 queries

#### Option B: Amazon Product Advertising API (Best Quality)
1. Sign up for Amazon Associates program
2. Apply for Product Advertising API access
3. Get approved (can take 1-2 weeks)
4. Get your Access Key, Secret Key, and Associate Tag

**Cost**: Free up to 8,640 requests/day

#### Option C: Bing Images (Alternative)
1. Go to [Azure Portal](https://portal.azure.com/)
2. Create Bing Search v7 resource
3. Get subscription key

**Cost**: Free tier available

## 2. Installation Steps

### Step 1: Install Python Dependencies
```bash
# Install required Python packages
pip install requests Pillow numpy lxml
```

### Step 2: Install Odoo Module
1. Copy the module folder to your Odoo addons directory:
   ```
   /opt/odoo/addons/product_image_automation/
   ```

2. Restart Odoo server

3. Update Apps List:
   - Go to Apps menu
   - Click "Update Apps List"

4. Install the module:
   - Search for "Product Image Automation"
   - Click Install

### Step 3: Initial Configuration

1. **Go to Configuration**:
   - Sales → Image Automation → Configuration
   - Or Settings → Image Automation

2. **Configure Image Source** (Choose one to start):

   **For Google Images**:
   - Enable "Use Google Images Fallback"
   - Enter your Google API Key
   - Enter your Custom Search Engine ID
   
   **For Amazon PA-API**:
   - Enable "Use Amazon Product Advertising API"
   - Enter Access Key, Secret Key, Partner Tag
   - Select your marketplace (likely 'US' or 'CA' for trionica.ec)

3. **Quality Settings** (Recommended for trionica.ec):
   ```
   Minimum Width: 800px
   Minimum Height: 600px
   Maximum Size: 3MB
   Preferred Formats: JPEG and PNG
   ```

4. **Rate Limiting** (Conservative start):
   ```
   Requests per Minute: 30
   Daily Limit: 500
   Batch Size: 25
   ```

5. **Enable Test Mode**:
   - Check "Test Mode"
   - Set "Test Product Limit: 10"

## 3. Initial Testing

### Test Configuration
1. Click "Test Configuration" button
2. Check Processing Logs for results
3. Verify API credentials work

### Run Small Test
1. Go to Sales → Image Automation → Products Needing Images
2. Select 5-10 products manually
3. Click "Fetch Images" button
4. Monitor logs in Processing Logs menu

### Verify Results
1. Check that images appear on products
2. Review log entries for success/failure rates
3. Adjust quality settings if needed

## 4. Production Setup

Once testing is successful:

### Disable Test Mode
1. Uncheck "Test Mode" in configuration
2. Enable "Daily Cron Job"
3. Set cron time (recommend 2-4 AM)

### Optimize Settings
Based on test results, adjust:
- Increase batch size if no timeouts
- Increase rate limits if APIs allow
- Adjust quality requirements based on results

### Run Backfill
1. Click "Run Backfill Job" to process existing products
2. Monitor progress in logs
3. This will process ALL products, so monitor API usage

## 5. Monitoring and Maintenance

### Daily Monitoring
- Check Processing Logs daily
- Monitor API usage vs limits
- Review failed products

### Weekly Tasks
- Review error patterns
- Optimize search terms for failed products
- Check API billing/usage

### Monthly Maintenance
- Review and update API credentials
- Clean up old logs (automated)
- Analyze success rates and optimize

## 6. Product Data Optimization for trionica.ec

To improve image matching success:

### Required Product Fields
Ensure products have:
- Clear, descriptive names
- SKU/Product Code (default_code)
- Barcode/EAN if available
- Product category

### Recommended Additional Fields
- UPC Code (for Amazon)
- Manufacturer Part Number
- Brand/Manufacturer name

### Naming Conventions
Use descriptive product names like:
- ❌ "Widget 123"
- ✅ "Bluetooth Wireless Headphones Sony WH-1000XM4"

## 7. Troubleshooting for trionica.ec

### Common Issues

**No Images Found**
- Check product names are descriptive enough
- Verify API credentials
- Check image quality requirements aren't too strict
- Review search terms in logs

**Rate Limiting (429 errors)**
- Reduce requests per minute
- Check daily API limits
- Spread processing across more time

**Poor Image Quality**
- Images too small: Lower minimum size requirements
- Wrong products: Improve product names and descriptions
- Watermarks: Try different image sources

### Getting Help
1. Check Processing Logs for error details
2. Review Odoo server logs
3. Test API credentials manually
4. Check API provider status pages

## 8. Scaling Recommendations

### For Large Product Catalogs (>1000 products)
- Use Amazon PA-API for better matching
- Process in smaller batches during off-hours
- Consider multiple API accounts for higher limits
- Monitor server resources during bulk processing

### Cost Management
- Start with free tiers
- Monitor usage patterns
- Optimize success rates to reduce API calls
- Consider caching and deduplication

## 9. Compliance and Legal

### Image Rights
- This module links to images, doesn't republish them
- Ensure compliance with image source terms of service
- Consider obtaining proper licensing for commercial use
- Amazon Associates program requires proper disclosure

### Data Privacy
- API keys stored encrypted in database
- Logs contain product data - review retention policies
- Consider GDPR compliance for EU customers

## 10. Success Metrics for trionica.ec

Track these KPIs:
- **Coverage**: % of products with images
- **Success Rate**: % of successful image fetches
- **Quality Score**: Average image quality ratings
- **Cost Efficiency**: Cost per successful image
- **Performance**: Processing time per product

Target goals:
- 95%+ product image coverage
- 80%+ success rate on first attempt
- <$0.01 cost per image
- <5 seconds processing per product

## Next Steps

1. Complete API account setup
2. Install and configure module with test mode
3. Test with 10-20 products
4. Gradually increase batch sizes
5. Enable production mode and daily automation
6. Monitor and optimize based on results

For technical support or questions specific to trionica.ec implementation, refer to the logs and adjust settings based on your product catalog characteristics.