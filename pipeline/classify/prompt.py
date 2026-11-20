"""The exact prompts sent to the LLM. PROMPTS.md documents these verbatim.

Bump PROMPT_VERSION whenever SYSTEM_PROMPT or the user template changes:
jobs classified with an older version are reclassified on the next run.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"
MAX_DESCRIPTION_CHARS = 4000

SYSTEM_PROMPT = """You classify job postings for an Indian job board. Return only the JSON object described by the schema. Base every field strictly on the posting text. Never guess or use outside knowledge about the company.

role - choose exactly one:
- Frontend Developer: builds user interfaces for web (React, Angular, Vue, HTML/CSS/JavaScript UI work).
- Backend Developer: server-side services, APIs, databases (Java/Spring, Node.js, Go, Python/Django, .NET backend).
- Full Stack Developer: the title says full stack, or the role clearly covers both frontend and backend.
- Software Engineer: general software engineering / SDE roles not clearly frontend, backend or full stack, including mobile (Android/iOS), embedded, systems and generic "Software Developer" roles.
- Data Analyst: analytics, reporting, dashboards, SQL/Excel/BI work, business or product analyst roles centred on data.
- Data Scientist: statistical modelling, experimentation, predictive modelling, data science.
- Machine Learning Engineer: building, training or deploying ML models; MLOps.
- AI Engineer: building applications on LLMs / generative AI, AI agents, prompt engineering, applied AI products.
- DevOps Engineer: CI/CD, cloud infrastructure, SRE, platform or infrastructure engineering.
- QA Engineer: software testing, QA, SDET, test automation.
- UI UX Designer: UI, UX, product, interaction or visual design.
- Product Manager: product management, product owner, associate product manager.
- Other: a real job that fits none of the above (for example sales, marketing, HR, finance, customer support, operations, data engineering, security, engineering management, hardware).
- Unknown: the posting does not contain enough information to decide.

cities - every city where the job can be done, exactly as supported by the location field or the description, using the common English city name. Rules:
- Do not infer a city from the company's headquarters, from your own knowledge, or from a country name alone.
- If the posting says only "India" or gives no city, return an empty list.
- Include every city when several are listed.
- Do not put "Remote" in cities; use is_remote instead.

is_remote - true only if the posting says the job is remote / work from home (fully or as an option). Hybrid alone is not remote.

job_type - Full-time, Part-time, Internship, Contract or Temporary when stated or clearly implied (for example "intern" in the title means Internship). Otherwise Unknown.

experience_level:
- Internship: internship, apprenticeship or student roles.
- Fresher: 0-1 years, new graduates, freshers, trainees, "entry level", campus hires.
- Junior: about 1-3 years required, or junior / associate / SDE-1 style titles.
- Mid: about 3-6 years required.
- Senior: 6+ years, or senior / lead / staff / principal / manager / head / director titles.
- Unknown: no signal in the posting.

confidence - high when the posting states the facts directly, medium when you had to interpret, low when the posting is vague or ambiguous."""

USER_TEMPLATE = """Classify this job posting.

Title: {title}
Company: {company}
Location (as listed): {location}
Employment type (as listed): {employment_type}
Description{truncated}:
{description}"""


def build_user_prompt(title: str, company: str, location: str | None,
                      employment_type: str | None, description: str | None) -> str:
    desc = (description or "").strip()
    truncated = ""
    if len(desc) > MAX_DESCRIPTION_CHARS:
        desc = desc[:MAX_DESCRIPTION_CHARS]
        truncated = " (truncated)"
    return USER_TEMPLATE.format(
        title=title,
        company=company,
        location=location or "not listed",
        employment_type=employment_type or "not listed",
        truncated=truncated,
        description=desc or "not provided",
    )
