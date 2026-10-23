"""Write the email subject + body, either from the user's template or with an AI model."""

import json
import re
from collections import defaultdict

PROVIDERS = {
    "Claude (Anthropic)": {
        "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"],
        "key_env": "ANTHROPIC_API_KEY",
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    "OpenAI": {
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"],
        "key_env": "OPENAI_API_KEY",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "Google Gemini": {
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "key_env": "GEMINI_API_KEY",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "OpenAI-compatible (Groq, OpenRouter, Ollama…)": {
        "models": ["llama-3.3-70b-versatile"],
        "key_env": "OPENAI_COMPAT_API_KEY",
        "key_url": "",
        "needs_base_url": True,
    },
}

# Claude models that take effort + structured outputs + server-side refusal fallbacks
_CLAUDE_CURRENT = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"}
_CLAUDE_FALLBACKS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

DEFAULT_SUBJECT = "Application for {target_role} – {my_name}"
DEFAULT_BODY = """Dear Hiring Team at {company},

I'm {my_name}, and I'm reaching out to ask whether {company} has any openings for the role of {target_role}{job_title_clause}.

{pitch}

I've attached my resume for your reference. I'd be glad to talk about how I could contribute to your team.

Thank you for your time.

Best regards,
{my_name}
{phone}
{my_email}
{linkedin}"""

PLACEHOLDERS = {
    "{company}": "Company name",
    "{job_title}": "Job title from the posting (may be empty)",
    "{job_title_clause}": "' (I saw your <job title> posting)' when a posting exists",
    "{target_role}": "The role you're looking for",
    "{location}": "Job location",
    "{job_url}": "Link to the job posting",
    "{my_name}": "Your name",
    "{my_email}": "Your email",
    "{phone}": "Your phone",
    "{linkedin}": "Your LinkedIn / portfolio",
    "{pitch}": "Your short pitch (set in Setup)",
}

SYSTEM_PROMPT = """You write short, genuine cold emails from a job seeker to a company, asking about job openings.

Rules:
- 110-170 words in the body. Plain text, no markdown, no emojis.
- Only state facts that appear in the candidate's resume or profile. Never invent experience, numbers or skills.
- Open with who the candidate is and the role they want. Connect 2-3 concrete strengths from the resume to the company or posting.
- If a job posting is given, refer to it by title. If not, ask whether they have openings for the role.
- Mention that the resume is attached. End with a polite call to action.
- Finish with a sign-off and the candidate's contact details exactly as given.
- Subject: specific and under 70 characters, e.g. "Python Developer application – Priya Sharma".

Return JSON only: {"subject": "...", "body": "..."}"""

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


class WriterError(Exception):
    pass


def _fields(profile: dict, company: dict) -> dict:
    job_title = company.get("job_title") or ""
    return {
        "company": company.get("name", ""),
        "job_title": job_title,
        "job_title_clause": f" (I saw your {job_title} posting)" if job_title else "",
        "target_role": profile.get("target_role", ""),
        "location": company.get("location") or "",
        "job_url": company.get("job_url") or "",
        "my_name": profile.get("name", ""),
        "my_email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "pitch": profile.get("pitch", ""),
    }


def render_template(subject_tpl: str, body_tpl: str, profile: dict, company: dict) -> tuple[str, str]:
    values = defaultdict(str, _fields(profile, company))
    subject = subject_tpl.format_map(values).strip()
    # A line that is just one placeholder (e.g. "{phone}") is dropped when that value is empty
    lines = [
        line.format_map(values)
        for line in body_tpl.splitlines()
        if not (re.fullmatch(r"\s*\{(\w+)\}\s*", line) and not values[line.strip()[1:-1]])
    ]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return subject, body


def _user_prompt(profile: dict, resume_text: str, company: dict, instructions: str) -> str:
    f = _fields(profile, company)
    posting = (
        f"Job posting: {f['job_title']} ({f['location']})\n{(company.get('job_description') or '')[:2000]}"
        if f["job_title"]
        else "No specific posting - this is a general enquiry."
    )
    return f"""<candidate>
Name: {f['my_name']}
Target role: {f['target_role']}
Email: {f['my_email']}
Phone: {f['phone']}
LinkedIn/Portfolio: {f['linkedin']}
Pitch: {f['pitch']}
</candidate>

<resume>
{resume_text[:12000]}
</resume>

<company>
Name: {f['company']}
Website: {company.get('website') or 'unknown'}
{posting}
</company>

{('Extra instructions from the candidate: ' + instructions) if instructions else ''}
Write the email now."""


def _parse(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise WriterError(f"The model didn't return JSON: {text[:200]!r}")
    try:
        data = json.loads(match.group(0), strict=False)  # models sometimes put raw newlines in strings
        return data["subject"].strip(), data["body"].strip()
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        raise WriterError(f"Couldn't read the model's reply: {e}") from e


def _claude(api_key: str, model: str, system: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    params = {
        "model": model,
        "max_tokens": 8000,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if model in _CLAUDE_CURRENT:
        params["output_config"] = {"effort": "medium", "format": {"type": "json_schema", "schema": EMAIL_SCHEMA}}
    try:
        if model in _CLAUDE_FALLBACKS:
            # If a safety classifier declines, the API retries on a fallback model in the same call
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise WriterError("Anthropic API key is invalid.")
    except anthropic.NotFoundError:
        raise WriterError(f"Model '{model}' was not found on your Anthropic account.")
    except anthropic.RateLimitError:
        raise WriterError("Anthropic rate limit hit - wait a minute and retry.")
    except anthropic.APIStatusError as e:
        raise WriterError(f"Anthropic API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise WriterError("Couldn't reach the Anthropic API - check your internet connection.")
    if response.stop_reason == "refusal":
        raise WriterError("The model declined to write this email.")
    return "".join(b.text for b in response.content if b.type == "text")


def _openai(api_key: str, model: str, system: str, prompt: str, base_url: str | None) -> str:
    import openai

    client = openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url or None)
    extra = {} if base_url else {"response_format": {"type": "json_object"}}
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            **extra,
        )
    except openai.AuthenticationError:
        raise WriterError("API key is invalid.")
    except openai.NotFoundError:
        raise WriterError(f"Model '{model}' was not found.")
    except openai.RateLimitError:
        raise WriterError("Rate limit / quota hit - check your plan or wait and retry.")
    except openai.APIStatusError as e:
        raise WriterError(f"API error {e.status_code}: {e.message}")
    except openai.APIConnectionError:
        raise WriterError("Couldn't reach the API - check the base URL and your connection.")
    return resp.choices[0].message.content or ""


def _gemini(api_key: str, model: str, system: str, prompt: str) -> str:
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json"),
        )
    except errors.APIError as e:
        raise WriterError(f"Gemini API error {e.code}: {e.message}")
    return resp.text or ""


def generate_email(
    provider: str,
    api_key: str,
    model: str,
    profile: dict,
    resume_text: str,
    company: dict,
    instructions: str = "",
    base_url: str | None = None,
) -> tuple[str, str]:
    prompt = _user_prompt(profile, resume_text, company, instructions)
    if provider == "Claude (Anthropic)":
        text = _claude(api_key, model, SYSTEM_PROMPT, prompt)
    elif provider == "Google Gemini":
        text = _gemini(api_key, model, SYSTEM_PROMPT, prompt)
    else:
        text = _openai(api_key, model, SYSTEM_PROMPT, prompt, base_url if PROVIDERS[provider].get("needs_base_url") else None)
    return _parse(text)
