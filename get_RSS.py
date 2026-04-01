import feedparser
import re
import os
import datetime
import time
import socket
import urllib.request
import urllib.error
import unicodedata
from collections import Counter
from rfeed import Item, Feed, Guid
from email.utils import parsedate_to_datetime

try:
    from curl_cffi import requests as browser_requests
except ImportError:
    browser_requests = None

# --- 配置区域 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "filtered_feed.xml")
MAX_ITEMS = 1000
JOURNAL_NAME_FILE = os.path.join(BASE_DIR, "期刊.txt")
FAILURE_LOG_FILE = os.path.join(BASE_DIR, "fetch_failures.tsv")
REQUEST_TIMEOUT = 20
RETRY_WAIT_SECONDS = 2
BROWSER_IMPERSONATE = "chrome124"
DEFAULT_FEED_TITLE = "Perovskite Solar Cell Watchlist"
DEFAULT_FEED_DESCRIPTION = (
    "Latest journal and preprint papers for FA-based, quasi-2D, "
    "Ruddlesden-Popper, and Dion-Jacobson perovskite solar cells."
)
MDPI_SLUG_ALIASES = {
    "condmat": "condensedmatter",
    "microwaves": "microwave",
}
# ----------------


def normalize_rss_url(url):
    if not url:
        return ""
    normalized = url.strip().replace("http://ieeexplore.ieee.org", "https://ieeexplore.ieee.org")
    mdpi_old_match = re.match(r"^https?://www\.mdpi\.com/journal/([^/?#]+)/rss/?$", normalized)
    if mdpi_old_match:
        slug = MDPI_SLUG_ALIASES.get(mdpi_old_match.group(1), mdpi_old_match.group(1))
        return f"https://www.mdpi.com/rss/journal/{slug}"

    mdpi_new_match = re.match(r"^https?://www\.mdpi\.com/rss/journal/([^/?#]+)/?$", normalized)
    if mdpi_new_match:
        slug = MDPI_SLUG_ALIASES.get(mdpi_new_match.group(1), mdpi_new_match.group(1))
        return f"https://www.mdpi.com/rss/journal/{slug}"

    return normalized


SOURCE_NAME_OVERRIDES = {
    normalize_rss_url(
        "https://export.arxiv.org/api/query?search_query=all:perovskite+AND+all:%22solar+cell%22&start=0&max_results=50&sortBy=submittedDate&sortOrder=descending"
    ): "arXiv perovskite solar cells",
    normalize_rss_url(
        "https://export.arxiv.org/api/query?search_query=all:%22quasi-2d%22+AND+all:perovskite&start=0&max_results=50&sortBy=submittedDate&sortOrder=descending"
    ): "arXiv quasi-2D perovskites",
    normalize_rss_url(
        "https://export.arxiv.org/api/query?search_query=all:%22ruddlesden-popper%22+AND+all:perovskite&start=0&max_results=50&sortBy=submittedDate&sortOrder=descending"
    ): "arXiv RP perovskites",
    normalize_rss_url(
        "https://export.arxiv.org/api/query?search_query=all:%22dion-jacobson%22+AND+all:perovskite&start=0&max_results=50&sortBy=submittedDate&sortOrder=descending"
    ): "arXiv DJ perovskites",
}


def normalize_journal_name(journal_name):
    if not journal_name:
        return "Unknown Journal"

    name = journal_name.strip()
    name = name.replace(" - new TOC", "")
    name = name.replace("ScienceDirect Publication: ", "")
    name = name.replace("acs: ", "")
    name = name.replace("RSC - ", "")

    if name.startswith("Wiley: "):
        name = name[len("Wiley: "):]
    if name.endswith(": Table of Contents"):
        name = name[: -len(": Table of Contents")]
    if name.endswith(" latest articles"):
        name = name[: -len(" latest articles")]

    return re.sub(r"\s+", " ", name).strip(" :")


def strip_title_prefix(title):
    if not title:
        return ""
    return re.sub(r"^\[[^\]]+\]\s*", "", title).strip()


def load_journal_title_mapping(filename):
    if not os.path.exists(filename):
        return {}

    with open(filename, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    mapping = {}
    for idx, line in enumerate(lines[:-1]):
        next_line = lines[idx + 1]
        if line.startswith("http") or not next_line.startswith("http"):
            continue
        mapping[normalize_rss_url(next_line)] = line
    return mapping


def create_feed_opener():
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0 Paper-Feed RSS Fetcher")]
    return opener


FEED_OPENER = create_feed_opener()


def is_mdpi_rss_url(url):
    return normalize_rss_url(url).startswith("https://www.mdpi.com/rss/journal/")


def fetch_feed_bytes(rss_url):
    normalized_rss_url = normalize_rss_url(rss_url)

    if is_mdpi_rss_url(normalized_rss_url) and browser_requests is not None:
        response = browser_requests.get(
            normalized_rss_url,
            timeout=REQUEST_TIMEOUT,
            impersonate=BROWSER_IMPERSONATE,
        )
        if response.status_code >= 400:
            raise urllib.error.HTTPError(
                normalized_rss_url,
                response.status_code,
                f"HTTP Error {response.status_code}",
                hdrs=response.headers,
                fp=None,
            )
        return response.content, response.status_code

    with FEED_OPENER.open(normalized_rss_url, timeout=REQUEST_TIMEOUT) as response:
        return response.read(), getattr(response, "status", None)


# --- 期刊缩写映射 ---
JOURNAL_ABBR = {
    # Elsevier / ScienceDirect
    "Medical Image Analysis": "MedIA",
    "Pattern Recognition": "PR",
    "Knowledge-Based Systems": "KBS",
    "Neural Networks": "NN",
    "Neurocomputing": "NC",
    "Computers in Biology and Medicine": "CBM",
    "Biomedical Signal Processing and Control": "BSPC",
    "Artificial Intelligence in Medicine": "AIM",
    "Engineering Applications of Artificial Intelligence": "EAAI",
    "Expert Systems with Applications": "ESWA",
    "Information Fusion": "IF",
    "NeuroImage": "NI",
    "Acta Materialia": "Acta Mater.",
    "Ceramics International": "Ceram. Int.",
    "Energy Conversion and Management": "ECM",
    "Heliyon": "Heliyon",
    "Integration, the VLSI Journal": "Integration",
    "Journal of Crystal Growth": "JCG",
    "Journal of Energy Storage": "JES",
    "Journal of Microelectronics and Electronic Packaging": "JMEP",
    "Materials Chemistry and Physics": "Mater. Chem. Phys.",
    "Materials Today Physics": "Mater. Today Phys.",
    "Microelectronic Engineering": "Microelectron. Eng.",
    "Microelectronics Journal": "Microelectron. J.",
    "Nano Energy": "Nano Energy",
    "Optical Materials": "Opt. Mater.",
    "Results in Physics": "Results Phys.",
    "Science Bulletin": "Sci. Bull.",
    "Solar Energy Advances": "Sol. Energy Adv.",
    "Solar Energy Materials and Solar Cells": "Sol. Energy Mater. Sol. Cells",
    "Solid-State Electronics": "SSE",
    "Synthetic Metals": "Synth. Met.",
    # IEEE
    "IEEE Aerospace and Electronic Systems Magazine": "IAESM",
    "IEEE ASSP Magazine": "ASSP Mag.",
    "IEEE Computer Applications in Power": "CAiP",
    "IEEE Design & Test of Computers": "D&TC",
    "IEEE Electrical Insulation Magazine": "EIM",
    "IEEE Electron Device Letters": "EDL",
    "IEEE Engineering in Medicine and Biology Magazine": "EMB Mag.",
    "IEEE Expert": "IEEE Expert",
    "IEEE Journal of Oceanic Engineering": "JOE",
    "IEEE Journal on Robotics and Automation": "JRA",
    "IEEE Journal on Selected Areas in Communications": "JSAC",
    "IEEE Network": "IEEE Netw.",
    "IEEE Photonics Technology Letters": "PTL",
    "IEEE Software": "IEEE Softw.",
    "IEEE Transactions on Energy Conversion": "TEC",
    "IEEE Transactions on Power Delivery": "TPWRD",
    "IEEE Transactions on Power Electronics": "TPE",
    "IEEE Transactions on Power Systems": "TPWRS",
    "IEEE Transactions on Semiconductor Manufacturing": "TSM",
    "IEEE Transactions on Ultrasonics, Ferroelectrics, and Frequency Control": "TUFFC",
    "IEEE Transactions on Medical Imaging": "TMI",
    "IEEE Transactions on Pattern Analysis and Machine Intelligence": "TPAMI",
    "IEEE Transactions on Image Processing": "TIP",
    "IEEE Transactions on Biomedical Engineering": "TBME",
    "IEEE Journal of Biomedical and Health Informatics": "JBHI",
    "Journal of Lightwave Technology": "JLT",
    # IET
    "IET Circuits, Devices & Systems": "IET CDS",
    "IET Electronics Letters": "Electron. Lett.",
    "IET Power Electronics": "IET PEL",
    # Wiley
    "Medical Physics": "MP",
    "Advanced Energy Materials": "AEM",
    "Advanced Electronic Materials": "AEM",
    "Advanced Functional Materials": "AFM",
    "Advanced Materials": "Adv. Mater.",
    "Advanced Materials Technologies": "AMT",
    "Advanced Science": "Adv. Sci.",
    "ChemPhysChem": "ChemPhysChem",
    "Chinese Journal of Chemistry": "CJC",
    "Energy & Environmental Materials": "EEM",
    "Energy Science & Engineering": "ESE",
    "International Journal of Circuit Theory and Applications": "IJCTA",
    "International Journal of Energy Research": "IJER",
    "Small Structures": "Small Struct.",
    "Solar RRL": "Solar RRL",
    # Springer
    "Analog Integrated Circuits and Signal Processing": "AICSP",
    "Circuits, Systems, and Signal Processing": "CSSP",
    "Journal of Electronic Materials": "JEM",
    "Journal of Electronic Testing": "JETTA",
    "Journal of Materials Science": "JMS",
    "Journal of Nanoparticle Research": "JNR",
    "Microsystem Technologies": "MST",
    "Nano Research": "Nano Res.",
    "Rare Metals": "Rare Met.",
    "Sci. China Mater.": "Sci. China Mater.",
    # MDPI
    "Applied Sciences": "Appl. Sci.",
    "Clean Technologies": "Clean Technol.",
    "International Journal of Molecular Sciences": "IJMS",
    "Journal of Composites Science": "JCS",
    "Journal of Functional Biomaterials": "JFB",
    "Journal of Low Power Electronics and Applications": "JLPEA",
    "Journal of Manufacturing and Materials Processing": "JMMP",
    "Materials Proceedings": "Mater. Proc.",
    # IOP / AIP / APS / Nature / Frontiers
    "2D Materials": "2D Mater.",
    "APL Materials": "APL Mater.",
    "Applied Physics Letters": "APL",
    "Communications Materials": "Commun. Mater.",
    "Frontiers in Energy Research": "Front. Energy Res.",
    "Frontiers in Materials": "Front. Mater.",
    "Journal of Applied Physics": "JAP",
    "Journal of Micromechanics and Microengineering": "JMM",
    "Journal of Physics D: Applied Physics": "J. Phys. D",
    "Journal of Physics: Condensed Matter": "JPCM",
    "Journal of Physics: Energy": "J. Phys. Energy",
    "Journal of Renewable and Sustainable Energy": "JRSE",
    "Journal of Semiconductors": "J. Semicond.",
    "Joule": "Joule",
    "Nano Letters": "Nano Lett.",
    "Nature Electronics": "Nat. Electron.",
    "Nature Communications": "Nat. Commun.",
    "Nature Energy": "Nat. Energy",
    "Nature Materials": "Nat. Mater.",
    "Nature Nanotechnology": "Nat. Nanotechnol.",
    "Nature Photonics": "Nat. Photon.",
    "Nature Reviews Materials": "Nat. Rev. Mater.",
    "Physical Review Materials": "PRM",
    "Science Advances": "Sci. Adv.",
    "Semiconductor Science and Technology": "SST",
    "Superconductor Science and Technology": "SSTech",
    # World Scientific / T&F / SCIRP
    "Circuits and Systems": "C&S",
    "ACS Applied Energy Materials": "ACS Appl. Energy Mater.",
    "ACS Applied Materials & Interfaces": "ACS Appl. Mater. Interfaces",
    "ACS Energy Letters": "ACS Energy Lett.",
    "Energy Environ. Sci.": "Energy Environ. Sci.",
    "International Journal of Electronics": "IJE",
    "Latest Results": "Latest Results",
    "Journal of Circuits, Systems and Computers": "JCSC",
    # arXiv
    "cs.CV updates on arXiv.org": "arXiv-CV",
    "eess.IV updates on arXiv.org": "arXiv-IV",
    "cs.LG updates on arXiv.org": "arXiv-ML",
    "arXiv perovskite solar cells": "arXiv-PSC",
    "arXiv quasi-2D perovskites": "arXiv-q2D",
    "arXiv RP perovskites": "arXiv-RP",
    "arXiv DJ perovskites": "arXiv-DJ",
}

RSS_JOURNAL_TITLE = load_journal_title_mapping(JOURNAL_NAME_FILE)


def get_journal_abbr(journal_name):
    journal_name = normalize_journal_name(journal_name)

    if journal_name in JOURNAL_ABBR:
        return JOURNAL_ABBR[journal_name]

    return journal_name


def classify_fetch_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}", str(exc)

    if isinstance(exc, urllib.error.URLError):
        inner = getattr(exc, "reason", None)
        if isinstance(inner, (socket.timeout, TimeoutError)):
            return "timeout", repr(exc)
        return "url_error", repr(exc)

    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout", repr(exc)

    return f"other_{type(exc).__name__}", repr(exc)


def build_failure_record(url, category, detail):
    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "category": category,
        "url": url,
        "detail": detail,
    }


def write_failure_log(failures):
    with open(FAILURE_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("timestamp\tcategory\turl\tdetail\n")
        for failure in failures:
            detail = str(failure["detail"]).replace("\t", " ").replace("\n", " ")
            f.write(
                f"{failure['timestamp']}\t{failure['category']}\t"
                f"{failure['url']}\t{detail}\n"
            )


def print_failure_summary(failures):
    if not failures:
        print("All RSS feeds fetched successfully.")
        return

    counts = Counter(failure["category"] for failure in failures)
    print("Fetch failure summary:")
    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")

def load_config(filename, env_var_name=None):
    """(保持你之前的 load_config 代码不变)"""
    if env_var_name and os.environ.get(env_var_name):
        print(f"Loading config from environment variable: {env_var_name}")
        content = os.environ[env_var_name]
        if '\n' in content:
            return [line.strip() for line in content.split('\n') if line.strip()]
        else:
            return [line.strip() for line in content.split(';') if line.strip()]

    file_path = filename if os.path.isabs(filename) else os.path.join(BASE_DIR, filename)

    if os.path.exists(file_path):
        print(f"Loading config from local file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]

    return []


def normalize_search_text(text):
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("α", " alpha ")
    normalized = normalized.replace("β", " beta ")
    normalized = re.sub(r"[\u2010-\u2015\u2212/-]+", " ", normalized)
    normalized = re.sub(r"[^0-9a-zA-Z+.\s]", " ", normalized)
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def build_feed_link():
    explicit_link = os.environ.get("RSS_FEED_LINK")
    if explicit_link:
        return explicit_link.strip()

    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repository:
        owner, repo = repository.split("/", 1)
        return f"https://{owner}.github.io/{repo}/filtered_feed.xml"

    return "https://github.com/your_username/your_repo"

# --- 新增：XML 非法字符清洗函数 ---
def remove_illegal_xml_chars(text):
    """
    移除 XML 1.0 不支持的 ASCII 控制字符 (Char value 0-8, 11-12, 14-31)
    """
    if not text:
        return ""
    illegal_chars = r'[\x00-\x08\x0b\x0c\x0e-\x1f]'
    return re.sub(illegal_chars, '', text)

def convert_struct_time_to_datetime(struct_time):
    if not struct_time:
        return datetime.datetime.now()
    return datetime.datetime.fromtimestamp(time.mktime(struct_time))

def parse_rss(rss_url, retries=3):
    print(f"Fetching: {rss_url}...")
    normalized_rss_url = normalize_rss_url(rss_url)
    last_failure = None

    for attempt in range(retries):
        try:
            feed_bytes, response_status = fetch_feed_bytes(rss_url)
            feed = feedparser.parse(feed_bytes)

            entries = []
            feed_title = feed.feed.get('title', 'Unknown Journal')
            journal_title = SOURCE_NAME_OVERRIDES.get(
                normalized_rss_url,
                RSS_JOURNAL_TITLE.get(normalized_rss_url, normalize_journal_name(feed_title)),
            )

            if getattr(feed, "bozo", 0) and not feed.entries:
                detail = f"attempt={attempt + 1}; {repr(feed.bozo_exception)}"
                last_failure = build_failure_record(rss_url, "parse_error", detail)
                print(f"Error parsing {rss_url} [parse_error]: {detail}")
                break

            if not feed.entries:
                detail = f"attempt={attempt + 1}; status={response_status}; feed_title={feed_title}"
                last_failure = build_failure_record(rss_url, "empty_feed", detail)
                print(f"Error parsing {rss_url} [empty_feed]: {detail}")
                break

            for entry in feed.entries:
                pub_struct = entry.get('published_parsed', entry.get('updated_parsed'))
                pub_date = convert_struct_time_to_datetime(pub_struct)

                entries.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'pub_date': pub_date,
                    'summary': entry.get('summary', entry.get('description', '')),
                    'journal': journal_title,
                    'id': entry.get('id', entry.get('link', ''))
                })
            return entries, None
        except Exception as e:
            category, detail = classify_fetch_error(e)
            detail = f"attempt={attempt + 1}; {detail}"
            last_failure = build_failure_record(rss_url, category, detail)
            print(f"Error parsing {rss_url} [{category}]: {detail}")

            if category in {"http_403", "http_404", "http_410"}:
                break

            if attempt < retries - 1:
                time.sleep(RETRY_WAIT_SECONDS)

    return [], last_failure

def get_existing_items():
    if not os.path.exists(OUTPUT_FILE):
        return []

    print(f"Loading existing items from {OUTPUT_FILE}...")
    try:
        feed = feedparser.parse(OUTPUT_FILE)
        if hasattr(feed, 'bozo') and feed.bozo == 1:
            print("Warning: Existing XML file might be corrupted. Ignoring old items.")

        entries = []
        for entry in feed.entries:
            pub_struct = entry.get('published_parsed')
            pub_date = convert_struct_time_to_datetime(pub_struct)

            entries.append({
                'title': strip_title_prefix(entry.get('title', '')),
                'link': entry.get('link', ''),
                'pub_date': pub_date,
                'summary': entry.get('summary', ''),
                'journal': entry.get('author', ''),
                'id': entry.get('id', entry.get('link', '')),
                'is_old': True
            })
        return entries
    except Exception as e:
        print(f"Error reading existing file: {e}")
        return []

def match_entry(entry, queries):
    text_to_search = normalize_search_text(entry['title'] + " " + entry['summary'])
    journal_name = normalize_journal_name(entry.get('journal', ''))

    if journal_name.startswith("arXiv ") and not any(
        term in text_to_search for term in ("solar cell", "photovoltaic", "tandem")
    ):
        return False

    for query in queries:
        keywords = [normalize_search_text(k.strip()) for k in query.split('AND')]
        match = True
        for keyword in keywords:
            if keyword and keyword not in text_to_search:
                match = False
                break
        if match:
            return True
    return False

def generate_rss_xml(items):
    """生成 RSS 2.0 XML 文件 (已加入非法字符清洗)"""
    rss_items = []

    items.sort(key=lambda x: x['pub_date'], reverse=True)
    items = items[:MAX_ITEMS]

    for item in items:
        base_title = strip_title_prefix(item['title'])
        abbr = get_journal_abbr(item['journal'])
        title = f"[{abbr}] {base_title}"

        clean_title = remove_illegal_xml_chars(title)
        clean_summary = remove_illegal_xml_chars(item['summary'])
        clean_journal = remove_illegal_xml_chars(item['journal'])

        rss_item = Item(
            title=clean_title,
            link=item['link'],
            description=clean_summary,
            author=clean_journal,
            guid=Guid(item['id']),
            pubDate=item['pub_date']
        )
        rss_items.append(rss_item)

    feed = Feed(
        title=os.environ.get("RSS_FEED_TITLE", DEFAULT_FEED_TITLE),
        link=build_feed_link(),
        description=os.environ.get("RSS_FEED_DESCRIPTION", DEFAULT_FEED_DESCRIPTION),
        language="en-US",
        lastBuildDate=datetime.datetime.now(),
        items=rss_items
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(feed.rss())
    print(f"Successfully generated {OUTPUT_FILE} with {len(rss_items)} items.")

def main():
    rss_urls = load_config('journals.dat', 'RSS_JOURNALS')
    queries = load_config('keywords.dat', 'RSS_KEYWORDS')

    if not rss_urls or not queries:
        print("Error: Configuration files are empty or missing.")
        return

    rebuild_from_scratch = os.environ.get("RSS_REBUILD_FROM_SCRATCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if rebuild_from_scratch:
        print("Skipping existing feed import because RSS_REBUILD_FROM_SCRATCH is enabled.")
        existing_entries = []
    else:
        existing_entries = get_existing_items()
    seen_ids = set(entry['id'] for entry in existing_entries)

    all_entries = existing_entries.copy()
    new_count = 0
    failures = []

    print("Starting RSS fetch from remote...")
    for url in rss_urls:
        fetched_entries, failure = parse_rss(url)
        if failure:
            failures.append(failure)

        for entry in fetched_entries:
            if entry['id'] in seen_ids:
                continue

            if match_entry(entry, queries):
                all_entries.append(entry)
                seen_ids.add(entry['id'])
                new_count += 1
                print(f"Match found: {entry['title'][:50]}...")

    print(f"Added {new_count} new entries.")
    write_failure_log(failures)
    print_failure_summary(failures)
    print(f"Wrote failure log to {FAILURE_LOG_FILE}.")
    generate_rss_xml(all_entries)

if __name__ == '__main__':
    main()
