import re
import csv


def load_token_exclude(path):
    tokens = set()
    try:
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                t = row.get('token', '').strip().upper()
                if t:
                    tokens.add(t)
    except FileNotFoundError:
        pass
    return tokens


def load_token_expand(path):
    expand = {}
    try:
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                src = row.get('source', '').strip().upper()
                targets = [t.strip().upper() for t in row.get('targets', '').split(',') if t.strip()]
                if src and targets:
                    expand[src] = targets
    except FileNotFoundError:
        pass
    return expand


def _fmt_float(val):
    if val == int(val):
        return str(int(val))
    return f"{val:.10f}".rstrip('0')


def _normalize_token(t):
    t = t.upper().strip()
    if not t:
        return ''

    # Drop pure punctuation (e.g. standalone "+/-" from split artifacts)
    if re.match(r'^[^A-Za-z0-9]+$', t):
        return ''

    # Underscore → hyphen
    t = t.replace('_', '-')

    # Capacitance: NF / N → UF  (100NF, 100N → 0.1UF)
    m = re.match(r'^(\d+(?:\.\d+)?)N[F]?$', t)
    if m:
        return _fmt_float(float(m.group(1)) / 1000) + 'UF'

    # Capacitance: PF / P → UF (unify all capacitance to UF for consistent comparison)
    m = re.match(r'^(\d+(?:\.\d+)?)P[F]?$', t)
    if m:
        val = float(m.group(1))
        return _fmt_float(val / 1_000_000) + 'UF'

    # Capacitance: UF variants (0.1UF, 0.1U, 0.1u)
    m = re.match(r'^(\d+(?:\.\d+)?)[Uu][Ff]?$', t)
    if m:
        return m.group(1) + 'UF'

    # Resistance: KOHM → K
    m = re.match(r'^(\d+(?:\.\d+)?)[Kk][Oo][Hh][Mm]$', t)
    if m:
        return m.group(1) + 'K'

    # Resistance: MOHM → M
    m = re.match(r'^(\d+(?:\.\d+)?)[Mm][Oo][Hh][Mm]$', t)
    if m:
        return m.group(1) + 'M'

    # Resistance: R notation (4R7 → 4.7OHM, 10R → 10OHM)
    m = re.match(r'^(\d+)[Rr](\d+)$', t)
    if m:
        return f"{m.group(1)}.{m.group(2)}OHM"
    m = re.match(r'^(\d+(?:\.\d+)?)[Rr]$', t)
    if m:
        return m.group(1) + 'OHM'

    # Inductance: NH → UH
    m = re.match(r'^(\d+(?:\.\d+)?)N[Hh]$', t)
    if m:
        return _fmt_float(float(m.group(1)) / 1000) + 'UH'

    # Inductance: UH
    m = re.match(r'^(\d+(?:\.\d+)?)[Uu][Hh]$', t)
    if m:
        return m.group(1) + 'UH'

    # Package: common 3-digit codes → pad to 4 digits
    if re.match(r'^\d{3}$', t) and t in {'201', '402', '603', '805'}:
        return '0' + t

    # Dimension: reorder so smaller value comes first.
    # ^...$ requires the entire token to be digits-X-digits, so package codes
    # like 6M3X12M5 (M = decimal point) never match — confirmed safe by RD.
    # If Ampere normalization is added in future, use r'^(\d+(?:\.\d+)?)A$'
    # (RD confirmed 5.08A = Ampere, not a package suffix).
    m = re.match(r'^(\d+)[Xx*](\d+)$', t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return f"{min(a, b)}*{max(a, b)}"

    return t


def _split_text(text):
    text = str(text)
    # Remove parenthetical markers like (EOP), (NP), etc.
    text = re.sub(r'\([A-Z/]+\)', ' ', text)
    # Replace | with space
    text = text.replace('|', ' ')
    # Normalize tolerance: ±10% → +/-10%
    text = re.sub(r'[±](\d+(?:\.\d+)?)%', r'+/-\1%', text)
    # Normalize power fractions: 1/10W → 0.1W
    text = re.sub(r'\b(\d+)/(\d+)[Ww]\b',
                  lambda m: _fmt_float(int(m.group(1)) / int(m.group(2))) + 'W', text)

    # Split on whitespace, comma, and colon.
    # Colon separates label prefixes from values (e.g. ESR:10M → ESR + 10M,
    # DCR:0.15OHM → DCR + 0.15OHM). This prevents label context from
    # polluting value tokens and avoids ambiguous M-suffix interpretation
    # (RD confirmed ESR:10M uses lowercase m = milli, not Mega).
    raw = re.split(r'[\s,:]+', text)

    tokens = []
    for t in raw:
        t = t.strip()
        if not t:
            continue
        # Split on "/" unless: starts with "+/-", or both sides are short letters (M/C, S/C)
        if ('/' in t
                and not t.startswith('+/-')
                and not re.match(r'^[A-Za-z]{1,3}/[A-Za-z]{1,3}$', t)):
            for part in t.split('/'):
                part = part.strip()
                if part:
                    tokens.append(part)
        else:
            tokens.append(t)
    return tokens


def tokenize_plm(desc_spec, token_exclude=None):
    tokens = set()
    for t in _split_text(str(desc_spec) if desc_spec else ''):
        n = _normalize_token(t)
        if n:
            tokens.add(n)
    if token_exclude:
        tokens -= token_exclude
    return frozenset(tokens)


def tokenize_bom(spec_summary, spec_cols, token_exclude=None, token_expand=None):
    parts = []
    if spec_summary and str(spec_summary).strip() not in ('', 'nan'):
        parts.append(str(spec_summary))
    for s in (spec_cols or []):
        if s and str(s).strip() not in ('', 'nan'):
            parts.append(str(s))

    tokens = set()
    for t in _split_text(' '.join(parts)):
        n = _normalize_token(t)
        if n:
            tokens.add(n)

    if token_exclude:
        tokens -= token_exclude

    # TOKEN_EXPAND: replace BOM-specific tokens with PLM vocabulary
    # Must run after TOKEN_EXCLUDE and before frozenset
    if token_expand:
        expanded = set()
        for t in tokens:
            if t in token_expand:
                expanded.update(token_expand[t])
            else:
                expanded.add(t)
        tokens = expanded

    return frozenset(tokens)
