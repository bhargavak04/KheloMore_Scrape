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
            return True
        except Exception as e:
            logger.error(f"Failed to click element: {str(e)}")
            return False
    
    async def load_all_venues(self, page):
        """Load all venues by clicking load more buttons"""
        logger.info("Starting to load all venues...")
        
        max_attempts = 50
        attempts = 0
        consecutive_failures = 0
        
        while attempts < max_attempts and consecutive_failures < 5:
            try:
                # Wait for page to stabilize
                await page.wait_for_load_state("networkidle", timeout=10000)
                await asyncio.sleep(2)
                
                # Count current venues
                current_venues = await page.query_selector_all(
                    "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div"
                )
                current_count = len(current_venues)
                logger.info(f"Currently loaded venues: {current_count}")
                
                # Scroll to bottom to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)
                
                # Try multiple load more button strategies
                load_more_clicked = False
                
                # Strategy 1: Specific xpath for load more button
                load_more_xpath = "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div[21]/div"
                load_more_element = await self.wait_for_element_with_retry(page, f"xpath={load_more_xpath}", timeout=5000)
                
                if load_more_element:
                    success = await self.safe_click(load_more_element, page)
                    if success:
                        logger.info("Clicked load more button using specific xpath")
                        load_more_clicked = True
                
                # Strategy 2: Generic load more selectors
                if not load_more_clicked:
                    load_more_selectors = [
                        "button:has-text('Load More')",
                        "div:has-text('Load More')",
                        "button:has-text('load more')",
                        "div:has-text('load more')",
                        "[class*='load-more']",
                        "[class*='loadmore']",
                        "button[class*='load']",
                        "div[class*='load']",
                        "//div[contains(text(), 'Load More')]",
                        "//button[contains(text(), 'Load More')]",
                        "//div[contains(@class, 'load')]",
                        "//button[contains(@class, 'load')]"
                    ]
                    
                    for selector in load_more_selectors:
                        try:
                            if selector.startswith("//"):
                                element = await page.wait_for_selector(f"xpath={selector}", timeout=3000)
                            else:
                                element = await page.wait_for_selector(selector, timeout=3000)
                            
                            if element and await element.is_visible():
                                success = await self.safe_click(element, page)
                                if success:
                                    logger.info(f"Clicked load more using selector: {selector}")
                                    load_more_clicked = True
                                    break
                        except:
                            continue
                
                if load_more_clicked:
                    consecutive_failures = 0
                    # Wait for new content to load
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(3)
                    
                    # Verify new content loaded
                    new_venues = await page.query_selector_all(
                        "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div"
                    )
                    new_count = len(new_venues)
                    
                    if new_count > current_count:
                        logger.info(f"Successfully loaded {new_count - current_count} new venues")
                    else:
                        consecutive_failures += 1
                        logger.warning("Load more clicked but no new venues loaded")
                else:
                    consecutive_failures += 1
                    logger.info("No load more button found, checking if all content loaded")
                    
                    # Wait and check again
                    await asyncio.sleep(5)
                    final_check = await page.query_selector_all(
                        "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div"
                    )
                    
                    if len(final_check) == current_count:
                        logger.info("All venues appear to be loaded")
                        break
                
                attempts += 1
                
            except Exception as e:
                logger.error(f"Error in loading loop: {str(e)}")
                consecutive_failures += 1
                attempts += 1
                await asyncio.sleep(3)
        
        # Get final count
        final_venues = await page.query_selector_all(
            "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div"
        )
        logger.info(f"Final venue count: {len(final_venues)}")
        return len(final_venues)
    
    async def extract_text_content(self, element):
        """Extract text content with better formatting"""
        try:
            # Get inner HTML to preserve some structure
            inner_html = await element.inner_html()
            
            # Get text content
            text_content = await element.text_content()
            
            if not text_content:
                return "N/A"
            
            # Clean up text content
            text_content = text_content.strip()
            
            # For better readability, try to preserve line breaks
            # Replace common HTML elements with line breaks
            import re
            if inner_html:
                # Add line breaks for common block elements
                formatted_html = re.sub(r'</?(div|li|p|h[1-6]|br)[^>]*>', '\n', inner_html)
                # Remove HTML tags
                formatted_text = re.sub(r'<[^>]+>', '', formatted_html)
                # Clean up multiple whitespaces and newlines
                formatted_text = re.sub(r'\n\s*\n', '\n', formatted_text)
                formatted_text = re.sub(r'\s+', ' ', formatted_text)
                formatted_text = formatted_text.strip()
                
                if formatted_text and len(formatted_text) > len(text_content) * 0.8:
                    return formatted_text
            
            return text_content
            
        except Exception as e:
            logger.warning(f"Error extracting text content: {str(e)}")
            return "N/A"

    async def extract_venue_data(self, page):
        """Extract venue data from current page"""
        venue_info = {}
        
        # Define selectors and their corresponding keys - Updated with your requested selectors
        selectors = {
            'name': "//*[@id='root']/div/div/div/div[4]/div[1]/div[1]/h1",
            'price': "//*[@id='root']/div/div/div/div[4]/div[1]/div[1]/div[3]/div/div[1]",
            'timing': "//*[@id='root']/div/div/div/div[4]/div[1]/div[1]/div[3]/div/div[2]",
            'address': "//*[@id='root']/div/div/div/div[4]/div[1]/div[3]/div[1]/div/div",
            'rating': "//*[@id='root']/div/div/div/div[4]/div[1]/div[3]/div[3]/div/div/div/span[1]",
            'raters': "//*[@id='root']/div/div/div/div[4]/div[1]/div[3]/div[3]/div/div/div/span[2]",
            'about_venue': "//*[@id='root']/div/div/div/div[4]/div[2]/div/div",
            'available_sports': "//*[@id='root']/div/div/div/div[4]/div[3]",
            'highlights': "//*[@id='root']/div/div/div/div[4]/div[4]/div",
            'amenities': "//*[@id='root']/div/div/div/div[4]/div[5]",
            'offer': "//*[@id='root']/div/div/div/div[4]/div[6]"
        }
        
        # Extract basic information
        for key, selector in selectors.items():
            try:
                element = await page.wait_for_selector(f"xpath={selector}", timeout=5000)
                if element:
                    venue_info[key] = await self.extract_text_content(element)
                else:
                    venue_info[key] = "N/A"
            except Exception as e:
                logger.warning(f"Failed to extract {key}: {str(e)}")
                venue_info[key] = "N/A"
        
        # Handle modal dialogs for facilities and venue rules
        modal_selectors = {
            'facilities': {
                'open_btn': "//*[@id='root']/div/div/div/div[4]/div[7]",
                'content': "/html/body/div[4]/div[3]/div/div/div/div[2]",
                'close_btn': "/html/body/div[4]/div[3]/div/div/div/div[1]/div/div[3]/svg"
            },
            'venue_rules': {
                'open_btn': "//*[@id='root']/div/div/div/div[4]/div[8]",
                'content': "/html/body/div[4]/div[3]/div/div/div/div[2]",
                'close_btn': "/html/body/div[4]/div[3]/div/div/div/div[1]/div/div[3]/svg"
            }
        }
        
        for key, modal in modal_selectors.items():
            try:
                open_btn = await page.wait_for_selector(f"xpath={modal['open_btn']}", timeout=3000)
                if open_btn and await open_btn.is_visible():
                    await self.safe_click(open_btn, page)
                    await asyncio.sleep(2)
                    
                    content_element = await page.wait_for_selector(f"xpath={modal['content']}", timeout=5000)
                    if content_element:
                        venue_info[key] = await self.extract_text_content(content_element)
                    else:
                        venue_info[key] = "N/A"
                    
                    # Close modal
                    close_btn = await page.wait_for_selector(f"xpath={modal['close_btn']}", timeout=3000)
                    if close_btn and await close_btn.is_visible():
                        await self.safe_click(close_btn, page)
                        await asyncio.sleep(1)
                else:
                    venue_info[key] = "N/A"
            except Exception as e:
                logger.warning(f"Failed to extract {key} from modal: {str(e)}")
                venue_info[key] = "N/A"
        
        # Log extracted data for debugging
        logger.info(f"Extracted venue data: {venue_info.get('name', 'Unknown venue')}")
        
        return venue_info
    
    async def scrape_city_venues(self, city):
        """Scrape venues for a specific city"""
        logger.info(f"Starting to scrape venues for {city}")
        city_venues = []
        
        async with async_playwright() as playwright:
            try:
                # Launch browser in headless mode for Railway
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-extensions',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                
                page = await browser.new_page()
                
                # Set viewport and user agent
                await page.set_viewport_size({"width": 1920, "height": 1080})
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
                
                # Process venues
                processed_count = 0
                max_retries = 3
                
                while processed_count < total_venues:
                    retry_count = 0
                    
                    while retry_count < max_retries:
                        try:
                            logger.info(f"Processing venue {processed_count + 1}/{total_venues} in {city}")
                            
                            # Re-query venues to avoid stale references
                            current_venues = await page.query_selector_all(
                                "//*[@id='root']/div/div/div/div/div[2]/div[2]/div[2]/div"
                            )
                            
                            if processed_count >= len(current_venues):
                                logger.info("No more venues to process")
                                break
                            
                            venue = current_venues[processed_count]
                            
                            # Click venue
                            await venue.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                            await venue.click()
                            
                            # Wait for venue details
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
                            
                            break  # Success, exit retry loop
                            
                        except Exception as e:
                            logger.error(f"Error processing venue {processed_count + 1} in {city}, attempt {retry_count + 1}: {str(e)}")
                            retry_count += 1
                            
                            if retry_count < max_retries:
                                try:
                                    await page.go_back()
                                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                                    await asyncio.sleep(3)
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
                await asyncio.sleep(10)
                
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
    <title>Venue Scraper</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .status { padding: 20px; border-radius: 5px; margin: 20px 0; }
        .success { background-color: #d4edda; border: 1px solid #c3e6cb; }
        .error { background-color: #f8d7da; border: 1px solid #f5c6cb; }
        .info { background-color: #cce7ff; border: 1px solid #b3d9ff; }
        button { padding: 10px 20px; margin: 10px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .progress { margin: 20px 0; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Venue Scraper</h1>
        <div class="info">
            <p>This tool scrapes venue data from KheloMore for multiple cities in India.</p>
            <p>Cities to scrape: {{ cities|length }}</p>
            <p><strong>Data being scraped:</strong></p>
            <ul>
                <li>Venue Name</li>
                <li>Price & Timing</li>
                <li>Address</li>
                <li>Rating & Number of Raters</li>
                <li>About Venue</li>
                <li>Available Sports</li>
                <li>Amenities</li>
                <li>Highlights</li>
                <li>Facilities (via modal)</li>
                <li>Venue Rules (via modal)</li>
                <li>Offers</li>
            </ul>
        </div>
        
        <button onclick="startScraping()">Start Scraping</button>
        <button onclick="checkStatus()">Check Status</button>
        <button onclick="downloadExcel()">Download Excel</button>
        
        <div id="status" class="progress"></div>
        
        <script>
            async function startScraping() {
                document.getElementById('status').innerHTML = '<div class="info">Starting scraping process...</div>';
                try {
                    const response = await fetch('/start_scraping', {method: 'POST'});
                    const result = await response.json();
                    document.getElementById('status').innerHTML = `<div class="success">${result.message}</div>`;
                } catch (error) {
                    document.getElementById('status').innerHTML = `<div class="error">Error: ${error.message}</div>`;
                }
            }
            
            async function checkStatus() {
                try {
                    const response = await fetch('/status');
                    const result = await response.json();
                    document.getElementById('status').innerHTML = `
                        <div class="info">
                            <h3>Scraping Status</h3>
                            <p>Total venues scraped: ${result.total_venues}</p>
                            <p>Cities completed: ${result.scraped_cities}</p>
                            <p>Cities failed: ${result.failed_cities}</p>
                            <p>Last updated: ${result.last_updated}</p>
                        </div>
                    `;
                } catch (error) {
                    document.getElementById('status').innerHTML = `<div class="error">Error: ${error.message}</div>`;
                }
            }
            
            function downloadExcel() {
                window.location.href = '/download_excel';
            }
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)