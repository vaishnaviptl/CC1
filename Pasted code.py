import requests
import json
import re

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode


class JobdexoScraper:

    BASE_URL = "https://jobdexo.com/"

    def __init__(self):

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            )
        }

    # ==================================================
    # FETCH PAGE
    # ==================================================

    def get_page(self, url):

        response = requests.get(
            url,
            headers=self.headers,
            timeout=15
        )

        response.raise_for_status()

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    # ==================================================
    # BUILD JOBDEXO SEARCH URL
    # ==================================================

    def build_search_url(self, role, page=1):

        params = {
            "page": page,
            "q": role
        }

        return (
            self.BASE_URL
            + "?"
            + urlencode(params)
        )

    # ==================================================
    # GET PAGINATION PAGES
    # ==================================================

    def get_pagination_pages(self, soup):

        pages = set()

        # Find pagination container
        pagination = soup.find(
            "nav",
            class_="pagination"
        )

        if pagination:

            for link in pagination.find_all(
                "a",
                href=True
            ):

                href = link["href"]

                match = re.search(
                    r"[?&]page=(\d+)",
                    href
                )

                if match:

                    pages.add(
                        int(match.group(1))
                    )

        # Page 1 always exists
        pages.add(1)

        return sorted(pages)

    # ==================================================
    # GET JOB LINKS FROM PAGE
    # ==================================================

    def get_job_links_from_page(self, soup):

        job_links = []

        # Find ALL links on the page
        for link in soup.find_all(
            "a",
            href=True
        ):

            href = link["href"].strip()

            # Keep only Jobdexo job pages
            if href.startswith("/job/"):

                full_url = urljoin(
                    self.BASE_URL,
                    href
                )

                if full_url not in job_links:

                    job_links.append(
                        full_url
                    )

        return job_links

    # ==================================================
    # GET ALL JOB LINKS FOR ROLE
    # ==================================================

    def get_job_links(self, role):

        # ----------------------------------------------
        # First search page
        # ----------------------------------------------

        first_url = self.build_search_url(
            role,
            page=1
        )

        print(
            f"Searching Jobdexo for: {role}"
        )

        print(
            f"URL: {first_url}"
        )

        first_soup = self.get_page(
            first_url
        )

        # ----------------------------------------------
        # Find pagination pages
        # ----------------------------------------------

        pages = self.get_pagination_pages(
            first_soup
        )

        print(
            f"Pagination pages found: {pages}"
        )

        # ----------------------------------------------
        # Collect all unique job links
        # ----------------------------------------------

        all_job_links = []

        for page in pages:

            page_url = self.build_search_url(
                role,
                page=page
            )

            print(
                f"Scraping search page {page}: "
                f"{page_url}"
            )

            try:

                if page == 1:

                    soup = first_soup

                else:

                    soup = self.get_page(
                        page_url
                    )

                job_links = (
                    self.get_job_links_from_page(
                        soup
                    )
                )

                print(
                    f"Found {len(job_links)} jobs "
                    f"on page {page}"
                )

                for job_link in job_links:

                    if job_link not in all_job_links:

                        all_job_links.append(
                            job_link
                        )

            except Exception as e:

                print(
                    f"Failed to scrape "
                    f"search page {page}: {e}"
                )

        return all_job_links

    # ==================================================
    # FIND JOBPOSTING JSON-LD
    # ==================================================

    def get_job_schema(self, soup):

        for script in soup.find_all("script"):

            raw = script.get_text(
                strip=True
            )

            if not raw:
                continue

            if "JobPosting" not in raw:
                continue

            # ------------------------------------------
            # Try normal JSON
            # ------------------------------------------

            try:

                data = json.loads(raw)

                # Direct JobPosting object
                if isinstance(data, dict):

                    if data.get("@type") == "JobPosting":

                        return data

                    # Check @graph
                    graph = data.get(
                        "@graph"
                    )

                    if isinstance(
                        graph,
                        list
                    ):

                        for item in graph:

                            if (
                                isinstance(
                                    item,
                                    dict
                                )
                                and item.get("@type")
                                == "JobPosting"
                            ):

                                return item

                # List of JSON objects
                elif isinstance(data, list):

                    for item in data:

                        if (
                            isinstance(
                                item,
                                dict
                            )
                            and item.get("@type")
                            == "JobPosting"
                        ):

                            return item

            except Exception:
                pass

            # ------------------------------------------
            # Regex fallback
            # ------------------------------------------

            title_match = re.search(
                r'"title"\s*:\s*"([^"]+)"',
                raw
            )

            company_match = re.search(
                r'"hiringOrganization"\s*:\s*\{.*?'
                r'"name"\s*:\s*"([^"]+)"',
                raw,
                re.DOTALL
            )

            location_match = re.search(
                r'"addressLocality"\s*:\s*"([^"]+)"',
                raw
            )

            if (
                title_match
                or company_match
                or location_match
            ):

                return {
                    "title": (
                        title_match.group(1)
                        if title_match
                        else ""
                    ),

                    "hiringOrganization": {
                        "name": (
                            company_match.group(1)
                            if company_match
                            else ""
                        )
                    },

                    "jobLocation": {
                        "address": {
                            "addressLocality": (
                                location_match.group(1)
                                if location_match
                                else ""
                            )
                        }
                    }
                }

        return None

    # ==================================================
    # EXTRACT APPLY URL
    # ==================================================

    def extract_apply_url(
        self,
        soup,
        job_url
    ):

        for link in soup.find_all(
            "a",
            href=True
        ):

            text = link.get_text(
                " ",
                strip=True
            ).lower()

            if "apply" in text:

                return urljoin(
                    self.BASE_URL,
                    link["href"]
                )

        # Fallback to Jobdexo page
        return job_url

    # ==================================================
    # EXTRACT JOB DETAILS
    # ==================================================

    def get_job_details(
        self,
        job_url
    ):

        soup = self.get_page(
            job_url
        )

        schema = self.get_job_schema(
            soup
        )

        job = {
            "title": "",
            "company": "",
            "location": "",
            "apply_url": "",
            "source": "Jobdexo"
        }

        # ------------------------------------------
        # TITLE
        # ------------------------------------------

        if schema:

            job["title"] = schema.get(
                "title",
                ""
            )

            # --------------------------------------
            # COMPANY
            # --------------------------------------

            organization = schema.get(
                "hiringOrganization",
                {}
            )

            if isinstance(
                organization,
                dict
            ):

                job["company"] = organization.get(
                    "name",
                    ""
                )

            # --------------------------------------
            # LOCATION
            # --------------------------------------

            location = schema.get(
                "jobLocation",
                {}
            )

            if isinstance(
                location,
                dict
            ):

                address = location.get(
                    "address",
                    {}
                )

                if isinstance(
                    address,
                    dict
                ):

                    job["location"] = address.get(
                        "addressLocality",
                        ""
                    )

        # ------------------------------------------
        # APPLY URL
        # ------------------------------------------

        job["apply_url"] = (
            self.extract_apply_url(
                soup,
                job_url
            )
        )

        return job

    # ==================================================
    # SCRAPE JOBS
    # ==================================================

    def scrape_jobs(
        self,
        role,
        location=None
    ):

        role = role.strip()

        if not role:

            return []

        # ------------------------------------------
        # Get all job links for role
        # ------------------------------------------

        job_links = self.get_job_links(
            role
        )

        print(
            f"\nTotal unique job links found: "
            f"{len(job_links)}"
        )

        jobs = []

        # ------------------------------------------
        # Scrape every job
        # ------------------------------------------

        for index, job_url in enumerate(
            job_links,
            start=1
        ):

            print(
                f"Scraping job {index}/"
                f"{len(job_links)}"
            )

            try:

                job = self.get_job_details(
                    job_url
                )

                jobs.append(job)

            except Exception as e:

                print(
                    f"Failed to scrape: "
                    f"{job_url}"
                )

                print(
                    f"Error: {e}"
                )

        # ------------------------------------------
        # OPTIONAL LOCATION FILTER
        # ------------------------------------------

        if location:

            location = (
                location
                .strip()
                .lower()
            )

            jobs = [
                job
                for job in jobs
                if location in (
                    job["location"]
                    .lower()
                )
            ]

        return jobs