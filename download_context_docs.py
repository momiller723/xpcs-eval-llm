import os
import json
import time
import re
import random
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# --------------------------------------------------------------------------------
# run with:
# python3 download_xpcs_scholarly.py
# --------------------------------------------------------------------------------

class GoogleScholarPDFDownloader:
    def __init__(self):
        self.output_dir = "xpcs_publications"
        os.makedirs(self.output_dir, exist_ok=True)
        self.download_log = []
        self.setup_driver()
    
    def setup_driver(self):
        """setup Chrome driver with options"""
        chrome_options = Options()
        
        prefs = {
            "download.default_directory": os.path.abspath(self.output_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True  # download PDFs instead of opening them
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # commenting out to see the browser actions happen in real time
        # chrome_options.add_argument("--headless")
        
        self.driver = webdriver.Chrome(options=chrome_options)
    
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    def add_delay(self, min_seconds=2, max_seconds=5):
        """add random delay"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def search_and_download(self, citation, index):
        """search Google Scholar and attempt to download PDF"""
        print(f"\n{'='*60}")
        print(f"Citation #{index}: {citation[:80]}...")
        
        search_url = f"https://scholar.google.com/scholar?q={quote(citation)}"
        print(f"Searching: {search_url}")
        
        try:
            # navigate to Google Scholar
            self.driver.get(search_url)
            self.add_delay(2, 4)
            
            # check if it got blocked
            if "captcha" in self.driver.current_url.lower() or "sorry" in self.driver.title.lower():
                print("Google Scholar is asking for CAPTCHA. Waiting longer...")
                self.add_delay(30, 60)
                return False
            
            # wait for results to load
            wait = WebDriverWait(self.driver, 10)
            
            # look for PDF links
            pdf_found = False
            
            # method 1: look for PDF links - they're usually in a div with class gs_or_ggsm
            try:
                # wait for search results to load
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "gs_r")))
                
                # find PDF links - they're in divs with class gs_or_ggsm
                pdf_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.gs_or_ggsm a")
                
                print(f"Found {len(pdf_elements)} potential PDF links")
                
                for element in pdf_elements:
                    link_text = element.text
                    href = element.get_attribute('href')
                    
                    print(f"  - Link text: '{link_text}', URL: {href[:50]}...")
                    
                    # check if this is a PDF link
                    if '[PDF]' in link_text or href.endswith('.pdf'):
                        print(f"Found PDF link: {href}")
                        
                        # click the link to download
                        print("Clicking PDF link...")
                        element.click()
                        self.add_delay(3, 5)
                        
                        # wait for download to complete
                        time.sleep(5)
                        
                        # check if PDF was downloaded
                        if self.check_download_complete(citation, index):
                            pdf_found = True
                            break
                
                # alternative: try looking for any link with [PDF] text
                if not pdf_found:
                    print("\nTrying alternative PDF link search...")
                    pdf_links = self.driver.find_elements(By.XPATH, "//a[contains(., '[PDF]')]")
                    
                    for link in pdf_links:
                        href = link.get_attribute('href')
                        print(f"Found alternative PDF link: {href}")
                        
                        link.click()
                        self.add_delay(3, 5)
                        time.sleep(5)
                        
                        if self.check_download_complete(citation, index):
                            pdf_found = True
                            break
                
            except Exception as e:
                print(f"Error finding PDF links: {e}")
                
                # debug: print page source snippet to see what's there
                try:
                    results = self.driver.find_elements(By.CLASS_NAME, "gs_r")
                    if results:
                        print("\nDebug - First result HTML snippet:")
                        print(results[0].get_attribute('innerHTML')[:500])
                except:
                    pass
            
            if pdf_found:
                self.download_log.append({
                    'status': 'success',
                    'citation': citation,
                    'index': index
                })
                return True
            else:
                print("Could not find or download PDF")
                self.download_log.append({
                    'status': 'failed',
                    'citation': citation,
                    'reason': 'No PDF found or download failed'
                })
                
                # save the page URL for manual access
                self.save_manual_url(citation, index, self.driver.current_url)
                return False
                
        except Exception as e:
            print(f"Error during search: {e}")
            self.download_log.append({
                'status': 'error',
                'citation': citation,
                'error': str(e)
            })
            return False
    
    def check_download_complete(self, citation, index):
        """check if a PDF was downloaded and rename it"""
        try:
            # extract filename info
            year_match = re.search(r'\b(19|20)\d{2}\b', citation)
            year = year_match.group() if year_match else ""
            author_match = re.match(r'^([A-Za-z]+)', citation)
            author = author_match.group(1) if author_match else ""
            
            filename = f"{index:03d}_{author}_{year}.pdf"
            
            # find the most recent PDF in the download directory
            pdf_files = [f for f in os.listdir(self.output_dir) if f.endswith('.pdf')]
            
            if pdf_files:
                # get the most recent file
                latest_pdf = max(pdf_files, key=lambda f: os.path.getctime(os.path.join(self.output_dir, f)))
                latest_path = os.path.join(self.output_dir, latest_pdf)
                
                # check if this file was created in the last 10 seconds
                if time.time() - os.path.getctime(latest_path) < 10:
                    # rename to our naming convention
                    new_path = os.path.join(self.output_dir, filename)
                    if latest_path != new_path:
                        os.rename(latest_path, new_path)
                        print(f"Downloaded and renamed to: {filename}")
                    else:
                        print(f"Downloaded: {filename}")
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking download: {e}")
            return False
    
    def save_manual_url(self, citation, index, url):
        """save URL for manual download"""
        urls_file = os.path.join(self.output_dir, f"{index:03d}_manual_download.txt")
        with open(urls_file, 'w') as f:
            f.write(f"Citation: {citation}\n\n")
            f.write(f"Google Scholar URL: {url}\n\n")
            f.write("This paper needs to be downloaded manually.\n")
    
    def process_citations(self, citations):
        """Process all citations with added delays"""
        print("AUTOMATED GOOGLE SCHOLAR PDF DOWNLOADER")
        print("======================================")
        print(f"Will process {len(citations)} citations")
        print("Note: Using delays between searches to avoid blocking\n")
        
        success_count = 0
        
        for i, citation in enumerate(citations, 1):
            if self.search_and_download(citation.strip(), i):
                success_count += 1
            
            # longer delay between searches to avoid blocking
            if i < len(citations):
                delay = random.uniform(10, 20)
                print(f"\n⏳ Waiting {delay:.1f} seconds before next search...")
                time.sleep(delay)
        
        # save download log
        log_file = os.path.join(self.output_dir, "download_log.json")
        with open(log_file, 'w') as f:
            json.dump(self.download_log, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"Summary: Downloaded {success_count}/{len(citations)} papers")
        print(f"Check {self.output_dir}/ for PDFs")
        
        # close driver
        self.driver.quit()

# citations present in the 2018 review
citations = [
    "Livet F. 2007. Diffraction with a coherent X-ray beam: dynamics and imaging. Acta Crystallogr. A 63:87–107",
    "Grübel G, Madsen A, Robert A. 2008. X-ray photon correlation spectroscopy (XPCS). In Soft-Matter Characterization, ed. R Borsali, R Pecora, pp. 953–95. New York: Springer",
    "Sutton M. 2008. A review of X-ray intensity fluctuation spectroscopy. C. R. Phys. 9:657–67",
]

if __name__ == "__main__":
    downloader = GoogleScholarPDFDownloader()
    
    # test with first 3 papers
    downloader.process_citations(citations[:3])

    print("\n\n Completed downloads. \n\n")
    