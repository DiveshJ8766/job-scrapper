# Prompts

This file documents, verbatim, what the pipeline sends to the LLM. It is generated from
`pipeline/classify/prompt.py` and `pipeline/classify/schema.py`. If you change those files,
bump `PROMPT_VERSION`; every job classified with an older version is reclassified on the next run.

- **Prompt version:** `v1`
- **Default model:** `gemini-2.5-flash-lite` (switch with `LLM_PROVIDER` / `LLM_MODEL`)
- **Temperature:** `0` (set by `LLM_TEMPERATURE`; omitted automatically for OpenAI reasoning models that reject it)
- **Max output tokens:** 512
- **Description limit:** first 4,000 characters (marked "(truncated)" when cut)

## System prompt

```text
You classify job postings for an Indian job board. Return only the JSON object described by the schema. Base every field strictly on the posting text. Never guess or use outside knowledge about the company.

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

confidence - high when the posting states the facts directly, medium when you had to interpret, low when the posting is vague or ambiguous.
```

## User message template

```text
Classify this job posting.

Title: {title}
Company: {company}
Location (as listed): {location}
Employment type (as listed): {employment_type}
Description{truncated}:
{description}
```

Missing fields are sent as `not listed` / `not provided`, never left blank or guessed.

### Example user message

```text
Classify this job posting.

Title: Associate Software Engineer (Frontend)
Company: Example Labs
Location (as listed): Bangalore, Karnataka, India
Employment type (as listed): Full-time
Description:
We are hiring freshers (0-1 years) to build React and TypeScript interfaces for our analytics product. Hybrid, 3 days a week in our Bangalore office.
```

## Structured output schema

The model must return exactly one JSON object. The schema goes to the provider's structured
output feature (Gemini `responseSchema` with `responseMimeType: application/json`; OpenAI
`response_format: json_schema` with `strict: true`). The response is then checked again by
Pydantic (`LLMClassification`, `extra="forbid"`), so a provider-side slip can't reach the database.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "role",
    "cities",
    "is_remote",
    "job_type",
    "experience_level",
    "confidence"
  ],
  "properties": {
    "role": {
      "type": "string",
      "enum": [
        "Frontend Developer",
        "Backend Developer",
        "Full Stack Developer",
        "Software Engineer",
        "Data Analyst",
        "Data Scientist",
        "Machine Learning Engineer",
        "AI Engineer",
        "DevOps Engineer",
        "QA Engineer",
        "UI UX Designer",
        "Product Manager",
        "Other",
        "Unknown"
      ]
    },
    "cities": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "is_remote": {
      "type": "boolean"
    },
    "job_type": {
      "type": "string",
      "enum": [
        "Full-time",
        "Part-time",
        "Internship",
        "Contract",
        "Temporary",
        "Unknown"
      ]
    },
    "experience_level": {
      "type": "string",
      "enum": [
        "Internship",
        "Fresher",
        "Junior",
        "Mid",
        "Senior",
        "Unknown"
      ]
    },
    "confidence": {
      "type": "string",
      "enum": [
        "high",
        "medium",
        "low"
      ]
    }
  }
}
```

(Gemini receives the same fields in its OpenAPI-subset dialect, see `json_schema_gemini()`.)

`confidence` is not stored on the job. It is kept in `classification_logs.classification_result`
and copied into the evaluation CSV, so low-confidence cases can be examined.

## Repair prompt (invalid output)

If the response is not valid JSON or fails schema validation, the same request is sent once more
with this appended to the user message:

```text
Your previous answer was rejected: <validation error, max 300 chars>
Return a corrected JSON object that matches the schema exactly.
```

## Post-processing (deterministic, after the LLM)

These rules run in code, not in the prompt (`pipeline/classify/classifier.py::postprocess`):

1. **City normalization.** Each city is mapped to one canonical name using `pipeline/cities.py`
   (Bangalore → Bengaluru, Gurgaon → Gurugram, Bombay → Mumbai, ...).
2. **Hallucination guard.** A city is kept only if the job's location field, title or description
   actually mentions it (under any alias). Anything else is dropped and recorded in
   `dropped_cities` in the log.
3. **Remote.** `is_remote` is kept only if the posting text contains a remote / work-from-home
   phrase. Remote jobs get `Remote` added to `cities` so they can be filtered.
4. **Unknown.** If no city survives, `cities = ["Unknown"]`.
5. `city` (single display value) = the first entry of `cities`.

## Design notes

- Category definitions sit in the system prompt so the shared prefix is identical for every
  request. That keeps behaviour consistent and lets providers apply implicit prompt caching.
- Ambiguous categories are settled explicitly in the prompt (mobile developers → Software Engineer,
  data engineers → Other, SDET → QA Engineer), so the evaluation measures the model rather than
  disagreements about definitions. The human evaluation labels follow the same definitions.
- The model only labels. Every value is checked against a fixed list, both by the schema and by
  CHECK constraints in Postgres.
