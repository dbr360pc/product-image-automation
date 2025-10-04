#!/usr/bin/env python3
"""
Google Custom Search API Test Script
This script tests your Google API credentials for the Product Image Automation module.

Usage:
1. Get your API Key from Google Cloud Console
2. Use your Custom Search Engine ID: 51f584a10f7ed43c1
3. Run this script to test before configuring Odoo

Requirements:
pip install requests
"""

import requests
import json
import sys

def test_google_custom_search():
    """Test Google Custom Search API with your credentials"""
    
    # Configuration - UPDATE THESE VALUES
    API_KEY = "AIzaSyD1NiiEJCUZBCyWrQrYaFuwXpc45ycqdWY"  # Replace with your actual API key from Google Cloud Console
    SEARCH_ENGINE_ID = "51f584a10f7ed43c1"  # Your Custom Search Engine ID (already correct)
    
    # Test search terms (using your actual products)
    test_queries = [
        "TP-LINK TL-WN821 Wireless 300Mbps",
        "HPE ProLiant MicroServer Gen11",
        "TP-LINK EAP225 Ceiling Mounted Wireless",
        "adapter 5V 2A power supply"
    ]
    
    print("=" * 60)
    print("Google Custom Search API Test")
    print("=" * 60)
    print(f"API Key: {API_KEY[:20]}...")
    print(f"Search Engine ID: {SEARCH_ENGINE_ID}")
    print("=" * 60)
    
    # Check if credentials are set
    if API_KEY == "YOUR_API_KEY_HERE":
        print("❌ ERROR: Please update the API_KEY variable with your actual API key!")
        print("\nHow to get your API Key:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Select project: gmao-471805")
        print("3. APIs & Services → Credentials")
        print("4. + CREATE CREDENTIALS → API Key")
        print("5. Copy the key and replace 'YOUR_API_KEY_HERE' in this script")
        return False
    
    success_count = 0
    
    for i, query in enumerate(test_queries, 1):
        print(f"\nTest {i}: Searching for '{query}'")
        print("-" * 40)
        
        try:
            # Google Custom Search API endpoint
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': API_KEY,
                'cx': SEARCH_ENGINE_ID,
                'q': query,
                'searchType': 'image',
                'imgSize': 'large',
                'imgType': 'photo',
                'num': 3,
                'safe': 'active'
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'items' in data and len(data['items']) > 0:
                    print(f"✅ SUCCESS: Found {len(data['items'])} images")
                    success_count += 1
                    
                    # Show first image details
                    item = data['items'][0]
                    print(f"   Image URL: {item.get('link', 'N/A')}")
                    print(f"   Title: {item.get('title', 'N/A')[:50]}...")
                    
                    # Check image dimensions if available
                    if 'image' in item:
                        img_info = item['image']
                        width = img_info.get('width', 'Unknown')
                        height = img_info.get('height', 'Unknown')
                        print(f"   Size: {width} x {height}")
                    
                else:
                    print("⚠️  WARNING: No images found for this query")
                    if 'searchInformation' in data:
                        total_results = data['searchInformation'].get('totalResults', '0')
                        print(f"   Total results: {total_results}")
                
            elif response.status_code == 403:
                error_data = response.json()
                error_message = error_data.get('error', {}).get('message', 'Unknown error')
                print(f"❌ ERROR 403: {error_message}")
                
                if "API key not valid" in error_message:
                    print("   → Check your API key")
                elif "Custom Search API" in error_message:
                    print("   → Enable Custom Search API in Google Cloud Console")
                elif "quota" in error_message.lower():
                    print("   → You may have exceeded your daily quota (100 free searches)")
                
                break
                
            elif response.status_code == 400:
                error_data = response.json()
                print(f"❌ ERROR 400: {error_data}")
                break
                
            else:
                print(f"❌ ERROR: HTTP {response.status_code}")
                print(f"Response: {response.text[:200]}...")
                break
                
        except requests.exceptions.Timeout:
            print("❌ ERROR: Request timeout (30 seconds)")
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR: Network error - {str(e)}")
        except json.JSONDecodeError:
            print("❌ ERROR: Invalid JSON response")
        except Exception as e:
            print(f"❌ ERROR: Unexpected error - {str(e)}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if success_count > 0:
        print(f"✅ SUCCESS: {success_count}/{len(test_queries)} searches worked!")
        print("\n🎉 Your Google API credentials are working correctly!")
        print("\nNext steps:")
        print("1. Go to Sales → Image Automation → Configuration in Odoo")
        print("2. Enable 'Use Google Images Fallback'")
        print(f"3. Enter API Key: {API_KEY}")
        print(f"4. Enter Search Engine ID: {SEARCH_ENGINE_ID}")
        print("5. Test the configuration in Odoo")
        
        # Calculate estimated usage
        print(f"\n💰 Usage Information:")
        print(f"   - Free tier: 100 searches/day")
        print(f"   - This test used: {success_count} searches")
        print(f"   - Remaining today: ~{100 - success_count} searches")
        
    else:
        print("❌ FAILED: No searches worked. Check your credentials!")
        print("\nTroubleshooting:")
        print("1. Verify your API key is correct")
        print("2. Enable 'Custom Search API' in Google Cloud Console")
        print("3. Check your Custom Search Engine settings")
        print("4. Ensure image search is enabled in your CSE")
    
    return success_count > 0

def check_requirements():
    """Check if required packages are installed"""
    try:
        import requests
        return True
    except ImportError:
        print("❌ ERROR: 'requests' package not installed")
        print("Please install it with: pip install requests")
        return False

if __name__ == "__main__":
    print("Google Custom Search API Test Script")
    print("For trionica.ec Product Image Automation")
    print()
    
    if not check_requirements():
        sys.exit(1)
    
    # Instructions
    print("Before running this test:")
    print("1. Get your API Key from Google Cloud Console")
    print("2. Edit this script and replace 'YOUR_API_KEY_HERE' with your actual key")
    print("3. Run the script again")
    print()
    
    success = test_google_custom_search()
    
    if success:
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Failure