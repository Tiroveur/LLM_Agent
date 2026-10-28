"""Garde-fou unique : règles externes, validation humaine, points d'entrée pour tous les outils."""

import hashlib
import logging
import posixpath
import re
import shlex
import tomllib

from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).with_name("security_rules.toml")

REFUSAL_MESSAGE = (
    "The user refused this action for security reasons. "
    "Do not retry it; find a safer approach."
)


@dataclass(frozen=True)
class Finding:
    level: str
    reason: str
    line_no: int
    line: str


def _load_rules(path: Path = RULES_PATH):
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    rules = [
        (rule["level"].upper(), re.compile(rule["pattern"], re.IGNORECASE), rule["reason"])
        for rule in data.get("rule", [])
    ]
    extensions = {e.lower() for e in data.get("settings", {}).get("always_ask_extensions", [])}
    return rules, extensions


_RULES, _ALWAYS_ASK_EXTENSIONS = _load_rules()
_approved: set[str] = set()


def scan(text: str) -> list[Finding]:
    """Renvoie les motifs dangereux trouvés, ligne par ligne (une alerte max par règle et par ligne)."""
    findings: list[Finding] = []
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        seen: set[str] = set()
        for level, regex, reason in _RULES:
            if reason not in seen and regex.search(line):
                seen.add(reason)
                findings.append(Finding(level, reason, line_no, line.strip()[:200]))
    return findings


def ask_human(kind: str, target: str, text: str, findings: list[Finding]) -> bool:
    """Affiche les alertes et demande une validation. Refuse par défaut."""
    key = hashlib.sha256(f"{kind}\0{target}\0{text}".encode()).hexdigest()
    if key in _approved:
        return True

    worst = "HIGH" if any(f.level == "HIGH" for f in findings) else "MEDIUM"
    print("\n" + "=" * 60)
    print(f"[ALERTE SECURITE - {worst}] {kind} : {target}")
    for f in findings:
        print(f"  [{f.level}] {f.reason} (ligne {f.line_no}) : {f.line}")
    if not findings:
        print("  Aucun motif précis, mais ce type de fichier demande une validation.")
    preview = text if len(text) <= 3000 else text[:3000] + "\n[... tronqué ...]"
    print("-" * 60 + f"\n{preview}\n" + "=" * 60)

    try:
        answer = input("Autoriser ? (o = oui / n = non / t = oui et ne plus redemander pour ceci) : ")
    except (EOFError, KeyboardInterrupt):
        return False

    answer = answer.strip().lower()
    if answer in {"t", "toujours"}:
        _approved.add(key)
        return True
    return answer in {"o", "oui", "y", "yes"}


def _referenced_tmp_files(command: str, limit: int = 5) -> list[str]:
    paths = re.findall(r"(/tmp/[\w./\-]+)", command)
    return list(dict.fromkeys(paths))[:limit]


def _read_sandbox_file(sandbox, path: str, max_bytes: int = 20000) -> str | None:
    exit_code, output = sandbox.execute(f"head -c {max_bytes} {shlex.quote(path)}")
    return output if exit_code == 0 else None


def check_file(file_path: str, content: str) -> str | None:
    """À appeler avant d'écrire ou de modifier un fichier. Renvoie un message de refus, ou None."""
    findings = scan(content)
    extension = posixpath.splitext(file_path)[1].lower()
    if (findings or extension in _ALWAYS_ASK_EXTENSIONS) and not ask_human(
        "Écriture de fichier", file_path, content or "", findings
    ):
        logger.warning("Écriture bloquée par l'utilisateur : %s", file_path)
        return REFUSAL_MESSAGE
    return None


def check_command(sandbox, command: str) -> str | None:
    """À appeler avant d'exécuter une commande. Examine aussi le contenu des scripts /tmp cités."""
    findings = scan(command)
    details = command

    for path in _referenced_tmp_files(command):
        script = _read_sandbox_file(sandbox, path)
        if script:
            script_findings = scan(script)
            if script_findings:
                findings += script_findings
                details += f"\n\n--- contenu de {path} ---\n{script}"

    if findings and not ask_human("Commande", command[:200], details, findings):
        logger.warning("Commande bloquée par l'utilisateur : %s", command)
        return REFUSAL_MESSAGE
    return None