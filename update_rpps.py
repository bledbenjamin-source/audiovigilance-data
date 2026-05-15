"""
Script de mise à jour automatique de la base RPPS — GitHub Action.
Télécharge le fichier data.gouv.fr, filtre les audioprothésistes (code 26),
normalise les colonnes SIRET/adresse/téléphone, et sauvegarde en Parquet.
Doit produire les mêmes colonnes que _telecharger_et_filtrer_parquet() dans l'app.
"""
import io, re, sys
import requests
import pandas as pd

PARQUET_URL  = "https://object.files.data.gouv.fr/hydra-parquet/hydra-parquet/fffda7e9-0ea2-4c35-bba0-4496f3af935d.parquet"
OUTPUT       = "audio_pro_clean.parquet"
COL_CODE_PRO = "Code profession"

def _trouver_colonne(cols, *candidats):
    """Retourne le premier candidat présent dans cols, sinon None."""
    for c in candidats:
        if c in cols:
            return c
    return None

def _val(df, col):
    """Série de la colonne col, nettoyée des NaN → chaîne vide."""
    if col is None or col not in df.columns:
        return pd.Series("", index=df.index)
    return (df[col].fillna("")
                   .astype(str)
                   .str.strip()
                   .replace({"nan": "", "None": "", "NaN": ""}))

# ── Téléchargement ────────────────────────────────────────────────────────────
print("⬇️  Téléchargement du fichier RPPS (peut prendre 1-2 min)...")
r = requests.get(PARQUET_URL, timeout=300, stream=True)
r.raise_for_status()
df_full = pd.read_parquet(io.BytesIO(r.content), engine="pyarrow")
print(f"✅ Fichier chargé : {len(df_full):,} lignes, {len(df_full.columns)} colonnes")

# ── Filtre audioprothésistes (code profession 26) ─────────────────────────────
df = df_full[df_full[COL_CODE_PRO].astype(str) == "26"].copy()
cols = set(df.columns)
print(f"✅ Audioprothésistes (code 26) : {len(df):,} lignes")

# ── Diagnostic colonnes disponibles ──────────────────────────────────────────
cols_siret = sorted([c for c in cols if "siret" in c.lower() or "siren" in c.lower()])
cols_voie  = sorted([c for c in cols if "voie" in c.lower()])
cols_adr   = sorted([c for c in cols if "adresse" in c.lower()])
cols_tel   = sorted([c for c in cols if "téléphone" in c.lower() or "telephone" in c.lower()])
print(f"📋 Colonnes SIRET/SIREN trouvées : {cols_siret}")
print(f"📋 Colonnes voie trouvées        : {cols_voie}")
print(f"📋 Colonnes adresse trouvées     : {cols_adr}")
print(f"📋 Colonnes téléphone trouvées   : {cols_tel}")

# ── SIRET 14 chiffres (priorité) puis SIREN 9 chiffres (fallback) ────────────
col_siret = _trouver_colonne(cols,
    "SIRET site",
    "Numéro SIRET",
    "SIRET",
    "siret",
)
col_siren = _trouver_colonne(cols,
    "Numéro SIREN",
    "SIREN",
    "Numéro d'identification du cabinet",
)
print(f"➡️  Colonne SIRET utilisée : {col_siret or 'NON TROUVÉE'}")
print(f"➡️  Colonne SIREN utilisée : {col_siren or 'NON TROUVÉE'}")

siret_s = _val(df, col_siret).str.replace(r"\D", "", regex=True)
siren_s = _val(df, col_siren).str.replace(r"\D", "", regex=True)

# SIRET valide = exactement 14 chiffres
df["siret_clean"] = siret_s.where(siret_s.str.len() == 14, "")
# Fallback SIREN = exactement 9 chiffres
no_siret = df["siret_clean"] == ""
df.loc[no_siret, "siret_clean"] = siren_s.where(siren_s.str.len() == 9, "")[no_siret]

pct_siret = round(df["siret_clean"].ne("").sum() / len(df) * 100)
print(f"✅ siret_clean : {pct_siret}% remplis "
      f"({df['siret_clean'].ne('').sum():,} / {len(df):,})")

if pct_siret == 0:
    print("❌ ERREUR : aucun SIRET trouvé — vérifiez les noms de colonnes ci-dessus")
    sys.exit(1)

# ── Adresse : numéro + libellé voie (priorité) puis champ consolidé ──────────
col_num_voie = _trouver_colonne(cols,
    "Numéro voie (coord. structure)",
    "Numéro voie",
    "Numero voie (coord. structure)",
)
col_lib_voie = _trouver_colonne(cols,
    "Libellé voie (coord. structure)",
    "Libelle voie (coord. structure)",
    "Libellé voie",
    "Libelle voie",
)
col_adr_full = _trouver_colonne(cols,
    "Adresse postale (coord. structure)",
    "Adresse postale",
)
print(f"➡️  Numéro voie  : {col_num_voie or 'NON TROUVÉE'}")
print(f"➡️  Libellé voie : {col_lib_voie or 'NON TROUVÉE'}")

num_v = _val(df, col_num_voie)
lib_v = _val(df, col_lib_voie)
adr_f = _val(df, col_adr_full)

df["adresse_clean"] = (num_v + " " + lib_v).str.strip()
vide = df["adresse_clean"].str.strip() == ""
df.loc[vide, "adresse_clean"] = adr_f[vide]

pct_adr = round(df["adresse_clean"].ne("").sum() / len(df) * 100)
print(f"✅ adresse_clean : {pct_adr}% remplis")

# ── Téléphone : structure puis praticien en fallback ─────────────────────────
col_tel_s = _trouver_colonne(cols,
    "Téléphone (coord. structure)",
    "Telephone (coord. structure)",
)
col_tel_pp = _trouver_colonne(cols,
    "Téléphone (coord. PP)",
    "Telephone (coord. PP)",
)
tel_s  = _val(df, col_tel_s)
tel_pp = _val(df, col_tel_pp)
df["tel_clean"] = tel_s.where(tel_s != "", tel_pp)

pct_tel = round(df["tel_clean"].ne("").sum() / len(df) * 100)
print(f"✅ tel_clean : {pct_tel}% remplis")

# ── Sauvegarde ────────────────────────────────────────────────────────────────
df.to_parquet(OUTPUT, engine="pyarrow", index=False)
print(f"\n✅ Fichier sauvegardé : {OUTPUT}")
print(f"   Lignes     : {len(df):,}")
print(f"   Colonnes   : {len(df.columns)}")
print(f"   SIRET      : {pct_siret}%")
print(f"   Adresse    : {pct_adr}%")
print(f"   Téléphone  : {pct_tel}%")
