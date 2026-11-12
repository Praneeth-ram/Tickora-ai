import pathlib

for path in pathlib.Path("backend/repositories").glob("*_repository.py"):
    text = path.read_text(encoding="utf-8")
    if "raise ValueError(" not in text:
        continue
    text = text.replace("raise ValueError(", "raise BadRequestError(")
    if "from backend.exceptions import BadRequestError" not in text:
        text = "from backend.exceptions import BadRequestError\n" + text
    path.write_text(text, encoding="utf-8")
    print("updated", path)