"""Third-person pronoun rewriting for admin/colleague queries."""
import re

_THIRD_PERSON_RULES = [
    (r"\byou['’]re\b", "{first} is"),
    (r"\byou['’]ve\b", "{first} has"),
    (r"\byou['’]ll\b", "{first} will"),
    (r"\byou['’]d\b", "{first} would"),
    (r"\byou\s+don['’]t\s+have\b", "{first} doesn't have"),
    (r"\byou\s+have\b", "{first} has"),
    (r"\byou\s+were\b", "{first} was"),
    (r"\byou\s+worked\b", "{first} worked"),
    (r"\byou\s+are\b", "{first} is"),
    (r"\byourself\b", "themselves"),
    (r"\byour\b", "{first}'s"),
    (r"\byou\b", "{first}"),
]

_QUOTED_SPAN_RE = re.compile(
    r"\"[^\"]*\"|(?<!\w)'[^']*'(?!\w)|\u201c[^\u201d]*\u201d|\u2018[^\u2019]*\u2019"
)


def _third_person(answer: str, subject_name: str | None) -> str:
    """When an admin asks about a colleague, speak about that person rather than the requester."""
    if not answer or not subject_name or not subject_name.strip():
        return answer
    first = subject_name.split()[0]
    rules = [
        (re.compile(pattern, re.IGNORECASE), template.replace("{first}", first))
        for pattern, template in _THIRD_PERSON_RULES
    ]

    def rewrite(segment: str) -> str:
        for regex, replacement in rules:
            segment = regex.sub(lambda _m, r=replacement: r, segment)
        return segment

    pieces = []
    position = 0
    for quoted in _QUOTED_SPAN_RE.finditer(answer):
        pieces.append(rewrite(answer[position:quoted.start()]))
        pieces.append(quoted.group())
        position = quoted.end()
    pieces.append(rewrite(answer[position:]))
    return "".join(pieces)
