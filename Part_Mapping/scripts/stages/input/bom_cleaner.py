import pandas as pd

from .input_validator import EXCLUDED_PUT_IN_BOM_VALUES, read_bom_table


def clean_bom(bom_path):
    """
    Returns (clean_df, review_items, spec_cols).

    clean_df    : one row per Location, ready for mapping
    review_items: list of dicts {Location, SpecSummary, Issue Type, Original Value}
    spec_cols   : list of Spec column names found in the file
    """
    df = read_bom_table(bom_path)

    spec_cols = [c for c in df.columns if c == 'Spec' or c.startswith('Spec.')]
    review_items = []

    # --- Filter by PutIntoBOM ---
    # Explicit exclusion markers are skipped. Other values stay in mapping because
    # real BOM files may contain site-specific product-line markers.
    put_values = df['PutIntoBOM'].fillna('').astype(str).str.strip().str.upper()
    clean_df = df[~put_values.isin(EXCLUDED_PUT_IN_BOM_VALUES)].copy()

    # --- Explode Location ---
    clean_df['Location'] = clean_df['Location'].fillna('').astype(str)
    clean_df['_loc_list'] = clean_df['Location'].apply(
        lambda x: [loc.strip() for loc in x.split(',') if loc.strip()]
    )

    clean_df['_loc_list'] = clean_df['_loc_list'].apply(lambda locs: locs or [''])

    # Explode to one row per location
    clean_df = clean_df.drop(columns=['Location']).explode('_loc_list')
    clean_df = clean_df.rename(columns={'_loc_list': 'Location'})
    clean_df = clean_df.reset_index(drop=True)

    # --- Detect Duplicate Locations ---
    loc_has_value = clean_df['Location'].astype(str).str.strip() != ''
    dup_locations = clean_df[
        loc_has_value & clean_df.duplicated(subset=['Location'], keep=False)
    ]['Location'].unique()
    for loc in dup_locations:
        for _, row in clean_df[clean_df['Location'] == loc].iterrows():
            review_items.append({
                'Location': loc,
                'SpecSummary': _safe(row, 'SpecSummary'),
                'Issue Type': 'Duplicate Location',
                'Original Value': loc,
            })
    # Duplicate rows stay in clean_df (mapping continues)

    # Reorder columns: Location first
    other_cols = [c for c in clean_df.columns if c != 'Location']
    clean_df = clean_df[['Location'] + other_cols]

    return clean_df, review_items, spec_cols


def _safe(row, col):
    val = row.get(col, '')
    return '' if pd.isna(val) else str(val)
