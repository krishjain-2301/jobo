"""Score how well a job fits the candidate - the "ATS match" idea.

score = 60% skill overlap + 40% role relevance

- Skill overlap: of the known skills a job description mentions, how many are
  also in the resume. The missing ones are what to add to the resume (if true)
  or to learn.
- Role relevance: do the candidate's target keywords (e.g. "red team", "llm")
  appear in the job title (full marks) or only in the description (half)?

Seniority is read from the title and "N+ years" phrases, so freshers can hide
roles they won't be considered for.
"""

import re
from dataclasses import dataclass, field

# canonical skill -> regex alternatives (matched case-insensitively on word boundaries)
SKILLS: dict[str, list[str]] = {
    # AI security
    "LLM red teaming": [r"red[- ]?team(?:ing|er)?s?\b.{0,40}\b(?:llm|ai|model)s?", r"(?:llm|ai|model)s?\b.{0,40}\bred[- ]?team"],
    "Red teaming": [r"red[- ]?team(?:ing|er|s)?"],
    "Prompt injection": [r"prompt[- ]injections?"],
    "Jailbreaking": [r"jailbreak(?:s|ing)?"],
    "Adversarial ML": [r"adversarial (?:ml|machine learning|attacks?|examples?|testing|robustness|inputs?)"],
    "AI safety": [r"ai safety", r"alignment research", r"model safety"],
    "AI security": [r"ai security", r"llm security", r"ml security", r"security (?:of|for) (?:ai|llms?|ml)"],
    "OWASP LLM Top 10": [r"owasp (?:top 10 )?for llm", r"owasp llm"],
    "OWASP Top 10": [r"owasp(?! llm)"],
    "LLMs": [r"llms?", r"large language models?", r"gpt-?\d?", r"foundation models?"],
    "RAG": [r"rag", r"retrieval[- ]augmented"],
    "AI agents": [r"(?:ai|llm|autonomous|multi)[- ]?agents?", r"agentic", r"tool[- ]use", r"agents? (?:frameworks?|workflows?|orchestration|misuse|tool)", r"langchain", r"langgraph"],
    "Evals": [r"evals?", r"evaluations? (?:framework|harness|suite)s?", r"benchmark(?:s|ing)?"],
    "Promptfoo": [r"promptfoo"],
    "PyRIT": [r"pyrit"],
    "Garak": [r"garak"],
    "Ollama": [r"ollama"],
    "Prompt engineering": [r"prompt engineering", r"prompting"],
    "Machine learning": [r"machine learning", r"\bml\b", r"deep learning"],
    "PyTorch": [r"pytorch"],
    "NLP": [r"nlp", r"natural language processing"],
    "Interpretability": [r"interpretability", r"mechanistic"],
    # offensive / application security
    "Penetration testing": [r"penetration test(?:ing|er)?", r"pen[- ]?test(?:ing|er)?", r"pentest(?:ing|er)?"],
    "VAPT": [r"vapt", r"vulnerability assessments?"],
    "Web security": [r"web (?:application )?security", r"web app(?:lication)? (?:testing|pentest)"],
    "API security": [r"api security", r"api (?:testing|pentest)"],
    "Application security": [r"application security", r"appsec"],
    "Bug bounty": [r"bug bount(?:y|ies)"],
    "CTF": [r"ctfs?", r"capture the flag"],
    "Exploit development": [r"exploit(?:ation| development)?"],
    "Threat modeling": [r"threat model(?:ing|s)?"],
    "Secure coding": [r"secure coding", r"secure code review", r"code review"],
    "Burp Suite": [r"burp(?: suite)?"],
    "Nmap": [r"nmap"],
    "Wireshark": [r"wireshark"],
    "SQLMap": [r"sqlmap"],
    "Metasploit": [r"metasploit"],
    "Kali Linux": [r"kali"],
    "Active Directory": [r"active directory"],
    "Cloud security": [r"cloud security", r"aws security", r"azure security"],
    "Incident response": [r"incident response", r"\bdfir\b"],
    "Threat intelligence": [r"threat intel(?:ligence)?"],
    "SIEM": [r"siem", r"splunk"],
    "Cryptography": [r"cryptograph(?:y|ic)"],
    "Reverse engineering": [r"reverse engineering", r"ghidra", r"ida pro"],
    "Fuzzing": [r"fuzz(?:ing|er)?"],
    "Malware analysis": [r"malware analysis"],
    "GRC": [r"\bgrc\b", r"governance,? risk"],
    "ISO 27001": [r"iso[/ ]?(?:iec )?27001"],
    "NIST": [r"nist"],
    "Privacy / PII": [r"\bpii\b", r"personal data", r"data privacy", r"redaction"],
    # engineering
    "Python": [r"python"],
    "C++": [r"c\+\+"],
    "Java": [r"java(?!script)"],
    "JavaScript": [r"javascript", r"\bjs\b"],
    "TypeScript": [r"typescript"],
    "Go": [r"golang", r"\bgo\b(?= (?:or|and|,))"],
    "Rust": [r"rust"],
    "SQL": [r"\bsql\b", r"postgres(?:ql)?", r"mysql", r"sqlite"],
    "Bash / scripting": [r"bash", r"shell scripting", r"scripting"],
    "Linux": [r"linux", r"unix"],
    "Git": [r"\bgit\b", r"github"],
    "Docker": [r"docker", r"containers?"],
    "Kubernetes": [r"kubernetes", r"\bk8s\b"],
    "AWS": [r"\baws\b", r"amazon web services"],
    "GCP": [r"\bgcp\b", r"google cloud"],
    "Azure": [r"azure"],
    "FastAPI": [r"fastapi"],
    "Flask": [r"flask"],
    "React": [r"react"],
    "Next.js": [r"next\.?js"],
    "Node.js": [r"node\.?js"],
    "REST APIs": [r"rest(?:ful)? apis?"],
    "CI/CD": [r"ci/cd", r"continuous integration", r"github actions"],
    "Security automation": [r"security automation", r"automat(?:e|ing) (?:security|attacks?|testing)"],
    "Technical writing": [r"technical writing", r"write[- ]?ups?", r"document(?:ing)? findings"],
    # web / frontend
    "HTML": [r"html5?"],
    "CSS": [r"css3?"],
    "Tailwind CSS": [r"tailwind(?:\s?css)?"],
    "Bootstrap": [r"bootstrap"],
    "Sass": [r"sass", r"scss"],
    "Vue.js": [r"vue(?:\.?js)?"],
    "Angular": [r"angular(?:js)?"],
    "Svelte": [r"svelte(?:kit)?"],
    "Redux": [r"redux"],
    "jQuery": [r"jquery"],
    "Responsive design": [r"responsive (?:design|web|layouts?|ui)", r"mobile[- ]first"],
    "Web accessibility": [r"accessibility", r"wcag", r"a11y"],
    "Webpack / Vite": [r"webpack", r"vite", r"babel"],
    # backend
    "Django": [r"django"],
    "Spring Boot": [r"spring boot", r"spring framework", r"spring mvc"],
    "Express.js": [r"express(?:\.js|js)"],
    "NestJS": [r"nest\.?js"],
    ".NET / C#": [r"\.net\b", r"asp\.net", r"dotnet", r"c#"],
    "PHP": [r"php"],
    "Laravel": [r"laravel"],
    "Ruby on Rails": [r"ruby on rails", r"rails", r"ruby"],
    "GraphQL": [r"graphql"],
    "gRPC": [r"grpc"],
    "Microservices": [r"micro-?services"],
    "WebSockets": [r"web ?sockets?"],
    "System design": [r"system design", r"distributed systems", r"scalab(?:le|ility)"],
    "PostgreSQL": [r"postgres(?:ql)?"],
    "MySQL": [r"mysql"],
    "MongoDB": [r"mongo(?:db)?"],
    "Redis": [r"redis"],
    "Firebase": [r"firebase", r"firestore"],
    "Kafka": [r"kafka"],
    "RabbitMQ": [r"rabbitmq"],
    "Elasticsearch": [r"elastic ?search"],
    # testing
    "Unit testing": [r"unit tests?", r"unit testing", r"test[- ]driven", r"\btdd\b"],
    "Jest": [r"jest"],
    "Cypress": [r"cypress"],
    "Selenium": [r"selenium"],
    "Playwright": [r"playwright"],
    "Postman / API testing": [r"postman", r"api testing"],
    # mobile
    "Android": [r"android"],
    "Kotlin": [r"kotlin"],
    "iOS": [r"ios"],
    "Swift": [r"swift(?:ui)?(?= |,|\.|$)"],
    "Flutter": [r"flutter", r"dart"],
    "React Native": [r"react native"],
    # data & ML
    "Pandas": [r"pandas"],
    "NumPy": [r"numpy"],
    "Excel": [r"(?:ms|microsoft|advanced) excel", r"excel (?:skills|sheets|formulas|modell?ing)", r"spreadsheets?", r"vlookup", r"pivot tables?"],
    "Power BI": [r"power ?bi"],
    "Tableau": [r"tableau"],
    "Statistics": [r"statistics", r"statistical", r"hypothesis testing", r"regression"],
    "Data visualization": [r"data visuali[sz]ation", r"dashboards?"],
    "A/B testing": [r"a/b test(?:s|ing)?", r"experimentation"],
    "Spark": [r"(?:apache )?spark", r"pyspark"],
    "Hadoop": [r"hadoop", r"hive"],
    "Airflow": [r"airflow"],
    "dbt": [r"\bdbt\b"],
    "ETL / data pipelines": [r"etl", r"elt", r"data pipelines?"],
    "Snowflake": [r"snowflake"],
    "BigQuery": [r"bigquery"],
    "R": [r"r programming", r"rstudio", r"\br language", r"tidyverse"],
    "TensorFlow": [r"tensorflow", r"keras"],
    "scikit-learn": [r"scikit[- ]learn", r"sklearn"],
    "Computer vision": [r"computer vision", r"opencv", r"image (?:processing|recognition)"],
    "Hugging Face": [r"hugging ?face", r"transformers library"],
    "MLOps": [r"mlops", r"model deployment", r"mlflow"],
    # devops & cloud
    "Terraform": [r"terraform"],
    "Ansible": [r"ansible"],
    "Jenkins": [r"jenkins"],
    "Monitoring": [r"prometheus", r"grafana", r"datadog", r"observability"],
    "Nginx": [r"nginx"],
    "Serverless": [r"serverless", r"aws lambda", r"cloud functions"],
    # design, product, marketing
    "Figma": [r"figma"],
    "UI/UX design": [r"ui/ux", r"ux design", r"ui design", r"user experience", r"interaction design", r"user interface design"],
    "Wireframing / prototyping": [r"wirefram(?:e|es|ing)", r"prototyp(?:e|es|ing)"],
    "Adobe Creative Suite": [r"photoshop", r"illustrator", r"adobe xd", r"after effects", r"premiere pro"],
    "User research": [r"user research", r"usability testing", r"user interviews"],
    "Product management": [r"product management", r"product roadmaps?", r"product requirements", r"\bprds?\b"],
    "Agile / Scrum": [r"agile", r"scrum", r"kanban", r"sprints?"],
    "Jira": [r"jira", r"confluence"],
    "SEO": [r"\bseo\b", r"search engine optimi[sz]ation"],
    "Google Analytics": [r"google analytics", r"\bga4\b"],
    "Content writing": [r"content writing", r"copywriting", r"blog posts?", r"content creation"],
    "Social media marketing": [r"social media", r"instagram", r"linkedin marketing"],
    "Performance marketing": [r"google ads", r"meta ads", r"facebook ads", r"\bppc\b", r"paid (?:media|campaigns?)", r"sem\b"],
    "Email marketing": [r"email marketing", r"mailchimp", r"hubspot"],
    # more languages
    "Scala": [r"scala"],
    "MATLAB": [r"matlab"],
    "C": [r"\bc programming", r"\bc language", r"embedded c"],
}

# A space in a pattern matches any whitespace, so skills split across PDF lines still match
_COMPILED = {
    name: re.compile(r"(?<![\w+])(?:" + "|".join(alts).replace(" ", r"\s+") + r")(?![\w+])", re.I)
    for name, alts in SKILLS.items()
}

SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|vp|vice president|chief|architect|cxo|cto|ciso)\b", re.I
)
JUNIOR_TITLE = re.compile(r"\b(intern(ship)?|trainee|apprentice|graduate|new grad|junior|jr\.?|entry[- ]level|fresher|associate)\b", re.I)
INTERN_TITLE = re.compile(r"\b(intern(ship)?|trainee|apprentice)\b", re.I)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(?:\d{1,2}\s*)?\+?\s*years?", re.I)
NON_TECH_TITLE = re.compile(
    r"\b(account executive|sales|marketing|recruit(er|ing)|finance|accounting|legal|counsel|people|hr\b|"
    r"customer success|office|executive assistant|partnerships?|business development|bdr|sdr|channel|"
    r"account (manager|director)|ar specialist|talent|payroll|operations manager|events?|communications|policy)\b",
    re.I,
)


@dataclass
class Match:
    score: int
    level: str  # "intern" | "entry" | "mid" | "senior" | "open"
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    relevant: bool = False  # keyword in the title, or several in the description


def _literal_hints(alternatives: list[str]) -> tuple[str, ...] | None:
    """The plain word each alternative starts with ("red[- ]?team" -> "red"). If any alternative
    doesn't start with a word, there is no safe shortcut and the regex always runs."""
    hints = []
    for alt in alternatives:
        alt = alt.lower().removeprefix(r"\b")
        word = ""
        for i, ch in enumerate(alt):
            # stop at the first non-letter, or at a letter that is optional/repeated ("llms?" -> "llm")
            if not ch.isalnum() or (i + 1 < len(alt) and alt[i + 1] in "?*{"):
                break
            word += ch
        if len(word) < 2:
            return None
        hints.append(word)
    return tuple(hints)


# Running ~90 regexes over a long job description is slow; a substring check first skips the skills that can't match
_HINTS = {name: _literal_hints(alts) for name, alts in SKILLS.items()}


def extract_skills(text: str) -> set[str]:
    text = text or ""
    low = text.lower()
    return {
        name for name, rx in _COMPILED.items()
        if (_HINTS[name] is None or any(h in low for h in _HINTS[name])) and rx.search(text)
    }


def seniority(title: str, description: str) -> str:
    """"intern" | "entry" | "mid" | "senior", or "open" when the posting doesn't say."""
    title = title or ""
    if INTERN_TITLE.search(title):
        return "intern"
    if SENIOR_TITLE.search(title):
        return "senior"
    if JUNIOR_TITLE.search(title):
        return "entry"
    years = [int(n) for n in YEARS.findall(description or "") if 0 < int(n) < 30]
    if not years:
        return "open"
    min_years = min(years)
    return "entry" if min_years <= 1 else "mid" if min_years < 5 else "senior"


def parse_keywords(text: str) -> list[str]:
    return [k.strip().lower() for k in re.split(r"[,\n]", text or "") if k.strip()]


# Role families: if the target role mentions a trigger, these keywords are suggested for the job filter
ROLE_FAMILIES = [
    (r"red team|ai security|llm security|adversarial|ai safety", ["red team", "ai security", "llm", "adversarial", "jailbreak", "prompt injection", "ai safety"]),
    (r"secur|cyber|pentest|penetration|soc\b|vapt|appsec|infosec", ["security", "cyber security", "penetration test", "soc analyst", "vapt", "appsec", "offensive security"]),
    (r"front ?-?end|web|react|angular|vue|ui developer|javascript", ["frontend", "front-end", "web developer", "web development", "react", "javascript", "ui developer"]),
    (r"full ?-?stack|mern|mean", ["full stack", "fullstack", "full-stack", "mern", "web developer"]),
    (r"back ?-?end|api|node|django|spring|java developer|python developer|golang", ["backend", "back-end", "api", "node", "python developer", "java developer"]),
    (r"android|ios|mobile|flutter|react native", ["android", "ios", "mobile", "flutter", "react native"]),
    (r"data analy|business analy|analytics|\bbi\b|power bi|tableau", ["data analyst", "business analyst", "analytics", "business intelligence", "power bi", "sql"]),
    (r"data scien|machine learning|\bml\b|ai engineer|ai developer|ai/ml|deep learning|nlp|computer vision|genai|generative ai",["machine learning", "ml engineer", "ai engineer", "data scientist", "deep learning", "nlp", "computer vision", "llm"]),
    (r"data engineer|etl|big data", ["data engineer", "etl", "data pipeline", "spark", "big data"]),
    (r"devops|cloud|sre|site reliability|platform|infra", ["devops", "cloud", "sre", "site reliability", "platform engineer", "infrastructure"]),
    (r"\bqa\b|test|sdet|quality", ["qa", "quality assurance", "sdet", "test engineer", "automation testing"]),
    (r"design|ui/ux|ux|ui\b", ["ui/ux", "ux designer", "ui designer", "product designer", "designer"]),
    (r"product manag|\bapm\b|product owner", ["product manager", "product management", "associate product manager", "apm", "product analyst"]),
    (r"market|seo|content|social media|growth|brand", ["marketing", "digital marketing", "seo", "content", "social media", "growth"]),
    (r"accountant|accounting|chartered|finance|financial|audit|tax", ["accountant", "accounting", "finance", "financial analyst", "audit", "tax"]),
    (r"\bhr\b|human resources|recruit|talent|people ops", ["hr", "human resources", "recruiter", "talent acquisition", "people operations"]),
    (r"sales|business develop|account executive|account manager", ["sales", "business development", "account executive", "sdr", "bdr"]),
    (r"software|sde|developer|programmer|engineer", ["software engineer", "software developer", "sde", "developer"]),
]
LEVEL_WORDS = re.compile(r"\b(intern(ship)?|trainee|junior|jr\.?|senior|sr\.?|fresher|graduate|entry[- ]level|associate|apprentice|i{1,3})\b", re.I)


def suggest_keywords(target_role: str) -> list[str]:
    """Job-filter keywords for any role: the role itself (without the level), plus its family's usual titles."""
    role = re.sub(r"\s+", " ", LEVEL_WORDS.sub(" ", target_role or "")).strip(" -,").lower()
    if not role:
        return []
    keywords = [role]
    for trigger, family in ROLE_FAMILIES[:-1]:          # the last family is the generic "software / developer" one
        if re.search(trigger, role):
            keywords += family
            if len(keywords) >= 10:
                break
    if len(keywords) == 1 and re.search(ROLE_FAMILIES[-1][0], role):
        keywords += ROLE_FAMILIES[-1][1]                # only when nothing more specific matched
    seen, out = set(), []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:12]


def has_keyword(keyword: str, text_low: str) -> bool:
    """Keyword at the start of a word: "llm" matches "LLMs" but not "fulfillment"; "red team" matches "red teaming"."""
    start = 0
    while (i := text_low.find(keyword, start)) != -1:
        if i == 0 or not text_low[i - 1].isalnum():
            return True
        start = i + 1
    return False


def score_job(resume_skills: set[str], keywords: list[str], title: str, description: str) -> Match:
    job_skills = extract_skills(f"{title} {description}")
    matched = sorted(job_skills & resume_skills)
    missing = sorted(job_skills - resume_skills)
    # A posting that names only 2 skills tells us little - full weight needs ~6 recognised skills
    confidence = min(1.0, len(job_skills) / 6)
    skill_part = (len(matched) / len(job_skills)) * confidence if job_skills else 0.0

    title_low, desc_low = (title or "").lower(), (description or "").lower()
    title_hit = any(has_keyword(k, title_low) for k in keywords)
    desc_hits = sum(has_keyword(k, desc_low) for k in keywords)
    # Broad words like "llm" appear in every AI company's postings, so one hit in the description counts for little
    role_part = 1.0 if title_hit else 0.5 if desc_hits >= 2 else 0.2 if desc_hits else 0.0
    # Sales/HR/finance titles are pushed down for people looking for technical roles - unless that's what they're after
    wants_non_tech = any(NON_TECH_TITLE.search(k) for k in keywords)
    if NON_TECH_TITLE.search(title or "") and not title_hit and not wants_non_tech:
        role_part = 0.0
        skill_part *= 0.5

    score = round(100 * (0.6 * skill_part + 0.4 * role_part))
    return Match(
        score=score,
        level=seniority(title, description),
        matched=matched,
        missing=missing,
        relevant=title_hit or desc_hits >= 2,
    )


def passes(match: Match, min_score: int, fresher_only: bool) -> bool:
    """Relevant (keywords in the title, or several in the description), good enough, and the right level.

    Internships pass on score alone - for a student, any internship that fits the skills is worth seeing.
    """
    if fresher_only and match.level in ("mid", "senior"):
        return False
    return (match.relevant or match.level == "intern") and match.score >= min_score
