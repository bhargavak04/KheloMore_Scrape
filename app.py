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
    
    async def safe_extract(self, page, selector, default=""):
        """Safely extract text from a selector with multiple fallback options"""
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                if text and text.strip():
                    return ' '.join(text.split()).strip()
            return default
        except Exception as e:
            logger.debug(f"Failed to extract with selector {selector}: {str(e)}")
            return default
    
    async def extract_text_content(self, element):
        """Extract and clean text content from an element"""
        try:
            text = await element.inner_text()
            # Clean up whitespace and newlines
            text = ' '.join(text.split())
            return text.strip()
        except Exception as e:
            logger.warning(f"Error extracting text: {str(e)}")
            return ""
    
    async def load_all_venues(self, page):
        """Load all venues by clicking load more buttons"""
        logger.info("Starting to load all venues...")
        
        max_attempts = 20  # Reduced to prevent long running times
        attempts = 0
        last_count = 0
        same_count = 0
        
        while attempts < max_attempts:
            try:
                # Wait for page to be interactive
                await page.wait_for_load_state("networkidle", timeout=10000)
                await asyncio.sleep(2)
                
                # Try multiple selectors to find venue cards
                venue_selectors = [
                    "div[class*='VenueCard']",
                    "div[data-testid*='venue']",
                    "div.card",
                    "div[class*='venue-card']",
                    "//div[contains(@class, 'venue')]"
                ]
                
                current_venues = []
                for selector in venue_selectors:
                    venues = await page.query_selector_all(selector)
                    if venues:
                        current_venues = venues
                        break
                
                current_count = len(current_venues)
                logger.info(f"Currently loaded venues: {current_count}")
                
                # Check if we're stuck at the same count
                if current_count == last_count:
                    same_count += 1
                    if same_count >= 3:  # If we've had the same count 3 times in a row
                        logger.info("No new venues loaded in last 3 attempts")
                        break
                else:
                    same_count = 0
                    last_count = current_count
                
                # Scroll to bottom to trigger lazy loading
                await page.evaluate("""
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                """)
                await asyncio.sleep(3)  # Wait for any lazy loading
                
                # Try to find and click load more button if it exists
                load_more_selectors = [
                    "button:has-text('Load More')",
                    "div:has-text('Load More')",
                    "button:has-text('Show More')",
                    "div:has-text('Show More')",
                    "//button[contains(., 'Load More')]",
                    "//div[contains(., 'Load More')]"
                ]
                
                load_more_clicked = False
                for selector in load_more_selectors:
                    try:
                        load_more = await page.query_selector(selector)
                        if load_more and await load_more.is_visible():
                            await load_more.click()
                            logger.info(f"Clicked load more button: {selector}")
                            load_more_clicked = True
                            await asyncio.sleep(3)  # Wait for content to load
                            break
                    except Exception as e:
                        continue
                
                # If no load more button found, we might be done
                if not load_more_clicked:
                    logger.info("No load more button found, checking if we have all venues")
                    # Check if we've scrolled to the bottom
                    at_bottom = await page.evaluate("""
                        (window.innerHeight + window.scrollY) >= document.body.offsetHeight - 100
                    """)
                    if at_bottom:
                        logger.info("Reached bottom of page")
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
                )
                
                # Set default timeout
                context.set_default_timeout(30000)
                
                page = await context.new_page()
                
                # Navigate to city page with retries
                city_url = f"https://www.khelomore.com/venues/{city.lower().replace(' ', '-')}"
                max_navigation_attempts = 3
                
                for attempt in range(max_navigation_attempts):
                    try:
                        logger.info(f"Navigating to {city_url} (attempt {attempt + 1}/{max_navigation_attempts})")
                        await page.goto(city_url, wait_until="networkidle", timeout=60000)
                        await asyncio.sleep(5)  # Wait for initial load
                        
                        # Check if we're on the right page
                        if "page not found" in (await page.title()).lower():
                            raise Exception(f"Page not found: {city_url}")
                            
                        break  # Success
                        
                    except Exception as e:
                        if attempt == max_navigation_attempts - 1:
                            raise
                        logger.warning(f"Navigation attempt {attempt + 1} failed: {str(e)}")
                        await asyncio.sleep(5)
                
                # Load all venues with improved error handling
                logger.info("Loading all venues...")
                venue_elements = await self.load_all_venues(page)
                
                if not venue_elements:
                    logger.warning(f"No venues found for {city}")
                    return city_venues
                
                total_venues = len(venue_elements)
                logger.info(f"Found {total_venues} venues in {city}")
                
                # Process venues with better error handling
                for idx, venue in enumerate(venue_elements, 1):
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            logger.info(f"Processing venue {idx}/{total_venues} in {city} (attempt {attempt + 1}/{max_retries})")
                            
                            # Scroll to and click the venue
                            await venue.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                            await venue.click()
                            
                            # Wait for details to load
                            try:
                                await page.wait_for_selector("div[class*='venue-details']", timeout=10000)
                            except:
                                pass  # Continue even if specific selector not found
                                
                            await asyncio.sleep(3)  # Additional wait for content
                            
                            # Extract venue data
                            venue_info = await self.extract_venue_data(page)
                            if venue_info:
                                venue_info.update({
                                    'city': city,
                                    'scraped_at': datetime.now().isoformat(),
                                    'venue_url': page.url
                                })
                                city_venues.append(venue_info)
                                logger.info(f"Scraped: {venue_info.get('name', 'Unknown')} in {city}")
                            
                            # Go back to list
                            await page.go_back(wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                            
                            # Re-query venues to avoid stale references
                            venue_elements = await self.load_all_venues(page)
                            if idx < len(venue_elements):
                                venue = venue_elements[idx]
                            
                            break  # Success, exit retry loop
                            
                        except Exception as e:
                            logger.error(f"Error processing venue {idx} in {city}: {str(e)}")
                            if attempt == max_retries - 1:
                                logger.error(f"Failed to process venue {idx} in {city} after {max_retries} attempts")
                                # Try to recover by reloading the page
                                try:
                                    await page.reload(wait_until="domcontentloaded")
                                    await asyncio.sleep(5)
                                    venue_elements = await self.load_all_venues(page)
                                    if idx < len(venue_elements):
                                        venue = venue_elements[idx]
                                except:
                                    pass
                            else:
                                await asyncio.sleep(3)  # Wait before retry
                
                logger.info(f"Completed scraping {city}: {len(city_venues)} venues")
                
            except Exception as e:
                logger.error(f"Error scraping city {city}: {str(e)}")
                self.failed_cities.append(city)
                import traceback
                logger.error(traceback.format_exc())
                
            finally:
                if browser:
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
    # Print startup message to help with debugging
    print(f"Starting server on port {port}")
    print("Environment variables:", os.environ)
    app.run(host="0.0.0.0", port=port, debug=False)