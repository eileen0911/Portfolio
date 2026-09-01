import json
import re
import time

try:
    from ..normalization.tokenizer import tokenize_bom
except ImportError:  # pragma: no cover - supports direct script execution
    from pathlib import Path
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.stages.normalization.tokenizer import tokenize_bom

STATUS_PRIORITY = {'Production': 0, 'Prototype': 1, 'Preliminary': 2}

SYSTEM_PROMPT = (
    "You are an electronic component part-mapping assistant. "
    "Return one compact JSON object immediately. "
    "Do not think step by step. Do not write analysis, markdown, comments, or extra text. "
    "Use only part numbers shown inside square brackets in the candidate lists, or NO_MATCH."
)

# ---------------------------------------------------------------------------
# Token intersection helpers
# ---------------------------------------------------------------------------

def _score_group(bom_set, index_dict):
    """Returns [(pn, score, desc, status), ...] sorted best-first."""
    rows = []
    for pn, (tok_set, desc, status) in index_dict.items():
        score = len(bom_set & tok_set)
        rows.append((pn, score, desc, status))
    rows.sort(key=lambda x: (-x[1], STATUS_PRIORITY.get(x[3], 99)))
    return rows


def _top_n(scored, n):
    return scored[:n]


PREFER_G_PREFIXES = {"45C", "448"}


def _prefer_g_key(part_number):
    match = re.fullmatch(r"(45C|448)-([GE])(\d+)", str(part_number).strip())
    if not match:
        return None
    prefix, variant, serial = match.groups()
    return prefix, serial, variant


def _dedupe_prefer_g_part_numbers(scored):
    """Drop matching -E PNs when a 45C/448 -G PN has the same serial."""
    g_keys = set()
    for pn, *_ in scored:
        parsed = _prefer_g_key(pn)
        if parsed and parsed[2] == "G":
            g_keys.add((parsed[0], parsed[1]))

    filtered = []
    for item in scored:
        pn = item[0]
        parsed = _prefer_g_key(pn)
        if parsed and parsed[2] == "E" and (parsed[0], parsed[1]) in g_keys:
            continue
        filtered.append(item)
    return filtered


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _build_prompt(spec_summary, spec_vals, active_cands, inactive_cands):
    lines = []
    lines.append(f"BOM spec summary: {spec_summary}")
    non_null = [v for v in spec_vals if v and str(v).strip() not in ('', 'nan')]
    if non_null:
        lines.append(f"BOM spec fields: {', '.join(str(v) for v in non_null)}")
    lines.append("")

    lines.append("Active candidates (Production/Prototype/Preliminary):")
    if active_cands:
        for i, (pn, score, desc, status) in enumerate(active_cands, 1):
            lines.append(f"{i}. [{pn}] score={score} status={status} desc={desc}")
    else:
        lines.append("No active candidates")
    lines.append("")

    lines.append("Inactive candidates (EOP/EOL/DNI):")
    if inactive_cands:
        for i, (pn, score, desc, status) in enumerate(inactive_cands, 1):
            lines.append(f"{i}. [{pn}] score={score} status={status} desc={desc}")
    else:
        lines.append("No inactive candidates")
    lines.append("")

    lines.append(
        "Choose the best match from each candidate group.\n"
        "Rules:\n"
        "- matched_part_number must be exactly one PLM part number from square brackets above, or NO_MATCH.\n"
        "- Do not use manufacturer part numbers from descriptions.\n"
        "- confidence must be one of High, Mid, Low.\n"
        "- difference must be an array of short strings. Use [] if there is no important difference.\n"
        "- Return valid JSON only. No markdown fences. No explanation outside JSON.\n"
        "- Do not include a reasoning field.\n"
        "Required JSON schema:"
    )
    lines.append('''{
  "best_active": {
    "matched_part_number": "PLM_PART_NUMBER_OR_NO_MATCH",
    "confidence": "High|Mid|Low",
    "difference": ["short difference"]
  },
  "best_inactive": {
    "matched_part_number": "PLM_PART_NUMBER_OR_NO_MATCH",
    "confidence": "High|Mid|Low",
    "difference": ["short difference"]
  }
}''')

    return '\n'.join(lines)

def _call_llm(client, model, prompt, retries=3, delay=2):
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=1200,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "enable_thinking": False,
                    "reasoning_effort": "none",
                },
            )
            choice = resp.choices[0]
            content = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", "")
            return content, finish_reason
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def _call_llm_for_json(client, model, prompt, parse_retries=2):
    raw = ""
    finish_reason = ""
    last_error = None
    user_prompt = "/no_think\n" + prompt

    for attempt in range(parse_retries + 1):
        raw, finish_reason = _call_llm(client, model, user_prompt)
        try:
            return _parse_response(raw), raw, finish_reason, None
        except ValueError as e:
            last_error = e
            user_prompt = (
                "/no_think\n"
                "Your previous answer was not valid JSON or was incomplete. "
                "Return exactly one complete JSON object using the required schema. "
                "No markdown, no comments, no text outside JSON.\n\n"
                + prompt
            )

    return None, raw, finish_reason, last_error

def _parse_response(text):
    """Returns parsed dict or raises ValueError."""
    if text is None:
        raise ValueError("Cannot parse JSON from empty response")

    original = str(text)
    text = _normalize_response_text(original)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != '{':
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Cannot parse JSON from: {_log_excerpt(original)}")


def _normalize_response_text(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'</?think>', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text).strip()
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\uff02": '"',
        "\uff5b": '{',
        "\uff5d": '}',
        "\uff3b": '[',
        "\uff3d": ']',
        "\uff1a": ':',
        "\uff0c": ',',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _log_excerpt(text, limit=1000):
    text = '' if text is None else str(text)
    text = text.replace('\r', '\\r').replace('\n', '\\n')
    return text[:limit]


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------

def _extract_result(parsed, key, candidates):
    """
    Extracts matched_part_number / confidence / difference from parsed dict.
    Returns (pn, conf, diff_list) with validation.
    """
    block = parsed.get(key, {})
    pn = str(block.get('matched_part_number', 'NO_MATCH')).strip()
    conf = str(block.get('confidence', 'Low')).strip()
    diff = block.get('difference', [])
    if not isinstance(diff, list):
        diff = [str(diff)]
    diff_str = '; '.join(str(d) for d in diff)

    valid_pns = {c[0] for c in candidates}
    if pn != 'NO_MATCH' and pn not in valid_pns:
        pn = 'NO_MATCH'
        conf = 'Low'

    return pn, conf, diff_str


def _build_top3(llm_pn, scored_cands, plm_index_group):
    """
    Returns list of up to 3 (pn, desc) tuples.
    #1 = LLM pick (or ('NO_MATCH','') if LLM found nothing).
    #2/#3 = token intersection rank, skipping whatever was chosen as #1.
    """
    result = []
    if llm_pn == 'NO_MATCH':
        result.append(('NO_MATCH', ''))
    elif llm_pn:
        desc = plm_index_group.get(llm_pn, ('', '', ''))[1]
        result.append((llm_pn, desc))

    for pn, score, desc, status in scored_cands:
        if len(result) >= 3:
            break
        if pn != llm_pn:
            result.append((pn, desc))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_parts(clean_df, plm_index, llm_client, model_name,
              top_n=10, token_exclude=None, token_expand=None, log_path=None,
              progress_callback=None):
    """
    Returns (result_df, review_items).
    result_df: clean_df rows + Active/Inactive result columns
    review_items: list of dicts for mapping-stage issues
    log_path: if set, writes full LLM prompt/response log to this file
    progress_callback: optional callable receiving progress dicts for UI updates
    """
    active_index = plm_index['active']
    inactive_index = plm_index['inactive']

    spec_cols = [c for c in clean_df.columns if c == 'Spec' or c.startswith('Spec.')]

    # --- Build BOM token sets ---
    bom_sets = []
    for _, row in clean_df.iterrows():
        spec_vals = [row.get(c) for c in spec_cols]
        bom_set = tokenize_bom(
            row.get('SpecSummary', ''),
            spec_vals,
            token_exclude=token_exclude,
            token_expand=token_expand,
        )
        bom_sets.append(bom_set)
    clean_df = clean_df.copy()
    clean_df['_bom_set'] = bom_sets

    # --- Deduplicate by frozenset; also track all locations per set ---
    unique_sets = {}   # frozenset -> representative row index
    set_locations = {} # frozenset -> list of Location strings
    for idx, bom_set in enumerate(bom_sets):
        loc = str(clean_df.iloc[idx].get('Location', ''))
        if bom_set not in unique_sets:
            unique_sets[bom_set] = idx
            set_locations[bom_set] = []
        set_locations[bom_set].append(loc)

    total = len(unique_sets)
    print(f"Total rows: {len(clean_df)}, unique token sets: {total}")
    _emit_progress(progress_callback, completed=0, total=total, status='Preparing LLM mapping')

    log_file = open(log_path, 'w', encoding='utf-8') if log_path else None

    def _log(text):
        if log_file:
            log_file.write(text + '\n')
            log_file.flush()

    review_items = []
    cache = {}  # frozenset -> result dict

    t_total = time.time()
    try:
        for call_idx, (bom_set, rep_idx) in enumerate(unique_sets.items(), 1):
            row = clean_df.iloc[rep_idx]
            spec_vals = [row.get(c) for c in spec_cols]
            spec_summary = str(row.get('SpecSummary', ''))
            locations = set_locations[bom_set]

            display_locations = [loc for loc in locations if str(loc).strip()]
            loc_str = ', '.join(display_locations[:3]) + (
                f' +{len(display_locations)-3}' if len(display_locations) > 3 else ''
            )
            if not loc_str:
                loc_str = 'No Location'
            spec_preview = spec_summary[:55] + ('...' if len(spec_summary) > 55 else '')
            ts = time.strftime('%H:%M:%S')
            print(f"{ts} [{call_idx:3d}/{total}] {loc_str:<12} {spec_preview}", end='', flush=True)
            _emit_progress(
                progress_callback,
                completed=call_idx - 1,
                total=total,
                status='Mapping',
                spec_summary=spec_summary,
                locations=display_locations,
            )

            # Token intersection
            active_scored = _dedupe_prefer_g_part_numbers(_score_group(bom_set, active_index))
            inactive_scored = _dedupe_prefer_g_part_numbers(_score_group(bom_set, inactive_index))
            active_cands = _top_n(active_scored, top_n)
            inactive_cands = _top_n(inactive_scored, top_n)

            prompt = _build_prompt(spec_summary, spec_vals, active_cands, inactive_cands)

            # --- Log: candidates + header ---
            _log('=' * 80)
            _log(f'[{call_idx}/{total}] Location(s): {", ".join(locations)}')
            _log(f'BOM tokens: {", ".join(sorted(bom_set))}')
            _log('[Active TOP10]')
            for i, (pn, score, desc, status) in enumerate(active_cands, 1):
                _log(f'  {i:2d}. [{pn}] score={score} | {desc[:70]}')
            _log('[Inactive TOP10]')
            for i, (pn, score, desc, status) in enumerate(inactive_cands, 1):
                _log(f'  {i:2d}. [{pn}] score={score} | {desc[:70]}')

            # LLM call
            t_call = time.time()
            raw = ''
            finish_reason = ''
            try:
                parsed, raw, finish_reason, parse_error = _call_llm_for_json(
                    llm_client,
                    model_name,
                    prompt,
                )
            except Exception as e:
                elapsed = time.time() - t_call
                raw = str(e)
                _log(f'RESULT: LLM_ERROR | {raw[:100]}')
                print(f"  -> LLM_ERROR ({elapsed:.1f}s)")
                cache[bom_set] = _error_result('LLM_ERROR', active_cands, inactive_cands,
                                               active_index, inactive_index)
                _emit_progress(
                    progress_callback,
                    completed=call_idx,
                    total=total,
                    status='Completed',
                    spec_summary=spec_summary,
                    locations=display_locations,
                )
                continue

            elapsed = time.time() - t_call

            if parse_error:
                _log(f'RESULT: PARSE_ERROR | finish_reason={finish_reason} | response_chars={len(raw)} | {parse_error}')
                _log(f'RAW_RESPONSE: {_log_excerpt(raw, 4000)}')
                print(f"  -> PARSE_ERROR ({elapsed:.1f}s)")
                cache[bom_set] = _error_result('PARSE_ERROR', active_cands, inactive_cands,
                                               active_index, inactive_index)
                _emit_progress(
                    progress_callback,
                    completed=call_idx,
                    total=total,
                    status='Completed',
                    spec_summary=spec_summary,
                    locations=display_locations,
                )
                continue

            act_pn, act_conf, act_diff = _extract_result(parsed, 'best_active', active_cands)
            inact_pn, inact_conf, inact_diff = _extract_result(parsed, 'best_inactive', inactive_cands)

            in_active = 'IN_TOP10' if act_pn in {c[0] for c in active_cands} else 'NOT_IN_TOP10'
            in_inactive = 'IN_TOP10' if inact_pn in {c[0] for c in inactive_cands} else 'NOT_IN_TOP10'
            _log(f'RESULT: Active={act_pn} [{act_conf}] {in_active} | Inactive={inact_pn} [{inact_conf}] {in_inactive}')

            act_flag = '' if in_active == 'IN_TOP10' else ' !'
            inact_flag = '' if in_inactive == 'IN_TOP10' else ' !'
            print(f"  -> A:{act_pn} [{act_conf}]{act_flag} | I:{inact_pn} [{inact_conf}]{inact_flag}  ({elapsed:.1f}s)")

            act_top3 = _build_top3(act_pn, active_scored, active_index)
            inact_top3 = _build_top3(inact_pn, inactive_scored, inactive_index)

            cache[bom_set] = {
                'active_top3': act_top3,
                'inactive_top3': inact_top3,
                'act_conf': act_conf,
                'act_diff': act_diff,
                'inact_conf': inact_conf,
                'inact_diff': inact_diff,
                'error': None,
            }
            _emit_progress(
                progress_callback,
                completed=call_idx,
                total=total,
                status='Completed',
                spec_summary=spec_summary,
                locations=display_locations,
            )
    finally:
        if log_file:
            _log('=' * 80)
            log_file.close()
        print(f"\n{time.strftime('%H:%M:%S')} LLM mapping done: {total} calls in {time.time() - t_total:.1f}s")

    # --- Map results back to all rows ---
    result_rows = []
    for idx, row in clean_df.iterrows():
        bom_set = row['_bom_set']
        res = cache.get(bom_set)
        loc = row.get('Location', '')
        spec_summary = str(row.get('SpecSummary', ''))

        out = row.drop('_bom_set').to_dict()

        if res is None or res.get('error') in ('LLM_ERROR', 'PARSE_ERROR'):
            error_tag = res['error'] if res else 'LLM_ERROR'
            issue = 'LLM Parse Error' if error_tag == 'PARSE_ERROR' else 'LLM Connection Error'
            review_items.append({'Location': loc, 'SpecSummary': spec_summary,
                                  'Issue Type': issue, 'Original Value': ''})
            out.update(_empty_result_cols(error_tag))
        else:
            act_top3 = res['active_top3']
            inact_top3 = res['inactive_top3']
            act_conf = res['act_conf']
            act_diff = res['act_diff']
            inact_conf = res['inact_conf']
            inact_diff = res['inact_diff']

            # Active TOP3
            a1_pn = act_top3[0][0] if len(act_top3) > 0 else 'NO_MATCH'
            a1_desc = act_top3[0][1] if len(act_top3) > 0 else ''
            a2_pn = act_top3[1][0] if len(act_top3) > 1 else ''
            a2_desc = act_top3[1][1] if len(act_top3) > 1 else ''
            a3_pn = act_top3[2][0] if len(act_top3) > 2 else ''
            a3_desc = act_top3[2][1] if len(act_top3) > 2 else ''

            # Inactive TOP3
            i1_pn = inact_top3[0][0] if len(inact_top3) > 0 else 'NO_MATCH'
            i1_desc = inact_top3[0][1] if len(inact_top3) > 0 else ''
            i2_pn = inact_top3[1][0] if len(inact_top3) > 1 else ''
            i2_desc = inact_top3[1][1] if len(inact_top3) > 1 else ''
            i3_pn = inact_top3[2][0] if len(inact_top3) > 2 else ''
            i3_desc = inact_top3[2][1] if len(inact_top3) > 2 else ''

            if a1_pn == 'NO_MATCH':
                act_conf = 'NO_MATCH'
                review_items.append({'Location': loc, 'SpecSummary': spec_summary,
                                      'Issue Type': 'No Active Match Found', 'Original Value': ''})
            elif act_conf == 'Low':
                review_items.append({'Location': loc, 'SpecSummary': spec_summary,
                                      'Issue Type': 'Low Confidence Mapping', 'Original Value': a1_pn})

            out.update({
                'Active_1_PN': a1_pn,
                'Active_1_Desc': a1_desc,
                'Active_1_Conf': act_conf,
                'Active_1_Diff': act_diff,
                'Active_2_PN': a2_pn,
                'Active_2_Desc': a2_desc,
                'Active_3_PN': a3_pn,
                'Active_3_Desc': a3_desc,
                'Inactive_1_PN': i1_pn,
                'Inactive_1_Desc': i1_desc,
                'Inactive_1_Conf': inact_conf,
                'Inactive_1_Diff': inact_diff,
                'Inactive_2_PN': i2_pn,
                'Inactive_2_Desc': i2_desc,
                'Inactive_3_PN': i3_pn,
                'Inactive_3_Desc': i3_desc,
            })

        result_rows.append(out)

    result_df = _reorder_columns(result_rows, spec_cols)
    return result_df, review_items


def _emit_progress(progress_callback, **payload):
    if progress_callback is None:
        return
    try:
        progress_callback(payload)
    except Exception:
        pass


def _error_result(tag, active_cands, inactive_cands, active_index, inactive_index):
    # Use top token intersection hits as fallback placeholders
    a1 = (active_cands[0][0], active_index.get(active_cands[0][0], ('', '', ''))[1]) if active_cands else ('', '')
    i1 = (inactive_cands[0][0], inactive_index.get(inactive_cands[0][0], ('', '', ''))[1]) if inactive_cands else ('', '')
    return {
        'active_top3': [a1],
        'inactive_top3': [i1],
        'act_conf': tag,
        'act_diff': '',
        'inact_conf': tag,
        'inact_diff': '',
        'error': tag,
    }


def _empty_result_cols(tag):
    return {
        'Active_1_PN': tag, 'Active_1_Desc': '', 'Active_1_Conf': tag, 'Active_1_Diff': '',
        'Active_2_PN': '', 'Active_2_Desc': '', 'Active_3_PN': '', 'Active_3_Desc': '',
        'Inactive_1_PN': tag, 'Inactive_1_Desc': '', 'Inactive_1_Conf': tag, 'Inactive_1_Diff': '',
        'Inactive_2_PN': '', 'Inactive_2_Desc': '', 'Inactive_3_PN': '', 'Inactive_3_Desc': '',
    }


def _reorder_columns(result_rows, spec_cols):
    if not result_rows:
        return _make_empty_df(spec_cols)
    import pandas as pd
    df = pd.DataFrame(result_rows)
    bom_cols = ['Location', 'SpecSummary'] + spec_cols + ['PutIntoBOM']
    active_cols = ['Active_1_PN', 'Active_1_Desc', 'Active_1_Conf', 'Active_1_Diff',
                   'Active_2_PN', 'Active_2_Desc', 'Active_3_PN', 'Active_3_Desc']
    inactive_cols = ['Inactive_1_PN', 'Inactive_1_Desc', 'Inactive_1_Conf', 'Inactive_1_Diff',
                     'Inactive_2_PN', 'Inactive_2_Desc', 'Inactive_3_PN', 'Inactive_3_Desc']
    ordered = [c for c in bom_cols if c in df.columns]
    ordered += [c for c in active_cols if c in df.columns]
    ordered += [c for c in inactive_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


def _make_empty_df(spec_cols):
    import pandas as pd
    cols = (['Location', 'SpecSummary'] + spec_cols +
            ['Active_1_PN', 'Active_1_Desc', 'Active_1_Conf', 'Active_1_Diff',
             'Active_2_PN', 'Active_2_Desc', 'Active_3_PN', 'Active_3_Desc',
             'Inactive_1_PN', 'Inactive_1_Desc', 'Inactive_1_Conf', 'Inactive_1_Diff',
             'Inactive_2_PN', 'Inactive_2_Desc', 'Inactive_3_PN', 'Inactive_3_Desc'])
    return pd.DataFrame(columns=cols)
