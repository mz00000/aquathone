import requests
from bs4 import BeautifulSoup
from selenium.webdriver.firefox.options import Options
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from jinja2 import Environment, FileSystemLoader
import argparse
import os

# Constants for timeouts and batch size
HTTP_TIMEOUT = 5  # Timeout for HTTP requests (in seconds)
BROWSER_TIMEOUT = 10  # Timeout for browser navigation (in seconds)
BATCH_SIZE = 100  # Number of subdomains per report

def fetch_subdomain(subdomain, headers):
    """
    Fetches the HTML content of a subdomain and extracts the page title.
    Also captures a screenshot of the subdomain's homepage.

    Args:
        subdomain (str): The subdomain to fetch.
        headers (dict): The headers to include in the HTTP request.

    Returns:
        tuple: A tuple containing the subdomain, page title, and screenshot filename.
    """
    try:
        url = f"http://{subdomain}"
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        print(f"Subdomain: {subdomain}")
        print(f"Status Code: {response.status_code}")
        
        # Parse the HTML content and extract the title
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title else "No Title Found"
        print(f"Page Title: {title}")
        
        # Capture a screenshot of the page
        screenshot_filename = take_screenshot(url, subdomain)
        
        return subdomain, title, screenshot_filename
    except (requests.exceptions.RequestException, Exception) as e:
        # Handle any errors during the request or processing
        print(f"Failed to fetch {subdomain}: {e}")
        return subdomain, "Failed to Fetch", None

def take_screenshot(url, subdomain):
    """
    Takes a screenshot of the specified URL using Firefox in headless mode.

    Note:
        This function is designed for ARM64 architecture and may not work on other architectures.

    Args:
        url (str): The URL to capture.
        subdomain (str): The subdomain name used for naming the screenshot file.

    Returns:
        str: The filename of the saved screenshot.
    """
    # Set up Firefox options for headless mode
    firefox_options = Options()
    firefox_options.add_argument("--headless")
    
    # Path to the Geckodriver (specific to ARM64 architecture)
    geckodriver_path = "/usr/local/bin/geckodriver"
    service = Service(geckodriver_path)
    
    # Initialize the WebDriver
    driver = webdriver.Firefox(service=service, options=firefox_options)
    
    try:
        # Create the directory for screenshots if it doesn't exist
        screenshot_dir = "screenshots"
        os.makedirs(screenshot_dir, exist_ok=True)
        
        # Define the screenshot filename
        screenshot_filename = f"{screenshot_dir}/{subdomain}.png"
        
        # Set a timeout for page loading and capture the screenshot
        driver.set_page_load_timeout(BROWSER_TIMEOUT)
        driver.get(url)
        driver.save_screenshot(screenshot_filename)
        print(f"Screenshot saved as {screenshot_filename}")
        
        return screenshot_filename
    except Exception as e:
        # Handle any errors during screenshot capture
        print(f"Failed to take screenshot for {subdomain}: {e}")
        return None
    finally:
        # Always close the browser
        driver.quit()

def load_subdomains(file_path):
    """
    Loads subdomains from a specified file, stripping any extra whitespace.

    Args:
        file_path (str): Path to the file containing subdomains.

    Returns:
        list: A list of subdomains.
    """
    with open(file_path, 'r') as file:
        subdomains = [line.strip() for line in file if line.strip()]
    return subdomains

def process_subdomains(subdomains, max_workers, headers):
    """
    Processes a list of subdomains concurrently, fetching data and taking screenshots.

    Args:
        subdomains (list): List of subdomains to process.
        max_workers (int): Number of concurrent workers for processing.
        headers (dict): The headers to include in the HTTP requests.

    Returns:
        list: A list of results, each containing subdomain, title, and screenshot filename.
    """
    results = []
    
    # Use ThreadPoolExecutor for concurrent processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_subdomain, subdomain, headers): subdomain for subdomain in subdomains}
        
        # Collect results as they complete
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    return results

def generate_html_report(results, output_file):
    """
    Generates an HTML report using the results of subdomain processing.

    Args:
        results (list): List of processed subdomains and their results.
        output_file (str): The filename for the output HTML report.
    """
    # Determine the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Set up the Jinja2 environment using the script's directory
    env = Environment(loader=FileSystemLoader(os.path.join(script_dir, 'templates')))
    template = env.get_template('report.html')
    
    # Render the HTML content with the results
    output_content = template.render(results=results)
    
    # Write the rendered HTML content to the output file
    with open(output_file, "w") as file:
        file.write(output_content)
    
    print(f"HTML report generated: {output_file}")

def split_and_process_subdomains(subdomains, max_workers, output_prefix, headers):
    """
    Splits a large list of subdomains into smaller batches and processes each batch,
    generating separate HTML reports for each batch.

    Args:
        subdomains (list): List of subdomains to process.
        max_workers (int): Number of concurrent workers for processing.
        output_prefix (str): Prefix for the output HTML report filenames.
        headers (dict): The headers to include in the HTTP requests.
    """
    # Split subdomains into batches of BATCH_SIZE
    for i in range(0, len(subdomains), BATCH_SIZE):
        batch = subdomains[i:i + BATCH_SIZE]
        
        # Process each batch and generate a report
        batch_results = process_subdomains(batch, max_workers, headers)
        output_file = f"{output_prefix}_{i//BATCH_SIZE + 1}.html"
        generate_html_report(batch_results, output_file)

def main():
    """
    Main function to handle argument parsing and initiate the subdomain processing and reporting.
    """
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Subdomain screenshot and report generator")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file containing subdomains")
    parser.add_argument("-o", "--output", default="subdomain_report", help="Prefix for the output HTML reports")
    parser.add_argument("-c", "--concurrency", type=int, default=5, help="Concurrency level")
    parser.add_argument("-H", "--header", action='append', help="Custom headers to include in the HTTP requests, e.g., 'Header: value'")
    args = parser.parse_args()

    # Parse headers into a dictionary
    headers = {}
    if args.header:
        for header in args.header:
            key, value = header.split(":", 1)
            headers[key.strip()] = value.strip()

    # Load subdomains from the input file
    subdomains = load_subdomains(args.input)
    
    # Split subdomains into batches and process each batch
    split_and_process_subdomains(subdomains, args.concurrency, args.output, headers)

if __name__ == "__main__":
    # Entry point for the script
    main()
