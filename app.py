import asyncio
import json
import pandas as pd
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright
from flask import Flask, send_file, jsonify, render_template_string
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cities to scrape
CITIES = [
    "bengaluru", "pune", "mumbai", "surat", "hyderabad", "delhi-&-ncr",
    "ahmedabad", "nagpur", "kolkata", "navi-mumbai", "gurugram", "noida",
    "delhi", "faridabad", "secunderabad", "ghaziabad", "kochi", "jabalpur",
    "jaipur", "chitilappilly", "thrissur", "thiruvananthapuram", "nashik",
    "chandigarh", "kolhapur", "warangal", "margao", "vadodara", "kannur",
    "kollam", "kottayam", "chennai", "nellore", "wayanad", "indore",
    "kozhikode", "malappuram", "palakkad", "coimbatore", "jalgaon",
    "sangli", "nagaur"
]

class VenueScraper:
    def __init__(self):
        self.venues_data = []
        self.failed_cities = []
        self.scraped_cities = []
        
    async def wait_for_element_with_retry(self, page, selector, timeout=30000, max_retries=3):
        """Wait for element with retry logic"""
        for attempt in range(max_retries):
            try:
                if selector.startswith("xpath="):
                    element = await page.wait_for_selector(selector, timeout=timeout)
                else:
                    element = await page.wait_for_selector(selector, timeout=timeout)
                    
                if element and await element.is_visible():
                    return element
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for selector {selector}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
        return None
    
    async def safe_click(self, element, page):
        """Safely click an element with error handling"""
        try:
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            await element.click()
            await asyncio.sleep(2)  # Wait for action to complete
            return True
        except Exception as e:
            logger.error(f"Failed to click element: {str(e)}")
            return False
    
    async def get_venue_elements(self, page):
        """Get all venue elements using multiple selectors"""
        venue_selectors = [
            "div[data-testid*='venue']",  # Common pattern for venues
            "div[class*='venue-card']",
            "div[class*='venue-item']",
            "div[class*='card']",
            "[data-venue-id]",
            # Fallback to the original selector but more flexible
            "#root div div div div div[2] div[2] div[2] > div",
            # Alternative structure selectors
            "div[role='button']",
            "a[href*='/venue/']",
            "div[onclick*='venue']"
        ]
        
        for selector in venue_selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    logger.info(f"Found {len(elements)} venues using selector: {selector}")
                    return elements
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {str(e)}")
                continue
        
        # If no specific selectors work, try a more generic approach
        try:
            # Look for clickable divs that might be venues
            all_divs = await page.query_selector_all("div")
            venue_divs = []
            
            for div in all_divs:
                try:
                    # Check if div might be a venue by looking for common patterns
                    text_content = await div.text_content()
                    if text_content and any(keyword in text_content.lower() for keyword in 
                                          ['₹', 'rating', 'open', 'closed', 'sports', 'court', 'field']):
                        venue_divs.append(div)
                except:
                    continue
            
            if venue_divs:
                logger.info(f"Found {len(venue_divs)} potential venues using generic approach")
                return venue_divs[:50]  # Limit to first 50 to avoid false positives
                
        except Exception as e:
            logger.error(f"Generic venue detection failed: {str(e)}")
        
        return []
    
    async def load_all_venues(self, page):
        """Load all venues by clicking load more buttons"""
        logger.info("Starting to load all venues...")
        
        max_attempts = 30
        attempts = 0
        consecutive_failures = 0
        last_venue_count = 0
        
        while attempts < max_attempts and consecutive_failures < 3:
            try:
                # Wait for page to stabilize
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(3)
                
                # Get current venues using flexible selectors
                current_venues = await self.get_venue_elements(page)
                current_count = len(current_venues)
                
                logger.info(f"Currently loaded venues: {current_count}")
                
                # Check if we have new venues
                if current_count == last_venue_count:
                    consecutive_failures += 1
                    logger.info(f"No new venues loaded. Consecutive failures: {consecutive_failures}")
                else:
                    consecutive_failures = 0
                    last_venue_count = current_count
                
                # Scroll to bottom to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)
                
                # Try to find and click load more button
                load_more_clicked = False
                
                # Enhanced load more button detection
                load_more_patterns = [
                    # Text-based selectors
                    "text='Load More'",
                    "text='load more'",
                    "text='Load more'",
                    "text='LOAD MORE'",
                    "text='Show More'",
                    "text='View More'",
                    
                    # Button selectors
                    "button:has-text('Load')",
                    "button:has-text('More')",
                    "div:has-text('Load More')",
                    "span:has-text('Load More')",
                    
                    # Class-based selectors
                    "[class*='load-more']",
                    "[class*='loadmore']",
                    "[class*='load_more']",
                    "[class*='show-more']",
                    "[class*='view-more']",
                    
                    # Generic button selectors
                    "button[class*='load']",
                    "div[class*='load']",
                    "button[class*='more']",
                    "div[class*='more']",
                    
                    # XPath alternatives
                    "xpath=//button[contains(text(), 'Load') or contains(text(), 'More')]",
                    "xpath=//div[contains(text(), 'Load More') or contains(text(), 'Show More')]",
                    "xpath=//span[contains(text(), 'Load More')]",
                    "xpath=//*[contains(@class, 'load') and contains(@class, 'more')]",
                    "xpath=//*[contains(@onclick, 'load') or contains(@onclick, 'more')]"
                ]
                
                for pattern in load_more_patterns:
                    try:
                        elements = await page.query_selector_all(pattern)
                        for element in elements:
                            if await element.is_visible():
                                success = await self.safe_click(element, page)
                                if success:
                                    logger.info(f"Clicked load more using pattern: {pattern}")
                                    load_more_clicked = True
                                    break
                        if load_more_clicked:
                            break
                    except Exception as e:
                        logger.debug(f"Pattern {pattern} failed: {str(e)}")
                        continue
                
                if load_more_clicked:
                    # Wait for new content to load
                    await page.wait_for_load_state("networkidle", timeout=20000)
                    await asyncio.sleep(5)
                    
                    # Verify new content loaded
                    new_venues = await self.get_venue_elements(page)
                    new_count = len(new_venues)
                    
                    if new_count > current_count:
                        logger.info(f"Successfully loaded {new_count - current_count} new venues")
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        logger.warning("Load more clicked but no new venues loaded")
                else:
                    logger.info("No load more button found")
                    consecutive_failures += 1
                
                attempts += 1
                
            except Exception as e:
                logger.error(f"Error in loading loop: {str(e)}")
                consecutive_failures += 1
                attempts += 1
                await asyncio.sleep(5)
        
        # Get final count
        final_venues = await self.get_venue_elements(page)
        final_count = len(final_venues)
        logger.info(f"Final venue count: {final_count}")
        return final_count
    
    async def extract_text_content(self, element):
        """Extract text content with better formatting"""
        try:
            text_content = await element.text_content()
            if not text_content:
                return "N/A"
            return text_content.strip()
        except Exception as e:
            logger.warning(f"Error extracting text content: {str(e)}")
            return "N/A"

    async def extract_venue_data(self, page):
        """Extract venue data from current page with improved selectors"""
        venue_info = {}
        
        # Wait for page to load completely
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # Define selectors with fallbacks
        selectors = {
            'name': [
                "h1",
                "h2",
                "[data-testid*='venue-name']",
                "[class*='venue-name']",
                "[class*='title']",
                "xpath=//h1 | //h2 | //*[contains(@class, 'name')]"
            ],
            'price': [
                "[class*='price']",
                "[data-testid*='price']",
                "xpath=//*[contains(text(), '₹')]",
                "xpath=//*[contains(@class, 'price')]"
            ],
            'timing': [
                "[class*='timing']",
                "[class*='hours']",
                "[data-testid*='timing']",
                "xpath=//*[contains(text(), 'AM') or contains(text(), 'PM')]",
                "xpath=//*[contains(@class, 'timing') or contains(@class, 'hours')]"
            ],
            'address': [
                "[class*='address']",
                "[class*='location']",
                "[data-testid*='address']",
                "xpath=//*[contains(@class, 'address') or contains(@class, 'location')]"
            ],
            'rating': [
                "[class*='rating']",
                "[data-testid*='rating']",
                "xpath=//*[contains(@class, 'rating')]//span[1]",
                "xpath=//*[contains(text(), '★') or contains(text(), '⭐')]"
            ],
            'raters': [
                "[class*='raters']",
                "[class*='reviews']",
                "xpath=//*[contains(@class, 'rating')]//span[2]",
                "xpath=//*[contains(text(), 'review') or contains(text(), 'rating')]"
            ]
        }
        
        # Extract basic information with fallbacks
        for key, selector_list in selectors.items():
            venue_info[key] = "N/A"
            
            for selector in selector_list:
                try:
                    if selector.startswith("xpath="):
                        elements = await page.query_selector_all(selector)
                    else:
                        elements = await page.query_selector_all(selector)
                    
                    for element in elements:
                        if await element.is_visible():
                            text = await self.extract_text_content(element)
                            if text and text != "N/A" and len(text.strip()) > 0:
                                venue_info[key] = text
                                break
                    
                    if venue_info[key] != "N/A":
                        break
                        
                except Exception as e:
                    logger.debug(f"Selector {selector} failed for {key}: {str(e)}")
                    continue
        
        # Extract additional information using more flexible selectors
        additional_info = {
            'about_venue': ["[class*='about']", "[class*='description']", "xpath=//*[contains(@class, 'about') or contains(@class, 'description')]"],
            'available_sports': ["[class*='sports']", "[class*='activities']", "xpath=//*[contains(@class, 'sports') or contains(@class, 'activities')]"],
            'highlights': ["[class*='highlight']", "[class*='features']", "xpath=//*[contains(@class, 'highlight') or contains(@class, 'features')]"],
            'amenities': ["[class*='amenities']", "[class*='facilities']", "xpath=//*[contains(@class, 'amenities') or contains(@class, 'facilities')]"],
            'offer': ["[class*='offer']", "[class*='deal']", "xpath=//*[contains(@class, 'offer') or contains(@class, 'deal')]"]
        }
        
        for key, selector_list in additional_info.items():
            venue_info[key] = "N/A"
            
            for selector in selector_list:
                try:
                    if selector.startswith("xpath="):
                        elements = await page.query_selector_all(selector)
                    else:
                        elements = await page.query_selector_all(selector)
                    
                    for element in elements:
                        if await element.is_visible():
                            text = await self.extract_text_content(element)
                            if text and text != "N/A" and len(text.strip()) > 0:
                                venue_info[key] = text
                                break
                    
                    if venue_info[key] != "N/A":
                        break
                        
                except Exception as e:
                    logger.debug(f"Selector {selector} failed for {key}: {str(e)}")
                    continue
        
        # Try to extract modal information (facilities, venue rules)
        modal_info = ['facilities', 'venue_rules']
        for modal_type in modal_info:
            venue_info[modal_type] = "N/A"
            
            try:
                # Look for buttons that might open modals
                modal_buttons = await page.query_selector_all("button, div[role='button'], [class*='modal'], [class*='popup']")
                
                for button in modal_buttons:
                    try:
                        button_text = await button.text_content()
                        if button_text and modal_type.replace('_', ' ').lower() in button_text.lower():
                            if await button.is_visible():
                                await self.safe_click(button, page)
                                await asyncio.sleep(2)
                                
                                # Look for modal content
                                modal_content = await page.query_selector("[role='dialog'], [class*='modal'], [class*='popup']")
                                if modal_content:
                                    content_text = await self.extract_text_content(modal_content)
                                    if content_text and content_text != "N/A":
                                        venue_info[modal_type] = content_text
                                    
                                    # Close modal
                                    close_buttons = await page.query_selector_all("[aria-label*='close'], [class*='close'], button:has-text('×')")
                                    for close_btn in close_buttons:
                                        if await close_btn.is_visible():
                                            await self.safe_click(close_btn, page)
                                            break
                                
                                break
                    except Exception as e:
                        logger.debug(f"Modal extraction failed: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Failed to extract {modal_type}: {str(e)}")
        
        # Get page URL as additional info
        venue_info['url'] = page.url
        
        # Log extracted data for debugging
        logger.info(f"Extracted venue data: {venue_info.get('name', 'Unknown venue')}")
        
        return venue_info
    
    async def scrape_city_venues(self, city):
        """Scrape venues for a specific city"""
        logger.info(f"Starting to scrape venues for {city}")
        city_venues = []
        
        async with async_playwright() as playwright:
            try:
                # Launch browser
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-extensions',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-blink-features=AutomationControlled'
                    ]
                )
                
                page = await browser.new_page()
                
                # Set realistic viewport and user agent
                await page.set_viewport_size({"width": 1920, "height": 1080})
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
                
                url = f"https://www.khelomore.com/sports-venues/{city}/sports/all"
                logger.info(f"Navigating to: {url}")
                
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(5)
                
                # Load all venues
                total_venues = await self.load_all_venues(page)
                
                if total_venues == 0:
                    logger.warning(f"No venues found for {city}")
                    return city_venues
                
                # Get all venue elements
                venue_elements = await self.get_venue_elements(page)
                
                # Process venues
                processed_count = 0
                max_retries = 3
                
                for i, venue in enumerate(venue_elements):
                    if processed_count >= min(total_venues, 50):  # Limit per city
                        break
                        
                    retry_count = 0
                    
                    while retry_count < max_retries:
                        try:
                            logger.info(f"Processing venue {processed_count + 1}/{min(total_venues, 50)} in {city}")
                            
                            # Scroll venue into view and click
                            await venue.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                            
                            # Try clicking the venue
                            success = await self.safe_click(venue, page)
                            if not success:
                                # Try alternative click methods
                                await page.evaluate("arguments[0].click()", venue)
                                await asyncio.sleep(2)
                            
                            # Wait for venue details page
                            await page.wait_for_load_state("domcontentloaded", timeout=30000)
                            await asyncio.sleep(3)
                            
                            # Extract venue data
                            venue_info = await self.extract_venue_data(page)
                            venue_info['city'] = city
                            venue_info['scraped_at'] = datetime.now().isoformat()
                            
                            city_venues.append(venue_info)
                            logger.info(f"Scraped: {venue_info.get('name', 'Unknown')} in {city}")
                            
                            # Go back to list
                            await page.go_back()
                            await page.wait_for_load_state("domcontentloaded", timeout=30000)
                            await asyncio.sleep(3)
                            
                            # Re-get venue elements as they might be stale
                            venue_elements = await self.get_venue_elements(page)
                            
                            break  # Success, exit retry loop
                            
                        except Exception as e:
                            logger.error(f"Error processing venue {processed_count + 1} in {city}, attempt {retry_count + 1}: {str(e)}")
                            retry_count += 1
                            
                            if retry_count < max_retries:
                                try:
                                    await page.go_back()
                                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                                    await asyncio.sleep(3)
                                    venue_elements = await self.get_venue_elements(page)
                                except:
                                    pass
                            else:
                                logger.error(f"Failed to process venue {processed_count + 1} in {city} after {max_retries} attempts")
                    
                    processed_count += 1
                
                await browser.close()
                logger.info(f"Completed scraping {city}: {len(city_venues)} venues")
                
            except Exception as e:
                logger.error(f"Error scraping city {city}: {str(e)}")
                self.failed_cities.append(city)
                try:
                    await browser.close()
                except:
                    pass
        
        return city_venues
    
    async def scrape_all_cities(self):
        """Scrape venues from all cities"""
        logger.info("Starting to scrape all cities")
        
        for city in CITIES:
            try:
                city_venues = await self.scrape_city_venues(city)
                self.venues_data.extend(city_venues)
                self.scraped_cities.append(city)
                
                # Save progress after each city
                self.save_progress()
                
                # Add delay between cities to avoid rate limiting
                await asyncio.sleep(15)
                
            except Exception as e:
                logger.error(f"Failed to scrape {city}: {str(e)}")
                self.failed_cities.append(city)
                continue
        
        logger.info(f"Scraping completed. Total venues: {len(self.venues_data)}")
        logger.info(f"Successful cities: {len(self.scraped_cities)}")
        logger.info(f"Failed cities: {len(self.failed_cities)}")
        
        return self.venues_data
    
    def save_progress(self):
        """Save current progress to files"""
        # Save JSON
        with open('venues_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.venues_data, f, indent=2, ensure_ascii=False)
        
        # Save Excel
        if self.venues_data:
            df = pd.DataFrame(self.venues_data)
            df.to_excel('venues_data.xlsx', index=False)
        
        # Save progress log
        progress = {
            'scraped_cities': self.scraped_cities,
            'failed_cities': self.failed_cities,
            'total_venues': len(self.venues_data),
            'last_updated': datetime.now().isoformat()
        }
        
        with open('progress.json', 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Progress saved: {len(self.venues_data)} venues")

# Flask app for Railway deployment
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Fixed Venue Scraper</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .status { padding: 20px; border-radius: 5px; margin: 20px 0; }
        .success { background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .error { background-color: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .info { background-color: #cce7ff; border: 1px solid #b3d9ff; color: #004085; }
        .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }
        button { padding: 12px 24px; margin: 10px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .progress { margin: 20px 0; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
        .improvements { background: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .improvements h3 { color: #2d5a2d; margin-top: 0; }
        .improvements ul { color: #2d5a2d; }
        h1 { color: #333; text-align: center; }
        .city-count { background: #f0f8ff; padding: 10px; border-radius: 5px; text-align: center; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏟️ Fixed Venue Scraper</h1>
        
        <div class="improvements">
            <h3>🚀 Improvements Made:</h3>
            <ul>
                <li><strong>Flexible Element Detection:</strong> Uses multiple selectors to find venues</li>
                <li><strong>Smart Load More:</strong> Enhanced button detection with multiple patterns</li>
                <li><strong>Robust Data Extraction:</strong> Fallback selectors for each data field</li>
                <li><strong>Better Error Handling:</strong> Retries and graceful degradation</li>
                <li><strong>Stale Element Prevention:</strong> Re-queries elements after navigation</li>
                <li><strong>Rate Limiting:</strong> Increased delays to avoid being blocked</li>
            </ul>
        </div>
        
        <div class="city-count">
            <strong>Cities to scrape: {{ cities|length }}</strong>
        </div>
        
        <div class="info">
            <p><strong>Data being scraped for each venue:</strong></p>
            <ul>
                <li>✅ Venue Name</li>
                <li>💰 Price & Timing</li>
                <li>📍 Address</li>
                <li>⭐ Rating & Number of Raters</li>
                <li>📝 About Venue</li>
                <li>🏃 Available Sports</li>
                <li>🏢 Amenities</li>
                <li>✨ Highlights</li>
                <li>🔧 Facilities (via modal)</li>
                <li>📋 Venue Rules (via modal)</li>
                <li>🎯 Offers</li>
                <li>🔗 URL</li>
            </ul>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <button onclick="startScraping()">🚀 Start Scraping</button>
            <button onclick="checkStatus()">📊 Check Status</button>
            <button onclick="downloadExcel()">📥 Download Excel</button>
        </div>
        
        <div id="status" class="progress"></div>
        
        <script>
            async function startScraping() {
                document.getElementById('status').innerHTML = '<div class="info">🔄 Starting scraping process... This may take a while.</div>';
                try {
                    const response = await fetch('/start_scraping', {method: 'POST'});
                    const result = await response.json();
                    if (result.error) {
                        document.getElementById('status').innerHTML = `<div class="error">❌ Error: ${result.error}</div>`;
                    } else {
                        document.getElementById('status').innerHTML = `<div class="success">✅ ${result.message}</div>`;
                    }
                } catch (error) {
                    document.getElementById('status').innerHTML = `<div class="error">❌ Error: ${error.message}</div>`;
                }
            }
            
            async function checkStatus() {
                try {
                    const response = await fetch('/status');
                    const result = await response.json();
                    document.getElementById('status').innerHTML = `
                        <div class="info">
                            <h3>📈 Scraping Status</h3>
                            <p><strong>Total venues scraped:</strong> ${result.total_venues}</p>
                            <p><strong>Cities completed:</strong> ${result.scraped_cities}</p>
                            <p><strong>Cities failed:</strong> ${result.failed_cities}</p>
                            <p><strong>Last updated:</strong> ${result.last_updated}</p>
                        </div>
                    `;
                } catch (error) {
                    document.getElementById('status').innerHTML = `<div class="error">❌ Error: ${error.message}</div>`;
                }
            }
            
            function downloadExcel() {
                window.location.href = '/download_excel';
            }
            
            // Auto-refresh status every 30 seconds when scraping
            setInterval(checkStatus, 30000);
        </script>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, cities=CITIES)

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    try:
        # Run scraping in background
        scraper = VenueScraper()
        asyncio.run(scraper.scrape_all_cities())
        return jsonify({'message': 'Scraping completed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status')
def status():
    try:
        if os.path.exists('progress.json'):
            with open('progress.json', 'r') as f:
                progress = json.load(f)
            return jsonify(progress)
        else:
            return jsonify({
                'total_venues': 0,
                'scraped_cities': 0,
                'failed_cities': 0,
                'last_updated': 'Never'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_excel')
def download_excel():
    try:
        if os.path.exists('venues_data.xlsx'):
            return send_file('venues_data.xlsx', as_attachment=True)
        else:
            return "No data available for download", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/test_city/<city>')
def test_city(city):
    """Test scraping a single city"""
    try:
        scraper = VenueScraper()
        city_data = asyncio.run(scraper.scrape_city_venues(city))
        return jsonify({
            'city': city,
            'venues_found': len(city_data),
            'sample_data': city_data[:2] if city_data else [],
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'city': city}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)