# server.py
from typing import Any, List, Dict, Optional
import httpx
import os
import logging
import json
from dotenv import load_dotenv

# Import MCP libraries
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    logging.error(f"Failed to import MCP libraries: {e}")
    raise

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp-nih-reporter.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('nih-reporter-mcp')
logger.info("Starting NIH RePORTER MCP server")

# Load environment variables from .env file
load_dotenv()

# Configuration
API_NAME = "NIH RePORTER"
API_BASE = "https://api.reporter.nih.gov/v2"

# Initialize FastMCP server
mcp = FastMCP(API_NAME)

class NIHReporterClient:
    """Client for interacting with the NIH RePORTER API"""
    
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
        }
    
    async def get_projects(self, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get projects from NIH RePORTER API"""
        logger.info(f"Fetching projects from NIH RePORTER with criteria: {criteria}")
        async with httpx.AsyncClient() as client:
            payload = {
                "criteria": criteria or {},
                "limit": criteria.get("limit", 50),
                "offset": criteria.get("offset", 0),
                "sort_field": criteria.get("sort_field", "project_start_date"),
                "sort_order": criteria.get("sort_order", "desc")
            }
            logger.debug(f"Sending payload to NIH API: {json.dumps(payload, indent=2)}")
            
            try:
                response = await client.post(
                    f"{API_BASE}/projects/search",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                response_data = response.json()
                logger.debug(f"Received response: {json.dumps(response_data, indent=2)}")
                return response_data
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse API response: {e}")
                logger.error(f"Raw response: {response.text}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error during API call: {str(e)}")
                raise

    def format_project_results(self, results: Dict[str, Any], include_publications: bool = False) -> str:
        """Format project results into markdown string with optional publication links"""
        logger.debug(f"Formatting results: {json.dumps(results, indent=2)}")
        
        if not results.get("results"):
            logger.info("No results found in API response")
            return "No projects found."
        
        try:
            formatted_results = []
            for project in results["results"]:
                # Format amount safely
                award_amount = project.get('award_amount')
                amount_str = f"${award_amount:,.2f}" if award_amount is not None else "N/A"
                
                # Get organization details safely
                org = project.get('organization', {})
                org_parts = []
                if org.get('org_name'):
                    org_parts.append(org.get('org_name'))
                if org.get('org_city'):
                    org_parts.append(org.get('org_city'))
                if org.get('org_state'):
                    org_parts.append(org.get('org_state'))
                org_details = ", ".join(org_parts) if org_parts else "N/A"
                
                # Format dates safely
                start_date = project.get('project_start_date') or 'N/A'
                end_date = project.get('project_end_date') or 'N/A'
                
                # Get study section info safely
                study_section = project.get('study_section', {})
                study_name = study_section.get('study_section_name', 'N/A')
                srg_code = study_section.get('srg_code', '')
                study_info = f"{study_name} ({srg_code})" if srg_code else study_name
                
                # Handle PIs safely
                pis = project.get('principal_investigators', [])
                pi_names = [pi.get('full_name', 'N/A') for pi in pis if pi.get('full_name')]
                pi_str = ", ".join(pi_names) if pi_names else "N/A"
                
                # Build project info with markdown formatting
                project_info = [
                    f"### {project.get('project_title', 'Untitled Project')}",
                    "",
                    f"**Project Number:** `{project.get('project_num', 'N/A')}`",
                    f"**Principal Investigator(s):** {pi_str}",
                    f"**Organization:** {org_details}",
                    f"**Fiscal Year:** {project.get('fiscal_year', 'N/A')}",
                    f"**Award Amount:** {amount_str}",
                    f"**Project Period:** {start_date} to {end_date}",
                    f"**Study Section:** {study_info}"
                ]
                
                # Add funding mechanism if available
                mechanism = project.get('funding_mechanism')
                if mechanism:
                    project_info.append(f"**Funding Mechanism:** {mechanism}")
                
                # Add IC Code if available
                ic_code = project.get('agency_ic_admin')
                if ic_code:
                    project_info.append(f"**Institute/Center:** {ic_code}")
                
                # Add RCDC terms if available
                rcdc_terms = project.get('rcdc_terms', [])
                if rcdc_terms:
                    terms_str = ", ".join(f"`{term}`" for term in rcdc_terms if term)
                    if terms_str:
                        project_info.append(f"**RCDC Terms:** {terms_str}")
                
                # Add abstract if it exists
                abstract = project.get('abstract_text')
                if abstract:
                    project_info.extend([
                        "",
                        "#### Abstract",
                        abstract
                    ])
                
                # Add PHR if it exists
                phr = project.get('phr_text')
                if phr:
                    project_info.extend([
                        "",
                        "#### Public Health Relevance",
                        phr
                    ])
                
                # Add publications section if available
                if include_publications and project.get('related_publications'):
                    project_info.extend([
                        "",
                        "#### Related Publications"
                    ])
                    
                    for pub in project.get('related_publications', []):
                        pmid = pub.get('pmid')
                        title = pub.get('title', 'Untitled Publication')
                        
                        pub_info = [""]
                        
                        # Always show the PMID if we have it
                        if pmid:
                            pub_info.append(f"##### {title} (PMID: [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/))")
                        else:
                            pub_info.append(f"##### {title}")
                        
                        # Add other details if we have them
                        if pub.get('authors'):
                            author_str = ", ".join(pub['authors'])
                            pub_info.append(f"**Authors:** {author_str}")
                        
                        if pub.get('journal_title'):
                            pub_info.append(f"**Journal:** {pub['journal_title']}")
                            
                        if pub.get('publication_year'):
                            pub_info.append(f"**Year:** {pub['publication_year']}")
                            
                        if pub.get('doi'):
                            pub_info.append(f"**DOI:** [{pub['doi']}](https://doi.org/{pub['doi']})")
                        
                        project_info.extend(pub_info)
                
                project_info.extend(["", "---", ""])
                formatted_results.append("\n".join(filter(None, project_info)))
            
            total = f"# NIH RePORTER Search Results\n\n**Total matching projects:** {results.get('meta', {}).get('total', 0)}"
            return f"{total}\n\n" + "\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"Error formatting results: {str(e)}")
            logger.error(f"Results that caused error: {json.dumps(results, indent=2)}")
            raise

    async def get_publications(self, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get publications from NIH RePORTER API"""
        logger.info(f"Fetching publications from NIH RePORTER with criteria: {criteria}")
        async with httpx.AsyncClient() as client:
            # Construct the payload according to API specification
            payload = {
                "criteria": {
                    "core_project_nums": criteria.get("criteria", {}).get("core_project_nums", [])
                },
                "limit": criteria.get("limit", 50),
                "offset": criteria.get("offset", 0)
            }
            
            # Add publication years if specified
            if "publication_years" in criteria.get("criteria", {}):
                payload["criteria"]["publication_years"] = criteria["criteria"]["publication_years"]
            
            logger.debug(f"Sending payload to NIH Publications API: {json.dumps(payload, indent=2)}")
            
            try:
                response = await client.post(
                    f"{API_BASE}/publications/search",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                response_data = response.json()
                
                # If we got PMIDs, fetch the full publication details from PubMed
                if response_data.get("results"):
                    pmids = [str(result.get("pmid")) for result in response_data["results"] if result.get("pmid")]
                    if pmids:
                        async with httpx.AsyncClient() as pubmed_client:
                            # Use E-utilities to get full publication details
                            pubmed_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
                            pubmed_response = await pubmed_client.get(pubmed_url)
                            pubmed_data = pubmed_response.json()
                            
                            # Update our results with PubMed data
                            for result in response_data["results"]:
                                if result.get("pmid"):
                                    pmid = str(result["pmid"])
                                    if pmid in pubmed_data.get("result", {}):
                                        pub_details = pubmed_data["result"][pmid]
                                        result.update({
                                            "title": pub_details.get("title", ""),
                                            "authors": [author.get("name", "") for author in pub_details.get("authors", [])],
                                            "journal_title": pub_details.get("fulljournalname", ""),
                                            "publication_year": pub_details.get("pubdate", "").split()[0] if pub_details.get("pubdate") else None
                                        })
                
                logger.debug(f"Received response: {json.dumps(response_data, indent=2)}")
                return response_data
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse API response: {e}")
                logger.error(f"Raw response: {response.text}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error during API call: {str(e)}")
                raise

    def format_publication_results(self, results: Dict[str, Any], include_projects: bool = False) -> str:
        """Format publication results into markdown string with optional project links"""
        logger.debug(f"Formatting publication results: {json.dumps(results, indent=2)}")
        
        if not results.get("results"):
            logger.info("No publications found in API response")
            return "No publications found."
        
        try:
            formatted_results = []
            for pub in results["results"]:
                # Format authors safely
                authors = pub.get('authors', [])
                author_str = ", ".join(authors) if authors else "N/A"
                
                pub_info = [
                    f"### {pub.get('title', 'Untitled Publication')}",
                    "",
                    f"**Authors:** {author_str}",
                    f"**PMID:** `{pub.get('pmid', 'N/A')}`",
                    f"**Core Project Number:** `{pub.get('core_project_num', 'N/A')}`"
                ]
                
                # Add publication year if available
                if pub.get('publication_year'):
                    pub_info.append(f"**Publication Year:** {pub['publication_year']}")
                
                # Add journal info if available
                if pub.get('journal_title'):
                    pub_info.append(f"**Journal:** {pub['journal_title']}")
                
                # Add DOI if available
                if pub.get('doi'):
                    pub_info.append(f"**DOI:** [{pub['doi']}](https://doi.org/{pub['doi']})")
                
                # Add project links if available
                if pub.get('core_project_num'):
                    pub_info.extend([
                        "",
                        "#### Related NIH Projects",
                        f"- Core Project: `{pub['core_project_num']}`"
                    ])
                
                pub_info.extend(["", "---", ""])
                formatted_results.append("\n".join(filter(None, pub_info)))
            
            total = f"# NIH RePORTER Publication Results\n\n**Total matching publications:** {results.get('meta', {}).get('total', 0)}"
            return f"{total}\n\n" + "\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"Error formatting publication results: {str(e)}")
            logger.error(f"Results that caused error: {json.dumps(results, indent=2)}")
            raise

# Initialize API client
api_client = NIHReporterClient()

@mcp.tool()
async def search_projects(
    fiscal_years: Optional[str] = None,
    pi_names: Optional[str] = None,
    organization: Optional[str] = None,
    org_state: Optional[str] = None,
    org_city: Optional[str] = None,
    org_type: Optional[str] = None,
    org_department: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    covid_response: Optional[str] = None,
    funding_mechanism: Optional[str] = None,
    ic_code: Optional[str] = None,
    rcdc_terms: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    newly_added_only: Optional[bool] = False,
    include_abstracts: Optional[bool] = True,
    limit: Optional[int] = 10
) -> str:
    """
    Search for NIH funded projects with advanced criteria
    
    Args:
        fiscal_years: Comma-separated list of fiscal years (e.g., "2022,2023")
        pi_names: Comma-separated list of PI names (will match any of the names)
        organization: Name of the organization
        org_state: Two-letter state code (e.g., "CA", "NY")
        org_city: City name
        org_type: Organization type
        org_department: Department name
        min_amount: Minimum award amount
        max_amount: Maximum award amount
        covid_response: COVID-19 response category (options: "Reg-CV", "CV", "C3", "C4", "C5", "C6")
        funding_mechanism: Type of funding (e.g., "R01", "F32", "K99")
        ic_code: Institute or Center code (e.g., "NCI", "NIMH")
        rcdc_terms: Comma-separated RCDC terms for research categorization
        start_date: Project start date (YYYY-MM-DD)
        end_date: Project end date (YYYY-MM-DD)
        newly_added_only: Only show recently added projects
        include_abstracts: Include project abstracts in results
        limit: Maximum number of results to return (default: 10, max: 50)
    """
    try:
        logger.info(f"Advanced search request received with parameters: {locals()}")
        
        criteria = {}
        
        # Basic criteria
        if fiscal_years:
            try:
                # Handle escaped quotes and clean the input string
                years_str = fiscal_years.replace('\\"', '').replace('"', '').strip()
                years = [int(year.strip()) for year in years_str.split(",") if year.strip()]
                if not years:
                    raise ValueError("No valid years found after parsing")
                criteria["fiscal_years"] = years
            except ValueError as e:
                logger.error(f"Invalid fiscal years format: {fiscal_years}, error: {str(e)}")
                return f"Error: Invalid fiscal years format. Please provide comma-separated years (e.g., 2020,2021)"
        
        # Handle multiple PI names
        if pi_names:
            try:
                # Handle escaped quotes and clean the input string
                names_str = pi_names.replace('\\"', '').replace('"', '').strip()
                names = [name.strip() for name in names_str.split(",") if name.strip()]
                if not names:
                    raise ValueError("No valid names found after parsing")
                criteria["pi_names"] = [{"any_name": name} for name in names]
            except Exception as e:
                logger.error(f"Invalid PI names format: {pi_names}, error: {str(e)}")
                return f"Error: Invalid PI names format. Please provide comma-separated names"
        
        # Organization criteria
        org_criteria = {}
        if organization:
            org_criteria["org_names"] = [organization.strip().strip('"').strip("'")]
        if org_state:
            org_criteria["org_states"] = [org_state.strip().strip('"').strip("'").upper()]
        if org_city:
            org_criteria["org_cities"] = [org_city.strip().strip('"').strip("'")]
        if org_type:
            org_criteria["org_types"] = [org_type.strip().strip('"').strip("'")]
        if org_department:
            org_criteria["org_depts"] = [org_department.strip().strip('"').strip("'")]
        if org_criteria:
            criteria.update(org_criteria)
        
        # Award amount range
        if min_amount is not None or max_amount is not None:
            criteria["award_amount_range"] = {
                "min_amount": min_amount if min_amount is not None else 0,
                "max_amount": max_amount if max_amount is not None else float('inf')
            }
        
        # COVID response
        if covid_response:
            criteria["covid_response"] = [covid_response]
        
        # Funding mechanism
        if funding_mechanism:
            criteria["funding_mechanism"] = funding_mechanism.strip().strip('"').strip("'")
            
        # Institute/Center code
        if ic_code:
            criteria["agency_ic_admin"] = ic_code.strip().strip('"').strip("'").upper()
            
        # RCDC terms
        if rcdc_terms:
            try:
                terms_str = rcdc_terms.strip().strip('"').strip("'")
                terms = [term.strip() for term in terms_str.split(",")]
                criteria["rcdc_terms"] = terms
            except Exception as e:
                logger.error(f"Invalid RCDC terms format: {rcdc_terms}")
                return f"Error: Invalid RCDC terms format. Please provide comma-separated terms without quotes"
        
        # Date criteria
        if start_date or end_date:
            criteria["date_range"] = {
                "start_date": start_date.strip().strip('"').strip("'") if start_date else None,
                "end_date": end_date.strip().strip('"').strip("'") if end_date else None
            }
        
        # Other filters
        if newly_added_only:
            criteria["newly_added_projects_only"] = True
        
        # Include fields
        include_fields = [
            "project_num", "project_title", "principal_investigators",
            "organization", "fiscal_year", "award_amount",
            "project_start_date", "project_end_date", "funding_mechanism",
            "agency_ic_admin", "rcdc_terms"
        ]
        if include_abstracts:
            include_fields.extend(["abstract_text", "phr_text"])
        
        # Ensure limit is within bounds
        try:
            criteria["limit"] = min(max(1, int(limit)), 50)
        except (ValueError, TypeError):
            logger.error(f"Invalid limit value: {limit}")
            return f"Error: Invalid limit value. Please provide a number between 1 and 50"
        
        logger.info(f"Constructed search criteria: {json.dumps(criteria, indent=2)}")
        
        results = await api_client.get_projects(criteria)
        return api_client.format_project_results(results)
        
    except Exception as e:
        logger.error(f"Project search failed: {str(e)}", exc_info=True)
        return f"Project search failed: {str(e)}\nPlease check the logs for more details."

@mcp.tool()
async def test_connection() -> str:
    """Test the connection to the NIH RePORTER API"""
    try:
        # Try to fetch a single project as a test
        result = await api_client.get_projects({"limit": 1})
        return "Successfully connected to NIH RePORTER API"
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return f"Connection test failed: {str(e)}"

@mcp.tool()
async def search_publications(
    pmids: Optional[str] = None,
    core_project_nums: Optional[str] = None,
    limit: Optional[int] = 10
) -> str:
    """
    Search for publications linked to NIH projects
    
    Args:
        pmids: Comma-separated list of PubMed IDs
        core_project_nums: Comma-separated list of NIH core project numbers
        limit: Maximum number of results to return (default: 10, max: 50)
    """
    try:
        logger.info(f"Publication search request received with parameters: {locals()}")
        
        criteria = {}
        
        # Handle PMIDs
        if pmids:
            pmid_list = [pmid.strip() for pmid in pmids.split(",")]
            criteria["pmids"] = pmid_list
        
        # Handle core project numbers
        if core_project_nums:
            proj_list = [num.strip() for num in core_project_nums.split(",")]
            criteria["core_project_nums"] = proj_list
        
        # Ensure limit is within bounds
        criteria["limit"] = min(max(1, limit), 50)
        
        logger.info(f"Constructed publication search criteria: {json.dumps(criteria, indent=2)}")
        
        results = await api_client.get_publications(criteria)
        return api_client.format_publication_results(results)
        
    except Exception as e:
        logger.error(f"Publication search failed: {str(e)}", exc_info=True)
        return f"Publication search failed: {str(e)}\nPlease check the logs for more details."

@mcp.tool()
async def search_combined(
    # Project search parameters
    fiscal_years: Optional[str] = None,
    pi_names: Optional[str] = None,
    organization: Optional[str] = None,
    org_state: Optional[str] = None,
    funding_mechanism: Optional[str] = None,
    ic_code: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    covid_response: Optional[str] = None,
    
    # Publication parameters
    include_publications: Optional[bool] = True,
    publication_years: Optional[str] = None,
    
    # General parameters
    limit: Optional[int] = 10
) -> str:
    """
    Search for NIH projects and their related publications in a single query
    
    Args:
        fiscal_years: Comma-separated list of fiscal years (e.g., "2022,2023")
        pi_names: Comma-separated list of PI names
        organization: Name of the organization
        org_state: Two-letter state code (e.g., "CA", "NY")
        funding_mechanism: Type of funding (e.g., "R01", "F32", "K99")
        ic_code: Institute or Center code (e.g., "NCI", "NIMH")
        min_amount: Minimum award amount
        max_amount: Maximum award amount
        covid_response: COVID-19 response category
        include_publications: Whether to include related publications
        publication_years: Comma-separated list of publication years
        limit: Maximum number of results to return (default: 10, max: 50)
    """
    try:
        logger.info(f"Combined search request received with parameters: {locals()}")
        
        # First, search for projects
        project_criteria = {}
        
        if fiscal_years:
            try:
                # Handle escaped quotes and clean the input string
                years_str = fiscal_years.replace('\\"', '').replace('"', '').strip()
                years = [int(year.strip()) for year in years_str.split(",") if year.strip()]
                if not years:
                    raise ValueError("No valid years found after parsing")
                project_criteria["fiscal_years"] = years
            except ValueError as e:
                logger.error(f"Invalid fiscal years format: {fiscal_years}, error: {str(e)}")
                return f"Error: Invalid fiscal years format. Please provide comma-separated years (e.g., 2020,2021)"
        
        if pi_names:
            try:
                # Handle escaped quotes and clean the input string
                names_str = pi_names.replace('\\"', '').replace('"', '').strip()
                names = [name.strip() for name in names_str.split(",") if name.strip()]
                if not names:
                    raise ValueError("No valid names found after parsing")
                project_criteria["pi_names"] = [{"any_name": name} for name in names]
            except Exception as e:
                logger.error(f"Invalid PI names format: {pi_names}, error: {str(e)}")
                return f"Error: Invalid PI names format. Please provide comma-separated names"
        
        if organization:
            project_criteria["org_names"] = [organization]
        
        if org_state:
            project_criteria["org_states"] = [org_state.upper()]
            
        if funding_mechanism:
            project_criteria["funding_mechanism"] = funding_mechanism.strip().strip('"').strip("'")
            
        if ic_code:
            project_criteria["agency_ic_admin"] = ic_code.strip().strip('"').strip("'").upper()
            
        if min_amount is not None or max_amount is not None:
            project_criteria["award_amount_range"] = {
                "min_amount": min_amount if min_amount is not None else 0,
                "max_amount": max_amount if max_amount is not None else float('inf')
            }
            
        if covid_response:
            project_criteria["covid_response"] = [covid_response]
        
        project_criteria["limit"] = min(max(1, limit), 50)
        
        logger.info(f"Searching for projects with criteria: {json.dumps(project_criteria, indent=2)}")
        project_results = await api_client.get_projects(project_criteria)
        
        # If we want publications, get them for each project
        if include_publications:
            project_nums = []
            for project in project_results.get("results", []):
                if project.get("project_num"):
                    project_nums.append(project["project_num"])
            
            if project_nums:
                pub_criteria = {
                    "criteria": {
                        "core_project_nums": project_nums
                    },
                    "limit": 100,  # Get more publications since they're related
                    "include_fields": [
                        "title",
                        "authors",
                        "journal_title",
                        "journal_issue",
                        "journal_volume",
                        "publication_year",
                        "pmid",
                        "doi",
                        "core_project_num"
                    ]
                }
                
                # Only add publication years if explicitly specified by the user
                if publication_years:
                    try:
                        years_str = publication_years.strip().strip('"').strip("'")
                        years = [int(year.strip()) for year in years_str.split(",")]
                        pub_criteria["criteria"]["publication_years"] = years
                        logger.info(f"Filtering publications by years: {years}")
                    except ValueError as e:
                        logger.error(f"Invalid publication years format: {publication_years}")
                        return f"Error: Invalid publication years format. Please provide comma-separated years without quotes (e.g., 2020,2021)"
                else:
                    logger.info("No publication years specified - will return all related publications regardless of year")
                
                logger.info(f"Searching for publications with criteria: {json.dumps(pub_criteria, indent=2)}")
                pub_results = await api_client.get_publications(pub_criteria)
                
                # Add publications to each project
                pub_by_project = {}
                for pub in pub_results.get("results", []):
                    proj_num = pub.get("core_project_num")
                    if proj_num:
                        if proj_num not in pub_by_project:
                            pub_by_project[proj_num] = []
                        pub_by_project[proj_num].append(pub)
                
                for project in project_results.get("results", []):
                    proj_num = project.get("project_num")
                    if proj_num in pub_by_project:
                        project["related_publications"] = pub_by_project[proj_num]
        
        return api_client.format_project_results(project_results, include_publications=include_publications)
        
    except Exception as e:
        logger.error(f"Combined search failed: {str(e)}", exc_info=True)
        return f"Combined search failed: {str(e)}\nPlease check the logs for more details."

# Run the server when this script is executed directly
if __name__ == "__main__":
    mcp.run(transport='stdio')
